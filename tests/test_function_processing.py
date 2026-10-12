"""Unit tests for the queue-triggered PDF processing workflow."""

import json
import os
import unittest
from unittest.mock import Mock, patch

from azure.core.exceptions import ResourceNotFoundError

from azure_functions import function_app


class FakeMessage:
    def __init__(self, document_id="doc-123"):
        self.document_id = document_id

    def get_body(self):
        event = {
            "eventType": "Microsoft.Storage.BlobCreated",
            "data": {"url": f"https://account.blob.core.windows.net/original-pdfs/{self.document_id}/original.pdf"},
        }
        return json.dumps(event).encode("utf-8")


class FakeTableClient:
    def __init__(self, entity, later_entity=None):
        self.entity = entity
        self.later_entity = later_entity
        self.get_count = 0
        self.status_updates = []

    def get_entity(self, _partition_key, _row_key):
        self.get_count += 1
        if self.later_entity is not None and self.get_count > 1:
            return self.later_entity
        return self.entity

    def update_entity(self, entity, mode):
        self.status_updates.append(entity["status"])


class FunctionProcessingTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"AzureWebJobsStorage": "UseDevelopmentStorage=true"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_successful_processing_marks_document_completed(self):
        table = FakeTableClient({"status": "Uploaded"})
        original_client = Mock()
        original_client.download_blob.return_value.readall.return_value = b"PDF"
        extracted_client = Mock()
        blob_service = Mock()
        blob_service.get_blob_client.side_effect = lambda container, blob: (
            extracted_client if container == "extracted-text" else original_client
        )
        reader = Mock(pages=[Mock(extract_text=lambda: "Candidate resume")])

        with patch("azure_functions.function_app.get_table_client", return_value=table), \
             patch("azure_functions.function_app.BlobServiceClient.from_connection_string", return_value=blob_service), \
             patch("azure_functions.function_app.PdfReader", return_value=reader):
            function_app.process_pdf(FakeMessage())

        self.assertEqual(table.status_updates, ["Processing", "Completed"])
        extracted_client.upload_blob.assert_called_once()

    def test_duplicate_completed_message_is_skipped_when_text_blob_exists(self):
        table = FakeTableClient({"status": "Completed"})
        extracted_client = Mock()
        extracted_client.exists.return_value = True
        blob_service = Mock()
        blob_service.get_blob_client.return_value = extracted_client

        with patch("azure_functions.function_app.get_table_client", return_value=table), \
             patch("azure_functions.function_app.BlobServiceClient.from_connection_string", return_value=blob_service):
            function_app.process_pdf(FakeMessage())

        self.assertEqual(table.status_updates, [])
        extracted_client.download_blob.assert_not_called()

    def test_missing_metadata_raises_for_queue_retry(self):
        table = Mock()
        table.get_entity.side_effect = ResourceNotFoundError(message="not found", response=Mock())

        with patch("azure_functions.function_app.get_table_client", return_value=table), \
             patch("azure_functions.function_app.time.sleep"):
            with self.assertRaises(RuntimeError):
                function_app.process_pdf(FakeMessage())

    def test_processing_failure_marks_document_failed_and_reraises(self):
        table = FakeTableClient({"status": "Uploaded"})
        original_client = Mock()
        original_client.download_blob.side_effect = RuntimeError("temporary failure")
        extracted_client = Mock()
        blob_service = Mock()
        blob_service.get_blob_client.side_effect = lambda container, blob: (
            extracted_client if container == "extracted-text" else original_client
        )

        with patch("azure_functions.function_app.get_table_client", return_value=table), \
             patch("azure_functions.function_app.BlobServiceClient.from_connection_string", return_value=blob_service):
            with self.assertRaises(RuntimeError):
                function_app.process_pdf(FakeMessage())

        self.assertEqual(table.status_updates, ["Processing", "Failed"])

    def test_failure_does_not_overwrite_a_completed_retry(self):
        table = FakeTableClient({"status": "Processing"}, later_entity={"status": "Completed"})
        original_client = Mock()
        original_client.download_blob.side_effect = RuntimeError("temporary failure")
        extracted_client = Mock()
        blob_service = Mock()
        blob_service.get_blob_client.side_effect = lambda container, blob: (
            extracted_client if container == "extracted-text" else original_client
        )

        with patch("azure_functions.function_app.get_table_client", return_value=table), \
             patch("azure_functions.function_app.BlobServiceClient.from_connection_string", return_value=blob_service):
            with self.assertRaises(RuntimeError):
                function_app.process_pdf(FakeMessage())

        self.assertEqual(table.status_updates, ["Processing"])


if __name__ == "__main__":
    unittest.main()
