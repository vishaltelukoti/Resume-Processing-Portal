# Mini Resume Processing Portal

A small, beginner-friendly FastAPI proof of concept for an Azure Storage assessment. An HR employee uploads a candidate resume as a PDF; the application stores the original document, extracts readable text, stores that text, and shows its processing status.

## Technology stack

- Python 3.11+
- FastAPI and Uvicorn
- HTML5, CSS3, and Jinja2 templates
- pypdf for text extraction
- Azure Blob Storage for PDFs and extracted text, Azure Table Storage for metadata

## Folder structure

```
mini-resume-portal/
├── main.py             # FastAPI routes and workflow coordination
├── storage.py          # Azure Blob Storage operations
├── metadata.py         # Azure Table Storage metadata operations
├── azure_functions/    # Queue-triggered PDF processing Function
├── templates/          # Jinja2 pages
├── static/css/         # Site styling
└── data/               # Local runtime files (ignored by Git)
```

## Asynchronous processing flow

1. The user selects a PDF (maximum 10 MB).
2. The portal validates its extension, content type, and `%PDF-` signature.
3. It uploads the original to `<document-id>/original.pdf` in the Azure container named by `AZURE_BLOB_CONTAINER`, then creates an `Uploaded` record in the `ResumeDocuments` Azure Table.
4. Event Grid places the BlobCreated event on `pdf-processing-queue`.
5. The queue-triggered Azure Function sets `Processing`, extracts PDF text, and writes `<document-id>.txt` to the extracted-text container.
6. The Function sets the table record to **Completed** or **Failed**. The details page refreshes every five seconds while processing is pending.

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

The portal reads both blob containers from `.env`. Metadata is always stored in the existing `ResumeDocuments` table with `PartitionKey` set to `Resume`.

Install dependencies and start the development server:

```powershell
pip install -r requirements.txt
uvicorn main:app --reload
```

Open the UI at `http://127.0.0.1:8000`. FastAPI Swagger documentation is at `http://127.0.0.1:8000/docs`.

To test, upload any normal text-based PDF resume using the dashboard's **Upload & Process** button. In Azure Portal, confirm the original blob appears in **original-pdfs**, then watch its `ResumeDocuments` table entity change from **Uploaded** to **Processing** and finally **Completed**. The extracted file appears in **extracted-text** as `<document-id>.txt`; the portal's document page displays and downloads it. The API endpoints remain available at `/api/documents` and `/api/documents/{document_id}`.

## Phase 2 Azure mapping (not implemented)

| Phase 1 local component | Phase 2 Azure replacement |
| --- | --- |
| Azure Blob Storage `original-pdfs` container | Implemented for original PDF uploads/downloads |
| Synchronous `processor.py` call | Implemented by the queue-triggered Azure Function |
| `data/extracted/` | Implemented by Azure Blob Storage `extracted-text` container |
| `data/metadata.json` | Implemented by Azure Table Storage |

The Phase 1 modules deliberately keep route coordination, file storage, metadata, and PDF processing separate, so those local implementations can be replaced independently when Azure services are introduced.
