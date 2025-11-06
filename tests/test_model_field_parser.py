"""Tests for ModelFieldParser class"""

import pytest
from model_field_parser import ModelFieldParser


class TestExtractRelationshipInfo:
    """Test _extract_relationship_info method"""

    def test_extracts_belongsto_relationship(self):
        """Test extracting belongsTo relationship info"""
        parser = ModelFieldParser()

        field = {"name": "photographer", "type": {"kind": "OBJECT", "name": "Reporter", "ofType": None}, "args": []}

        result = parser._extract_relationship_info(field)

        assert result is not None
        assert result["target_model"] == "Reporter"
        assert result["foreign_key"] == "photographerId"

    def test_extracts_with_non_null_wrapper(self):
        """Test extracting relationship with NON_NULL wrapper"""
        parser = ModelFieldParser()

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
        parser = ModelFieldParser()

        # Connection types should be filtered out by _extract_relationship_info
        field = {"name": "posts", "type": {"kind": "OBJECT", "name": "ModelPostConnection", "ofType": None}, "args": []}

        result = parser._extract_relationship_info(field)

        # Connection types are filtered, so result should be None
        assert result is None


class TestParseModelStructure:
    """Test parse_model_structure method with belongsTo relationships"""

    def test_includes_all_fields_except_metadata(self):
        """Test that all fields except metadata and relationship objects are included"""
        parser = ModelFieldParser()

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
        parser = ModelFieldParser()

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
        parser = ModelFieldParser()

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
        parser = ModelFieldParser()

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
        parser = ModelFieldParser()

        field = {"name": "address", "type": {"kind": "OBJECT", "name": "Address", "ofType": None}, "description": None}

        result = parser._parse_field(field)

        assert result["is_custom_type"] is True
        assert result["type"] == "Address"

    def test_skips_connections(self):
        """Test that Connection types are skipped"""
        parser = ModelFieldParser()

        field = {
            "name": "posts",
            "type": {"kind": "OBJECT", "name": "ModelPostConnection", "ofType": None},
            "description": None,
        }

        result = parser._parse_field(field)

        assert result == {}

    def test_skips_metadata_fields(self):
        """Test that metadata fields are skipped"""
        parser = ModelFieldParser()

        for field_name in ["id", "createdAt", "updatedAt", "owner"]:
            field = {
                "name": field_name,
                "type": {"kind": "SCALAR", "name": "String", "ofType": None},
                "description": None,
            }

            result = parser._parse_field(field)

            assert result == {}, f"Should skip metadata field: {field_name}"


class TestIntegrationBelongsToFlow:
    """Integration tests for full belongsTo relationship flow"""

    def test_full_story_model_with_photographer(self):
        """Test complete Story model with photographer belongsTo relationship"""
        parser = ModelFieldParser()

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
        parser = ModelFieldParser()

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
