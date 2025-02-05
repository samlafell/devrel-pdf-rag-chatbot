# PDF Data Extractor Component

TODO

The resulting dataset can then be queried using natural language through the [Chat Bot interface](../chatbot/) provided.

## First Steps

First, you'll need to get a local copy of the code, set up a CrateDB database and get an OpenAI API key.  Follow the instructions in the [main README](../README.md), returning here when you're ready.

## Preparing a Virtual Environment

You should create and activate a Python Virtual Environment to install this project's dependencies into.  To do this, run the following commands:

```bash
cd data-extractor
python -m venv venv
. ./venv/bin/activate
```
Now install the dependencies that this project requires:

```bash
pip install -r requirements.txt
```

## Configure your Environment File

The data extractor has several configuration parameters.  These are all defined in a `.env` file and should be considered secrets, don't commit them to source control!

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

**Save your changes before attempting to run the chat bot.**

## Preparing the PDF Files

We've supplied a couple of example PDF files.  If you'd like to replace them with files of your own choosing, simply place your own PDFs in `../chatbot/static` and delete ours.

## Running the Data Extractor

TODO

```bash
python extract.py
```