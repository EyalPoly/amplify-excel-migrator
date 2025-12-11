"""Tests for RecordValidator class"""

import pytest
import pandas as pd
from amplify_excel_migrator.data.validator import RecordValidator


class TestValidateRequiredFields:
    """Test validate_required_fields static method"""

    def test_returns_empty_list_when_all_required_fields_present(self):
        row_dict = {"name": "John", "age": 25}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True},
                {"name": "age", "is_id": False, "is_required": True},
            ]
        }

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert errors == []

    def test_returns_error_for_missing_required_field(self):
        row_dict = {"name": "John"}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True},
                {"name": "age", "is_id": False, "is_required": True},
            ]
        }

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert len(errors) == 1
        assert "Required field 'age' is missing" in errors[0]

    def test_returns_error_for_nan_value_in_required_field(self):
        row_dict = {"name": "John", "age": float("nan")}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True},
                {"name": "age", "is_id": False, "is_required": True},
            ]
        }

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert len(errors) == 1
        assert "Required field 'age' is missing" in errors[0]

    def test_ignores_optional_fields(self):
        row_dict = {"name": "John"}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True},
                {"name": "age", "is_id": False, "is_required": False},
                {"name": "email", "is_id": False, "is_required": False},
            ]
        }

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert errors == []

    def test_strips_id_suffix_from_foreign_key_fields(self):
        row_dict = {"name": "John"}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True},
                {"name": "authorId", "is_id": True, "is_required": True},
            ]
        }

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert len(errors) == 1
        assert "Required field 'author' is missing" in errors[0]

    def test_returns_multiple_errors_for_multiple_missing_fields(self):
        row_dict = {}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True},
                {"name": "age", "is_id": False, "is_required": True},
                {"name": "email", "is_id": False, "is_required": True},
            ]
        }

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert len(errors) == 3
        assert any("name" in error for error in errors)
        assert any("age" in error for error in errors)
        assert any("email" in error for error in errors)

    def test_handles_empty_row_dict(self):
        row_dict = {}
        parsed_model = {"fields": [{"name": "name", "is_id": False, "is_required": True}]}

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert len(errors) == 1

    def test_handles_empty_fields_list(self):
        row_dict = {"name": "John"}
        parsed_model = {"fields": []}

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert errors == []

    def test_validates_only_required_fields_in_mixed_model(self):
        row_dict = {"name": "John", "age": 25}
        parsed_model = {
            "fields": [
                {"name": "name", "is_id": False, "is_required": True},
                {"name": "age", "is_id": False, "is_required": False},
                {"name": "email", "is_id": False, "is_required": True},
                {"name": "phone", "is_id": False, "is_required": False},
            ]
        }

        errors = RecordValidator.validate_required_fields(row_dict, parsed_model)

        assert len(errors) == 1
        assert "email" in errors[0]


class TestValidateForeignKey:
    """Test validate_foreign_key static method"""

    def test_returns_empty_list_when_fk_exists_in_cache(self):
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {"John Doe": "author-123"}}}

        errors = RecordValidator.validate_foreign_key(field, "John Doe", fk_cache)

        assert errors == []

    def test_returns_error_when_required_fk_not_in_cache(self):
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {"Jane Doe": "author-456"}}}

        errors = RecordValidator.validate_foreign_key(field, "John Doe", fk_cache)

        assert len(errors) == 1
        assert "Author: John Doe does not exist" in errors[0]

    def test_returns_empty_list_when_optional_fk_not_in_cache(self):
        field = {"name": "authorId", "is_id": True, "is_required": False, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {"Jane Doe": "author-456"}}}

        errors = RecordValidator.validate_foreign_key(field, "John Doe", fk_cache)

        assert errors == []

    def test_returns_error_when_related_model_not_in_cache_required(self):
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {}

        errors = RecordValidator.validate_foreign_key(field, "John Doe", fk_cache)

        assert len(errors) == 1
        assert "No pre-fetched data for required foreign key Author" in errors[0]

    def test_returns_empty_list_when_related_model_not_in_cache_optional(self):
        field = {"name": "authorId", "is_id": True, "is_required": False, "related_model": "Author"}
        fk_cache = {}

        errors = RecordValidator.validate_foreign_key(field, "John Doe", fk_cache)

        assert errors == []

    def test_infers_related_model_from_field_name(self):
        field = {"name": "authorId", "is_id": True, "is_required": True}
        fk_cache = {"Author": {"lookup": {"John Doe": "author-123"}}}

        errors = RecordValidator.validate_foreign_key(field, "John Doe", fk_cache)

        assert errors == []

    def test_infers_related_model_with_correct_capitalization(self):
        field = {"name": "categoryId", "is_id": True, "is_required": True}
        fk_cache = {"Category": {"lookup": {"Books": "cat-123"}}}

        errors = RecordValidator.validate_foreign_key(field, "Books", fk_cache)

        assert errors == []

    def test_converts_value_to_string_for_lookup(self):
        field = {"name": "categoryId", "is_id": True, "is_required": True, "related_model": "Category"}
        fk_cache = {"Category": {"lookup": {"123": "cat-abc"}}}

        errors = RecordValidator.validate_foreign_key(field, 123, fk_cache)

        assert errors == []

    def test_handles_numeric_fk_values(self):
        field = {"name": "userId", "is_id": True, "is_required": True, "related_model": "User"}
        fk_cache = {"User": {"lookup": {"42": "user-xyz"}}}

        errors = RecordValidator.validate_foreign_key(field, 42, fk_cache)

        assert errors == []

    def test_validates_with_explicit_related_model(self):
        field = {"name": "createdById", "is_id": True, "is_required": True, "related_model": "User"}
        fk_cache = {"User": {"lookup": {"admin": "user-1"}}}

        errors = RecordValidator.validate_foreign_key(field, "admin", fk_cache)

        assert errors == []

    def test_error_message_includes_model_and_value(self):
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {}}}

        errors = RecordValidator.validate_foreign_key(field, "Unknown Author", fk_cache)

        assert len(errors) == 1
        assert "Author" in errors[0]
        assert "Unknown Author" in errors[0]

    def test_handles_empty_lookup_dict(self):
        field = {"name": "authorId", "is_id": True, "is_required": True, "related_model": "Author"}
        fk_cache = {"Author": {"lookup": {}}}

        errors = RecordValidator.validate_foreign_key(field, "John Doe", fk_cache)

        assert len(errors) == 1
        assert "does not exist" in errors[0]
