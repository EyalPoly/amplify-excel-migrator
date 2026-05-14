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
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                }
            ]
        }

        records, row_dict, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert len(records) == 2
        assert records[0]["name"] == "John"
        assert records[1]["name"] == "Jane"
        assert len(failed) == 0

    def test_creates_row_dict_by_primary_field(self, transformer):
        df = pd.DataFrame({"name": ["John", "Jane"], "age": [25, 30]})
        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                }
            ]
        }

        records, row_dict, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert "John" in row_dict
        assert "Jane" in row_dict
        assert row_dict["John"]["age"] == 25
        assert row_dict["Jane"]["age"] == 30

    def test_handles_transformation_errors(self, transformer):
        df = pd.DataFrame({"name": ["John", "Jane"], "age": [25, 30]})
        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                }
            ]
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
            "fields": [
                {
                    "name": "age",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                }
            ]
        }

        records, row_dict, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert "Row 1" in row_dict
        assert "Row 2" in row_dict

    def test_skips_none_records(self, transformer):
        df = pd.DataFrame({"name": ["John", "Jane"]})
        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                }
            ]
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
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                },
                {
                    "name": "age",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                },
            ]
        }

        result = transformer.transform_row_to_record(row_dict, parsed_model, {})

        assert result["name"] == "John"
        assert result["age"] == 25

    def test_skips_none_values(self, transformer):
        row_dict = {"name": "John", "age": 25}
        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                },
                {
                    "name": "email",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                },
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
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                },
                {
                    "name": "age",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                },
                {
                    "name": "city",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                },
            ]
        }

        result = transformer.transform_row_to_record(row_dict, parsed_model, {})

        assert len(result) == 3

    def test_collects_all_field_errors_before_raising(self, transformer):
        """A row with 2 bad fields must report both errors, not just the first."""
        row_dict = {"name": "John", "depth": "bad", "temperature": "also_bad"}
        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "String",
                },
                {
                    "name": "depth",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
                {
                    "name": "temperature",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
            ]
        }

        def parse_side_effect(row, field, cache):
            if field["name"] == "depth":
                raise ValueError("'depth' could not be parsed as Float (value: 'bad')")
            if field["name"] == "temperature":
                raise ValueError("'temperature' could not be parsed as Float (value: 'also_bad')")
            return row.get(field["name"])

        transformer.parse_input = MagicMock(side_effect=parse_side_effect)

        with pytest.raises(ValueError) as exc_info:
            transformer.transform_row_to_record(row_dict, parsed_model, {})

        error = str(exc_info.value)
        assert "'depth' could not be parsed as Float (value: 'bad')" in error
        assert "'temperature' could not be parsed as Float (value: 'also_bad')" in error

    def test_field_errors_joined_with_pipe_separator(self, transformer):
        parsed_model = {
            "fields": [
                {
                    "name": "a",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Int",
                },
                {
                    "name": "b",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Int",
                },
            ]
        }
        transformer.parse_input = MagicMock(
            side_effect=[
                ValueError("error A"),
                ValueError("error B"),
            ]
        )

        with pytest.raises(ValueError, match=r"error A \| error B"):
            transformer.transform_row_to_record({}, parsed_model, {})

    def test_raises_on_single_optional_field_error(self, transformer):
        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "String",
                },
                {
                    "name": "depth",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
            ]
        }
        transformer.parse_input = MagicMock(
            side_effect=[
                "John",
                ValueError("'depth' could not be parsed as Float (value: 'invalid')"),
            ]
        )

        with pytest.raises(ValueError, match="depth"):
            transformer.transform_row_to_record({"name": "John", "depth": "invalid"}, parsed_model, {})

    def test_all_fields_are_attempted_even_after_error(self, transformer):
        """The loop must not stop at the first failing field."""
        call_order = []

        def parse_side_effect(row, field, cache):
            call_order.append(field["name"])
            if field["name"] == "depth":
                raise ValueError("bad depth")
            return row.get(field["name"])

        transformer.parse_input = MagicMock(side_effect=parse_side_effect)

        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "String",
                },
                {
                    "name": "depth",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
                {
                    "name": "temperature",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
            ]
        }

        with pytest.raises(ValueError):
            transformer.transform_row_to_record(
                {"name": "John", "depth": "bad", "temperature": 25.0},
                parsed_model,
                {},
            )

        assert call_order == ["name", "depth", "temperature"]

    def test_no_error_raised_when_all_fields_parse_successfully(self, transformer):
        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "String",
                },
                {
                    "name": "depth",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
            ]
        }
        transformer.parse_input = MagicMock(side_effect=["John", 10.5])

        result = transformer.transform_row_to_record({"name": "John", "depth": 10.5}, parsed_model, {})

        assert result == {"name": "John", "depth": 10.5}

    def test_required_and_optional_errors_both_collected(self, transformer):
        """Required field error and optional field error appear together in combined message."""
        parsed_model = {
            "fields": [
                {
                    "name": "date",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "AWSDate",
                },
                {
                    "name": "depth",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
            ]
        }
        transformer.parse_input = MagicMock(
            side_effect=[
                ValueError("Required field 'date' is missing"),
                ValueError("'depth' could not be parsed as Float (value: 'bad')"),
            ]
        )

        with pytest.raises(ValueError) as exc_info:
            transformer.transform_row_to_record({}, parsed_model, {})

        error = str(exc_info.value)
        assert "date" in error
        assert "depth" in error

    def test_combined_error_ends_up_in_failed_rows(self, transformer):
        """End-to-end: transform_rows_to_records stores the combined error string."""
        df = pd.DataFrame([{"name": "John", "depth": "bad", "temperature": "bad"}])
        parsed_model = {
            "fields": [
                {
                    "name": "name",
                    "is_id": False,
                    "is_required": True,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "String",
                },
                {
                    "name": "depth",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
                {
                    "name": "temperature",
                    "is_id": False,
                    "is_required": False,
                    "is_list": False,
                    "is_scalar": False,
                    "type": "Float",
                },
            ]
        }

        def raise_on_bad(row, field, cache):
            if field["name"] in ("depth", "temperature"):
                raise ValueError(f"'{field['name']}' could not be parsed as Float (value: 'bad')")
            return row.get(field["name"])

        transformer.parse_input = MagicMock(side_effect=raise_on_bad)

        _, _, failed = transformer.transform_rows_to_records(df, parsed_model, "name", {})

        assert len(failed) == 1
        error = failed[0]["error"]
        assert "depth" in error
        assert "temperature" in error


class TestParseInput:
    """Test parse_input method"""

    def test_parses_regular_field(self, transformer):
        row_dict = {"name": "John"}
        field = {
            "name": "name",
            "is_id": False,
            "is_required": True,
            "is_list": False,
            "is_scalar": False,
        }

        result = transformer.parse_input(row_dict, field, {})

        assert result == "John"

    def test_returns_none_for_missing_optional_field(self, transformer):
        row_dict = {"name": "John"}
        field = {
            "name": "email",
            "is_id": False,
            "is_required": False,
            "is_list": False,
            "is_scalar": False,
        }

        result = transformer.parse_input(row_dict, field, {})

        assert result is None

    def test_raises_error_for_missing_required_field(self, transformer):
        row_dict = {"name": "John"}
        field = {
            "name": "age",
            "is_id": False,
            "is_required": True,
            "is_list": False,
            "is_scalar": False,
        }

        with pytest.raises(ValueError, match="Required field 'age' is missing"):
            transformer.parse_input(row_dict, field, {})

    def test_returns_none_for_nan_values(self, transformer):
        row_dict = {"name": "John", "age": float("nan")}
        field = {
            "name": "age",
            "is_id": False,
            "is_required": False,
            "is_list": False,
            "is_scalar": False,
        }

        result = transformer.parse_input(row_dict, field, {})

        assert result is None

    def test_cleans_input_value(self, transformer, mock_field_parser):
        row_dict = {"name": "  John  "}
        field = {
            "name": "name",
            "is_id": False,
            "is_required": True,
            "is_list": False,
            "is_scalar": False,
        }
        mock_field_parser.clean_input.return_value = "John"

        result = transformer.parse_input(row_dict, field, {})

        mock_field_parser.clean_input.assert_called_once_with("  John  ")

    def test_resolves_foreign_key_field(self, transformer):
        row_dict = {"author": "John Doe"}
        field = {
            "name": "authorId",
            "is_id": True,
            "is_required": True,
            "related_model": "Author",
        }
        fk_cache = {"Author": {"lookup": {"John Doe": "author-123"}}}

        result = transformer.parse_input(row_dict, field, fk_cache)

        assert result == "author-123"

    def test_parses_scalar_array_field(self, transformer, mock_field_parser):
        row_dict = {"tags": "tag1,tag2,tag3"}
        field = {
            "name": "tags",
            "is_id": False,
            "is_required": False,
            "is_list": True,
            "is_scalar": True,
        }
        mock_field_parser.parse_scalar_array.return_value = ["tag1", "tag2", "tag3"]

        result = transformer.parse_input(row_dict, field, {})

        assert result == ["tag1", "tag2", "tag3"]

    def test_uses_field_parser_for_regular_fields(self, transformer, mock_field_parser):
        row_dict = {"age": "25"}
        field = {
            "name": "age",
            "is_id": False,
            "is_required": True,
            "is_list": False,
            "is_scalar": False,
        }
        mock_field_parser.parse_field_input.return_value = 25

        result = transformer.parse_input(row_dict, field, {})

        mock_field_parser.parse_field_input.assert_called_once()

    def test_raises_for_optional_field_when_parse_returns_none(self, transformer, mock_field_parser):
        """Optional field with a present value that fails to parse must raise, not silently drop."""
        row_dict = {"depth": "5-4"}
        field = {
            "name": "depth",
            "is_id": False,
            "is_required": False,
            "is_list": False,
            "is_scalar": False,
            "type": "Float",
        }
        mock_field_parser.parse_field_input.side_effect = None
        mock_field_parser.parse_field_input.return_value = None

        with pytest.raises(ValueError, match="'depth'"):
            transformer.parse_input(row_dict, field, {})

    def test_error_message_includes_field_name_type_and_value(self, transformer, mock_field_parser):
        row_dict = {"temperature": "warm"}
        field = {
            "name": "temperature",
            "is_id": False,
            "is_required": False,
            "is_list": False,
            "is_scalar": False,
            "type": "Float",
        }
        mock_field_parser.parse_field_input.side_effect = None
        mock_field_parser.parse_field_input.return_value = None

        with pytest.raises(ValueError) as exc_info:
            transformer.parse_input(row_dict, field, {})

        error = str(exc_info.value)
        assert "'temperature'" in error
        assert "Float" in error
        assert "warm" in error

    def test_does_not_raise_for_optional_field_absent_from_row(self, transformer):
        """Missing optional field → None is correct, must not raise."""
        row_dict = {}
        field = {
            "name": "depth",
            "is_id": False,
            "is_required": False,
            "is_list": False,
            "is_scalar": False,
            "type": "Float",
        }

        result = transformer.parse_input(row_dict, field, {})

        assert result is None

    def test_does_not_raise_for_optional_field_with_nan_value(self, transformer):
        """NaN optional field → None is correct, must not raise."""
        row_dict = {"depth": float("nan")}
        field = {
            "name": "depth",
            "is_id": False,
            "is_required": False,
            "is_list": False,
            "is_scalar": False,
            "type": "Float",
        }

        result = transformer.parse_input(row_dict, field, {})

        assert result is None

    def test_returns_falsy_non_none_values_correctly(self, transformer, mock_field_parser):
        """parse_field_input returning 0 must not be treated as a parse failure."""
        row_dict = {"count": 0}
        field = {
            "name": "count",
            "is_id": False,
            "is_required": False,
            "is_list": False,
            "is_scalar": False,
            "type": "Int",
        }
        mock_field_parser.parse_field_input.return_value = 0

        result = transformer.parse_input(row_dict, field, {})

        assert result == 0

    def test_returns_false_boolean_correctly(self, transformer, mock_field_parser):
        row_dict = {"pregnant": "N"}
        field = {
            "name": "pregnant",
            "is_id": False,
            "is_required": False,
            "is_list": False,
            "is_scalar": False,
            "type": "Boolean",
        }
        mock_field_parser.parse_field_input.side_effect = None
        mock_field_parser.parse_field_input.return_value = False

        result = transformer.parse_input(row_dict, field, {})

        assert result is False

    def test_calls_build_custom_type_for_custom_type_field(self, transformer, mock_field_parser):
        """is_custom_type field is handled by build_custom_type_from_columns, not parse_field_input."""
        row_dict = {"length": "80.5"}
        custom_type_fields = [{"name": "length", "type": "Float", "is_required": False}]
        field = {
            "name": "individualGroups",
            "is_id": False,
            "is_required": False,
            "is_list": True,
            "is_scalar": False,
            "is_custom_type": True,
            "type": "IndividualGroup",
            "custom_type_fields": custom_type_fields,
        }
        mock_field_parser.build_custom_type_from_columns.return_value = [{"length": 80.5}]

        result = transformer.parse_input(row_dict, field, {})

        assert result == [{"length": 80.5}]

    def test_passes_pd_series_to_build_custom_type(self, transformer, mock_field_parser):
        """build_custom_type_from_columns must receive a pd.Series, not a dict."""
        row_dict = {"length": "80.5"}
        custom_type_fields = [{"name": "length", "type": "Float", "is_required": False}]
        field = {
            "name": "individualGroups",
            "is_id": False,
            "is_required": False,
            "is_list": True,
            "is_scalar": False,
            "is_custom_type": True,
            "type": "IndividualGroup",
            "custom_type_fields": custom_type_fields,
        }
        mock_field_parser.build_custom_type_from_columns.return_value = [{"length": 80.5}]

        transformer.parse_input(row_dict, field, {})

        call_args = mock_field_parser.build_custom_type_from_columns.call_args
        assert isinstance(call_args[0][0], pd.Series)

    def test_custom_type_returns_none_when_all_sub_columns_absent(self, transformer, mock_field_parser):
        """When all sub-columns are absent, build_custom_type_from_columns returns None."""
        row_dict = {}  # no individualGroups sub-columns present
        field = {
            "name": "individualGroups",
            "is_id": False,
            "is_required": False,
            "is_list": True,
            "is_scalar": False,
            "is_custom_type": True,
            "type": "IndividualGroup",
            "custom_type_fields": [],
        }
        mock_field_parser.build_custom_type_from_columns.return_value = None

        result = transformer.parse_input(row_dict, field, {})

        assert result is None

    def test_custom_type_error_propagates_from_build_custom_type(self, transformer, mock_field_parser):
        """ValueError from build_custom_type_from_columns propagates out of parse_input."""
        row_dict = {"length": "bad"}
        field = {
            "name": "individualGroups",
            "is_id": False,
            "is_required": False,
            "is_list": True,
            "is_scalar": False,
            "is_custom_type": True,
            "type": "IndividualGroup",
            "custom_type_fields": [],
        }
        mock_field_parser.build_custom_type_from_columns.side_effect = ValueError(
            "'length' could not be parsed as Float (value: 'bad')"
        )

        with pytest.raises(ValueError, match="'length'"):
            transformer.parse_input(row_dict, field, {})

    def test_custom_type_does_not_require_field_name_in_row_dict(self, transformer, mock_field_parser):
        """Custom type fields span multiple columns — the field name itself is never a row key."""
        # row_dict has sub-columns but NOT "individualGroups" as a key
        row_dict = {"length": "80.5", "stage": "ADULT"}
        field = {
            "name": "individualGroups",
            "is_id": False,
            "is_required": False,
            "is_list": True,
            "is_scalar": False,
            "is_custom_type": True,
            "type": "IndividualGroup",
            "custom_type_fields": [],
        }
        mock_field_parser.build_custom_type_from_columns.return_value = [{"length": 80.5, "stage": "ADULT"}]

        result = transformer.parse_input(row_dict, field, {})

        assert result == [{"length": 80.5, "stage": "ADULT"}]


class TestResolveForeignKey:
    """Test _resolve_foreign_key static method"""

    def test_resolves_fk_with_explicit_related_model(self, transformer):
        field = {
            "name": "authorId",
            "is_id": True,
            "is_required": True,
            "related_model": "Author",
        }
        fk_cache = {"Author": {"lookup": {"John Doe": "author-123"}}}

        result = transformer._resolve_foreign_key(field, "John Doe", fk_cache)

        assert result == "author-123"

    def test_infers_related_model_from_field_name(self, transformer):
        field = {"name": "authorId", "is_id": True, "is_required": True}
        fk_cache = {"Author": {"lookup": {"John Doe": "author-123"}}}

        result = transformer._resolve_foreign_key(field, "John Doe", fk_cache)

        assert result == "author-123"

    def test_raises_error_for_missing_optional_fk(self, transformer):
        field = {
            "name": "authorId",
            "is_id": True,
            "is_required": False,
            "related_model": "Author",
        }
        fk_cache = {"Author": {"lookup": {"Jane Doe": "author-456"}}}

        with pytest.raises(ValueError, match="'author': 'John Doe' does not exist"):
            transformer._resolve_foreign_key(field, "John Doe", fk_cache)

    def test_raises_error_for_missing_required_fk(self, transformer):
        field = {
            "name": "authorId",
            "is_id": True,
            "is_required": True,
            "related_model": "Author",
        }
        fk_cache = {"Author": {"lookup": {"Jane Doe": "author-456"}}}

        with pytest.raises(ValueError, match="'author': 'John Doe' does not exist"):
            transformer._resolve_foreign_key(field, "John Doe", fk_cache)

    def test_raises_error_for_missing_cache_optional_field(self, transformer):
        field = {
            "name": "authorId",
            "is_id": True,
            "is_required": False,
            "related_model": "Author",
        }
        fk_cache = {}

        with pytest.raises(ValueError, match="No pre-fetched data for 'author'"):
            transformer._resolve_foreign_key(field, "John Doe", fk_cache)

    def test_raises_error_for_missing_cache_required_field(self, transformer):
        field = {
            "name": "authorId",
            "is_id": True,
            "is_required": True,
            "related_model": "Author",
        }
        fk_cache = {}

        with pytest.raises(ValueError, match="No pre-fetched data for 'author'"):
            transformer._resolve_foreign_key(field, "John Doe", fk_cache)

    def test_converts_value_to_string_for_lookup(self, transformer):
        field = {
            "name": "categoryId",
            "is_id": True,
            "is_required": True,
            "related_model": "Category",
        }
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


class TestDefaultFkValues:
    """Test default_fk_values fallback for missing required FK fields."""

    def _fk_field(self, name="reporterId", related_model="Reporter"):
        return {
            "name": name,
            "is_id": True,
            "is_required": True,
            "related_model": related_model,
            "is_list": False,
            "is_scalar": False,
            "is_custom_type": False,
        }

    def test_uses_default_fk_id_when_fk_field_is_missing(self, mock_field_parser):
        transformer = DataTransformer(
            field_parser=mock_field_parser,
            default_fk_values={"Reporter": "default-reporter-id"},
        )
        result = transformer.parse_input({}, self._fk_field(), {})
        assert result == "default-reporter-id"

    def test_uses_default_fk_id_when_fk_field_is_nan(self, mock_field_parser):
        transformer = DataTransformer(
            field_parser=mock_field_parser,
            default_fk_values={"Reporter": "default-reporter-id"},
        )
        result = transformer.parse_input({"reporter": float("nan")}, self._fk_field(), {})
        assert result == "default-reporter-id"

    def test_raises_when_fk_missing_and_model_not_in_defaults(self, mock_field_parser):
        transformer = DataTransformer(
            field_parser=mock_field_parser,
            default_fk_values={"Photographer": "photographer-id"},
        )
        with pytest.raises(ValueError, match="Required field 'reporter' is missing"):
            transformer.parse_input({}, self._fk_field(), {})

    def test_raises_when_fk_missing_and_no_defaults_configured(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser)
        with pytest.raises(ValueError, match="Required field 'reporter' is missing"):
            transformer.parse_input({}, self._fk_field(), {})

    def test_infers_related_model_from_field_name_when_no_related_model_key(self, mock_field_parser):
        field = {
            "name": "photographerId",
            "is_id": True,
            "is_required": True,
            "is_list": False,
            "is_scalar": False,
            "is_custom_type": False,
        }
        transformer = DataTransformer(
            field_parser=mock_field_parser,
            default_fk_values={"Photographer": "default-photographer-id"},
        )
        result = transformer.parse_input({}, field, {})
        assert result == "default-photographer-id"

    def test_normal_fk_lookup_still_works_when_value_is_present(self, mock_field_parser):
        transformer = DataTransformer(
            field_parser=mock_field_parser,
            default_fk_values={"Reporter": "default-reporter-id"},
        )
        mock_field_parser.clean_input.return_value = "Jane"
        fk_cache = {"Reporter": {"lookup": {"Jane": "real-reporter-id"}}}
        result = transformer.parse_input({"reporter": "Jane"}, self._fk_field(), fk_cache)
        assert result == "real-reporter-id"


class TestFillUnknown:
    """Test fill_unknown fallback for missing required non-FK fields."""

    def _field(self, name, field_type, *, is_enum=False):
        return {
            "name": name,
            "is_id": False,
            "is_required": True,
            "is_list": False,
            "is_scalar": True,
            "is_custom_type": False,
            "is_enum": is_enum,
            "type": field_type,
        }

    def test_string_field_returns_unknown(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser, fill_unknown=True)
        result = transformer.parse_input({}, self._field("title", "String"), {})
        assert result == "UNKNOWN"

    def test_int_field_returns_zero(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser, fill_unknown=True)
        result = transformer.parse_input({}, self._field("count", "Int"), {})
        assert result == 0

    def test_float_field_returns_zero(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser, fill_unknown=True)
        result = transformer.parse_input({}, self._field("depth", "Float"), {})
        assert result == 0.0

    def test_boolean_field_returns_false(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser, fill_unknown=True)
        result = transformer.parse_input({}, self._field("active", "Boolean"), {})
        assert result is False

    def test_aws_date_field_returns_epoch(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser, fill_unknown=True)
        result = transformer.parse_input({}, self._field("date", "AWSDate"), {})
        assert result == "1970-01-01"

    def test_aws_datetime_field_returns_epoch(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser, fill_unknown=True)
        result = transformer.parse_input({}, self._field("createdAt", "AWSDateTime"), {})
        assert result == "1970-01-01T00:00:00.000Z"

    def test_enum_field_returns_unknown(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser, fill_unknown=True)
        result = transformer.parse_input({}, self._field("status", "Status", is_enum=True), {})
        assert result == "UNKNOWN"

    def test_raises_when_fill_unknown_is_false(self, transformer):
        with pytest.raises(ValueError, match="Required field 'title' is missing"):
            transformer.parse_input({}, self._field("title", "String"), {})

    def test_fk_field_still_raises_even_when_fill_unknown_is_true(self, mock_field_parser):
        transformer = DataTransformer(field_parser=mock_field_parser, fill_unknown=True)
        fk_field = {
            "name": "reporterId",
            "is_id": True,
            "is_required": True,
            "related_model": "Reporter",
            "is_list": False,
            "is_scalar": False,
            "is_custom_type": False,
        }
        with pytest.raises(ValueError, match="Required field 'reporter' is missing"):
            transformer.parse_input({}, fk_field, {})
