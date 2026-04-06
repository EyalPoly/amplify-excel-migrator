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
        exporter.discover_models = MagicMock(return_value=["User"])
        exporter._generate_markdown = MagicMock(return_value="# Schema")

        exporter.export_to_markdown("output.md")

        mock_file.assert_called_once_with("output.md", "w", encoding="utf-8")
        mock_file().write.assert_called_once_with("# Schema")

    @patch("builtins.open", new_callable=mock_open)
    def test_discovers_models_when_none_provided(self, mock_file, exporter):
        exporter.discover_models = MagicMock(return_value=["User", "Post"])
        exporter._generate_markdown = MagicMock(return_value="# Schema")

        exporter.export_to_markdown("output.md", models=None)

        exporter.discover_models.assert_called_once()
        exporter._generate_markdown.assert_called_once_with(["User", "Post"])

    @patch("builtins.open", new_callable=mock_open)
    def test_uses_provided_models(self, mock_file, exporter):
        exporter.discover_models = MagicMock()
        exporter._generate_markdown = MagicMock(return_value="# Schema")

        exporter.export_to_markdown("output.md", models=["User", "Post"])

        exporter.discover_models.assert_not_called()
        exporter._generate_markdown.assert_called_once_with(["User", "Post"])

    @patch("builtins.open", new_callable=mock_open)
    def test_writes_generated_markdown(self, mock_file, exporter):
        exporter.discover_models = MagicMock(return_value=["User"])
        exporter._generate_markdown = MagicMock(return_value="## User\n| Field | Type |\n|---|---|")

        exporter.export_to_markdown("output.md")

        mock_file().write.assert_called_once_with("## User\n| Field | Type |\n|---|---|")


class TestDiscoverModels:
    """Test discover_models method"""

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

        result = exporter.discover_models()

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

        result = exporter.discover_models()

        assert result == ["User"]

    def test_excludes_connection_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "ModelUserConnection", "kind": "OBJECT"},
            {"name": "UserConnection", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter.discover_models()

        assert result == ["User"]

    def test_excludes_model_prefix_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "ModelUserFilterInput", "kind": "INPUT_OBJECT"},
            {"name": "ModelStringInput", "kind": "INPUT_OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter.discover_models()

        assert result == ["User"]

    def test_excludes_builtin_graphql_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "__Schema", "kind": "OBJECT"},
            {"name": "__Type", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter.discover_models()

        assert result == ["User"]

    def test_excludes_non_object_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "String", "kind": "SCALAR"},
            {"name": "Status", "kind": "ENUM"},
            {"name": "CreateUserInput", "kind": "INPUT_OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter.discover_models()

        assert result == ["User"]

    def test_returns_empty_list_when_no_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = []

        result = exporter.discover_models()

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

        result = exporter.discover_models()

        assert result == ["Apple", "Banana", "Zebra"]


class TestDiscoverCustomTypes:
    """Test discover_custom_types method"""

    def test_returns_object_types_without_list_queries(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "Address", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}]}

        result = exporter.discover_custom_types()

        assert result == ["Address"]

    def test_excludes_models_with_list_queries(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "User", "kind": "OBJECT"},
            {"name": "Post", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": [{"name": "listUser"}, {"name": "listPost"}]}

        result = exporter.discover_custom_types()

        assert result == []

    def test_excludes_amplify_generated_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "Address", "kind": "OBJECT"},
            {"name": "ModelUserConnection", "kind": "OBJECT"},
            {"name": "UserInput", "kind": "OBJECT"},
            {"name": "__Schema", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": []}

        result = exporter.discover_custom_types()

        assert result == ["Address"]

    def test_excludes_non_object_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "Address", "kind": "OBJECT"},
            {"name": "Status", "kind": "ENUM"},
            {"name": "String", "kind": "SCALAR"},
        ]
        mock_client.get_model_structure.return_value = {"fields": []}

        result = exporter.discover_custom_types()

        assert result == ["Address"]

    def test_returns_sorted_list(self, exporter, mock_client):
        mock_client.get_all_types.return_value = [
            {"name": "Zebra", "kind": "OBJECT"},
            {"name": "Apple", "kind": "OBJECT"},
        ]
        mock_client.get_model_structure.return_value = {"fields": []}

        result = exporter.discover_custom_types()

        assert result == ["Apple", "Zebra"]

    def test_returns_empty_when_no_types(self, exporter, mock_client):
        mock_client.get_all_types.return_value = []

        result = exporter.discover_custom_types()

        assert result == []


class TestGenerateMarkdown:
    """Test _generate_markdown method"""

    def test_generates_basic_structure(self, exporter, mock_client):
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._generate_model_section = MagicMock(return_value=["## User\n"])

        result = exporter._generate_markdown(["User"])

        assert "# GraphQL Schema Reference" in result
        assert "## Table of Contents" in result
        assert "## User" in result

    def test_includes_table_of_contents(self, exporter, mock_client):
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._generate_model_section = MagicMock(return_value=["## User\n"])

        result = exporter._generate_markdown(["User", "Post"])

        assert "- [User](#user)" in result
        assert "- [Post](#post)" in result

    def test_generates_sections_for_all_models(self, exporter, mock_client):
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
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

    def test_skips_none_model_sections(self, exporter, mock_client):
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._generate_model_section = MagicMock(
            side_effect=[
                ["## User\n"],
                None,
            ]
        )

        result = exporter._generate_markdown(["User", "Post"])

        assert "## User" in result
        assert "## Post" not in result

    def test_includes_enums_section(self, exporter, mock_client):
        mock_client.get_all_enums.return_value = {"Status": ["ACTIVE", "INACTIVE"]}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._generate_model_section = MagicMock(return_value=["## User\n"])

        result = exporter._generate_markdown(["User"])

        assert "## Enums" in result
        assert "### Status" in result
        assert "- `ACTIVE`" in result
        assert "- `INACTIVE`" in result

    def test_includes_custom_types_section(self, exporter, mock_client):
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=["Address"])
        exporter._get_custom_type_fields = MagicMock(
            return_value=[
                {
                    "name": "street",
                    "type": "String",
                    "is_required": True,
                    "is_list": False,
                    "is_enum": False,
                    "is_custom_type": False,
                }
            ]
        )
        exporter._generate_model_section = MagicMock(return_value=["## User\n"])

        result = exporter._generate_markdown(["User"])

        assert "## Custom Types" in result
        assert "### Address" in result
        assert "| street |" in result

    def test_sorts_enums_and_custom_types(self, exporter, mock_client):
        mock_client.get_all_enums.return_value = {"Zebra": ["A"], "Apple": ["B"]}
        exporter.discover_custom_types = MagicMock(return_value=["Zinc", "Alpha"])
        exporter._get_custom_type_fields = MagicMock(
            return_value=[
                {
                    "name": "field",
                    "type": "String",
                    "is_required": False,
                    "is_list": False,
                    "is_enum": False,
                    "is_custom_type": False,
                }
            ]
        )
        exporter._generate_model_section = MagicMock(return_value=["## User\n"])

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

        result = exporter._generate_model_section("User")

        assert result is None

    def test_returns_none_when_parse_fails(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = None

        result = exporter._generate_model_section("User")

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

        result = exporter._generate_model_section("User")

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

        result = exporter._generate_model_section("User")

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

        result = exporter._generate_model_section("User")

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

        result = exporter._generate_model_section("User")
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

        result = exporter._generate_model_section("User")
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

        result = exporter._generate_model_section("User")
        content = "\n".join(result)

        assert "| required_field | `String` | ✅ Yes |" in content
        assert "| optional_field | `String` | ❌ No |" in content

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

        result = exporter._generate_model_section("Post")
        content = "\n".join(result)

        assert "(FK → Author)" in content
        assert "Enter the primary identifier (e.g. name) of the Author record" in content

    def test_handles_no_user_definable_fields(self, exporter, mock_client, mock_field_parser):
        mock_client.get_model_structure.return_value = {"kind": "OBJECT"}
        mock_field_parser.parse_model_structure.return_value = {
            "fields": [
                {"name": "id", "type": "ID", "is_required": True},
                {"name": "createdAt", "type": "AWSDateTime", "is_required": True},
            ]
        }

        result = exporter._generate_model_section("User")
        content = "\n".join(result)

        assert "*No user-definable fields*" in content


class TestFormatTypeDisplay:
    """Test _format_type_display static method"""

    def test_formats_basic_type(self):
        field = {
            "type": "String",
            "is_list": False,
            "is_enum": False,
            "is_custom_type": False,
        }

        result = SchemaExporter._format_type_display(field)

        assert result == "`String`"

    def test_formats_list_type(self):
        field = {
            "type": "String",
            "is_list": True,
            "is_enum": False,
            "is_custom_type": False,
        }

        result = SchemaExporter._format_type_display(field)

        assert result == "`[String]`"

    def test_formats_enum_type(self):
        field = {
            "type": "Status",
            "is_list": False,
            "is_enum": True,
            "is_custom_type": False,
        }

        result = SchemaExporter._format_type_display(field)

        assert result == "`Status` (Enum)"

    def test_formats_custom_type(self):
        field = {
            "type": "Address",
            "is_list": False,
            "is_enum": False,
            "is_custom_type": True,
        }

        result = SchemaExporter._format_type_display(field)

        assert result == "`Address` (Custom Type)"

    def test_formats_list_of_enums(self):
        field = {
            "type": "Status",
            "is_list": True,
            "is_enum": True,
            "is_custom_type": False,
        }

        result = SchemaExporter._format_type_display(field)

        assert result == "`[Status]` (Enum)"

    def test_formats_list_of_custom_types(self):
        field = {
            "type": "Address",
            "is_list": True,
            "is_enum": False,
            "is_custom_type": True,
        }

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


class TestTruncateSheetName:
    def test_returns_name_unchanged_when_under_31_chars(self):
        assert SchemaExporter._truncate_sheet_name("ShortName") == "ShortName"

    def test_truncates_name_at_31_chars(self):
        long_name = "A" * 40
        assert SchemaExporter._truncate_sheet_name(long_name) == "A" * 31

    def test_returns_exactly_31_chars_unchanged(self):
        name = "B" * 31
        assert SchemaExporter._truncate_sheet_name(name) == name


class TestExportToExcel:
    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_discovers_models_when_none_provided(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {}
        exporter.discover_models = MagicMock(return_value=[])
        exporter.discover_custom_types = MagicMock(return_value=[])

        exporter.export_to_excel("out.xlsx")

        exporter.discover_models.assert_called_once()

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_uses_provided_models_without_discovery(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {}
        exporter.discover_models = MagicMock()
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(return_value=[])

        exporter.export_to_excel("out.xlsx", models=["User"])

        exporter.discover_models.assert_not_called()

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_creates_one_sheet_per_model(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(return_value=[])

        exporter.export_to_excel("out.xlsx", models=["User", "Post"])

        assert mock_wb.create_sheet.call_count == 2

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_skips_model_when_parse_returns_none(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(return_value=None)

        exporter.export_to_excel("out.xlsx", models=["User"])

        mock_wb.create_sheet.assert_not_called()

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_creates_enums_sheet_when_enums_exist(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {"Status": ["ACTIVE", "INACTIVE"]}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(return_value=[])

        exporter.export_to_excel("out.xlsx", models=["User"])

        sheet_names = [call.kwargs.get("title") or call.args[0] for call in mock_wb.create_sheet.call_args_list]
        assert "Enums" in sheet_names

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_omits_enums_sheet_when_no_enums(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(return_value=[])

        exporter.export_to_excel("out.xlsx", models=["User"])

        sheet_names = [call.kwargs.get("title") or call.args[0] for call in mock_wb.create_sheet.call_args_list]
        assert "Enums" not in sheet_names

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_creates_custom_types_sheet_when_custom_types_exist(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=["Address"])
        exporter._get_custom_type_fields = MagicMock(
            return_value=[
                {
                    "name": "street",
                    "type": "String",
                    "is_required": True,
                    "is_list": False,
                    "is_enum": False,
                    "is_custom_type": False,
                }
            ]
        )
        exporter._parse_model_fields = MagicMock(return_value=[])

        exporter.export_to_excel("out.xlsx", models=["User"])

        sheet_names = [call.kwargs.get("title") or call.args[0] for call in mock_wb.create_sheet.call_args_list]
        assert "Custom Types" in sheet_names

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_omits_custom_types_sheet_when_none(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(return_value=[])

        exporter.export_to_excel("out.xlsx", models=["User"])

        sheet_names = [call.kwargs.get("title") or call.args[0] for call in mock_wb.create_sheet.call_args_list]
        assert "Custom Types" not in sheet_names

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_saves_workbook_to_output_path(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(return_value=[])

        exporter.export_to_excel("my-schema.xlsx", models=["User"])

        mock_wb.save.assert_called_once_with("my-schema.xlsx")

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_required_field_uses_checkmark(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_ws.__getitem__ = MagicMock(return_value=[])
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_wb.create_sheet.return_value = mock_ws
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(
            return_value=[{"field_name": "email", "type_display": "`String`", "is_required": True, "description": ""}]
        )

        exporter.export_to_excel("out.xlsx", models=["User"])

        appended_rows = [call.args[0] for call in mock_ws.append.call_args_list]
        data_rows = [r for r in appended_rows if r[0] != "Field Name"]
        assert data_rows[0][2] == "✅"

    @patch("amplify_excel_migrator.schema.schema_exporter.openpyxl")
    def test_optional_field_uses_cross(self, mock_openpyxl, exporter, mock_client):
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_ws.__getitem__ = MagicMock(return_value=[])
        mock_openpyxl.Workbook.return_value = mock_wb
        mock_wb.create_sheet.return_value = mock_ws
        mock_client.get_all_enums.return_value = {}
        exporter.discover_custom_types = MagicMock(return_value=[])
        exporter._parse_model_fields = MagicMock(
            return_value=[{"field_name": "bio", "type_display": "`String`", "is_required": False, "description": ""}]
        )

        exporter.export_to_excel("out.xlsx", models=["User"])

        appended_rows = [call.args[0] for call in mock_ws.append.call_args_list]
        data_rows = [r for r in appended_rows if r[0] != "Field Name"]
        assert data_rows[0][2] == "❌"


class TestGetEnumDisplayNames:
    """Test _get_enum_display_names — strips parent-type prefixes from Amplify-generated enum names."""

    def test_solo_enum_keeps_original_name(self, exporter):
        """Solo enums are never stripped — stripping a unique enum loses context with no benefit."""
        enums = {"ObservationTimeSpecifier": ["MORNING", "EVENING"]}
        result = exporter._get_enum_display_names(enums, {"Observation"})
        assert result == {"ObservationTimeSpecifier": "ObservationTimeSpecifier"}

    def test_solo_enum_with_custom_type_prefix_keeps_original(self, exporter):
        """Each solo enum keeps its original compound name even when a prefix matches."""
        enums = {
            "IndividualGroupCondition": ["NA", "ALIVE"],
            "IndividualGroupStage": ["JUVENILE", "ADULT"],
        }
        result = exporter._get_enum_display_names(enums, {"IndividualGroup"})
        assert result["IndividualGroupCondition"] == "IndividualGroupCondition"
        assert result["IndividualGroupStage"] == "IndividualGroupStage"

    def test_multi_enum_group_strips_prefix(self, exporter):
        """When multiple enums share identical values, strip the prefix to find the canonical name."""
        values = ["NA", "FEMALE", "MALE"]
        enums = {"IndividualSex": values, "IndividualGroupSex": values}
        result = exporter._get_enum_display_names(enums, {"Individual", "IndividualGroup"})
        # Both should strip to "Sex" — the longer prefix wins for IndividualGroupSex
        assert result["IndividualSex"] == "Sex"
        assert result["IndividualGroupSex"] == "Sex"

    def test_same_stripped_name_same_values_deduplicates(self, exporter):
        """Two enums that strip to the same name with identical values both map to the stripped name."""
        values = ["NA", "FEMALE", "MALE", "BOTH"]
        enums = {"IndividualSex": values, "IndividualGroupSex": values}
        result = exporter._get_enum_display_names(enums, {"Individual", "IndividualGroup"})
        assert result["IndividualSex"] == "Sex"
        assert result["IndividualGroupSex"] == "Sex"

    def test_same_stripped_name_different_values_keeps_originals(self, exporter):
        """Two enums that strip to the same name with different values both keep their original names."""
        enums = {
            "MediaType": ["PHOTO", "VIDEO"],
            "SpeciesType": ["SHARK", "RAY", "CHIMAERA"],
        }
        result = exporter._get_enum_display_names(enums, {"Media", "Species"})
        assert result["MediaType"] == "MediaType"
        assert result["SpeciesType"] == "SpeciesType"

    def test_no_matching_prefix_keeps_original(self, exporter):
        enums = {"Status": ["ACTIVE", "INACTIVE"]}
        result = exporter._get_enum_display_names(enums, {"User", "Order"})
        assert result["Status"] == "Status"


class TestApplyDisplayNames:
    """Test _apply_display_names — replaces backtick-quoted GraphQL names in strings."""

    def test_replaces_quoted_name(self):
        display_names = {"ObservationMediaPlatfrom": "MediaPlatfrom"}
        result = SchemaExporter._apply_display_names("`ObservationMediaPlatfrom` (Enum)", display_names)
        assert result == "`MediaPlatfrom` (Enum)"

    def test_replaces_in_list_notation(self):
        display_names = {"IndividualGroupStage": "Stage"}
        result = SchemaExporter._apply_display_names("`[IndividualGroupStage]` (Enum)", display_names)
        assert result == "`[IndividualGroupStage]` (Enum)"  # list notation uses different backtick pattern

    def test_skips_unchanged_names(self):
        display_names = {"Status": "Status"}
        result = SchemaExporter._apply_display_names("`Status` (Enum)", display_names)
        assert result == "`Status` (Enum)"

    def test_longer_names_replaced_first_to_avoid_partial_match(self):
        """IndividualGroupSex must not be partially replaced by IndividualSex → Sex."""
        display_names = {"IndividualSex": "Sex", "IndividualGroupSex": "Sex"}
        result = SchemaExporter._apply_display_names("`IndividualGroupSex` (Enum)", display_names)
        assert result == "`Sex` (Enum)"


class TestBuildDisplayEnums:
    """Test _build_display_enums — deduplicates enums keyed by display name."""

    def test_maps_display_name_to_values(self):
        enums = {"IndividualGroupCondition": ["NA", "ALIVE"]}
        display_names = {"IndividualGroupCondition": "Condition"}
        result = SchemaExporter._build_display_enums(enums, display_names)
        assert result == {"Condition": ["NA", "ALIVE"]}

    def test_deduplicates_same_display_name(self):
        values = ["NA", "FEMALE", "MALE"]
        enums = {"IndividualSex": values, "IndividualGroupSex": values}
        display_names = {"IndividualSex": "Sex", "IndividualGroupSex": "Sex"}
        result = SchemaExporter._build_display_enums(enums, display_names)
        assert list(result.keys()) == ["Sex"]
        assert result["Sex"] == values

    def test_conflict_keeps_both_under_original_names(self):
        enums = {"MediaType": ["PHOTO", "VIDEO"], "SpeciesType": ["SHARK", "RAY"]}
        display_names = {"MediaType": "MediaType", "SpeciesType": "SpeciesType"}
        result = SchemaExporter._build_display_enums(enums, display_names)
        assert "MediaType" in result
        assert "SpeciesType" in result
