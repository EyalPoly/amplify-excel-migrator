"""Tests for BatchUploader class"""

import pytest
from unittest.mock import MagicMock
from amplify_excel_migrator.migration.batch_uploader import BatchUploader


@pytest.fixture
def mock_amplify_client():
    return MagicMock()


@pytest.fixture
def uploader(mock_amplify_client):
    return BatchUploader(amplify_client=mock_amplify_client)


class TestBatchUploaderInit:
    """Test BatchUploader initialization"""

    def test_initializes_with_client(self, mock_amplify_client):
        uploader = BatchUploader(amplify_client=mock_amplify_client)
        assert uploader.amplify_client == mock_amplify_client


class TestUploadRecords:
    """Test upload_records method"""

    def test_uploads_records_successfully(self, uploader, mock_amplify_client):
        records = [{"name": "John"}, {"name": "Jane"}]
        parsed_model = {"fields": []}
        mock_amplify_client.upload.return_value = (2, 0, [])

        success, errors, failed = uploader.upload_records(records, "TestSheet", parsed_model)

        assert success == 2
        assert errors == 0
        assert failed == []
        mock_amplify_client.upload.assert_called_once_with(records, "TestSheet", parsed_model)

    def test_returns_zeros_for_empty_records(self, uploader, mock_amplify_client):
        success, errors, failed = uploader.upload_records([], "TestSheet", {})

        assert success == 0
        assert errors == 0
        assert failed == []
        mock_amplify_client.upload.assert_not_called()

    def test_returns_upload_errors(self, uploader, mock_amplify_client):
        records = [{"name": "John"}, {"name": "Jane"}]
        parsed_model = {"fields": []}
        failed_uploads = [{"primary_field": "name", "primary_field_value": "Jane", "error": "Upload error"}]
        mock_amplify_client.upload.return_value = (1, 1, failed_uploads)

        success, errors, failed = uploader.upload_records(records, "TestSheet", parsed_model)

        assert success == 1
        assert errors == 1
        assert len(failed) == 1
        assert failed[0]["error"] == "Upload error"

    def test_delegates_to_amplify_client(self, uploader, mock_amplify_client):
        records = [{"name": "Test"}]
        parsed_model = {"fields": [{"name": "name"}]}
        mock_amplify_client.upload.return_value = (1, 0, [])

        uploader.upload_records(records, "MySheet", parsed_model)

        mock_amplify_client.upload.assert_called_once_with(records, "MySheet", parsed_model)
