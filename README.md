# Mini Resume Processing Portal

A small, beginner-friendly FastAPI proof of concept for an Azure Storage assessment. An HR employee uploads a candidate resume as a PDF; the application stores the original document, extracts readable text, stores that text, and shows its processing status.

## Technology stack

- Python 3.11+
- FastAPI and Uvicorn
- HTML5, CSS3, and Jinja2 templates
- pypdf for text extraction
- Azure Blob Storage for original PDFs, plus local extracted text and JSON metadata

## Folder structure

```
mini-resume-portal/
├── main.py             # FastAPI routes and workflow coordination
├── storage.py          # Local PDF/TXT file operations
├── processor.py        # pypdf text extraction
├── metadata.py         # Atomic JSON metadata operations
├── templates/          # Jinja2 pages
├── static/css/         # Site styling
└── data/               # Local runtime files (ignored by Git)
```

## Local processing flow

1. The user selects a PDF (maximum 10 MB).
2. The portal validates its extension, content type, and `%PDF-` signature.
3. It uploads the original to `<document-id>/original.pdf` in the Azure container named by `AZURE_BLOB_CONTAINER`, then records the blob name in `data/metadata.json`.
4. It synchronously extracts text from the uploaded PDF with pypdf and saves it at `data/extracted/<document-id>.txt`.
5. Metadata progresses from **Uploaded** to **Processing**, then **Completed** or **Failed**.

Textless, corrupt, and encrypted PDFs are reported as failures. OCR is intentionally out of scope.

## Run locally on Windows

From the project folder, create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Create a `.env` file in the project root (never commit it):

```dotenv
AZURE_STORAGE_CONNECTION_STRING=your-connection-string
AZURE_BLOB_CONTAINER=original-pdfs
AZURE_EXTRACTED_CONTAINER=extracted-text
```

`AZURE_EXTRACTED_CONTAINER` is reserved for the next Azure milestone; extracted TXT files remain local today.

Install dependencies and start the development server:

```powershell
pip install -r requirements.txt
uvicorn main:app --reload
```

Open the UI at `http://127.0.0.1:8000`. FastAPI Swagger documentation is at `http://127.0.0.1:8000/docs`.

To test, upload any normal text-based PDF resume using the dashboard's **Upload & Process** button. In Azure Portal, open storage account **vishalstoragepoc**, then the **original-pdfs** container: a blob named `<document-id>/original.pdf` should appear. Open the document page and select **Download Original PDF** to confirm the portal retrieves that blob. Extracted text remains available locally from the same page. The API endpoints are also available at `/api/documents` and `/api/documents/{document_id}`.

## Phase 2 Azure mapping (not implemented)

| Phase 1 local component | Phase 2 Azure replacement |
| --- | --- |
| Azure Blob Storage `original-pdfs` container | Already implemented for original PDF uploads/downloads |
| Synchronous `processor.py` call | Azure Event Grid + Queue Storage + queue-triggered Function |
| `data/extracted/` | Azure Blob Storage `extracted-text` container |
| `data/metadata.json` | Azure Table Storage |

The Phase 1 modules deliberately keep route coordination, file storage, metadata, and PDF processing separate, so those local implementations can be replaced independently when Azure services are introduced.
