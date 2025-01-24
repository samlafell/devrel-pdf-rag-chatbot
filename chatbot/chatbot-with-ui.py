import streamlit as st
from chatbot import chatbot_query  # Import chatbot query function

# Configure the Streamlit page
st.set_page_config(
    page_title="Document QA Chatbot",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed"  # Sidebar minimized
)

# Add custom CSS for styling
st.markdown("""
    <style>
    .stApp {
        max-width: 800px;
        margin: 0 auto;
    }
    .chat-message {
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
        flex-direction: column;
    }
    .user-message {
        background-color: #e8eaed;
        color: #000000;
    }
    .bot-message {
        background-color: #2b313e;
        color: #ffffff;
    }
    .source-info {
        font-size: 0.8rem;
        color: #b4b4b4;
        margin-top: 0.5rem;
        border-top: 1px solid #555;
        padding-top: 0.5rem;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Header
st.title("📚 Document QA Chatbot")
st.markdown("Ask questions about your documents and get AI-powered answers with source references.")

# Chat input
user_query = st.chat_input("Ask a question...")

# Process user input
if user_query:
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": user_query})
    
    # Show a loading spinner while processing the response
    with st.spinner("Thinking..."):
        try:
            # Get chatbot response
            response = chatbot_query(user_query)

            # Clean and parse response, add header text for sources.
            sources = []
            for source in response["results"]:
                # Format for one source response:
                # Score: 0.3417, Document: How-to-Build-AI-driven-Knowledge-Assistants.pdf, Page: 10, Type: image.
                sources.append(f"<li>Score: {source['score']}, Document: {source['doc']}, Page: {source['page']}, Type: {source['type']}</li>")

            formatted_response = f"{response['response'].replace("\033[92m", "").replace("\033[0m", "").strip()}<br><br><strong>Sources:</strong><br><ul>{''.join(sources)}</ul>"
            
            # Append assistant response as a single message
            st.session_state.messages.append({"role": "assistant", "content": formatted_response})

        except Exception as e:
            # Handle errors gracefully
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"An error occurred: {e}"
            })


# Display chat history
for message in st.session_state.messages:
    if message["role"] == "user":
        with st.container():
            st.markdown(f"""
                <div class="chat-message user-message">
                    <div><strong>You:</strong> {message["content"]}</div>
                </div>
                """, 
                unsafe_allow_html=True
            )
    elif message["role"] == "assistant":
        with st.container():
            # Render the assistant response with additional spacing
            st.markdown(f"""
                <div class="chat-message bot-message">
                    <div><strong>Assistant:</strong><br>{message["content"].replace("\n", "<br>")}</div>
                </div>
                """, 
                unsafe_allow_html=True
            )

# Add a clear chat button in the sidebar
if st.sidebar.button("Clear Chat"):
    st.session_state.messages = []
    st.rerun()