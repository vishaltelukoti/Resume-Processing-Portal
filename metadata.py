"""Azure Table Storage metadata repository for resume documents."""

import os
from datetime import datetime, timezone
from pathlib import Path

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.data.tables import TableServiceClient, UpdateMode
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")
TABLE_NAME = "ResumeDocuments"
PARTITION_KEY = "Resume"


class MetadataStorageError(Exception):
    """A safe error raised when Azure Table Storage cannot be used."""


def _table_client():
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise MetadataStorageError("Azure Table Storage is not configured.")
    try:
        return TableServiceClient.from_connection_string(connection_string).get_table_client(TABLE_NAME)
    except (ValueError, AzureError) as exc:
        raise MetadataStorageError("Azure Table Storage configuration is unavailable.") from exc


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_document(document_id: str, filename: str, file_type: str,
                    original_blob_name: str | None = None, original_path: str | None = None) -> dict:
    """Create the initial Uploaded record after the original blob is stored."""
    entity = {"PartitionKey": PARTITION_KEY, "RowKey": document_id, "document_id": document_id,
              "filename": filename, "file_type": file_type, "upload_date": _utc_timestamp(),
              "status": "Uploaded", "original_blob_name": original_blob_name or ""}
    try:
        _table_client().create_entity(entity=entity)
        return entity
    except AzureError as exc:
        raise MetadataStorageError("The document metadata could not be saved.") from exc


def update_status(document_id: str, status: str, extracted_path: str | None = None,
                  error_message: str | None = None, extracted_blob_name: str | None = None) -> dict | None:
    """Update a record; extracted_path remains for compatibility with old callers."""
    try:
        table_client = _table_client()
        entity = table_client.get_entity(PARTITION_KEY, document_id)
        entity["status"] = status
        blob_name = extracted_blob_name or extracted_path
        if blob_name is not None:
            entity["extracted_blob_name"] = blob_name
        if error_message is not None:
            entity["error_message"] = error_message
        table_client.update_entity(entity=entity, mode=UpdateMode.MERGE)
        return dict(entity)
    except ResourceNotFoundError:
        return None
    except AzureError as exc:
        raise MetadataStorageError("The document status could not be updated.") from exc


def get_document(document_id: str) -> dict | None:
    try:
        return dict(_table_client().get_entity(PARTITION_KEY, document_id))
    except ResourceNotFoundError:
        return None
    except AzureError as exc:
        raise MetadataStorageError("The document metadata could not be retrieved.") from exc


def list_documents() -> list[dict]:
    try:
        entities = _table_client().query_entities(query_filter=f"PartitionKey eq '{PARTITION_KEY}'")
        return sorted((dict(entity) for entity in entities), key=lambda item: item.get("upload_date", ""), reverse=True)
    except AzureError as exc:
        raise MetadataStorageError("The document list could not be retrieved.") from exc
