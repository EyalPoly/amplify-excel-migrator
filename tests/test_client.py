"""Tests for AmplifyClient class"""

import pytest
import pandas as pd
from unittest.mock import MagicMock
from amplify_excel_migrator.client import AmplifyClient


class TestBuildForeignKeyLookups:
    """Test build_foreign_key_lookups method for performance optimization"""

    def test_builds_lookup_cache_for_related_models(self):
        """Test that FK lookup cache is built correctly"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(
            return_value=[
                {"id": "reporter-1", "name": "John Doe"},
                {"id": "reporter-2", "name": "Jane Smith"},
            ]
        )

        df = pd.DataFrame({"photographer": ["John Doe", "Jane Smith"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Verify cache was built
        assert "Reporter" in result
        assert result["Reporter"]["lookup"]["John Doe"] == "reporter-1"
        assert result["Reporter"]["lookup"]["Jane Smith"] == "reporter-2"
        assert result["Reporter"]["primary_field"] == "name"

        # Verify API was called once
        client._executor.get_primary_field_name.assert_called_once_with("Reporter", parsed_model_structure)
        client._executor.get_records.assert_called_once_with("Reporter", "name", False)

    def test_skips_non_id_fields(self):
        """Test that non-ID fields are skipped"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock()
        client._executor.get_records = MagicMock()

        df = pd.DataFrame({"title": ["Story 1"], "content": ["Content 1"]})
        parsed_model_structure = {
            "fields": [
                {"name": "title", "is_id": False, "is_required": True},
                {"name": "content", "is_id": False, "is_required": False},
            ]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # No lookups should be built
        assert result == {}
        client._executor.get_primary_field_name.assert_not_called()
        client._executor.get_records.assert_not_called()

    def test_skips_fields_not_in_dataframe(self):
        """Test that fields not in DataFrame columns are skipped"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock()

        df = pd.DataFrame({"title": ["Story 1"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # No lookups should be built
        assert result == {}
        client._executor.get_primary_field_name.assert_not_called()

    def test_infers_related_model_from_field_name(self):
        """Test that related model is inferred when not explicitly provided"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(return_value=[{"id": "author-1", "name": "Author One"}])

        df = pd.DataFrame({"author": ["Author One"]})
        parsed_model_structure = {
            "fields": [
                {"name": "authorId", "is_id": True, "is_required": True}
                # No related_model - should infer "Author" from "authorId"
            ]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Verify cache was built with inferred model name
        assert "Author" in result
        assert result["Author"]["lookup"]["Author One"] == "author-1"

        # Verify API was called with inferred model name
        client._executor.get_primary_field_name.assert_called_once_with("Author", parsed_model_structure)

    def test_handles_errors_gracefully(self):
        """Test that errors in fetching don't crash the whole process"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(side_effect=Exception("API Error"))

        df = pd.DataFrame({"photographer": ["John Doe"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        # Should not raise exception
        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Cache should be empty but process continues
        assert result == {}

    def test_deduplicates_same_related_model(self):
        """Test that the same related model is only fetched once"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(return_value=[{"id": "reporter-1", "name": "John Doe"}])

        df = pd.DataFrame({"photographer": ["John Doe"], "editor": ["Jane Smith"]})
        parsed_model_structure = {
            "fields": [
                {"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"},
                {"name": "editorId", "is_id": True, "is_required": True, "related_model": "Reporter"},
            ]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Only one Reporter lookup should exist
        assert len(result) == 1
        assert "Reporter" in result

        # API should be called only once
        client._executor.get_primary_field_name.assert_called_once()
        client._executor.get_records.assert_called_once()

    def test_handles_empty_records_response(self):
        """Test that empty records from API don't break the cache"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(return_value=None)  # API returns None

        df = pd.DataFrame({"photographer": ["John Doe"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Cache should be empty
        assert result == {}

    def test_filters_out_records_without_primary_field(self):
        """Test that records without the primary field are filtered out"""
        client = AmplifyClient(api_endpoint="https://test.com")

        client._executor.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        client._executor.get_records = MagicMock(
            return_value=[
                {"id": "reporter-1", "name": "John Doe"},
                {"id": "reporter-2"},  # Missing name
                {"id": "reporter-3", "name": None},  # None name
                {"id": "reporter-4", "name": "Jane Smith"},
            ]
        )

        df = pd.DataFrame({"photographer": ["John Doe", "Jane Smith"]})
        parsed_model_structure = {
            "fields": [{"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}]
        }

        result = client.build_foreign_key_lookups(df, parsed_model_structure)

        # Only valid records should be in cache
        assert len(result["Reporter"]["lookup"]) == 2
        assert "John Doe" in result["Reporter"]["lookup"]
        assert "Jane Smith" in result["Reporter"]["lookup"]
