import os
import re
import fitz  # (from PyMuPDF)
import requests
from dotenv import load_dotenv
from base64 import b64encode
from requests.auth import HTTPBasicAuth
from openai import OpenAI


# Load environment variables
load_dotenv()

CRATEDB_URL = os.getenv("CRATEDB_URL")
CRATEDB_USERNAME = os.getenv("CRATEDB_USERNAME")
CRATEDB_PASSWORD = os.getenv("CRATEDB_PASSWORD")
CRATEDB_FULL_TEXT_ANALYZER = os.getenv("CRATEDB_FULL_TEXT_ANALYZER")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PDF_DIR = os.getenv("PDF_DIR")
COLLECTION_NAME = os.getenv("PDF_COLLECTION_TABLE_NAME")
GPT_MODEL = os.getenv("GPT_MODEL")
TEXT_EMBEDDING_MODEL = os.getenv("TEXT_EMBEDDING_MODEL")
MAX_IMAGE_DESCRIPTION_TOKENS = int(os.getenv("MAX_IMAGE_DESCRIPTION_TOKENS"))
IMAGE_DESCRIPTION_TEMPERATURE = float(os.getenv("IMAGE_DESCRIPTION_TEMPERATURE"))

# Instantiate OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

def execute_cratedb_query(query, args=None):
    data = {"stmt": query}
    if args:
        data["args"] = args
    response = requests.post(
        CRATEDB_URL, json=data, auth=HTTPBasicAuth(CRATEDB_USERNAME, CRATEDB_PASSWORD)
    )
    if response.status_code != 200:
        print(f"CrateDB query failed: {response.text}")
        return None
    return response.json()

def create_table():
    query = f"""
    CREATE TABLE IF NOT EXISTS {COLLECTION_NAME} (
        id TEXT PRIMARY KEY,
        document_name TEXT,
        page_number INT,
        content_type TEXT,
        content TEXT INDEX USING FULLTEXT WITH (analyzer = '{CRATEDB_FULL_TEXT_ANALYZER}'),
        content_embedding FLOAT_VECTOR(1536)
    )
    """
    execute_cratedb_query(query)
    execute_cratedb_query(f"REFRESH TABLE {COLLECTION_NAME}")
    print(f"Table {COLLECTION_NAME} is ready.")

def store_in_cratedb(
    content_id, document_name, page_number, content_type, content, embedding
):
    """
    Stores extracted text or image data in CrateDB.

    Parameters:
    - content_id (str): Unique identifier for the content.
    - document_name (str): Name of the source PDF file.
    - page_number (int): Page number of the content.
    - content_type (str): Type of content ("text" or "image").
    - content (str): The actual text or image description.
    - embedding (list): The vector embedding of the content.

    Notes:
    - Inserts the data into the specified CrateDB table.
    - Content and embeddings are indexed for efficient retrieval.
    """
    query = f"""
    INSERT INTO {COLLECTION_NAME} (id, document_name, page_number, content_type, content, content_embedding)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    execute_cratedb_query(
        query,
        [content_id, document_name, page_number, content_type, content, embedding],
    )
    print(f"Stored content: {content_id}")

def extract_text_with_cleaning(doc):
    """
    Extracts and cleans text from a PDF, removing repetitive headers/footers.

    Parameters:
    - doc (fitz.Document): A PyMuPDF document object.

    Returns:
    - list: A list of dictionaries with "page" (page number) and "text" (cleaned chunk).

    Process:
    1. Identifies repeating headers/footers by analyzing all pages.
    2. Removes identified headers/footers from each page.
    3. Splits the remaining text into sentence-aware chunks.
    4. Returns the cleaned and chunked text with metadata.
    """
    all_chunks = []
    header_candidates = []

    # Identify potential headers/footers
    for page in doc:
        text_lines = page.get_text("text").splitlines()
        if len(text_lines) > 2:
            header_candidates.append(text_lines[0])  # Add first line as header
            header_candidates.append(text_lines[-1])  # Add last line as footer

    # Find common headers/footers across pages
    common_headers = {
        k
        for k, v in dict.fromkeys(header_candidates).items()
        if header_candidates.count(k) > 2
    }

    # Process each page
    for page_num, page in enumerate(doc):
        text_lines = page.get_text("text").splitlines()
        clean_lines = [line for line in text_lines if line not in common_headers]
        cleaned_text = clean_text("\n".join(clean_lines))
        chunks = sentence_aware_chunking(cleaned_text)

        # Store chunks with metadata
        for chunk in chunks:
            if len(chunk) > 50:  # Only include meaningful chunks
                all_chunks.append({"page": page_num + 1, "text": chunk})
    return all_chunks


def clean_text(text):
    """
    Cleans raw text by removing unnecessary elements.

    Parameters:
    - text (str): The raw text to clean.

    Returns:
    - str: The cleaned and normalized text.

    Cleaning Steps:
    - Removes URLs, email addresses, and phone numbers.
    - Replaces multiple spaces with a single space.
    """
    text = re.sub(r"https?://\S+|www\.\S+", "", text)  # Remove URLs
    text = re.sub(r"\S+@\S+\.\S+", "", text)  # Remove emails
    text = re.sub(r"\+?\d[\d\s\-\(\)]{8,}\d", "", text)  # Remove phone numbers
    text = re.sub(r"\s{2,}", " ", text)  # Replace multiple spaces
    return text.strip()

def sentence_aware_chunking(text, max_chunk_size=500, overlap=50):
    """
    Splits text into manageable chunks, preserving sentence boundaries.

    Parameters:
    - text (str): The input text to chunk.
    - max_chunk_size (int): Maximum size of each chunk (in characters).
    - overlap (int): Number of overlapping characters between consecutive chunks.

    Returns:
    - list: A list of text chunks.

    Notes:
    - Ensures sentences are not split across chunks for better context retention.
    - Useful for generating embeddings and storing in CrateDB.
    """
    sentences = re.split(r"(?<=[.!?]) +", text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < max_chunk_size:
            current_chunk += " " + sentence
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

def extract_surrounding_text(page_text, position=0, max_length=300):
    """
    Extracts nearby text to provide context for an image.

    Parameters:
    - page_text (str): The full text of the page containing the image.
    - position (int): Approximate index of the image on the page.
    - max_length (int): Maximum number of characters to include in the snippet.

    Returns:
    - str: A snippet of text surrounding the image's position.

    Notes:
    - Captures sentences around the image's position for better contextualization.
    """
    lines = re.split(r"(?<=[.!?])\s+", page_text)  # Split into sentences
    start = max(0, position - 1)
    end = min(len(lines), position + 2)  # Capture sentences around the position

    # Combine and trim to max_length
    surrounding_snippet = " ".join(lines[start:end])
    return surrounding_snippet[:max_length].strip()

def encode_image(image_bytes):
    return base64.b64encode(image_bytes).decode("utf-8")

def get_text_embedding_openai(text):
    """
    Generates a vector embedding for the given text using OpenAI's embedding model.

    Parameters:
    - text (str): The text content to embed.

    Returns:
    - list: A list of floats representing the embedding vector.
    - None: If the embedding generation fails (e.g., invalid input, API error).

    Notes:
    - The embedding helps in similarity searches for text retrieval.
    """
    try:
        text = text.replace("\n", " ")  # Clean up newlines
        response = client.embeddings.create(input=[text], model=TEXT_EMBEDDING_MODEL)
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding for text: {text[:50]}... Error: {e}")
        return None

def generate_text_embedding(text, document_name, page_num, idx):
    """
    Generates an embedding for a text chunk and stores it in CrateDB.

    Parameters:
    - text (str): The text content to embed.
    - document_name (str): Name of the source document.
    - page_num (int): Page number where the text is located.
    - idx (int): Index of the chunk in the page.
    """
    embedding = get_text_embedding_openai(text)
    if embedding:
        content_id = f"text_{document_name}_{page_num}_{idx}"
        store_in_cratedb(content_id, document_name, page_num, "text", text, embedding)
        print(f"Stored text embedding: {content_id}")

def generate_image_description(image_bytes):
    """
    Generates a detailed description of an image using OpenAI's GPT-4 Turbo.

    Parameters:
    - image_bytes (bytes): The binary data of the image.

    Returns:
    - str: A detailed description of the image.
    - "Image description unavailable": If the description generation fails.

    Process:
    1. Encodes the image to Base64.
    2. Sends the encoded image to OpenAI GPT-4 Turbo.
    3. Extracts and returns the generated description.
    """
    try:
        # Encode the image to base64
        encoded_image = b64encode(image_bytes).decode("utf-8")

        # Call the GPT model - needs to be a model with vision capabilities.
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at describing images in detail. Provide rich and concise descriptions of the key visual elements of any image.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": "Describe this image in detail."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encoded_image}"
                            },
                        },
                    ],
                },
            ],
            max_tokens=MAX_IMAGE_DESCRIPTION_TOKENS,
            temperature=IMAGE_DESCRIPTION_TEMPERATURE,
        )

        # Extract and return the description
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"Error generating image description: {e}")
        return "Image description unavailable."

def generate_image_embedding(image_bytes, surrounding_text, document_name, page_num, img_index):
    """
    Generates a description for an image, creates an embedding, and stores it in CrateDB.

    Parameters:
    - image_bytes (bytes): The binary data of the image.
    - surrounding_text (str): Contextual text near the image.
    - document_name (str): Name of the source document.
    - page_num (int): Page number where the image is located.
    - img_index (int): Index of the image on the page.
    """
    # Generate image description
    image_description = generate_image_description(image_bytes)

    # Combine description with surrounding text
    combined_description = f"{image_description} Context: {surrounding_text}"

    # Generate embedding
    embedding = get_text_embedding_openai(combined_description)
    if embedding:
        content_id = f"image_{document_name}_{page_num}_{img_index}"
        store_in_cratedb(
            content_id, document_name, page_num, "image", combined_description, embedding
        )
        print(f"Stored image embedding: {content_id}")


def process_pdf(pdf_path):
    """
    Processes a PDF file by extracting text and images, generating embeddings,
    and storing the data in CrateDB.

    Parameters:
    - pdf_path (str): The file path of the PDF to process.
    """
    print(f"Processing {pdf_path}")
    doc = fitz.open(pdf_path)
    document_name = os.path.basename(pdf_path)

    # Extract and process text with improved chunking
    extracted_chunks = extract_text_with_cleaning(doc)
    for idx, chunk_data in enumerate(extracted_chunks):
        page_num = chunk_data["page"]
        chunk_text = chunk_data["text"]

        # Generate text embedding
        generate_text_embedding(chunk_text, document_name, page_num, idx)

    # Process images with clean, minimal surrounding context
    for page_num, page in enumerate(doc):
        full_page_text = page.get_text("text")
        cleaned_page_text = clean_text(full_page_text)

        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]

            # Extract surrounding text for context
            surrounding_text = extract_surrounding_text(
                cleaned_page_text, position=img_index
            )

            # Generate image embedding
            generate_image_embedding(
                image_bytes, surrounding_text, document_name, page_num + 1, img_index
            )

def process_local_pdfs():
    """
    Processes all PDFs in the specified directory.

    Process:
    1. Iterates through PDF files in the directory.
    2. Calls `process_pdf` for each file to extract and store data.

    Notes:
    - Skips the directory if no PDF files are found.
    """
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")]
    if not pdf_files:
        print("No PDF files found in the directory.")
        return
    for pdf_file in pdf_files:
        pdf_path = os.path.join(PDF_DIR, pdf_file)
        process_pdf(pdf_path)

if __name__ == "__main__":
    # Step 1: Create or refresh the database table
    create_table()

    # Step 2: Process all PDFs in the specified directory
    process_local_pdfs()  

