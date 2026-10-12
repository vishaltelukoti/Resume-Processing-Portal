"""FastAPI routes for the Mini Resume Processing Portal."""

from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import metadata
import storage


PROJECT_DIR = Path(__file__).resolve().parent
MAX_FILE_SIZE = 10 * 1024 * 1024
PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
PENDING_STATUSES = {"Uploaded", "Processing"}

app = FastAPI(title="Mini Resume Processing Portal")
app.mount("/static", StaticFiles(directory=PROJECT_DIR / "static"), name="static")
templates = Jinja2Templates(directory=PROJECT_DIR / "templates")


def dashboard_response(request: Request, error: str | None = None) -> Response:
    """Render the dashboard with its document history.

    Args:
        request: Current FastAPI request.
        error: Optional safe message to show to the user.

    Returns:
        Rendered dashboard response.
    """
    try:
        documents = metadata.list_documents()
    except metadata.MetadataStorageError:
        documents = []
        error = error or "Document history is temporarily unavailable."

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"documents": documents, "error": error},
        status_code=400 if error else 200,
    )


@app.get("/")
def dashboard(request: Request) -> Response:
    """Render the document upload dashboard."""
    return dashboard_response(request)


@app.post("/upload")
async def upload_resume(request: Request, resume: UploadFile = File(...)) -> Response:
    """Validate a PDF, upload it, and create its initial metadata entity.

    The Azure Function processes the blob asynchronously after Event Grid places
    its BlobCreated event on the processing queue.

    Args:
        request: Current FastAPI request.
        resume: Uploaded PDF supplied by the user.

    Returns:
        A dashboard error response or a redirect to the document details page.
    """
    filename = Path(resume.filename or "").name
    if not filename or Path(filename).suffix.lower() != ".pdf":
        return dashboard_response(request, "Please choose a PDF file.")
    if resume.content_type not in PDF_CONTENT_TYPES:
        return dashboard_response(
            request,
            "The uploaded file must have a PDF content type.",
        )

    content = await resume.read(MAX_FILE_SIZE + 1)
    if not content:
        return dashboard_response(request, "The uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE:
        return dashboard_response(request, "PDF files must be 10 MB or smaller.")
    if not content.startswith(b"%PDF-"):
        return dashboard_response(
            request,
            "The uploaded file does not have a valid PDF signature.",
        )

    document_id = str(uuid4())
    try:
        original_blob_name = storage.upload_original_pdf(document_id, content)
        try:
            metadata.create_document(
                document_id,
                filename,
                resume.content_type,
                original_blob_name=original_blob_name,
            )
        except Exception:
            # No entity exists yet, so this newly uploaded blob is safe to remove.
            storage.delete_original_pdf(original_blob_name)
            raise
    except storage.AzureStorageError:
        return dashboard_response(
            request,
            "Azure storage is unavailable. Please try again later.",
        )
    except metadata.MetadataStorageError:
        return dashboard_response(
            request,
            "Document metadata storage is unavailable. Please try again later.",
        )
    except Exception:
        return dashboard_response(
            request,
            "The upload could not be saved. Please try again.",
        )
    finally:
        await resume.close()

    return RedirectResponse(url=f"/documents/{document_id}", status_code=303)


@app.get("/documents/{document_id}")
def document_details(request: Request, document_id: str) -> Response:
    """Render document status and extracted text when available.

    Args:
        request: Current FastAPI request.
        document_id: UUID of the requested document.

    Returns:
        Rendered details page. Pending pages refresh every five seconds.

    Raises:
        HTTPException: If the document does not exist or metadata is unavailable.
    """
    try:
        document = metadata.get_document(document_id)
    except metadata.MetadataStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail="Document metadata is temporarily unavailable.",
        ) from exc
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    extracted_text = None
    if document["status"] == "Completed" and document.get("extracted_blob_name"):
        try:
            extracted_text = storage.download_extracted_text(
                document["extracted_blob_name"]
            ).decode("utf-8")
        except storage.AzureStorageError:
            extracted_text = None

    response = templates.TemplateResponse(
        request=request,
        name="document.html",
        context={"document": document, "extracted_text": extracted_text},
    )
    if document["status"] in PENDING_STATUSES:
        response.headers["Refresh"] = "5"
    return response


@app.get("/download/pdf/{document_id}")
def download_pdf(document_id: str) -> Response:
    """Download an original PDF by its stored document identifier.

    Raises:
        HTTPException: If metadata or the requested PDF is unavailable.
    """
    try:
        document = metadata.get_document(document_id)
    except metadata.MetadataStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail="Document metadata is temporarily unavailable.",
        ) from exc
    if not document:
        raise HTTPException(status_code=404, detail="Original PDF not found.")

    if document.get("original_blob_name"):
        try:
            content = storage.download_original_pdf(document["original_blob_name"])
        except storage.AzureStorageError as exc:
            raise HTTPException(
                status_code=404,
                detail="Original PDF is unavailable.",
            ) from exc

        filename = quote(Path(document["filename"]).name)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )

    path = storage.get_original_pdf_path(document_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Original PDF not found.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=Path(document["filename"]).name,
    )


@app.get("/download/text/{document_id}")
def download_text(document_id: str) -> Response:
    """Download extracted text by its stored document identifier.

    Raises:
        HTTPException: If metadata or extracted text is unavailable.
    """
    try:
        document = metadata.get_document(document_id)
    except metadata.MetadataStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail="Document metadata is temporarily unavailable.",
        ) from exc
    if not document or not document.get("extracted_blob_name"):
        raise HTTPException(status_code=404, detail="Extracted text file not found.")

    try:
        content = storage.download_extracted_text(document["extracted_blob_name"])
    except storage.AzureStorageError as exc:
        raise HTTPException(
            status_code=404,
            detail="Extracted text file not found.",
        ) from exc

    filename = quote(f"{Path(document['filename']).stem}.txt")
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@app.get("/api/documents")
def api_documents() -> list[metadata.Document]:
    """Return all document metadata as JSON.

    Raises:
        HTTPException: If Azure Table Storage is unavailable.
    """
    try:
        return metadata.list_documents()
    except metadata.MetadataStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail="Document metadata is temporarily unavailable.",
        ) from exc


@app.get("/api/documents/{document_id}")
def api_document(document_id: str) -> metadata.Document:
    """Return metadata for one document as JSON.

    Raises:
        HTTPException: If metadata is unavailable or the document does not exist.
    """
    try:
        document = metadata.get_document(document_id)
    except metadata.MetadataStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail="Document metadata is temporarily unavailable.",
        ) from exc
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document
