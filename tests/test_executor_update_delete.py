"""Tests for QueryExecutor create_record, update_record, and delete_record methods"""

import pytest
from unittest.mock import MagicMock
from amplify_excel_migrator.graphql import QueryExecutor, GraphQLClient


@pytest.fixture
def mock_client():
    client = MagicMock(spec=GraphQLClient)
    return client


@pytest.fixture
def executor(mock_client):
    return QueryExecutor(mock_client, batch_size=2)


class TestCreateRecord:

    def test_creates_record_and_returns_result(self, executor):
        executor.client.request = MagicMock(
            return_value={"data": {"createCountry": {"id": "123", "name": "Israel Red"}}}
        )

        result = executor.create_record("Country", {"name": "Israel Red"}, return_fields=["id", "name"])

        assert result == {"id": "123", "name": "Israel Red"}
        executor.client.request.assert_called_once()
        call_args = executor.client.request.call_args
        assert "createCountry" in call_args[0][0]
        assert call_args[0][1] == {"input": {"name": "Israel Red"}}

    def test_returns_none_on_failure(self, executor):
        executor.client.request = MagicMock(return_value=None)

        result = executor.create_record("Country", {"name": "Test"})

        assert result is None

    def test_returns_none_when_no_data_key(self, executor):
        executor.client.request = MagicMock(return_value={"errors": [{"message": "error"}]})

        result = executor.create_record("Country", {"name": "Test"})

        assert result is None

    def test_uses_default_return_fields(self, executor):
        executor.client.request = MagicMock(return_value={"data": {"createCountry": {"id": "123"}}})

        result = executor.create_record("Country", {"name": "Test"})

        assert result == {"id": "123"}
        call_args = executor.client.request.call_args
        assert "id" in call_args[0][0]


class TestUpdateRecord:

    def test_updates_record_and_returns_result(self, executor):
        executor.client.request = MagicMock(
            return_value={"data": {"updateCountry": {"id": "123", "name": "Israel Med"}}}
        )

        result = executor.update_record("Country", "123", {"name": "Israel Med"}, return_fields=["id", "name"])

        assert result == {"id": "123", "name": "Israel Med"}
        executor.client.request.assert_called_once()
        call_args = executor.client.request.call_args
        assert "updateCountry" in call_args[0][0]
        assert call_args[0][1] == {"input": {"id": "123", "name": "Israel Med"}}

    def test_returns_none_on_failure(self, executor):
        executor.client.request = MagicMock(return_value=None)

        result = executor.update_record("Country", "123", {"name": "Israel Med"})

        assert result is None

    def test_returns_none_when_no_data_key(self, executor):
        executor.client.request = MagicMock(return_value={"errors": [{"message": "error"}]})

        result = executor.update_record("Country", "123", {"name": "Israel Med"})

        assert result is None

    def test_uses_default_return_fields(self, executor):
        executor.client.request = MagicMock(return_value={"data": {"updateCountry": {"id": "123"}}})

        result = executor.update_record("Country", "123", {"name": "Israel Med"})

        assert result == {"id": "123"}
        call_args = executor.client.request.call_args
        assert "id" in call_args[0][0]

    def test_passes_multiple_update_fields(self, executor):
        executor.client.request = MagicMock(
            return_value={"data": {"updateSite": {"id": "s1", "name": "Eilat", "countryId": "red-id"}}}
        )

        result = executor.update_record(
            "Site", "s1", {"name": "Eilat", "countryId": "red-id"}, return_fields=["id", "name", "countryId"]
        )

        assert result == {"id": "s1", "name": "Eilat", "countryId": "red-id"}
        call_args = executor.client.request.call_args
        assert call_args[0][1] == {"input": {"id": "s1", "name": "Eilat", "countryId": "red-id"}}


class TestDeleteRecord:

    def test_deletes_record_and_returns_result(self, executor):
        executor.client.request = MagicMock(return_value={"data": {"deleteCountry": {"id": "123"}}})

        result = executor.delete_record("Country", "123")

        assert result == {"id": "123"}
        executor.client.request.assert_called_once()
        call_args = executor.client.request.call_args
        assert "deleteCountry" in call_args[0][0]
        assert call_args[0][1] == {"input": {"id": "123"}}

    def test_returns_none_on_failure(self, executor):
        executor.client.request = MagicMock(return_value=None)

        result = executor.delete_record("Country", "123")

        assert result is None

    def test_returns_none_when_no_data_key(self, executor):
        executor.client.request = MagicMock(return_value={"errors": [{"message": "error"}]})

        result = executor.delete_record("Country", "123")

        assert result is None

    def test_uses_custom_return_fields(self, executor):
        executor.client.request = MagicMock(
            return_value={"data": {"deleteCountry": {"id": "123", "name": "Old Country"}}}
        )

        result = executor.delete_record("Country", "123", return_fields=["id", "name"])

        assert result == {"id": "123", "name": "Old Country"}
        call_args = executor.client.request.call_args
        assert "name" in call_args[0][0]
