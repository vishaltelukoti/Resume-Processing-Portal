import io
import json
import logging
import os
import time
from urllib.parse import unquote, urlparse

import azure.functions as func
from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.data.tables import TableServiceClient, UpdateMode
from azure.storage.blob import BlobServiceClient, ContentSettings
from pypdf import PdfReader


TABLE_NAME = "ResumeDocuments"
PARTITION_KEY = "Resume"
ORIGINAL_CONTAINER = "original-pdfs"
EXTRACTED_CONTAINER = "extracted-text"
METADATA_LOOKUP_ATTEMPTS = 3
METADATA_LOOKUP_DELAY_SECONDS = 2

app = func.FunctionApp()


def get_table_client(connection_string: str):
    return TableServiceClient.from_connection_string(connection_string).get_table_client(TABLE_NAME)


def get_document_with_retry(table_client, document_id: str):
    """Wait briefly for FastAPI to create metadata after the BlobCreated event."""
    for attempt in range(METADATA_LOOKUP_ATTEMPTS):
        try:
            return table_client.get_entity(PARTITION_KEY, document_id)
        except ResourceNotFoundError:
            if attempt < METADATA_LOOKUP_ATTEMPTS - 1:
                time.sleep(METADATA_LOOKUP_DELAY_SECONDS)
    raise RuntimeError("Document metadata is not available yet.")


def update_status(table_client, entity, status: str, **properties):
    entity["status"] = status
    entity.update(properties)
    table_client.update_entity(entity=entity, mode=UpdateMode.MERGE)


def mark_failed_unless_completed(table_client, document_id: str):
    """Do not let a delayed retry replace a successful Completed status."""
    current_document = table_client.get_entity(PARTITION_KEY, document_id)
    if current_document.get("status") == "Completed":
        logging.info("Document is already completed; keeping its successful status: %s", document_id)
        return
    update_status(table_client, current_document, "Failed", error_message="The PDF could not be processed.")


@app.function_name(name="ProcessPDF")
@app.queue_trigger(arg_name="msg", queue_name="pdf-processing-queue", connection="AzureWebJobsStorage")
def process_pdf(msg: func.QueueMessage):
    """Process an original blob and keep its Azure Table status current."""
    event = json.loads(msg.get_body().decode("utf-8"))
    if event.get("eventType") != "Microsoft.Storage.BlobCreated":
        logging.info("Ignoring event type: %s", event.get("eventType"))
        return

    blob_path = unquote(urlparse(event["data"]["url"]).path.lstrip("/"))
    container_name, blob_name = blob_path.split("/", 1)
    if container_name != ORIGINAL_CONTAINER or not blob_name.endswith(".pdf"):
        logging.info("Ignoring unrelated blob event")
        return

    document_id = blob_name.split("/", 1)[0]
    connection_string = os.environ["AzureWebJobsStorage"]
    table_client = get_table_client(connection_string)
    document = None

    try:
        document = get_document_with_retry(table_client, document_id)
        blob_service = BlobServiceClient.from_connection_string(connection_string)
        extracted_blob_name = f"{document_id}.txt"
        extracted_client = blob_service.get_blob_client(EXTRACTED_CONTAINER, extracted_blob_name)
        if document.get("status") == "Completed" and extracted_client.exists():
            logging.info("Document is already completed; skipping duplicate message: %s", document_id)
            return

        update_status(table_client, document, "Processing")
        pdf_bytes = blob_service.get_blob_client(container_name, blob_name).download_blob().readall()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if not extracted_text:
            raise ValueError("PDF has no extractable text")

        extracted_client.upload_blob(
            extracted_text.encode("utf-8"), overwrite=True,
            content_settings=ContentSettings(content_type="text/plain; charset=utf-8"),
        )
        update_status(table_client, document, "Completed", extracted_blob_name=extracted_blob_name,
                      error_message="")
        logging.info("Successfully processed document: %s", document_id)
    except Exception:
        logging.exception("Processing failed for document: %s", document_id)
        if document is not None:
            try:
                mark_failed_unless_completed(table_client, document_id)
            except AzureError:
                logging.exception("Could not update failed status for document: %s", document_id)
        # Queue-triggered Functions retry messages that raise an exception.
        raise
