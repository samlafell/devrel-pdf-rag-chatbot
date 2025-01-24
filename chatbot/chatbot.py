import os
import re
import requests
import spacy
from dotenv import load_dotenv
from openai import OpenAI
from requests.auth import HTTPBasicAuth

# Load environment variables
load_dotenv()

CRATEDB_URL = os.getenv("CRATEDB_URL")
CRATEDB_USERNAME = os.getenv("CRATEDB_USERNAME")
CRATEDB_PASSWORD = os.getenv("CRATEDB_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
COLLECTION_NAME = os.getenv("PDF_COLLECTION_TABLE_NAME")
RESULTS_LIMIT = 3  # Number of results to return

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# Instantiate OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Debug flag for debugging intermediate steps
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# ANSI escape codes for formatting
GREEN = "\033[92m"
RESET = "\033[0m"


def execute_cratedb_query(query, args=None):
    data = {"stmt": query}
    if args:
        data["args"] = args

    response = requests.post(
        CRATEDB_URL, json=data, auth=HTTPBasicAuth(CRATEDB_USERNAME, CRATEDB_PASSWORD)
    )

    if response.status_code != 200:
        print(f"CrateDB query failed: {response.text}") if DEBUG else None
        return None
    return response.json()


def extract_keywords_pos(question):
    """
    Extracts meaningful keywords from the question using POS tagging.
    """
    doc = nlp(question)
    keywords = [token.text for token in doc if token.pos_ in {"NOUN", "PROPN", "VERB"}]
    return " ".join(keywords)


def get_text_embedding(text, model="text-embedding-ada-002"):
    """
    Generates a vector embedding for a given text using OpenAI's embedding model.
    """
    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding: {e}") if DEBUG else None
        return None

def knn_search(query_embedding, collection_name, results_limit=RESULTS_LIMIT):
    """
    Searches the vector index in CrateDB using a KNN algorithm.
    Parameters:
    - query_embedding: Vector embedding of the query
    - collection_name: Name of the database collection
    - results_limit: Number of results to return
    """
    embedding_string = ",".join(map(str, query_embedding))
    if DEBUG:
        print(
            f"\n### KNN Search Query Embedding (first 10): {query_embedding[:10]} ###\n"
        )

    query = f"""
    SELECT id, document_name, page_number, content_type, content, _score
    FROM {collection_name}
    WHERE knn_match(content_embedding, ARRAY[{embedding_string}], {results_limit})
    ORDER BY _score DESC
    LIMIT {results_limit}
    """
    response = execute_cratedb_query(query)
    if response and "rows" in response:
        if DEBUG:
            print(f"\n### KNN Search Results ({len(response['rows'])} rows): ###")
            for row in response["rows"]:
                print(f"Page {row[2]} (Score: {row[-1]}): {row[4][:200]}...")
        return response["rows"]
    return []

def full_text_search(keywords, collection_name, results_limit=RESULTS_LIMIT):
    """
    Searches the full-text index in CrateDB using BM25 (Best Matching 25) algorithm.

    Parameters:
    - keywords (str): The extracted keywords from the user's query.
    - collection_name (str): The name of the database collection to search.
    - results_limit (int): The maximum number of results to return.

    Returns:
    - list: A list of rows containing the matching records, including their scores and metadata.
    - Empty list: If no results are found or if the query fails.

    Debugging:
    - Prints the BM25 search query and results when DEBUG is enabled.
    """
    if DEBUG:
        print(f'\n### BM25 Search Query: "{keywords}" ###\n')

    query = f"""
    SELECT id, document_name, page_number, content_type, content, _score AS bm25_score
    FROM {collection_name}
    WHERE MATCH(content, '{keywords}')
    ORDER BY bm25_score DESC
    LIMIT {results_limit}
    """
    response = execute_cratedb_query(query)
    return response["rows"] if response and "rows" in response else []

def perform_hybrid_search(
    question, alpha=0.8, collection_name=COLLECTION_NAME, results_limit=RESULTS_LIMIT
):
    """
    Parameters:
    - question (str): The user's input question.
    - alpha (float): Weight for KNN scores in the hybrid scoring formula.
    - collection_name (str): The name of the database collection to search.
    - results_limit (int): The maximum number of results to return.

    Returns:
    - list: A list of rows containing the combined results, sorted by hybrid scores.

    Process:
    1. Generates a query embedding and extracts keywords.
    2. Performs KNN search and BM25 search independently.
    3. Normalizes scores and combines results with weighted averaging.
    4. Returns the top results sorted by hybrid scores.
    """
    query_embedding = get_text_embedding(question)
    keywords = extract_keywords_pos(question)

    if DEBUG:
        print(f"\nExtracted Keywords for BM25: {keywords}\n")

    knn_results = knn_search(query_embedding, collection_name, results_limit)
    bm25_results = full_text_search(keywords, collection_name, results_limit)

    # Normalize and merge results
    knn_max = max(row[-1] for row in knn_results) if knn_results else 1
    bm25_max = max(row[-1] for row in bm25_results) if bm25_results else 1

    def normalize(score, max_score):
        return score / max_score if max_score > 0 else 0

    merged = {}
    for row in knn_results:
        merged[row[0]] = {"score": normalize(row[-1], knn_max) * alpha, "data": row}
    for row in bm25_results:
        if row[0] in merged:
            merged[row[0]]["score"] += normalize(row[-1], bm25_max) * (1 - alpha)
        else:
            merged[row[0]] = {
                "score": normalize(row[-1], bm25_max) * (1 - alpha),
                "data": row,
            }

    results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    return [result["data"] for result in results[:results_limit]]

def generate_answer(question, context):
    """
    Generates a concise and clear answer to the user's question based on the provided context.

    Parameters:
    - question (str): The user's input question.
    - context (str): The retrieved context containing relevant information.

    Returns:
    - str: A text response generated by OpenAI's GPT-3.5-turbo.
    - "I'm sorry, I couldn't generate an answer.": If the generation fails.

    Notes:
    - The function uses a structured prompt to guide the language model's response. Changing the prompt will have an effect on the answers provided by the chatbot.
    - Includes sources in the prompt to provide traceability in the answer.
    """
    prompt = f"""
    You are a skilled technical assistant. Use the following document context to answer the question concisely and clearly. Focus on the most relevant information. Avoid redundancy, but provide a full explanation. Include references to figures or images if mentioned:

    Context:
    {context}

    Question:
    {question}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating answer: {e}") if DEBUG else None
        return "I'm sorry, I couldn't generate an answer."


def chatbot_query(question):
    """
    Parameters:
    - question (str): The user's input question.

    Returns:
    - dict: A dictionary containing different components of the response.  

    Debugging:
    - Prints intermediate steps (e.g., search results, context) when DEBUG is enabled.
    """
    results = perform_hybrid_search(question)
    if not results:
        return "No relevant documents found."

    print(f"DEBUG: Results structure: {results}") if DEBUG else None

    unique_context = set()
    hybrid_results_with_scores = []

    for result in results:
        print(f"DEBUG: Single result: {result}") if DEBUG else None
        # Dynamically unpack, focusing only on relevant fields
        _, doc_name, page_num, content_type, content, score, *_ = result

        # Convert score to float safely
        try:
            score = float(score)
        except ValueError:
            score = 0.0  # Default if score conversion fails

        # Prepare the context snippet
        context_snippet = f"Page {page_num} (Document: {doc_name}, Type: {content_type}, Score: {score:.4f})"

        if content not in unique_context:  # Avoid duplicates
            unique_context.add(content)
            hybrid_results_with_scores.append({
                "text": context_snippet,
                "doc": doc_name,
                "page": page_num,
                "type": content_type,
                "score": score
            })

    # Combine context for LLM
    context = "\n".join(c["text"] for c in hybrid_results_with_scores)
    if DEBUG:
        print(f"\n### Retrieved Context with Scores ###\n{context}\n")

    # Generate the answer using the LLM
    answer = generate_answer(question, context)

    # Format the response with the answer and sources separated by a blank line

    # formatted_response = (
    #     f"{GREEN}{answer}{RESET}\n\n"  # Add a blank line after the answer
    #     "Sources:\n" + "\n".join(c["text"] for c in hybrid_results_with_scores)
    # )
    return {
        "response": f"{GREEN}{answer}{RESET}",
        "sources": "\n".join(c["text"] for c in hybrid_results_with_scores),
        "results": hybrid_results_with_scores
    }


def chatbot_interface():
    """

    Process:
    1. Prompts the user to input a question.
    2. Calls `chatbot_query` to process the query and generate a response.
    3. Displays the answer and sources in a formatted style (answer in green).
    4. Exits gracefully when the user types "exit".

    Notes:
    - Designed for iterative question-answering with minimal latency.
    """
    print("\nWelcome to the PDF Data Chatbot!")
    while True:
        user_query = input("Ask a question ('exit' quits): ").strip()
        if user_query.lower() == "exit":
            print("Goodbye!")
            break
        response = chatbot_query(user_query)
        print(f"\nAnswer:\n{response['response']}\n\nSources:\n{response['sources']}\n")

if __name__ == "__main__":
    chatbot_interface()        