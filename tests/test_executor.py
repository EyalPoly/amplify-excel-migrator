"""Tests for QueryExecutor class"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from amplify_excel_migrator.graphql import QueryExecutor, GraphQLClient


@pytest.fixture
def mock_client():
    """Create a mock GraphQL client"""
    client = MagicMock(spec=GraphQLClient)
    return client


@pytest.fixture
def executor(mock_client):
    """Create a QueryExecutor with mock client"""
    return QueryExecutor(mock_client, batch_size=2)


class TestQueryExecutorInit:
    """Test QueryExecutor initialization"""

    def test_initializes_with_client(self, mock_client):
        executor = QueryExecutor(mock_client)
        assert executor.client == mock_client
        assert executor.batch_size == 20
        assert executor.records_cache == {}

    def test_initializes_with_custom_batch_size(self, mock_client):
        executor = QueryExecutor(mock_client, batch_size=50)
        assert executor.batch_size == 50


class TestGetModelStructure:
    """Test get_model_structure method"""

    def test_delegates_to_schema_introspector(self, executor):
        executor.schema.get_model_structure = MagicMock(return_value={"fields": []})

        result = executor.get_model_structure("Story")

        executor.schema.get_model_structure.assert_called_once_with("Story")
        assert result == {"fields": []}


class TestGetPrimaryFieldName:
    """Test get_primary_field_name method"""

    def test_delegates_to_schema_introspector(self, executor):
        model_structure = {"fields": [{"name": "title"}]}
        executor.schema.get_primary_field_name = MagicMock(return_value=("title", False, "String"))

        result = executor.get_primary_field_name("Story", model_structure)

        executor.schema.get_primary_field_name.assert_called_once_with("Story", model_structure)
        assert result == ("title", False, "String")


class TestListRecordsBySecondaryIndex:
    """Test list_records_by_secondary_index method"""

    def test_lists_all_records_without_value(self, executor):
        executor._get_list_query_name = MagicMock(return_value="listStories")
        executor.client.request = MagicMock(
            return_value={"data": {"listStories": {"items": [{"id": "1"}], "nextToken": None}}}
        )

        result = executor.list_records_by_secondary_index("Story", "title")

        assert result == [{"id": "1"}]
        assert executor.client.request.call_count == 1

    def test_lists_records_with_pagination(self, executor):
        executor._get_list_query_name = MagicMock(return_value="listStories")
        executor.client.request = MagicMock(
            side_effect=[
                {"data": {"listStories": {"items": [{"id": "1"}], "nextToken": "token1"}}},
                {"data": {"listStories": {"items": [{"id": "2"}], "nextToken": None}}},
            ]
        )

        result = executor.list_records_by_secondary_index("Story", "title")

        assert result == [{"id": "1"}, {"id": "2"}]
        assert executor.client.request.call_count == 2

    def test_lists_records_with_specific_value(self, executor):
        executor.client.request = MagicMock(
            return_value={"data": {"listStoryByTitle": {"items": [{"id": "1", "title": "Test"}], "nextToken": None}}}
        )

        result = executor.list_records_by_secondary_index("Story", "title", value="Test")

        assert result == [{"id": "1", "title": "Test"}]

    def test_returns_none_when_no_items_found(self, executor):
        executor._get_list_query_name = MagicMock(return_value="listStories")
        executor.client.request = MagicMock(return_value={"data": {"listStories": {"items": [], "nextToken": None}}})

        result = executor.list_records_by_secondary_index("Story", "title")

        assert result is None

    def test_handles_error_response(self, executor):
        executor._get_list_query_name = MagicMock(return_value="listStories")
        executor.client.request = MagicMock(return_value=None)

        result = executor.list_records_by_secondary_index("Story", "title")

        assert result is None


class TestListRecordsByField:
    """Test list_records_by_field method"""

    def test_lists_records_without_filter(self, executor):
        executor._get_list_query_name = MagicMock(return_value="listStories")
        executor.client.request = MagicMock(
            return_value={"data": {"listStories": {"items": [{"id": "1"}], "nextToken": None}}}
        )

        result = executor.list_records_by_field("Story", "title")

        assert result == [{"id": "1"}]

    def test_lists_records_with_filter(self, executor):
        executor._get_list_query_name = MagicMock(return_value="listStories")
        executor.client.request = MagicMock(
            return_value={"data": {"listStories": {"items": [{"id": "1", "title": "Test"}], "nextToken": None}}}
        )

        result = executor.list_records_by_field("Story", "title", value="Test")

        assert result == [{"id": "1", "title": "Test"}]

    def test_returns_none_when_no_records(self, executor):
        executor._get_list_query_name = MagicMock(return_value="listStories")
        executor.client.request = MagicMock(return_value={"data": {"listStories": {"items": [], "nextToken": None}}})

        result = executor.list_records_by_field("Story", "title")

        assert result is None


class TestGetRecordById:
    """Test get_record_by_id method"""

    def test_gets_record_by_id(self, executor):
        executor.client.request = MagicMock(return_value={"data": {"getStory": {"id": "123", "title": "Test Story"}}})

        result = executor.get_record_by_id("Story", "123")

        assert result == {"id": "123", "title": "Test Story"}

    def test_returns_none_when_not_found(self, executor):
        executor.client.request = MagicMock(return_value={"data": {"getStory": None}})

        result = executor.get_record_by_id("Story", "999")

        assert result is None

    def test_returns_none_on_error(self, executor):
        executor.client.request = MagicMock(return_value=None)

        result = executor.get_record_by_id("Story", "123")

        assert result is None


class TestGetRecords:
    """Test get_records method"""

    def test_returns_cached_records(self, executor):
        cached_data = [{"id": "1"}]
        executor.records_cache["Story"] = cached_data

        result = executor.get_records("Story", "title", False)

        assert result == cached_data

    def test_fetches_and_caches_records(self, executor):
        executor.list_records_by_field = MagicMock(return_value=[{"id": "1"}])

        result = executor.get_records("Story", "title", False)

        assert result == [{"id": "1"}]
        assert executor.records_cache["Story"] == [{"id": "1"}]

    def test_uses_secondary_index_when_specified(self, executor):
        executor.list_records_by_secondary_index = MagicMock(return_value=[{"id": "1"}])

        result = executor.get_records("Story", "title", True)

        executor.list_records_by_secondary_index.assert_called_once()
        assert result == [{"id": "1"}]

    def test_returns_none_when_no_primary_field(self, executor):
        result = executor.get_records("Story", None, False)

        assert result is None


class TestGetRecord:
    """Test get_record method"""

    def test_gets_record_by_id_when_provided(self, executor):
        executor.get_record_by_id = MagicMock(return_value={"id": "123"})

        result = executor.get_record("Story", record_id="123")

        executor.get_record_by_id.assert_called_once_with("Story", "123")
        assert result == {"id": "123"}

    def test_gets_record_by_primary_field(self, executor):
        executor.get_records = MagicMock(
            return_value=[{"id": "1", "title": "Story 1"}, {"id": "2", "title": "Story 2"}]
        )

        result = executor.get_record("Story", primary_field="title", value="Story 2")

        assert result == {"id": "2", "title": "Story 2"}

    def test_returns_none_when_record_not_found(self, executor):
        executor.get_records = MagicMock(return_value=[{"id": "1", "title": "Story 1"}])

        result = executor.get_record("Story", primary_field="title", value="Story 999")

        assert result is None

    def test_derives_primary_field_from_structure(self, executor):
        model_structure = {"fields": []}
        executor.get_primary_field_name = MagicMock(return_value=("title", False, "String"))
        executor.get_records = MagicMock(return_value=[{"id": "1", "title": "Test"}])

        result = executor.get_record("Story", parsed_model_structure=model_structure, value="Test")

        executor.get_primary_field_name.assert_called_once_with("Story", model_structure)
        assert result == {"id": "1", "title": "Test"}


class TestUpload:
    """Test upload method"""

    def test_uploads_records_in_batches(self, executor):
        records = [{"title": "Story 1"}, {"title": "Story 2"}, {"title": "Story 3"}]
        model_structure = {"fields": []}

        executor.get_primary_field_name = MagicMock(return_value=("title", False, "String"))

        with patch("asyncio.run", return_value=(2, 0, [])):
            success, error, failed = executor.upload(records, "Story", model_structure)

        # With batch_size=2, should have 2 batches
        assert success > 0

    def test_returns_error_when_no_primary_field(self, executor):
        records = [{"title": "Story 1"}]
        model_structure = {"fields": []}

        executor.get_primary_field_name = MagicMock(return_value=(None, False, None))

        success, error, failed = executor.upload(records, "Story", model_structure)

        assert success == 0
        assert error == len(records)


class TestBuildForeignKeyLookups:
    """Test build_foreign_key_lookups method"""

    def test_builds_lookup_cache_for_id_fields(self, executor):
        import pandas as pd

        df = pd.DataFrame({"photographer": ["John Doe", "Jane Smith"]})
        model_structure = {"fields": [{"name": "photographerId", "is_id": True, "related_model": "Reporter"}]}

        executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        executor.get_records = MagicMock(
            return_value=[{"id": "1", "name": "John Doe"}, {"id": "2", "name": "Jane Smith"}]
        )

        result = executor.build_foreign_key_lookups(df, model_structure)

        assert "Reporter" in result
        assert result["Reporter"]["lookup"]["John Doe"] == "1"
        assert result["Reporter"]["lookup"]["Jane Smith"] == "2"
        assert result["Reporter"]["primary_field"] == "name"

    def test_skips_non_id_fields(self, executor):
        import pandas as pd

        df = pd.DataFrame({"title": ["Story 1"]})
        model_structure = {"fields": [{"name": "title", "is_id": False}]}

        result = executor.build_foreign_key_lookups(df, model_structure)

        assert result == {}

    def test_skips_fields_not_in_dataframe(self, executor):
        import pandas as pd

        df = pd.DataFrame({"title": ["Story 1"]})
        model_structure = {"fields": [{"name": "photographerId", "is_id": True, "related_model": "Reporter"}]}

        result = executor.build_foreign_key_lookups(df, model_structure)

        assert result == {}

    def test_infers_related_model_from_field_name(self, executor):
        import pandas as pd

        df = pd.DataFrame({"author": ["Author One"]})
        model_structure = {"fields": [{"name": "authorId", "is_id": True}]}

        executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        executor.get_records = MagicMock(return_value=[{"id": "1", "name": "Author One"}])

        result = executor.build_foreign_key_lookups(df, model_structure)

        assert "Author" in result

    def test_handles_errors_gracefully(self, executor):
        import pandas as pd

        df = pd.DataFrame({"photographer": ["John"]})
        model_structure = {"fields": [{"name": "photographerId", "is_id": True, "related_model": "Reporter"}]}

        executor.get_primary_field_name = MagicMock(side_effect=Exception("Error"))

        result = executor.build_foreign_key_lookups(df, model_structure)

        assert result == {}

    def test_deduplicates_same_related_model(self, executor):
        import pandas as pd

        df = pd.DataFrame({"photographer": ["John"], "editor": ["Jane"]})
        model_structure = {
            "fields": [
                {"name": "photographerId", "is_id": True, "related_model": "Reporter"},
                {"name": "editorId", "is_id": True, "related_model": "Reporter"},
            ]
        }

        executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        executor.get_records = MagicMock(return_value=[{"id": "1", "name": "John"}])

        result = executor.build_foreign_key_lookups(df, model_structure)

        assert len(result) == 1
        assert "Reporter" in result
        executor.get_primary_field_name.assert_called_once()
