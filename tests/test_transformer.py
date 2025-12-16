"""Tests for DataTransformer class"""

import pytest
from unittest.mock import MagicMock
import pandas as pd
from amplify_excel_migrator.data.transformer import DataTransformer


@pytest.fixture
def mock_field_parser():
    parser = MagicMock()
    parser.clean_input.side_effect = lambda x: x
    parser.parse_field_input.side_effect = lambda field, name, value: value
    parser.parse_scalar_array.side_effect = lambda field, name, value: (
        value.split(",") if isinstance(value, str) else value
    )
    return parser


@pytest.fixture
def transformer(mock_field_parser):
    return DataTransformer(field_parser=mock_field_parser)


class TestDataTransformerInit:
    """Test DataTransformer initialization"""

    def test_initializes_with_field_parser(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser)
        assert transformer.field_parser == mock_field_parser


class TestTransformRowsToRecords:
    """Test transform_rows_to_records method"""

    def test_transforms_all_rows_successfully(self, transformer):
        df = pd.DataFrame({"name": ["John", "Jane"], "age": [25, 30]})
        parsed_model = {
            "fields": [{"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}]
        }

        records, row_dict, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert len(records) == 2
        assert records[0]["name"] == "John"
        assert records[1]["name"] == "Jane"
        assert len(failed) == 0

    def test_creates_row_dict_by_primary_field(self, transformer):
        df = pd.DataFrame({"name": ["John", "Jane"], "age": [25, 30]})
        parsed_model = {
            "fields": [{"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}]
        }

        records, row_dict, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert "John" in row_dict
        assert "Jane" in row_dict
        assert row_dict["John"]["age"] == 25
        assert row_dict["Jane"]["age"] == 30

    def test_handles_transformation_errors(self, transformer):
        df = pd.DataFrame({"name": ["John", "Jane"], "age": [25, 30]})
        parsed_model = {
            "fields": [{"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}]
        }

        transformer.transform_row_to_record = MagicMock(side_effect=[{"name": "John"}, Exception("Transform error")])

        records, row_dict, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert len(records) == 1
        assert len(failed) == 1
        assert failed[0]["primary_field"] == "name"
        assert failed[0]["primary_field_value"] == "Jane"
        assert "Transform error" in failed[0]["error"]

    def test_uses_row_count_when_primary_field_missing(self, transformer):
        df = pd.DataFrame({"age": [25, 30]})
        parsed_model = {
            "fields": [{"name": "age", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}]
        }

        records, row_dict, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert "Row 1" in row_dict
        assert "Row 2" in row_dict

    def test_skips_none_records(self, transformer):
        df = pd.DataFrame({"name": ["John", "Jane"]})
        parsed_model = {
            "fields": [{"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}]
        }

        transformer.transform_row_to_record = MagicMock(side_effect=[{"name": "John"}, None])

        records, row_dict, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert len(records) == 1
        assert records[0]["name"] == "John"


class TestTransformRowToRecord:
    """Test transform_row_to_record method"""

    def test_transforms_row_with_all_fields(self, transformer):
        row_dict = {"name": "John", "age": 25}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False},
                {"name": "age", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False},
            ]
        }

        result = transformer.transform_row_to_record(row_dict, parsed_model, {})

        assert result["name"] == "John"
        assert result["age"] == 25

    def test_skips_none_values(self, transformer):
        row_dict = {"name": "John", "age": 25}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False},
                {"name": "email", "is_id": False, "is_required": False, "is_list": False, "is_scalar": False},
            ]
        }

        transformer.parse_input = MagicMock(side_effect=[lambda: "John", lambda: None][0:2])
        transformer.parse_input.side_effect = ["John", None]

        result = transformer.transform_row_to_record(row_dict, parsed_model, {})

        assert "name" in result
        assert "email" not in result

    def test_processes_all_fields_in_model(self, transformer):
        row_dict = {"name": "John", "age": 25, "city": "NYC"}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False},
                {"name": "age", "is_id": False, "is_required": False, "is_list": False, "is_scalar": False},
                {"name": "city", "is_id": False, "is_required": False, "is_list": False, "is_scalar": False},
            ]
        }

        result = transformer.transform_row_to_record(row_dict, parsed_model, {})

        assert len(result) == 3


class TestParseInput:
    """Test parse_input method"""

    def test_parses_regular_field(self, transformer):
        row_dict = {"name": "John"}
        field = {"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}

        result = transformer.parse_input(row_dict, field, {})

        assert result == "John"

    def test_returns_none_for_missing_optional_field(self, transformer):
        row_dict = {"name": "John"}
        field = {"name": "email", "is_id": False, "is_required": False, "is_list": False, "is_scalar": False}

        result = transformer.parse_input(row_dict, field, {})

        assert result is None

    def test_raises_error_for_missing_required_field(self, transformer):
        row_dict = {"name": "John"}
        field = {"name": "age", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}

        with pytest.raises(ValueError, match="Required field 'age' is missing"):
            transformer.parse_input(row_dict, field, {})

    def test_returns_none_for_nan_values(self, transformer):
        row_dict = {"name": "John", "age": float("nan")}
        field = {"name": "age", "is_id": False, "is_required": False, "is_list": False, "is_scalar": False}

        result = transformer.parse_input(row_dict, field, {})

        assert result is None

    def test_cleans_input_value(self, transformer, mock_field_parser):
        row_dict = {"name": "  John  "}
        field = {"name": "name", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}
        mock_field_parser.clean_input.return_value = "John"

        result = transformer.parse_input(row_dict, field, {})

        mock_field_parser.clean_input.assert_called_once_with("  John  ")

    def test_resolves_foreign_key_field(self, transformer):
        row_dict = {"author": "John Doe"}
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {"John Doe": "author-123"}}}

        result = transformer.parse_input(row_dict, field, fk_cache)

        assert result == "author-123"

    def test_parses_scalar_array_field(self, transformer, mock_field_parser):
        row_dict = {"tags": "tag1,tag2,tag3"}
        field = {"name": "tags", "is_id": False, "is_required": False, "is_list": True, "is_scalar": True}
        mock_field_parser.parse_scalar_array.return_value = ["tag1", "tag2", "tag3"]

        result = transformer.parse_input(row_dict, field, {})

        assert result == ["tag1", "tag2", "tag3"]

    def test_uses_field_parser_for_regular_fields(self, transformer, mock_field_parser):
        row_dict = {"age": "25"}
        field = {"name": "age", "is_id": False, "is_required": True, "is_list": False, "is_scalar": False}
        mock_field_parser.parse_field_input.return_value = 25

        result = transformer.parse_input(row_dict, field, {})

        mock_field_parser.parse_field_input.assert_called_once()


class TestResolveForeignKey:
    """Test _resolve_foreign_key static method"""

    def test_resolves_fk_with_explicit_related_model(self, transformer):
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {"John Doe": "author-123"}}}

        result = transformer._resolve_foreign_key(field, "John Doe", fk_cache)

        assert result == "author-123"

    def test_infers_related_model_from_field_name(self, transformer):
        field = {"name": "authorId", "is_id": True, "is_required": True}
        fk_cache = {"Author": {"lookup": {"John Doe": "author-123"}}}

        result = transformer._resolve_foreign_key(field, "John Doe", fk_cache)

        assert result == "author-123"

    def test_raises_error_for_missing_optional_fk(self, transformer):
        field = {"name": "authorId", "is_id": True, "is_required": False, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {"Jane Doe": "author-456"}}}

        with pytest.raises(ValueError, match="Author: John Doe does not exist"):
            transformer._resolve_foreign_key(field, "John Doe", fk_cache)

    def test_raises_error_for_missing_required_fk(self, transformer):
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {"Jane Doe": "author-456"}}}

        with pytest.raises(ValueError, match="Author: John Doe does not exist"):
            transformer._resolve_foreign_key(field, "John Doe", fk_cache)

    def test_raises_error_for_missing_cache_optional_field(self, transformer):
        field = {"name": "authorId", "is_id": True, "is_required": False, "related_model": "Author"}
        fk_cache = {}

        with pytest.raises(ValueError, match="No pre-fetched data for Author"):
            transformer._resolve_foreign_key(field, "John Doe", fk_cache)

    def test_raises_error_for_missing_cache_required_field(self, transformer):
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {}

        with pytest.raises(ValueError, match="No pre-fetched data for Author"):
            transformer._resolve_foreign_key(field, "John Doe", fk_cache)

    def test_converts_value_to_string_for_lookup(self, transformer):
        field = {"name": "categoryId", "is_id": True, "is_required": True, "related_model": "Category"}
        fk_cache = {"Category": {"lookup": {"123": "cat-abc"}}}

        result = transformer._resolve_foreign_key(field, 123, fk_cache)

        assert result == "cat-abc"


class TestToCamelCase:
    """Test to_camel_case static method"""

    def test_converts_snake_case(self, transformer):
        assert transformer.to_camel_case("first_name") == "firstName"
        assert transformer.to_camel_case("last_name") == "lastName"

    def test_converts_kebab_case(self, transformer):
        assert transformer.to_camel_case("first-name") == "firstName"
        assert transformer.to_camel_case("last-name") == "lastName"

    def test_converts_space_separated(self, transformer):
        assert transformer.to_camel_case("first name") == "firstName"
        assert transformer.to_camel_case("last name") == "lastName"

    def test_converts_pascal_case(self, transformer):
        assert transformer.to_camel_case("FirstName") == "firstName"
        assert transformer.to_camel_case("LastName") == "lastName"

    def test_handles_mixed_separators(self, transformer):
        assert transformer.to_camel_case("first_name-value") == "firstNameValue"
        assert transformer.to_camel_case("user ID_number") == "userIDNumber"

    def test_preserves_already_camel_case(self, transformer):
        assert transformer.to_camel_case("firstName") == "firstName"
        assert transformer.to_camel_case("lastName") == "lastName"

    def test_handles_single_word(self, transformer):
        assert transformer.to_camel_case("name") == "name"
        assert transformer.to_camel_case("age") == "age"

    def test_handles_empty_string(self, transformer):
        result = transformer.to_camel_case("")
        assert result == ""

    def test_handles_consecutive_separators(self, transformer):
        assert transformer.to_camel_case("first__name") == "firstName"
        assert transformer.to_camel_case("last--name") == "lastName"
