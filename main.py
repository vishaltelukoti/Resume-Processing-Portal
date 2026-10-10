"""Web routes for the Mini Resume Processing Portal (local Phase 1)."""

from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import metadata
import processor
import storage


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

app = FastAPI(title="Mini Resume Processing Portal")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def dashboard_response(request: Request, error: str | None = None):
    """Render the dashboard, optionally with a safe user-facing error."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"documents": metadata.list_documents(), "error": error},
        status_code=400 if error else 200,
    )


@app.get("/")
def dashboard(request: Request):
    return dashboard_response(request)


@app.post("/upload")
async def upload_resume(request: Request, resume: UploadFile = File(...)):
    """Validate, store, and synchronously extract text from one PDF."""
    filename = Path(resume.filename or "").name
    if not filename or Path(filename).suffix.lower() != ".pdf":
        return dashboard_response(request, "Please choose a PDF file.")
    if resume.content_type not in PDF_CONTENT_TYPES:
        return dashboard_response(request, "The uploaded file must have a PDF content type.")

    content = await resume.read(MAX_FILE_SIZE + 1)
    if not content:
        return dashboard_response(request, "The uploaded file is empty.")
    if len(content) > MAX_FILE_SIZE:
        return dashboard_response(request, "PDF files must be 10 MB or smaller.")
    if not content.startswith(b"%PDF-"):
        return dashboard_response(request, "The uploaded file does not have a valid PDF signature.")

    document_id = str(uuid4())
    try:
        original_blob_name = storage.upload_original_pdf(document_id, content)
        metadata.create_document(
            document_id, filename, resume.content_type, original_blob_name=original_blob_name
        )
        metadata.update_status(document_id, "Processing")

        try:
            extracted_text = processor.extract_pdf_text_from_bytes(content)
            extracted_path = storage.save_extracted_text(document_id, extracted_text)
            metadata.update_status(document_id, "Completed", extracted_path=extracted_path)
        except processor.PdfProcessingError as exc:
            metadata.update_status(document_id, "Failed", error_message=str(exc))
        except Exception:
            # Do not expose unexpected implementation details in the UI.
            metadata.update_status(document_id, "Failed", error_message="The PDF could not be processed.")
    except storage.AzureStorageError:
        return dashboard_response(request, "Azure storage is unavailable. Please try again later.")
    except Exception:
        return dashboard_response(request, "The upload could not be saved. Please try again.")
    finally:
        await resume.close()

    return RedirectResponse(url=f"/documents/{document_id}", status_code=303)


@app.get("/documents/{document_id}")
def document_details(request: Request, document_id: str):
    document = metadata.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    extracted_text = None
    if document["status"] == "Completed" and storage.extracted_file_exists(document_id):
        extracted_text = storage.read_extracted_text(document_id)
    return templates.TemplateResponse(
        request=request,
        name="document.html",
        context={"document": document, "extracted_text": extracted_text},
    )


@app.get("/download/pdf/{document_id}")
def download_pdf(document_id: str):
    document = metadata.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Original PDF not found.")

    # Azure-backed documents use their saved blob name. Older local records still work.
    if document.get("original_blob_name"):
        try:
            content = storage.download_original_pdf(document["original_blob_name"])
        except storage.AzureStorageError:
            raise HTTPException(status_code=404, detail="Original PDF is unavailable.")
        filename = quote(Path(document["filename"]).name)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )

    path = storage.get_original_pdf_path(document_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Original PDF not found.")
    return FileResponse(path, media_type="application/pdf", filename=Path(document["filename"]).name)


@app.get("/download/text/{document_id}")
def download_text(document_id: str):
    document = metadata.get_document(document_id)
    path = storage.get_extracted_text_path(document_id)
    if not document or not path.is_file():
        raise HTTPException(status_code=404, detail="Extracted text file not found.")
    download_name = f"{Path(document['filename']).stem}.txt"
    return FileResponse(path, media_type="text/plain", filename=download_name)


@app.get("/api/documents")
def api_documents():
    return metadata.list_documents()


@app.get("/api/documents/{document_id}")
def api_document(document_id: str):
    document = metadata.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document
