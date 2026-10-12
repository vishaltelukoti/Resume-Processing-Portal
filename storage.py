"""Azure original-PDF and local extracted-text operations."""

from pathlib import Path

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv
import logging
import os


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")
logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
EXTRACTED_DIR = DATA_DIR / "extracted"


def _ensure_directories() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)


class AzureStorageError(Exception):
    """A safe error raised when Azure Blob Storage cannot be used."""


def _original_pdfs_container():
    """Return the configured container client without exposing credentials."""
    return _blob_container("AZURE_BLOB_CONTAINER")


def _extracted_text_container():
    return _blob_container("AZURE_EXTRACTED_CONTAINER")


def _blob_container(container_setting: str):
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv(container_setting)
    if not connection_string or not container_name:
        raise AzureStorageError("Azure Blob Storage is not configured.")
    try:
        service_client = BlobServiceClient.from_connection_string(connection_string)
        return service_client.get_container_client(container_name)
    except (ValueError, AzureError) as exc:
        raise AzureStorageError("Azure Blob Storage configuration is unavailable.") from exc


def get_original_pdf_path(document_id: str) -> Path:
    """Build the fixed storage path; users never supply a filename/path."""
    return UPLOADS_DIR / document_id / "original.pdf"


def get_extracted_text_path(document_id: str) -> Path:
    return EXTRACTED_DIR / f"{document_id}.txt"


def upload_original_pdf(document_id: str, content: bytes) -> str:
    """Upload a PDF to Azure and return its blob name for local metadata."""
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
        raise AzureStorageError("The original PDF could not be uploaded to Azure Blob Storage.") from exc


def download_original_pdf(blob_name: str) -> bytes:
    """Download an original PDF from Azure using the stored blob name."""
    try:
        return _original_pdfs_container().get_blob_client(blob_name).download_blob().readall()
    except AzureStorageError:
        raise
    except AzureError as exc:
        raise AzureStorageError("The original PDF could not be downloaded from Azure Blob Storage.") from exc


def download_extracted_text(blob_name: str) -> bytes:
    """Download extracted text from Azure Blob Storage."""
    try:
        return _extracted_text_container().get_blob_client(blob_name).download_blob().readall()
    except AzureStorageError:
        raise
    except AzureError as exc:
        raise AzureStorageError("The extracted text could not be downloaded from Azure Blob Storage.") from exc


def delete_original_pdf(blob_name: str) -> bool:
    """Delete a newly uploaded blob when its metadata record could not be created."""
    try:
        _original_pdfs_container().get_blob_client(blob_name).delete_blob()
        return True
    except (AzureStorageError, AzureError):
        # Blob name contains only the generated document ID; never log credentials.
        logger.warning("Could not clean up uploaded Azure blob: %s", blob_name)
        return False


def save_extracted_text(document_id: str, text: str) -> str:
    _ensure_directories()
    path = get_extracted_text_path(document_id)
    path.write_text(text, encoding="utf-8")
    return str(path)


def read_extracted_text(document_id: str) -> str:
    return get_extracted_text_path(document_id).read_text(encoding="utf-8")


def extracted_file_exists(document_id: str) -> bool:
    return get_extracted_text_path(document_id).is_file()
