# CrateDB RAG Chatbot

This is the Chatbot component, responsible for receiving a natural language query from the user then performing a hybrid KNN and keyword search in CrateDB to identify relevant information from a set of PDF files that were previously ingested using the [Data Extractor](../data-extractor/).

Results are presented back to the user in natural language by sending them to an LLM.

## First Steps

First, you'll need to get a local copy of the code, set up a CrateDB database and get an OpenAI API key.  Follow the instructions in the [main README](../README.md), returning here when you're ready.

## Preparing a Virtual Environment

You should create and activate a Python Virtual Environment to install this project's dependencies into.  To do this, run the following commands:

```bash
cd chatbot
python -m venv venv
. ./venv/bin/activate
```

Now install the dependencies that this project requires:

```bash
pip install -r requirements.txt
```

The chatbot uses [Spacy](https://spacy.io/) to perform natural language processing on queries from the user.  You'll need to download Spacy's [English pipeline model](https://spacy.io/models/en#en_core_web_sm) before continuing:

```bash
python -m spacy download en_core_web_sm
```

## Configure your Environment File

The chatbot has several configuration parameters.  These are all defined in a `.env` file and should be considered secrets, don't commit them to source control!

To get you started, we've provided a template file `env.example`.  Create a `.env` file by running the following command:

```bash
cp env.example .env
```

Then edit `.env` and make the following changes:

* Set the value of `CRATEDB_URL` to:
  * `https://<hostname>:4200/_sql` if you are using a cloud database, replacing `<hostname>` with the host name, which looks something like `some-host-name.gke1.us-central1.gcp.cratedb.net`.
  * `http://localhost:4200/_sql` if you're using Docker.
* Set the value of `CRATEDB_USERNAME` to `admin` if you are using a cloud database, or `crate` if you are using Docker.
* Set the value of `CRATEDB_PASSWORD` to your database password if you are using a cloud database, or leave it blank if you are using Docker.
* Set the value of `OPENAI_API_KEY` to your OpenAI API key.

**Save your changes before attempting to run the chatbot.**

## Running the Chatbot

The chatbot has two interfaces.  One has a basic terminal prompt, the other is a web application using the [Streamlit framework](https://streamlit.io/).

### Terminal Interface

Start the chatbot's terminal interface with the following command:

```bash
python chatbot.py
```

The interface will appear in the terminal window.

If you'd prefer to run the web interface, use this command:

```bash
streamlit run chatbot-with-ui.py
```

Your browser should open a new tab with the chatbot interface in it.  If it doesn't, point your browser at `http://localhost:8501/` to see it.

## Interacting with the Chatbot

Once you've started the chatbot, ask it a question using natual language.  For example you might ask:

"How does CrateDB fit into the AI ecosystem, specifically in the area of knowledge assistants?"

The chatbot will generate its answer by performing hybrid search queries against the chunked PDF text and image data stored in CrateDB and feeding the responses as context to an LLM.

If you're using the Streamlit web interface, each link to a source document is clickable and should open the document for you on the page referenced.