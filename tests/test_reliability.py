"""Small regression tests for path resolution and Azure upload rollback."""

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import metadata
import storage


class ReliabilityTests(unittest.TestCase):
    def test_local_paths_are_based_on_the_project_directory(self):
        project_dir = Path(storage.__file__).resolve().parent
        self.assertEqual(storage.DATA_DIR, project_dir / "data")
        self.assertEqual(metadata.METADATA_FILE, project_dir / "data" / "metadata.json")

    def test_upload_deletes_new_blob_when_metadata_creation_fails(self):
        client = TestClient(main.app)
        blob_name = "new-document/original.pdf"

        with patch("main.storage.upload_original_pdf", return_value=blob_name), \
             patch("main.metadata.create_document", side_effect=OSError("disk unavailable")), \
             patch("main.storage.delete_original_pdf", return_value=True) as delete_blob:
            response = client.post(
                "/upload",
                files={"resume": ("resume.pdf", b"%PDF-1.4", "application/pdf")},
            )

        self.assertEqual(response.status_code, 400)
        delete_blob.assert_called_once_with(blob_name)


if __name__ == "__main__":
    unittest.main()
