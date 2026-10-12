"""Azure Table Storage metadata operations for resume documents."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.data.tables import TableServiceClient, UpdateMode
from dotenv import load_dotenv


Document = dict[str, Any]
PROJECT_DIR = Path(__file__).resolve().parent
TABLE_NAME = "ResumeDocuments"
PARTITION_KEY = "Resume"

load_dotenv(PROJECT_DIR / ".env")


class MetadataStorageError(Exception):
    """Raised when Azure Table Storage cannot be used safely."""


def _table_client() -> Any:
    """Create a client for the configured resume metadata table.

    Returns:
        The Azure Table client for ``ResumeDocuments``.

    Raises:
        MetadataStorageError: If the connection string is missing or invalid.
    """
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise MetadataStorageError("Azure Table Storage is not configured.")

    try:
        service_client = TableServiceClient.from_connection_string(connection_string)
        return service_client.get_table_client(TABLE_NAME)
    except (ValueError, AzureError) as exc:
        raise MetadataStorageError(
            "Azure Table Storage configuration is unavailable."
        ) from exc


def _utc_timestamp() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_document(
    document_id: str,
    filename: str,
    file_type: str,
    original_blob_name: str | None = None,
    original_path: str | None = None,
) -> Document:
    """Create the initial ``Uploaded`` metadata record.

    Args:
        document_id: UUID generated for the uploaded document.
        filename: Original filename supplied by the user.
        file_type: Validated PDF MIME type.
        original_blob_name: Azure Blob Storage name for the original PDF.
        original_path: Retained for backwards-compatible callers; not stored.

    Returns:
        The entity written to Azure Table Storage.

    Raises:
        MetadataStorageError: If the entity cannot be created.
    """
    del original_path  # Azure Blob Storage replaced local original-PDF paths.
    entity: Document = {
        "PartitionKey": PARTITION_KEY,
        "RowKey": document_id,
        "document_id": document_id,
        "filename": filename,
        "file_type": file_type,
        "upload_date": _utc_timestamp(),
        "status": "Uploaded",
        "original_blob_name": original_blob_name or "",
    }

    try:
        _table_client().create_entity(entity=entity)
        return entity
    except AzureError as exc:
        raise MetadataStorageError("The document metadata could not be saved.") from exc


def update_status(
    document_id: str,
    status: str,
    extracted_path: str | None = None,
    error_message: str | None = None,
    extracted_blob_name: str | None = None,
) -> Document | None:
    """Update status and optional processing fields for one document.

    Args:
        document_id: UUID of the document to update.
        status: New processing status.
        extracted_path: Legacy alias for ``extracted_blob_name``.
        error_message: Safe user-facing processing failure message.
        extracted_blob_name: Azure Blob Storage name for extracted text.

    Returns:
        The updated entity, or ``None`` when it does not exist.

    Raises:
        MetadataStorageError: If Azure Table Storage cannot update the entity.
    """
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


def get_document(document_id: str) -> Document | None:
    """Get one document entity by its identifier.

    Args:
        document_id: UUID of the requested document.

    Returns:
        The document entity, or ``None`` when it does not exist.

    Raises:
        MetadataStorageError: If Azure Table Storage cannot be queried.
    """
    try:
        return dict(_table_client().get_entity(PARTITION_KEY, document_id))
    except ResourceNotFoundError:
        return None
    except AzureError as exc:
        raise MetadataStorageError(
            "The document metadata could not be retrieved."
        ) from exc


def list_documents() -> list[Document]:
    """List resume documents, newest upload first.

    Returns:
        All document entities in the resume partition.

    Raises:
        MetadataStorageError: If Azure Table Storage cannot be queried.
    """
    try:
        entities = _table_client().query_entities(
            query_filter=f"PartitionKey eq '{PARTITION_KEY}'"
        )
        return sorted(
            (dict(entity) for entity in entities),
            key=lambda item: item.get("upload_date", ""),
            reverse=True,
        )
    except AzureError as exc:
        raise MetadataStorageError(
            "The document list could not be retrieved."
        ) from exc
