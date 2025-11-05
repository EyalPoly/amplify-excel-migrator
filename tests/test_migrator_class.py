"""Tests for ExcelToAmplifyMigrator class"""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch
from migrator import ExcelToAmplifyMigrator


class TestToCamelCase:
    """Test to_camel_case static method"""

    def test_space_separated(self):
        """Test conversion with space-separated words"""
        assert ExcelToAmplifyMigrator.to_camel_case("user name") == "userName"
        assert ExcelToAmplifyMigrator.to_camel_case("User Name") == "userName"
        assert ExcelToAmplifyMigrator.to_camel_case("first name last name") == "firstNameLastName"

    def test_hyphen_separated(self):
        """Test conversion with hyphen-separated words"""
        assert ExcelToAmplifyMigrator.to_camel_case("user-name") == "userName"
        assert ExcelToAmplifyMigrator.to_camel_case("first-name") == "firstName"

    def test_underscore_separated(self):
        """Test conversion with underscore-separated words"""
        assert ExcelToAmplifyMigrator.to_camel_case("user_name") == "userName"
        assert ExcelToAmplifyMigrator.to_camel_case("first_name") == "firstName"

    def test_pascal_case(self):
        """Test conversion from PascalCase"""
        assert ExcelToAmplifyMigrator.to_camel_case("UserName") == "userName"
        assert ExcelToAmplifyMigrator.to_camel_case("FirstName") == "firstName"
        # Note: APIKey becomes aPIKey because each capital letter is treated as new word start
        assert ExcelToAmplifyMigrator.to_camel_case("APIKey") == "aPIKey"

    def test_already_camel_case(self):
        """Test that already camelCase strings remain unchanged"""
        assert ExcelToAmplifyMigrator.to_camel_case("firstName") == "firstName"
        assert ExcelToAmplifyMigrator.to_camel_case("userName") == "userName"

    def test_mixed_separators(self):
        """Test conversion with mixed separators"""
        assert ExcelToAmplifyMigrator.to_camel_case("user name-id") == "userNameId"
        assert ExcelToAmplifyMigrator.to_camel_case("first_name last-name") == "firstNameLastName"

    def test_single_word(self):
        """Test single word conversion"""
        assert ExcelToAmplifyMigrator.to_camel_case("user") == "user"
        assert ExcelToAmplifyMigrator.to_camel_case("User") == "user"

    def test_with_extra_spaces(self):
        """Test handling of extra spaces"""
        assert ExcelToAmplifyMigrator.to_camel_case("  user  name  ") == "userName"


class TestExcelToAmplifyMigratorInit:
    """Test ExcelToAmplifyMigrator initialization"""

    def test_initialization(self):
        """Test that migrator initializes correctly"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        assert migrator.excel_file_path == "test.xlsx"
        assert migrator.amplify_client is None
        assert migrator.model_field_parser is not None

    def test_init_client(self):
        """Test client initialization"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        with patch("migrator.AmplifyClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            migrator.init_client(
                api_endpoint="https://test.com",
                region="us-east-1",
                user_pool_id="pool-id",
                client_id="client-id",
                username="test@example.com",
            )

            # Verify AmplifyClient was created with correct parameters
            mock_client_class.assert_called_once_with(
                api_endpoint="https://test.com", user_pool_id="pool-id", region="us-east-1", client_id="client-id"
            )

            # Verify init_cognito_client was called
            mock_client.init_cognito_client.assert_called_once()


class TestTransformRowToRecord:
    """Test transform_row_to_record method"""

    def test_transforms_simple_row(self):
        """Test transforming a simple row"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock the parse_input method
        migrator.parse_input = MagicMock(side_effect=lambda row, field, _: row.get(field["name"]))

        row = pd.Series({"name": "John", "email": "john@example.com"})
        parsed_model_structure = {
            "fields": [{"name": "name", "is_required": True}, {"name": "email", "is_required": True}]
        }

        result = migrator.transform_row_to_record(row, parsed_model_structure)

        assert result == {"name": "John", "email": "john@example.com"}

    def test_skips_none_values(self):
        """Test that None values are skipped"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock parse_input to return None for some fields
        def mock_parse_input(row, field, _):
            if field["name"] == "optional":
                return None
            return row.get(field["name"])

        migrator.parse_input = MagicMock(side_effect=mock_parse_input)

        row = pd.Series({"name": "John", "optional": None})
        parsed_model_structure = {
            "fields": [{"name": "name", "is_required": True}, {"name": "optional", "is_required": False}]
        }

        result = migrator.transform_row_to_record(row, parsed_model_structure)

        assert result == {"name": "John"}
        assert "optional" not in result


class TestTransformRowsToRecords:
    """Test transform_rows_to_records method"""

    def test_transforms_dataframe(self):
        """Test transforming entire DataFrame"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock transform_row_to_record
        migrator.transform_row_to_record = MagicMock(
            side_effect=[{"name": "John", "email": "john@example.com"}, {"name": "Jane", "email": "jane@example.com"}]
        )

        df = pd.DataFrame({"Name": ["John", "Jane"], "Email": ["john@example.com", "jane@example.com"]})

        parsed_model_structure = {"fields": []}

        records = migrator.transform_rows_to_records(df, parsed_model_structure)

        assert len(records) == 2
        assert records[0]["name"] == "John"
        assert records[1]["name"] == "Jane"

    def test_converts_column_names_to_camel_case(self):
        """Test that DataFrame columns are converted to camelCase"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock transform_row_to_record to capture the row
        captured_rows = []

        def capture_row(row, _):
            captured_rows.append(row)
            return {"test": "value"}

        migrator.transform_row_to_record = MagicMock(side_effect=capture_row)

        df = pd.DataFrame({"User Name": ["John"], "Email Address": ["john@example.com"]})

        parsed_model_structure = {"fields": []}

        migrator.transform_rows_to_records(df, parsed_model_structure)

        # Check that columns were converted to camelCase
        assert "userName" in captured_rows[0].index
        assert "emailAddress" in captured_rows[0].index

    def test_handles_errors_in_rows(self):
        """Test that errors in individual rows don't stop processing"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock to raise error for second row
        def mock_transform(row, _):
            if row.name == 1:  # Second row
                raise ValueError("Test error")
            return {"name": row["name"]}

        migrator.transform_row_to_record = MagicMock(side_effect=mock_transform)

        df = pd.DataFrame({"name": ["John", "Jane", "Bob"]})

        parsed_model_structure = {"fields": []}

        records = migrator.transform_rows_to_records(df, parsed_model_structure)

        # Should have 2 records (skipped the one with error)
        assert len(records) == 2
        assert records[0]["name"] == "John"
        assert records[1]["name"] == "Bob"


class TestReadExcel:
    """Test read_excel method"""

    def test_reads_excel_file(self, tmp_path):
        """Test reading Excel file"""
        # Create a test Excel file
        excel_file = tmp_path / "test.xlsx"
        df = pd.DataFrame({"Name": ["John", "Jane"], "Age": [30, 25]})
        df.to_excel(excel_file, sheet_name="Users", index=False)

        migrator = ExcelToAmplifyMigrator(str(excel_file))

        sheets = migrator.read_excel()

        assert "Users" in sheets
        assert len(sheets["Users"]) == 2
        assert list(sheets["Users"]["Name"]) == ["John", "Jane"]

    def test_reads_multiple_sheets(self, tmp_path):
        """Test reading Excel file with multiple sheets"""
        excel_file = tmp_path / "test.xlsx"

        with pd.ExcelWriter(excel_file) as writer:
            df1 = pd.DataFrame({"Name": ["John"]})
            df2 = pd.DataFrame({"Title": ["Post1"]})
            df1.to_excel(writer, sheet_name="Users", index=False)
            df2.to_excel(writer, sheet_name="Posts", index=False)

        migrator = ExcelToAmplifyMigrator(str(excel_file))

        sheets = migrator.read_excel()

        assert len(sheets) == 2
        assert "Users" in sheets
        assert "Posts" in sheets


class TestParseInputWithRelationships:
    """Test parse_input method with belongsTo relationships"""

    def test_uses_related_model_when_present(self):
        """Test that parse_input uses related_model from field metadata"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client
        mock_client = MagicMock()
        mock_client.get_record.return_value = {"id": "reporter-123"}
        migrator.amplify_client = mock_client

        row = pd.Series({"photographer": "John Doe"})
        field = {
            "name": "photographerId",
            "is_id": True,
            "is_required": True,
            "related_model": "Reporter",  # This should be used instead of inferring "Photographer"
        }
        parsed_model_structure = {"fields": []}

        result = migrator.parse_input(row, field, parsed_model_structure)

        # Should have called get_record with "Reporter", not "Photographer"
        mock_client.get_record.assert_called_once_with(
            "Reporter", parsed_model_structure=parsed_model_structure, value="John Doe"
        )
        assert result == "reporter-123"

    def test_falls_back_to_field_name_inference(self):
        """Test that parse_input falls back to field name inference when related_model absent"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client
        mock_client = MagicMock()
        mock_client.get_record.return_value = {"id": "user-456"}
        migrator.amplify_client = mock_client

        row = pd.Series({"author": "Jane Smith"})
        field = {
            "name": "authorId",
            "is_id": True,
            "is_required": False,
            # No related_model property - should infer "Author" from "authorId"
        }
        parsed_model_structure = {"fields": []}

        result = migrator.parse_input(row, field, parsed_model_structure)

        # Should infer "Author" from "authorId"
        mock_client.get_record.assert_called_once_with(
            "Author", parsed_model_structure=parsed_model_structure, value="Jane Smith"
        )
        assert result == "user-456"

    def test_handles_missing_related_record(self):
        """Test handling when related record is not found"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client to return None
        mock_client = MagicMock()
        mock_client.get_record.return_value = None
        migrator.amplify_client = mock_client

        row = pd.Series({"photographer": "Unknown Person"})
        field = {"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}
        parsed_model_structure = {"fields": []}

        result = migrator.parse_input(row, field, parsed_model_structure)

        assert result is None

    def test_handles_related_record_with_null_id(self):
        """Test handling when related record exists but has null ID"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client to return record with null id
        mock_client = MagicMock()
        mock_client.get_record.return_value = {"id": None}
        migrator.amplify_client = mock_client

        row = pd.Series({"photographer": "John Doe"})
        field = {"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}
        parsed_model_structure = {"fields": []}

        # Should raise ValueError because field is required and ID is None
        with pytest.raises(ValueError, match="Reporter: John Doe does not exist"):
            migrator.parse_input(row, field, parsed_model_structure)

    def test_handles_optional_id_field_with_null(self):
        """Test handling optional ID field when related record ID is null"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client to return record with null id
        mock_client = MagicMock()
        mock_client.get_record.return_value = {"id": None}
        migrator.amplify_client = mock_client

        row = pd.Series({"photographer": "John Doe"})
        field = {
            "name": "photographerId",
            "is_id": True,
            "is_required": False,  # Optional field
            "related_model": "Reporter",
        }
        parsed_model_structure = {"fields": []}

        result = migrator.parse_input(row, field, parsed_model_structure)

        # Should return None without raising error for optional field
        assert result is None

    def test_integration_with_real_scenario(self):
        """Test full integration with Story -> Reporter relationship"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client
        mock_client = MagicMock()
        mock_client.get_record.return_value = {"id": "reporter-abc-123"}
        migrator.amplify_client = mock_client

        # Simulate Excel row
        row = pd.Series({"title": "Breaking News", "photographer": "Alice Johnson", "content": "Story content here"})

        # Field definition with related_model
        photographer_id_field = {
            "name": "photographerId",
            "is_id": True,
            "is_required": True,
            "related_model": "Reporter",  # Comes from: photographer: a.belongsTo("Reporter", "photographerId")
        }

        parsed_model_structure = {"fields": []}

        result = migrator.parse_input(row, photographer_id_field, parsed_model_structure)

        # Should query Reporter model (not Photographer)
        mock_client.get_record.assert_called_once_with(
            "Reporter", parsed_model_structure=parsed_model_structure, value="Alice Johnson"
        )
        assert result == "reporter-abc-123"
