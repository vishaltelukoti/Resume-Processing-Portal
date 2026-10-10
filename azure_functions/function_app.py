import io
import json
import logging
import os
from urllib.parse import unquote, urlparse

import azure.functions as func
from azure.storage.blob import BlobServiceClient, ContentSettings
from pypdf import PdfReader

app = func.FunctionApp()


@app.function_name(name="ProcessPDF")
@app.queue_trigger(
    arg_name="msg",
    queue_name="pdf-processing-queue",
    connection="AzureWebJobsStorage",
)
def process_pdf(msg: func.QueueMessage):
    """Download an uploaded PDF, extract text, and save it to Blob Storage."""

    event = json.loads(msg.get_body().decode("utf-8"))

    if event.get("eventType") != "Microsoft.Storage.BlobCreated":
        logging.info("Ignoring event type: %s", event.get("eventType"))
        return

    blob_url = event["data"]["url"]
    parsed_url = urlparse(blob_url)
    blob_path = unquote(parsed_url.path.lstrip("/"))

    container_name, blob_name = blob_path.split("/", 1)

    if container_name != "original-pdfs" or not blob_name.endswith(".pdf"):
        logging.info("Ignoring unrelated blob event")
        return

    document_id = blob_name.split("/")[0]

    # Connect to Azure Storage.
    connection_string = os.environ["AzureWebJobsStorage"]
    blob_service = BlobServiceClient.from_connection_string(connection_string)

    # Download original PDF.
    pdf_client = blob_service.get_blob_client(
        container=container_name,
        blob=blob_name,
    )
    pdf_bytes = pdf_client.download_blob().readall()

    # Extract text from PDF.
    reader = PdfReader(io.BytesIO(pdf_bytes))
    extracted_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )

    # Upload extracted text.
    text_client = blob_service.get_blob_client(
        container="extracted-text",
        blob=f"{document_id}.txt",
    )
    text_client.upload_blob(
        extracted_text.encode("utf-8"),
        overwrite=True,
        content_settings=ContentSettings(
            content_type="text/plain; charset=utf-8"
        ),
    )

    logging.info("Successfully processed document: %s", document_id)