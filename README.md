# Mini Resume Processing Portal

Mini Resume Processing Portal is a beginner-friendly FastAPI proof of concept
for an Azure Storage assessment. An HR employee uploads a PDF resume; the portal
stores the original in Azure Blob Storage, tracks it in Azure Table Storage, and
shows extracted text after a queue-triggered Azure Function finishes processing.

## Current architecture

The portal uses an asynchronous Azure Storage workflow:

1. FastAPI validates the PDF and uploads it to `original-pdfs`.
2. FastAPI creates an `Uploaded` entity in the `ResumeDocuments` Azure Table.
3. Azure Event Grid sends the BlobCreated event to `pdf-processing-queue`.
4. The `ProcessPDF` Azure Function receives the queue message and waits briefly
   if the metadata entity has not been created yet.
5. The Function changes the status to `Processing`, extracts text with `pypdf`,
   and uploads `<document-id>.txt` to `extracted-text`.
6. The Function changes the table status to `Completed` or `Failed`. Failures
   are re-raised so Azure Queue Storage can retry transient errors.
7. The portal reads document history from Azure Table Storage and both download
   endpoints read their files from Azure Blob Storage.

The Function handles duplicate queue messages safely: completed documents with
an existing extracted text blob are skipped.

## Technology stack

- Python 3.11+
- FastAPI and Uvicorn
- HTML5, CSS3, and Jinja2
- `pypdf`
- Azure Blob Storage
- Azure Table Storage
- Azure Event Grid and Azure Queue Storage
- Azure Functions (Python v2 programming model)

## Folder structure

```text
mini-resume-portal/
├── main.py                         # FastAPI routes and upload workflow
├── metadata.py                     # Azure Table Storage metadata operations
├── storage.py                      # Azure Blob Storage operations
├── processor.py                    # Local PDF helper retained for compatibility
├── requirements.txt                # Portal dependencies
├── templates/
│   ├── base.html                   # Shared Jinja layout
│   ├── index.html                  # Dashboard and upload form
│   └── document.html               # Document details page
├── static/
│   └── css/
│       └── style.css               # Responsive portal styles
├── tests/
│   ├── test_reliability.py         # Portal storage/metadata tests
│   └── test_function_processing.py # Function workflow tests
└── azure_functions/
    ├── function_app.py             # ProcessPDF queue-triggered Function
    ├── host.json                   # Azure Functions host configuration
    ├── requirements.txt            # Function dependencies
    └── local.settings.json         # Local-only Function settings; ignored by Git
```

## Azure resources and configuration

The following resources must already exist in storage account `vishalstoragepoc`:

- Blob container: `original-pdfs`
- Blob container: `extracted-text`
- Queue: `pdf-processing-queue`
- Table: `ResumeDocuments`
- Event Grid subscription: BlobCreated events from `original-pdfs` to
  `pdf-processing-queue`

### Portal configuration

Create a root `.env` file. It is ignored by Git and must never contain a
connection string in source-controlled files.

```dotenv
AZURE_STORAGE_CONNECTION_STRING=your-storage-connection-string
AZURE_BLOB_CONTAINER=original-pdfs
AZURE_EXTRACTED_CONTAINER=extracted-text
```

The portal stores each entity using `PartitionKey=Resume` and
`RowKey=<document-id>`.

### Azure Function configuration

For local Function development, create `azure_functions/local.settings.json`
from the following shape. This file is ignored by Git.

```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "your-storage-connection-string"
  }
}
```

For a deployed Function App, set `AzureWebJobsStorage` in the Function App
application settings instead. Do not commit secrets.

## Run the FastAPI portal locally on Windows

From the project root:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open these URLs:

- Portal: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Run the Azure Function locally on Windows

Install Azure Functions Core Tools first. Then open a second PowerShell window:

```powershell
cd azure_functions
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
func start
```

`func start` listens for messages from `pdf-processing-queue` using the
`AzureWebJobsStorage` setting. The FastAPI portal and the Function can use
separate virtual environments.

## Run the automated checks

From the project root, after activating the root `.venv`:

```powershell
python -m compileall -q main.py metadata.py storage.py processor.py azure_functions/function_app.py tests
python -m unittest discover -s tests -v
```

The tests use mocks and do not upload files to Azure.

## Test the end-to-end flow

1. Start the FastAPI portal and the Azure Function listener.
2. Upload a normal, text-based PDF smaller than 10 MB from the dashboard.
3. In Azure Portal, confirm `<document-id>/original.pdf` appears in
   `original-pdfs`.
4. Verify the corresponding `ResumeDocuments` entity changes through
   `Uploaded`, `Processing`, and `Completed`.
5. Confirm `<document-id>.txt` appears in `extracted-text`.
6. Refresh the document details page, or wait for its automatic five-second
   refresh. The extracted text and download link should appear after completion.
7. Use **Download Original PDF** and **Download Extracted TXT** to verify both
   Blob Storage download paths.

Corrupt, encrypted, or textless PDFs result in a safe `Failed` status. OCR is
not included in this proof of concept.

## Routes

| Route | Purpose |
| --- | --- |
| `GET /` | Dashboard, upload form, and document history |
| `POST /upload` | Validate, upload, and create initial metadata |
| `GET /documents/{document_id}` | Document status and extracted text |
| `GET /download/pdf/{document_id}` | Download original PDF |
| `GET /download/text/{document_id}` | Download extracted text |
| `GET /api/documents` | List document metadata as JSON |
| `GET /api/documents/{document_id}` | Retrieve one metadata entity as JSON |
| `GET /docs` | FastAPI Swagger documentation |

## Notes and limitations

- Processing is asynchronous; a newly uploaded document may remain `Uploaded`
  or `Processing` briefly.
- The Function retains the original PDF even when extraction fails, allowing
  HR users to download it and allowing queue retries to recover transient errors.
- No authentication, OCR, AI scoring, Docker, or database is included.
- Existing local file helper functions remain only for backward compatibility;
  current uploads, metadata, and extracted text use Azure Storage services.
