"""JSON metadata repository for local development (single server only)."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


METADATA_FILE = Path("data") / "metadata.json"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_all() -> list[dict]:
    if not METADATA_FILE.exists():
        return []
    try:
        data = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # A development portal should continue serving rather than crash on bad local data.
        return []


def _write_all(documents: list[dict]) -> None:
    """Write to a temporary file then replace the JSON file atomically."""
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = METADATA_FILE.with_suffix(".tmp")
    temporary_file.write_text(json.dumps(documents, indent=2), encoding="utf-8")
    os.replace(temporary_file, METADATA_FILE)


def create_document(document_id: str, filename: str, file_type: str,
                    original_blob_name: str | None = None, original_path: str | None = None) -> dict:
    documents = _read_all()
    document = {
        "document_id": document_id,
        "filename": filename,
        "file_type": file_type,
        "upload_date": _utc_timestamp(),
        "status": "Uploaded",
        # original_path supports documents created before Azure integration.
        "original_path": original_path,
        "original_blob_name": original_blob_name,
        "extracted_path": None,
        "error_message": None,
    }
    documents.append(document)
    _write_all(documents)
    return document


def update_status(document_id: str, status: str, extracted_path: str | None = None,
                  error_message: str | None = None) -> dict | None:
    documents = _read_all()
    for document in documents:
        if document["document_id"] == document_id:
            document["status"] = status
            if extracted_path is not None:
                document["extracted_path"] = extracted_path
            if error_message is not None:
                document["error_message"] = error_message
            _write_all(documents)
            return document
    return None


def get_document(document_id: str) -> dict | None:
    return next((item for item in _read_all() if item["document_id"] == document_id), None)


def list_documents() -> list[dict]:
    return sorted(_read_all(), key=lambda item: item.get("upload_date", ""), reverse=True)
