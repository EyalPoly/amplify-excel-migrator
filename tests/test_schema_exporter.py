"""Tests for SchemaExporter class"""

import pytest
from unittest.mock import MagicMock, mock_open, patch
from amplify_excel_migrator.schema.schema_exporter import SchemaExporter


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_field_parser():
    parser = MagicMock()
    parser.metadata_fields = ["id", "createdAt", "updatedAt", "owner"]
    return parser


@pytest.fixture
def exporter(mock_client, mock_field_parser):
    return SchemaExporter(client=mock_client, field_parser=mock_field_parser)


class TestSchemaExporterInit:
    """Test SchemaExporter initialization"""

    def test_initializes_with_client_and_field_parser(self, mock_client, mock_field_parser):
        exporter = SchemaExporter(client=mock_client, field_parser=mock_field_parser)
        assert exporter.client == mock_client
        assert exporter.field_parser == mock_field_parser


class TestExportToMarkdown:
    """Test export_to_markdown method"""

    @patch("builtins.open", new_callable=mock_open)
    def test_exports_to_specified_path(self, mock_file, exporter):
        exporter._discover_models = MagicMock(return_value=["User"])
        exporter._generate_markdown = MagicMock(return_value="# Schema")

        exporter.export_to_markdown("output.md")

        mock_file.assert_called_once_with("output.md", "w", encoding="utf-8")
        mock_file().write.assert_called_once_with("# Schema")

    @patch("builtins.open", new_callable=mock_open)
    def test_discovers_models_when_none_provided(self, mock_file, exporter):
        exporter._discover_models = MagicMock(return_value=["User", "Post"])
        exporter._generate_markdown = MagicMock(return_value="# Schema")

        exporter.export_to_markdown("output.md", models=None)

        exporter._discover_models.assert_called_once()
        exporter._generate_markdown.assert_called_once_with(["User", "Post"])

    @patch("builtins.open", new_callable=mock_open)
    def test_uses_provided_models(self, mock_file, exporter):
        exporter._discover_models = MagicMock()
        exporter._generate_markdown = MagicMock(return_value="# Schema")

        exporter.export_to_markdown("output.md", models=["User", "Post"])

        exporter._discover_models.assert_not_called()
        exporter._generate_markdown.assert_called_once_with(["User", "Post"])

    @patch("builtins.open", new_callable=mock_open)
    def test_writes_generated_markdown(self, mock_file, exporter):
        exporter._discover_models = MagicMock(return_value=["User"])
        exporter._generate_markdown = MagicMock(return_value="## User\n| Field | Type |\n|---|---|")

        exporter.export_to_markdown("output.md")

        mock_file().write.assert_called_once_with("## User\n| Field | Type |\n|---|---|")


class TestDiscoverModels:
    """Test _discover_models method"""

    def test_discovers_models_from_schema(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "Post", "kind": "OBJECT"},
            {"name": "Query", "kind": "OBJECT"},
            {"name": "String", "kind": "SCALAR"},
        ]
        mock_client.get_model_structure.return_value = {
            "fields": [
                {"name": "listUser"},
                {"name": "listPost"},
                {"name": "getUser"},
            ]
        }

        result = exporter._discover_models()

        assert set(result) == {"User", "Post"}
        mock_client.get_all_types.assert_called_once()

    def test_excludes_query_mutation_subscription(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "Query", "kind": "OBJECT"},
            {"name": "Mutation", "kind": "OBJECT"},
            {"name": "Subscription", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter._discover_models()

        assert result == ["User"]

    def test_excludes_connection_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "ModelUserConnection", "kind": "OBJECT"},
            {"name": "UserConnection", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter._discover_models()

        assert result == ["User"]

    def test_excludes_model_prefix_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "ModelUserFilterInput", "kind": "INPUT_OBJECT"},
            {"name": "ModelStringInput", "kind": "INPUT_OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter._discover_models()

        assert result == ["User"]

    def test_excludes_builtin_graphql_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "__Schema", "kind": "OBJECT"},
            {"name": "__Type", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter._discover_models()

        assert result == ["User"]

    def test_excludes_non_object_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "String", "kind": "SCALAR"},
            {"name": "Status", "kind": "ENUM"},
            {"name": "CreateUserInput", "kind": "INPUT_OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter._discover_models()

        assert result == ["User"]

    def test_returns_empty_list_when_no_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = []

        result = exporter._discover_models()

        assert result == []

    def test_returns_sorted_model_list(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "Zebra", "kind": "OBJECT"},
            {"name": "Apple", "kind": "OBJECT"},
            {"name": "Banana", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {
            "fields": [
                {"name": "listZebra"},
                {"name": "listApple"},
                {"name": "listBanana"},
            ]
        }

        result = exporter._discover_models()

        assert result == ["Apple", "Banana", "Zebra"]


class TestGenerateMarkdown:
    """Test _generate_markdown method"""

    def test_generates_basic_structure(self, exporter):
        exporter._generate_model_section = MagicMock(return_value=["## User\n"])

        result = exporter._generate_markdown(["User"])

        assert "# GraphQL Schema Reference" in result
        assert "## Table of Contents" in result
        assert "## User" in result

    def test_includes_table_of_contents(self, exporter):
        exporter._generate_model_section = MagicMock(return_value=["## User\n"])

        result = exporter._generate_markdown(["User", "Post"])

        assert "- [User](#user)" in result
        assert "- [Post](#post)" in result

    def test_generates_sections_for_all_models(self, exporter):
        exporter._generate_model_section = MagicMock(
            side_effect=[
                ["## User\n"],
                ["## Post\n"],
            ]
        )

        result = exporter._generate_markdown(["User", "Post"])

        assert exporter._generate_model_section.call_count == 2
        assert "## User" in result
        assert "## Post" in result

    def test_skips_none_model_sections(self, exporter):
        exporter._generate_model_section = MagicMock(
            side_effect=[
                ["## User\n"],
                None,
            ]
        )

        result = exporter._generate_markdown(["User", "Post"])

        assert "## User" in result
        assert "## Post" not in result

    def test_includes_enums_section(self, exporter):
        def side_effect(model, enums, custom_types):
            if model == "User":
                enums["Status"] = ["ACTIVE", "INACTIVE"]
            return ["## User\n"]

        exporter._generate_model_section = MagicMock(side_effect=side_effect)

        result = exporter._generate_markdown(["User"])

        assert "## Enums" in result
        assert "### Status" in result
        assert "- `ACTIVE`" in result
        assert "- `INACTIVE`" in result

    def test_includes_custom_types_section(self, exporter):
        def side_effect(model, enums, custom_types):
            if model == "User":
                custom_types["Address"] = [
                    {"name": "street", "type": "String", "is_required": True},
                ]
            return ["## User\n"]

        exporter._generate_model_section = MagicMock(side_effect=side_effect)
        exporter._format_type_display = MagicMock(return_value="`String`")

        result = exporter._generate_markdown(["User"])

        assert "## Custom Types" in result
        assert "### Address" in result
        assert "| street |" in result

    def test_sorts_enums_and_custom_types(self, exporter):
        def side_effect(model, enums, custom_types):
            enums["Zebra"] = ["A"]
            enums["Apple"] = ["B"]
            custom_types["Zinc"] = []
            custom_types["Alpha"] = []
            return ["## User\n"]

        exporter._generate_model_section = MagicMock(side_effect=side_effect)

        result = exporter._generate_markdown(["User"])

        apple_pos = result.find("### Apple")
        zebra_pos = result.find("### Zebra")
        alpha_pos = result.find("### Alpha")
        zinc_pos = result.find("### Zinc")

        assert apple_pos < zebra_pos
        assert alpha_pos < zinc_pos


class TestGenerateModelSection:
    """Test _generate_model_section method"""

    def test_returns_none_when_no_structure(self, exporter, mock_client):
        mock_client.get_model_structure.return_value = None

        result = exporter._generate_model_section("User", {}, {})

        assert result is None

    def test_returns_none_when_parse_fails(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = None

        result = exporter._generate_model_section("User", {}, {})

        assert result is None

    def test_includes_model_name_as_header(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {
                    "name": "name",
                    "type": "String",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                }
            ]
        }
        exporter._format_type_display = MagicMock(return_value="`String`")

        result = exporter._generate_model_section("User", {}, {})

        assert "## User" in "\n".join(result)

    def test_includes_description_if_present(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "description": "User model description",
            "fields": [
                {
                    "name": "name",
                    "type": "String",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                }
            ],
        }
        exporter._format_type_display = MagicMock(return_value="`String`")

        result = exporter._generate_model_section("User", {}, {})

        assert "User model description" in "\n".join(result)

    def test_includes_excel_sheet_name(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {
                    "name": "name",
                    "type": "String",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                }
            ]
        }
        exporter._format_type_display = MagicMock(return_value="`String`")

        result = exporter._generate_model_section("User", {}, {})

        assert "**Excel Sheet Name:** `User`" in "\n".join(result)

    def test_filters_metadata_fields(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {
                    "name": "name",
                    "type": "String",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                },
                {
                    "name": "id",
                    "type": "ID",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                },
                {
                    "name": "createdAt",
                    "type": "AWSDateTime",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                },
            ]
        }
        exporter._format_type_display = MagicMock(return_value="`String`")

        result = exporter._generate_model_section("User", {}, {})
        content = "\n".join(result)

        assert "| name |" in content
        assert "| id |" not in content
        assert "| createdAt |" not in content

    def test_creates_field_table(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {
                    "name": "email",
                    "type": "String",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                }
            ]
        }
        exporter._format_type_display = MagicMock(return_value="`String`")

        result = exporter._generate_model_section("User", {}, {})
        content = "\n".join(result)

        assert "| Field Name | Type | Required | Description |" in content
        assert "| email | `String` | ✅ Yes |  |" in content

    def test_marks_required_fields(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {
                    "name": "required_field",
                    "type": "String",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                },
                {
                    "name": "optional_field",
                    "type": "String",
                    "is_required": False,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                },
            ]
        }
        exporter._format_type_display = MagicMock(return_value="`String`")

        result = exporter._generate_model_section("User", {}, {})
        content = "\n".join(result)

        assert "| required_field | `String` | ✅ Yes |" in content
        assert "| optional_field | `String` | ❌ No |" in content

    def test_tracks_enums(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {
                    "name": "status",
                    "type": "Status",
                    "is_required": True,
                    "is_enum": True,
                    "is_custom_type": False,
                    "is_list": False,
                }
            ]
        }
        exporter._format_type_display = MagicMock(return_value="`Status` (Enum)")
        exporter._get_enum_values = MagicMock(return_value=["ACTIVE", "INACTIVE"])

        enums = {}
        exporter._generate_model_section("User", enums, {})

        assert "Status" in enums
        assert enums["Status"] == ["ACTIVE", "INACTIVE"]

    def test_tracks_custom_types(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {
                    "name": "address",
                    "type": "Address",
                    "is_required": False,
                    "is_enum": False,
                    "is_custom_type": True,
                    "is_list": False,
                }
            ]
        }
        exporter._format_type_display = MagicMock(return_value="`Address` (Custom Type)")
        exporter._get_custom_type_fields = MagicMock(return_value=[{"name": "street"}])

        custom_types = {}
        exporter._generate_model_section("User", {}, custom_types)

        assert "Address" in custom_types
        assert custom_types["Address"] == [{"name": "street"}]

    def test_adds_foreign_key_info(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {
                    "name": "author",
                    "type": "Author",
                    "is_required": True,
                    "is_enum": False,
                    "is_custom_type": False,
                    "is_list": False,
                    "related_model": "Author",
                    "foreign_key": "authorId",
                }
            ]
        }
        exporter._format_type_display = MagicMock(return_value="`Author`")

        result = exporter._generate_model_section("Post", {}, {})
        content = "\n".join(result)

        assert "(FK → Author)" in content
        assert "Foreign key: Use `authorId` column with ID from Author model" in content

    def test_handles_no_user_definable_fields(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {"name": "id", "type": "ID", "is_required": True},
                {"name": "createdAt", "type": "AWSDateTime", "is_required": True},
            ]
        }

        result = exporter._generate_model_section("User", {}, {})
        content = "\n".join(result)

        assert "*No user-definable fields*" in content


class TestFormatTypeDisplay:
    """Test _format_type_display static method"""

    def test_formats_basic_type(self):
        field = {"type": "String", "is_list": False, "is_enum": False, "is_custom_type": False}

        result = SchemaExporter._format_type_display(field)

        assert result == "`String`"

    def test_formats_list_type(self):
        field = {"type": "String", "is_list": True, "is_enum": False, "is_custom_type": False}

        result = SchemaExporter._format_type_display(field)

        assert result == "`[String]`"

    def test_formats_enum_type(self):
        field = {"type": "Status", "is_list": False, "is_enum": True, "is_custom_type": False}

        result = SchemaExporter._format_type_display(field)

        assert result == "`Status` (Enum)"

    def test_formats_custom_type(self):
        field = {"type": "Address", "is_list": False, "is_enum": False, "is_custom_type": True}

        result = SchemaExporter._format_type_display(field)

        assert result == "`Address` (Custom Type)"

    def test_formats_list_of_enums(self):
        field = {"type": "Status", "is_list": True, "is_enum": True, "is_custom_type": False}

        result = SchemaExporter._format_type_display(field)

        assert result == "`[Status]` (Enum)"

    def test_formats_list_of_custom_types(self):
        field = {"type": "Address", "is_list": True, "is_enum": False, "is_custom_type": True}

        result = SchemaExporter._format_type_display(field)

        assert result == "`[Address]` (Custom Type)"


class TestGetEnumValues:
    """Test _get_enum_values method"""

    def test_returns_enum_values(self, exporter, mock_client):
        mock_client.get_model_structure.return_value = {
            "enumValues": [
                {"name": "ACTIVE"},
                {"name": "INACTIVE"},
            ]
        }

        result = exporter._get_enum_values("Status")

        assert result == ["ACTIVE", "INACTIVE"]

    def test_returns_empty_list_when_no_enum_values(self, exporter, mock_client):
        mock_client.get_model_structure.return_value = {}

        result = exporter._get_enum_values("Status")

        assert result == []

    def test_returns_empty_list_when_structure_is_none(self, exporter, mock_client):
        mock_client.get_model_structure.return_value = None

        result = exporter._get_enum_values("Status")

        assert result == []


class TestGetCustomTypeFields:
    """Test _get_custom_type_fields method"""

    def test_returns_custom_type_fields(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {"name": "street", "type": "String"},
                {"name": "city", "type": "String"},
            ]
        }

        result = exporter._get_custom_type_fields("Address")

        assert len(result) == 2
        assert result[0]["name"] == "street"
        assert result[1]["name"] == "city"

    def test_filters_metadata_fields(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {"name": "street", "type": "String"},
                {"name": "id", "type": "ID"},
            ]
        }

        result = exporter._get_custom_type_fields("Address")

        assert len(result) == 1
        assert result[0]["name"] == "street"

    def test_returns_empty_list_when_no_structure(self, exporter, mock_client):
        mock_client.get_model_structure.return_value = None

        result = exporter._get_custom_type_fields("Address")

        assert result == []

    def test_returns_empty_list_when_parse_fails(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = None

        result = exporter._get_custom_type_fields("Address")

        assert result == []
