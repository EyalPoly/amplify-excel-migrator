"""Tests for SchemaIntrospector class"""

import pytest
from unittest.mock import MagicMock, patch
from amplify_excel_migrator.schema.introspector import SchemaIntrospector


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def introspector(mock_client):
    return SchemaIntrospector(client=mock_client)


class TestSchemaIntrospectorInit:
    """Test SchemaIntrospector initialization"""

    def test_initializes_with_client(self, mock_client):
        introspector = SchemaIntrospector(client=mock_client)
        assert introspector.client == mock_client


class TestGetModelStructure:
    """Test get_model_structure method"""

    @patch("amplify_excel_migrator.schema.introspector.QueryBuilder")
    def test_returns_type_structure_from_response(self, mock_query_builder, introspector, mock_client):
        mock_query_builder.build_introspection_query.return_value = "query { __type }"
        mock_client.request.return_value = {"data": {"__type": {"name": "User", "fields": []}}}

        result = introspector.get_model_structure("User")

        assert result == {"name": "User", "fields": []}
        mock_query_builder.build_introspection_query.assert_called_once_with("User")
        mock_client.request.assert_called_once_with("query { __type }")

    @patch("amplify_excel_migrator.schema.introspector.QueryBuilder")
    def test_returns_empty_dict_when_no_type_in_response(self, mock_query_builder, introspector, mock_client):
        mock_query_builder.build_introspection_query.return_value = "query { __type }"
        mock_client.request.return_value = {"data": {}}

        result = introspector.get_model_structure("User")

        assert result == {}

    @patch("amplify_excel_migrator.schema.introspector.QueryBuilder")
    def test_returns_empty_dict_when_no_data_in_response(self, mock_query_builder, introspector, mock_client):
        mock_query_builder.build_introspection_query.return_value = "query { __type }"
        mock_client.request.return_value = {}

        result = introspector.get_model_structure("User")

        assert result == {}

    @patch("amplify_excel_migrator.schema.introspector.QueryBuilder")
    def test_returns_empty_dict_when_response_is_none(self, mock_query_builder, introspector, mock_client):
        mock_query_builder.build_introspection_query.return_value = "query { __type }"
        mock_client.request.return_value = None

        result = introspector.get_model_structure("User")

        assert result == {}


class TestGetPrimaryFieldName:
    """Test get_primary_field_name method"""

    def test_returns_secondary_index_if_exists(self, introspector):
        introspector._get_secondary_index = MagicMock(return_value="email")
        parsed_model = {
            "fields": [
                {
                    "name": "email",
                    "type": "String",
                    "is_required": True,
                    "is_scalar": True,
                }
            ]
        }

        field_name, is_secondary, field_type = introspector.get_primary_field_name("User", parsed_model)

        assert field_name == "email"
        assert is_secondary is True
        assert field_type == "String"

    def test_returns_first_required_scalar_field_when_no_secondary_index(self, introspector):
        introspector._get_secondary_index = MagicMock(return_value="")
        parsed_model = {
            "fields": [
                {"name": "id", "is_required": True, "is_scalar": True, "type": "ID"},
                {
                    "name": "email",
                    "is_required": True,
                    "is_scalar": True,
                    "type": "String",
                },
            ]
        }

        field_name, is_secondary, field_type = introspector.get_primary_field_name("User", parsed_model)

        assert field_name == "email"
        assert is_secondary is False
        assert field_type == "String"

    def test_skips_id_field(self, introspector):
        introspector._get_secondary_index = MagicMock(return_value="")
        parsed_model = {
            "fields": [
                {"name": "id", "is_required": True, "is_scalar": True, "type": "ID"},
                {
                    "name": "username",
                    "is_required": True,
                    "is_scalar": True,
                    "type": "String",
                },
            ]
        }

        field_name, is_secondary, field_type = introspector.get_primary_field_name("User", parsed_model)

        assert field_name == "username"

    def test_returns_empty_string_when_no_suitable_field(self, introspector):
        introspector._get_secondary_index = MagicMock(return_value="")
        parsed_model = {"fields": [{"name": "id", "is_required": True, "is_scalar": True, "type": "ID"}]}

        field_name, is_secondary, field_type = introspector.get_primary_field_name("User", parsed_model)

        assert field_name == ""
        assert is_secondary is False
        assert field_type == "String"

    def test_uses_field_type_from_secondary_index_field(self, introspector):
        introspector._get_secondary_index = MagicMock(return_value="age")
        parsed_model = {"fields": [{"name": "age", "type": "Int", "is_required": True, "is_scalar": True}]}

        field_name, is_secondary, field_type = introspector.get_primary_field_name("User", parsed_model)

        assert field_type == "Int"

    def test_defaults_to_string_type_when_secondary_index_field_not_found(self, introspector):
        introspector._get_secondary_index = MagicMock(return_value="email")
        parsed_model = {"fields": [{"name": "name", "type": "String", "is_required": True, "is_scalar": True}]}

        field_name, is_secondary, field_type = introspector.get_primary_field_name("User", parsed_model)

        assert field_type == "String"


class TestGetSecondaryIndex:
    """Test _get_secondary_index method"""

    def test_returns_secondary_index_field_name(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "getUserByEmail", "args": []},
                    {"name": "listUsers", "args": []},
                ]
            }
        )

        result = introspector._get_secondary_index("User")

        assert result == "email"

    def test_returns_empty_string_when_no_secondary_index(self, introspector):
        introspector.get_model_structure = MagicMock(return_value={"fields": [{"name": "listUsers", "args": []}]})

        result = introspector._get_secondary_index("User")

        assert result == ""

    def test_returns_empty_string_when_query_structure_is_empty(self, introspector):
        introspector.get_model_structure = MagicMock(return_value={})

        result = introspector._get_secondary_index("User")

        assert result == ""

    def test_handles_camel_case_field_names(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "getProductBySku", "args": []},
                ]
            }
        )

        result = introspector._get_secondary_index("Product")

        assert result == "sku"

    def test_handles_multi_word_field_names(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "getOrderByOrderNumber", "args": []},
                ]
            }
        )

        result = introspector._get_secondary_index("Order")

        assert result == "orderNumber"

    def test_returns_first_matching_secondary_index(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "getUserByEmail", "args": []},
                    {"name": "getUserByUsername", "args": []},
                ]
            }
        )

        result = introspector._get_secondary_index("User")

        assert result == "email"


class TestGetListQueryName:
    """Test get_list_query_name method"""

    def test_returns_simple_list_query_name(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "listUsers", "args": []},
                ]
            }
        )

        result = introspector.get_list_query_name("User")

        assert result == "listUsers"

    def test_returns_plural_list_query_name(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "listCategories", "args": []},
                ]
            }
        )

        result = introspector.get_list_query_name("Category")

        assert result == "listCategories"

    def test_handles_compound_model_names(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "listOrderItems", "args": []},
                ]
            }
        )

        result = introspector.get_list_query_name("OrderItem")

        assert result == "listOrderItems"

    def test_returns_none_when_no_matching_query(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "getUser", "args": []},
                ]
            }
        )

        result = introspector.get_list_query_name("User")

        assert result is None

    def test_returns_default_when_query_structure_is_empty(self, introspector):
        introspector.get_model_structure = MagicMock(return_value={})

        result = introspector.get_list_query_name("User")

        assert result == "listUsers"

    def test_skips_queries_with_by_in_name(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "listUsersByEmail", "args": []},
                    {"name": "listUsers", "args": []},
                ]
            }
        )

        result = introspector.get_list_query_name("User")

        assert result == "listUsers"

    def test_tries_multiple_plural_forms(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "listPeople", "args": []},
                ]
            }
        )

        result = introspector.get_list_query_name("Person")

        assert result == "listPeople"

    def test_handles_multi_capital_model_names(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "listAPIKeys", "args": []},
                ]
            }
        )

        result = introspector.get_list_query_name("APIKey")

        assert result == "listAPIKeys"

    def test_returns_first_matching_candidate(self, introspector):
        introspector.get_model_structure = MagicMock(
            return_value={
                "fields": [
                    {"name": "listUser", "args": []},
                    {"name": "listUsers", "args": []},
                ]
            }
        )

        result = introspector.get_list_query_name("User")

        assert result in ["listUser", "listUsers"]
