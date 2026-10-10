"""PDF text extraction for the local synchronous processing step."""

from pathlib import Path
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfProcessingError(Exception):
    """An expected PDF problem that can be shown safely to the user."""


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a local PDF path (kept for local compatibility)."""
    return _extract_text(pdf_path)


def extract_pdf_text_from_bytes(content: bytes) -> str:
    """Extract text from the uploaded PDF without creating another local original."""
    return _extract_text(BytesIO(content))


def _extract_text(pdf_source: Path | BytesIO) -> str:
    try:
        reader = PdfReader(pdf_source)
        if reader.is_encrypted:
            raise PdfProcessingError("Encrypted PDFs are not supported.")
        text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    except PdfProcessingError:
        raise
    except PdfReadError as exc:
        raise PdfProcessingError("The PDF is corrupted or cannot be read.") from exc
    except Exception as exc:
        raise PdfProcessingError("The PDF text could not be extracted.") from exc

    if not text:
        raise PdfProcessingError("This PDF has no extractable text. OCR is outside this portal's scope.")
    return text
