"""Small regression tests for path resolution and Azure upload rollback."""

import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import metadata
import storage


class ReliabilityTests(unittest.TestCase):
    def test_storage_paths_are_based_on_the_project_directory(self):
        project_dir = Path(storage.__file__).resolve().parent
        self.assertEqual(storage.DATA_DIR, project_dir / "data")
        self.assertEqual(metadata.PROJECT_DIR, project_dir)
        self.assertEqual(metadata.TABLE_NAME, "ResumeDocuments")

    def test_upload_deletes_new_blob_when_metadata_creation_fails(self):
        blob_name = "new-document/original.pdf"

        class FakeUpload:
            filename = "resume.pdf"
            content_type = "application/pdf"

            async def read(self, _size):
                return b"%PDF-1.4"

            async def close(self):
                return None

        with patch("main.storage.upload_original_pdf", return_value=blob_name), \
             patch("main.metadata.create_document", side_effect=OSError("disk unavailable")), \
             patch("main.storage.delete_original_pdf", return_value=True) as delete_blob, \
             patch("main.dashboard_response", return_value="upload error"):
            response = asyncio.run(main.upload_resume(None, FakeUpload()))

        self.assertEqual(response, "upload error")
        delete_blob.assert_called_once_with(blob_name)

    def test_table_document_uses_the_required_keys(self):
        class FakeTableClient:
            def create_entity(self, entity):
                self.entity = entity

        table_client = FakeTableClient()
        with patch("metadata._table_client", return_value=table_client):
            document = metadata.create_document("doc-123", "resume.pdf", "application/pdf", "doc-123/original.pdf")

        self.assertEqual(document["PartitionKey"], "Resume")
        self.assertEqual(document["RowKey"], "doc-123")
        self.assertEqual(document["status"], "Uploaded")


if __name__ == "__main__":
    unittest.main()
