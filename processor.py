"""PDF text extraction helpers used by the local compatibility path."""

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfProcessingError(Exception):
    """Raised when a PDF cannot be read or has no extractable text."""


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a local PDF path.

    Args:
        pdf_path: Local path of the PDF to read.

    Returns:
        Extracted PDF text.

    Raises:
        PdfProcessingError: If the PDF is unreadable, encrypted, or textless.
    """
    return _extract_text(pdf_path)


def extract_pdf_text_from_bytes(content: bytes) -> str:
    """Extract text from PDF bytes without writing an original file locally.

    Args:
        content: Complete validated PDF file content.

    Returns:
        Extracted PDF text.

    Raises:
        PdfProcessingError: If the PDF is unreadable, encrypted, or textless.
    """
    return _extract_text(BytesIO(content))


def _extract_text(pdf_source: Path | BytesIO) -> str:
    """Read and validate extractable text from a pypdf-compatible source."""
    try:
        reader = PdfReader(pdf_source)
        if reader.is_encrypted:
            raise PdfProcessingError("Encrypted PDFs are not supported.")

        text = "\n\n".join(
            (page.extract_text() or "").strip() for page in reader.pages
        ).strip()
    except PdfProcessingError:
        raise
    except PdfReadError as exc:
        raise PdfProcessingError("The PDF is corrupted or cannot be read.") from exc
    except Exception as exc:
        raise PdfProcessingError("The PDF text could not be extracted.") from exc

    if not text:
        raise PdfProcessingError(
            "This PDF has no extractable text. OCR is outside this portal's scope."
        )
    return text
