"""Tests for FieldParser class"""

import pytest
from amplify_excel_migrator.schema import FieldParser


class TestExtractRelationshipInfo:
    """Test _extract_relationship_info method"""

    def test_extracts_belongsto_relationship(self):
        """Test extracting belongsTo relationship info"""
        parser = FieldParser()

        field = {"name": "photographer", "type": {"kind": "OBJECT", "name": "Reporter", "ofType": None}, "args": []}

        result = parser._extract_relationship_info(field)

        assert result is not None
        assert result["target_model"] == "Reporter"
        assert result["foreign_key"] == "photographerId"

    def test_extracts_with_non_null_wrapper(self):
        """Test extracting relationship with NON_NULL wrapper"""
        parser = FieldParser()

        field = {
            "name": "author",
            "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "OBJECT", "name": "User", "ofType": None}},
            "args": [],
        }

        result = parser._extract_relationship_info(field)

        assert result is not None
        assert result["target_model"] == "User"
        assert result["foreign_key"] == "authorId"

    def test_extracts_from_all_fields(self):
        """Test that _extract_relationship_info filters out Connection types"""
        parser = FieldParser()

        # Connection types should be filtered out by _extract_relationship_info
        field = {"name": "posts", "type": {"kind": "OBJECT", "name": "ModelPostConnection", "ofType": None}, "args": []}

        result = parser._extract_relationship_info(field)

        # Connection types are filtered, so result should be None
        assert result is None


class TestParseModelStructure:
    """Test parse_model_structure method with belongsTo relationships"""

    def test_raises_value_error_on_empty_introspection(self):
        """Test that ValueError is raised when introspection result is empty"""
        parser = FieldParser()

        with pytest.raises(ValueError, match="Introspection result cannot be empty"):
            parser.parse_model_structure(None)

        with pytest.raises(ValueError, match="Introspection result cannot be empty"):
            parser.parse_model_structure({})

    def test_includes_all_fields_except_metadata(self):
        """Test that all fields except metadata and relationship objects are included"""
        parser = FieldParser()

        introspection_result = {
            "name": "Story",
            "kind": "OBJECT",
            "description": None,
            "fields": [
                {
                    "name": "id",
                    "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID"}},
                    "description": None,
                },
                {
                    "name": "photographerId",
                    "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID"}},
                    "description": None,
                },
                {
                    "name": "photographer",
                    "type": {"kind": "OBJECT", "name": "Reporter", "ofType": None},
                    "description": None,
                    "args": [],
                },
                {"name": "title", "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "description": None},
            ],
        }

        result = parser.parse_model_structure(introspection_result)

        field_names = [f["name"] for f in result["fields"]]

        # Should include all fields except metadata (id) and relationship objects (photographer)
        assert "photographerId" in field_names
        assert "photographer" not in field_names  # Relationship OBJECT fields are filtered
        assert "title" in field_names
        assert "id" not in field_names  # metadata filtered

    def test_adds_related_model_to_foreign_key(self):
        """Test that foreign key fields get related_model property"""
        parser = FieldParser()

        introspection_result = {
            "name": "Story",
            "kind": "OBJECT",
            "description": None,
            "fields": [
                {
                    "name": "photographerId",
                    "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID"}},
                    "description": None,
                },
                {
                    "name": "photographer",
                    "type": {"kind": "OBJECT", "name": "Reporter", "ofType": None},
                    "description": None,
                    "args": [],
                },
            ],
        }

        result = parser.parse_model_structure(introspection_result)

        photographer_id_field = next(f for f in result["fields"] if f["name"] == "photographerId")

        assert "related_model" in photographer_id_field
        assert photographer_id_field["related_model"] == "Reporter"

    def test_handles_multiple_relationships(self):
        """Test handling multiple belongsTo relationships"""
        parser = FieldParser()

        introspection_result = {
            "name": "Story",
            "kind": "OBJECT",
            "description": None,
            "fields": [
                {"name": "authorId", "type": {"kind": "SCALAR", "name": "ID", "ofType": None}, "description": None},
                {
                    "name": "author",
                    "type": {"kind": "OBJECT", "name": "User", "ofType": None},
                    "description": None,
                    "args": [],
                },
                {"name": "editorId", "type": {"kind": "SCALAR", "name": "ID", "ofType": None}, "description": None},
                {
                    "name": "editor",
                    "type": {"kind": "OBJECT", "name": "User", "ofType": None},
                    "description": None,
                    "args": [],
                },
            ],
        }

        result = parser.parse_model_structure(introspection_result)

        field_names = [f["name"] for f in result["fields"]]

        # ID fields are included, relationship objects are filtered
        assert "authorId" in field_names
        assert "author" not in field_names  # Relationship objects are filtered
        assert "editorId" in field_names
        assert "editor" not in field_names  # Relationship objects are filtered

        # Check related_model properties on ID fields
        author_id_field = next(f for f in result["fields"] if f["name"] == "authorId")
        editor_id_field = next(f for f in result["fields"] if f["name"] == "editorId")

        assert author_id_field["related_model"] == "User"
        assert editor_id_field["related_model"] == "User"

    def test_preserves_custom_types(self):
        """Test that custom type OBJECT fields are preserved (not filtered)"""
        parser = FieldParser()

        introspection_result = {
            "name": "User",
            "kind": "OBJECT",
            "description": None,
            "fields": [
                {"name": "name", "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "description": None},
                {
                    "name": "addresses",
                    "type": {
                        "kind": "LIST",
                        "name": None,
                        "ofType": {"kind": "OBJECT", "name": "Address", "ofType": None},
                    },
                    "description": None,
                },
            ],
        }

        result = parser.parse_model_structure(introspection_result)

        field_names = [f["name"] for f in result["fields"]]

        # Custom type list should be preserved
        assert "addresses" in field_names
        addresses_field = next(f for f in result["fields"] if f["name"] == "addresses")
        assert addresses_field["is_custom_type"] is True
        assert addresses_field["is_list"] is True


class TestParseFieldWithRelationships:
    """Test _parse_field method behavior with relationship fields"""

    def test_marks_custom_type_correctly(self):
        """Test that custom type fields are marked correctly"""
        parser = FieldParser()

        field = {"name": "address", "type": {"kind": "OBJECT", "name": "Address", "ofType": None}, "description": None}

        result = parser._parse_field(field)

        assert result["is_custom_type"] is True
        assert result["type"] == "Address"

    def test_skips_connections(self):
        """Test that Connection types are skipped"""
        parser = FieldParser()

        field = {
            "name": "posts",
            "type": {"kind": "OBJECT", "name": "ModelPostConnection", "ofType": None},
            "description": None,
        }

        result = parser._parse_field(field)

        assert result == {}

    def test_skips_metadata_fields(self):
        """Test that metadata fields are skipped"""
        parser = FieldParser()

        for field_name in ["id", "createdAt", "updatedAt", "owner"]:
            field = {
                "name": field_name,
                "type": {"kind": "SCALAR", "name": "String", "ofType": None},
                "description": None,
            }

            result = parser._parse_field(field)

            assert result == {}, f"Should skip metadata field: {field_name}"


class TestCleanInput:
    """Test clean_input static method for Unicode character cleaning"""

    def test_strips_whitespace(self):
        """Test that leading and trailing whitespace is stripped"""
        parser = FieldParser()

        assert parser.clean_input("  test  ") == "test"
        assert parser.clean_input("\t test \n") == "test"
        assert parser.clean_input("   ") == ""

    def test_removes_unicode_control_characters(self):
        """Test that Unicode control characters (Cc) are removed"""
        parser = FieldParser()

        # NULL character (U+0000)
        assert parser.clean_input("test\x00value") == "testvalue"
        # BELL character (U+0007)
        assert parser.clean_input("test\x07value") == "testvalue"
        # BACKSPACE character (U+0008)
        assert parser.clean_input("test\x08value") == "testvalue"

    def test_removes_unicode_format_characters(self):
        """Test that Unicode format characters (Cf) are removed"""
        parser = FieldParser()

        # Zero-width space (U+200B)
        assert parser.clean_input("test\u200bvalue") == "testvalue"
        # Zero-width non-joiner (U+200C)
        assert parser.clean_input("test\u200cvalue") == "testvalue"
        # Soft hyphen (U+00AD)
        assert parser.clean_input("test\u00advalue") == "testvalue"
        # Left-to-right mark (U+200E)
        assert parser.clean_input("test\u200evalue") == "testvalue"

    def test_preserves_newline_tab_carriage_return(self):
        """Test that newline, tab, and carriage return are preserved"""
        parser = FieldParser()

        # Newline (U+000A)
        assert parser.clean_input("test\nvalue") == "test\nvalue"
        # Tab (U+0009)
        assert parser.clean_input("test\tvalue") == "test\tvalue"
        # Carriage return (U+000D)
        assert parser.clean_input("test\rvalue") == "test\rvalue"

    def test_handles_non_string_input(self):
        """Test that non-string values are returned unchanged"""
        parser = FieldParser()

        assert parser.clean_input(123) == 123
        assert parser.clean_input(123.45) == 123.45
        assert parser.clean_input(None) is None
        assert parser.clean_input(True) is True
        assert parser.clean_input([1, 2, 3]) == [1, 2, 3]

    def test_handles_empty_string(self):
        """Test that empty string is handled correctly"""
        parser = FieldParser()

        assert parser.clean_input("") == ""

    def test_preserves_valid_unicode_characters(self):
        """Test that valid Unicode characters are preserved"""
        parser = FieldParser()

        # Emoji
        assert parser.clean_input("test 😀 value") == "test 😀 value"
        # Hebrew
        assert parser.clean_input("שלום") == "שלום"
        # Chinese
        assert parser.clean_input("你好") == "你好"
        # Arabic
        assert parser.clean_input("مرحبا") == "مرحبا"

    def test_complex_string_with_multiple_control_chars(self):
        """Test cleaning string with multiple control characters"""
        parser = FieldParser()

        # Mix of control characters that should be removed and preserved
        input_str = "  test\x00\u200b\nvalue\t\u00adend  "
        expected = "test\nvalue\tend"
        assert parser.clean_input(input_str) == expected


class TestIntegrationBelongsToFlow:
    """Integration tests for full belongsTo relationship flow"""

    def test_full_story_model_with_photographer(self):
        """Test complete Story model with photographer belongsTo relationship"""
        parser = FieldParser()

        # Simulate real GraphQL introspection response
        introspection_result = {
            "data": {
                "__type": {
                    "name": "Story",
                    "kind": "OBJECT",
                    "description": None,
                    "fields": [
                        {
                            "name": "id",
                            "type": {
                                "kind": "NON_NULL",
                                "name": None,
                                "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None},
                            },
                            "description": None,
                        },
                        {
                            "name": "title",
                            "type": {
                                "kind": "NON_NULL",
                                "name": None,
                                "ofType": {"kind": "SCALAR", "name": "String", "ofType": None},
                            },
                            "description": None,
                        },
                        {
                            "name": "photographerId",
                            "type": {
                                "kind": "NON_NULL",
                                "name": None,
                                "ofType": {"kind": "SCALAR", "name": "ID", "ofType": None},
                            },
                            "description": None,
                        },
                        {
                            "name": "photographer",
                            "type": {"kind": "OBJECT", "name": "Reporter", "ofType": None},
                            "description": None,
                            "args": [],
                        },
                        {
                            "name": "createdAt",
                            "type": {
                                "kind": "NON_NULL",
                                "name": None,
                                "ofType": {"kind": "SCALAR", "name": "AWSDateTime", "ofType": None},
                            },
                            "description": None,
                        },
                        {
                            "name": "updatedAt",
                            "type": {
                                "kind": "NON_NULL",
                                "name": None,
                                "ofType": {"kind": "SCALAR", "name": "AWSDateTime", "ofType": None},
                            },
                            "description": None,
                        },
                    ],
                }
            }
        }

        result = parser.parse_model_structure(introspection_result)

        # Verify model info
        assert result["name"] == "Story"
        assert result["kind"] == "OBJECT"

        # Get field names
        field_names = [f["name"] for f in result["fields"]]

        # Should include regular fields and foreign key, but not relationship object fields
        assert "title" in field_names
        assert "photographerId" in field_names
        assert "photographer" not in field_names  # Relationship OBJECT fields are filtered

        # Should NOT include metadata fields
        assert "id" not in field_names
        assert "createdAt" not in field_names
        assert "updatedAt" not in field_names

        # Verify photographerId has related_model
        photographer_id_field = next(f for f in result["fields"] if f["name"] == "photographerId")
        assert photographer_id_field["is_id"] is True
        assert photographer_id_field["is_required"] is True
        assert photographer_id_field["related_model"] == "Reporter"
        assert photographer_id_field["type"] == "ID"

    def test_model_without_relationships(self):
        """Test model without any belongsTo relationships"""
        parser = FieldParser()

        introspection_result = {
            "name": "User",
            "kind": "OBJECT",
            "description": None,
            "fields": [
                {
                    "name": "id",
                    "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "ID"}},
                    "description": None,
                },
                {
                    "name": "name",
                    "type": {"kind": "NON_NULL", "name": None, "ofType": {"kind": "SCALAR", "name": "String"}},
                    "description": None,
                },
                {"name": "email", "type": {"kind": "SCALAR", "name": "String", "ofType": None}, "description": None},
            ],
        }

        result = parser.parse_model_structure(introspection_result)

        field_names = [f["name"] for f in result["fields"]]

        # Should have regular fields (no id as it's metadata)
        assert "name" in field_names
        assert "email" in field_names
        assert "id" not in field_names

        # No fields should have related_model
        for field in result["fields"]:
            assert "related_model" not in field


class TestParseScalarArray:
    """Test parse_scalar_array method for handling array fields"""

    def test_parses_json_array_format(self):
        """Test parsing JSON array format"""
        parser = FieldParser()
        field = {"name": "urls", "type": "AWSURL", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(
            field, "urls", '["https://url1.com", "https://url2.com", "https://url3.com"]'
        )

        assert result == ["https://url1.com", "https://url2.com", "https://url3.com"]

    def test_parses_semicolon_separated(self):
        """Test parsing semicolon-separated values"""
        parser = FieldParser()
        field = {"name": "urls", "type": "AWSURL", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "urls", "https://url1.com; https://url2.com; https://url3.com")

        assert result == ["https://url1.com", "https://url2.com", "https://url3.com"]

    def test_parses_comma_separated(self):
        """Test parsing comma-separated values"""
        parser = FieldParser()
        field = {"name": "tags", "type": "String", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "tags", "tag1, tag2, tag3")

        assert result == ["tag1", "tag2", "tag3"]

    def test_parses_space_separated(self):
        """Test parsing space-separated values"""
        parser = FieldParser()
        field = {"name": "tags", "type": "String", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "tags", "tag1 tag2 tag3")

        assert result == ["tag1", "tag2", "tag3"]

    def test_parses_int_array(self):
        """Test parsing integer array"""
        parser = FieldParser()
        field = {"name": "numbers", "type": "Int", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "numbers", "1, 2, 3, 4, 5")

        assert result == [1, 2, 3, 4, 5]

    def test_parses_float_array(self):
        """Test parsing float array"""
        parser = FieldParser()
        field = {"name": "scores", "type": "Float", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "scores", "1.5, 2.7, 3.9")

        assert result == [1.5, 2.7, 3.9]

    def test_parses_boolean_array(self):
        """Test parsing boolean array"""
        parser = FieldParser()
        field = {"name": "flags", "type": "Boolean", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "flags", "true, false, yes, no")

        assert result == [True, False, True, False]

    def test_returns_none_for_empty_value(self):
        """Test that empty values return None"""
        parser = FieldParser()
        field = {"name": "tags", "type": "String", "is_list": True, "is_scalar": True}

        assert parser.parse_scalar_array(field, "tags", "") is None
        assert parser.parse_scalar_array(field, "tags", None) is None
        import pandas as pd

        assert parser.parse_scalar_array(field, "tags", pd.NA) is None

    def test_handles_single_value_as_array(self):
        """Test that single value is returned as single-item array"""
        parser = FieldParser()
        field = {"name": "tags", "type": "String", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "tags", "single-value")

        assert result == ["single-value"]

    def test_skips_empty_elements(self):
        """Test that empty elements are skipped"""
        parser = FieldParser()
        field = {"name": "tags", "type": "String", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "tags", "tag1, , tag3, , tag5")

        assert result == ["tag1", "tag3", "tag5"]

    def test_cleans_whitespace_from_elements(self):
        """Test that whitespace is cleaned from elements"""
        parser = FieldParser()
        field = {"name": "tags", "type": "String", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "tags", "  tag1  ,  tag2  ,  tag3  ")

        assert result == ["tag1", "tag2", "tag3"]

    def test_handles_mixed_separators_prioritizes_semicolon(self):
        """Test that semicolon takes priority over comma and space"""
        parser = FieldParser()
        field = {"name": "values", "type": "String", "is_list": True, "is_scalar": True}

        # When semicolon is present, use it (even if commas exist)
        result = parser.parse_scalar_array(field, "values", "val1, val2; val3, val4")

        assert result == ["val1, val2", "val3, val4"]

    def test_handles_json_array_with_numbers(self):
        """Test JSON array with numbers"""
        parser = FieldParser()
        field = {"name": "numbers", "type": "Int", "is_list": True, "is_scalar": True}

        result = parser.parse_scalar_array(field, "numbers", "[1, 2, 3, 4, 5]")

        assert result == [1, 2, 3, 4, 5]

    def test_handles_invalid_type_conversion_gracefully(self):
        """Test that invalid type conversions are skipped with warning"""
        parser = FieldParser()
        field = {"name": "numbers", "type": "Int", "is_list": True, "is_scalar": True}

        # Mix of valid and invalid integers
        result = parser.parse_scalar_array(field, "numbers", "1, abc, 3, xyz, 5")

        # Only valid numbers should be included
        assert result == [1, 3, 5]

    def test_handles_enum_array(self):
        """Test parsing enum array"""
        parser = FieldParser()
        field = {"name": "statuses", "type": "Status", "is_list": True, "is_scalar": True, "is_enum": True}

        result = parser.parse_scalar_array(field, "statuses", "active, pending, completed")

        assert result == ["ACTIVE", "PENDING", "COMPLETED"]
