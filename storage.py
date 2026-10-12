"""Azure Blob Storage and local compatibility file operations."""

import logging
import os
from pathlib import Path
from typing import Any

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
EXTRACTED_DIR = DATA_DIR / "extracted"

logger = logging.getLogger(__name__)
load_dotenv(PROJECT_DIR / ".env")


class AzureStorageError(Exception):
    """Raised when Azure Blob Storage cannot be used safely."""


def _ensure_directories() -> None:
    """Create local compatibility directories when they are needed."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)


def _original_pdfs_container() -> Any:
    """Return the configured client for original PDF blobs."""
    return _blob_container("AZURE_BLOB_CONTAINER")


def _extracted_text_container() -> Any:
    """Return the configured client for extracted text blobs."""
    return _blob_container("AZURE_EXTRACTED_CONTAINER")


def _blob_container(container_setting: str) -> Any:
    """Build a Blob Container client from the configured environment.

    Args:
        container_setting: Environment variable that names the container.

    Returns:
        Azure container client for the requested storage container.

    Raises:
        AzureStorageError: If Azure Blob Storage is not configured or is invalid.
    """
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv(container_setting)
    if not connection_string or not container_name:
        raise AzureStorageError("Azure Blob Storage is not configured.")

    try:
        service_client = BlobServiceClient.from_connection_string(connection_string)
        return service_client.get_container_client(container_name)
    except (ValueError, AzureError) as exc:
        raise AzureStorageError(
            "Azure Blob Storage configuration is unavailable."
        ) from exc


def get_original_pdf_path(document_id: str) -> Path:
    """Return the fixed legacy local path for an original PDF.

    Args:
        document_id: UUID of the requested document.

    Returns:
        The legacy local PDF path. User-provided filenames are never used.
    """
    return UPLOADS_DIR / document_id / "original.pdf"


def get_extracted_text_path(document_id: str) -> Path:
    """Return the fixed legacy local path for extracted text."""
    return EXTRACTED_DIR / f"{document_id}.txt"


def upload_original_pdf(document_id: str, content: bytes) -> str:
    """Upload an original PDF and return its Azure Blob name.

    Args:
        document_id: UUID generated for the uploaded document.
        content: Validated PDF bytes.

    Returns:
        Blob name stored in Azure Table Storage metadata.

    Raises:
        AzureStorageError: If the upload cannot be completed.
    """
    blob_name = f"{document_id}/original.pdf"
    try:
        _original_pdfs_container().upload_blob(
            name=blob_name,
            data=content,
            overwrite=False,
            content_settings=ContentSettings(content_type="application/pdf"),
        )
        return blob_name
    except AzureStorageError:
        raise
    except AzureError as exc:
        raise AzureStorageError(
            "The original PDF could not be uploaded to Azure Blob Storage."
        ) from exc


def download_original_pdf(blob_name: str) -> bytes:
    """Download an original PDF from Azure Blob Storage.

    Args:
        blob_name: Original PDF blob name saved in metadata.

    Returns:
        The complete PDF content.

    Raises:
        AzureStorageError: If the PDF cannot be downloaded.
    """
    try:
        blob_client = _original_pdfs_container().get_blob_client(blob_name)
        return blob_client.download_blob().readall()
    except AzureStorageError:
        raise
    except AzureError as exc:
        raise AzureStorageError(
            "The original PDF could not be downloaded from Azure Blob Storage."
        ) from exc


def download_extracted_text(blob_name: str) -> bytes:
    """Download extracted text from Azure Blob Storage.

    Args:
        blob_name: Extracted text blob name saved in metadata.

    Returns:
        UTF-8 encoded extracted text.

    Raises:
        AzureStorageError: If the text blob cannot be downloaded.
    """
    try:
        blob_client = _extracted_text_container().get_blob_client(blob_name)
        return blob_client.download_blob().readall()
    except AzureStorageError:
        raise
    except AzureError as exc:
        raise AzureStorageError(
            "The extracted text could not be downloaded from Azure Blob Storage."
        ) from exc


def delete_original_pdf(blob_name: str) -> bool:
    """Delete a new blob when its initial metadata record could not be created.

    Args:
        blob_name: Newly uploaded original PDF blob to remove.

    Returns:
        ``True`` when deletion succeeds; otherwise ``False`` after safe logging.
    """
    try:
        _original_pdfs_container().get_blob_client(blob_name).delete_blob()
        return True
    except (AzureStorageError, AzureError):
        logger.warning("Could not clean up uploaded Azure blob: %s", blob_name)
        return False


def save_extracted_text(document_id: str, text: str) -> str:
    """Save extracted text locally for legacy compatibility."""
    _ensure_directories()
    path = get_extracted_text_path(document_id)
    path.write_text(text, encoding="utf-8")
    return str(path)


def read_extracted_text(document_id: str) -> str:
    """Read legacy locally stored extracted text."""
    return get_extracted_text_path(document_id).read_text(encoding="utf-8")


def extracted_file_exists(document_id: str) -> bool:
    """Return whether legacy locally stored extracted text is available."""
    return get_extracted_text_path(document_id).is_file()
