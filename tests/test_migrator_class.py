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
        migrator.parse_input = MagicMock(side_effect=lambda row, field, _, fk_cache: row.get(field["name"]))

        row_dict = {"name": "John", "email": "john@example.com"}
        parsed_model_structure = {
            "fields": [{"name": "name", "is_required": True}, {"name": "email", "is_required": True}]
        }

        result = migrator.transform_row_to_record(row_dict, parsed_model_structure, {})

        assert result == {"name": "John", "email": "john@example.com"}

    def test_skips_none_values(self):
        """Test that None values are skipped"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock parse_input to return None for some fields
        def mock_parse_input(row, field, _, fk_cache):
            if field["name"] == "optional":
                return None
            return row.get(field["name"])

        migrator.parse_input = MagicMock(side_effect=mock_parse_input)

        row_dict = {"name": "John", "optional": None}
        parsed_model_structure = {
            "fields": [{"name": "name", "is_required": True}, {"name": "optional", "is_required": False}]
        }

        result = migrator.transform_row_to_record(row_dict, parsed_model_structure, {})

        assert result == {"name": "John"}
        assert "optional" not in result


class TestTransformRowsToRecords:
    """Test transform_rows_to_records method"""

    def test_transforms_dataframe(self):
        """Test transforming entire DataFrame"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Initialize instance state
        migrator.failed_records_by_sheet = {}
        migrator._current_sheet = "TestSheet"
        migrator.failed_records_by_sheet["TestSheet"] = []

        # Mock amplify_client
        migrator.amplify_client = MagicMock()
        migrator.amplify_client.get_primary_field_name.return_value = ("name", False, "String")

        # Mock transform_row_to_record
        migrator.transform_row_to_record = MagicMock(
            side_effect=[{"name": "John", "email": "john@example.com"}, {"name": "Jane", "email": "jane@example.com"}]
        )

        df = pd.DataFrame({"Name": ["John", "Jane"], "Email": ["john@example.com", "jane@example.com"]})

        parsed_model_structure = {"fields": []}

        records, row_dict_by_primary = migrator.transform_rows_to_records(df, parsed_model_structure, "TestSheet")

        assert len(records) == 2
        assert records[0]["name"] == "John"
        assert records[1]["name"] == "Jane"
        assert len(migrator.failed_records_by_sheet["TestSheet"]) == 0

    def test_converts_column_names_to_camel_case(self):
        """Test that DataFrame columns are converted to camelCase"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Initialize instance state
        migrator.failed_records_by_sheet = {}
        migrator._current_sheet = "TestSheet"
        migrator.failed_records_by_sheet["TestSheet"] = []

        # Mock amplify_client
        migrator.amplify_client = MagicMock()
        migrator.amplify_client.get_primary_field_name.return_value = ("userName", False, "String")

        # Mock transform_row_to_record to capture the row
        captured_rows = []

        def capture_row(row, _, fk_cache):
            captured_rows.append(row)
            return {"test": "value"}

        migrator.transform_row_to_record = MagicMock(side_effect=capture_row)

        df = pd.DataFrame({"User Name": ["John"], "Email Address": ["john@example.com"]})

        parsed_model_structure = {"fields": []}

        records, row_dict_by_primary = migrator.transform_rows_to_records(df, parsed_model_structure, "TestSheet")

        # Check that columns were converted to camelCase
        assert "userName" in captured_rows[0]
        assert "emailAddress" in captured_rows[0]

    def test_handles_errors_in_rows(self):
        """Test that errors in individual rows don't stop processing"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Initialize instance state
        migrator.failed_records_by_sheet = {}
        migrator._current_sheet = "TestSheet"
        migrator.failed_records_by_sheet["TestSheet"] = []

        # Mock amplify_client
        migrator.amplify_client = MagicMock()
        migrator.amplify_client.get_primary_field_name.return_value = ("name", False, "String")

        # Mock to raise error for second row
        call_count = [0]

        def mock_transform(row, _, fk_cache):
            call_count[0] += 1
            if call_count[0] == 2:  # Second call
                raise ValueError("Test error")
            return {"name": row["name"]}

        migrator.transform_row_to_record = MagicMock(side_effect=mock_transform)

        df = pd.DataFrame({"name": ["John", "Jane", "Bob"]})

        parsed_model_structure = {"fields": []}

        records, row_dict_by_primary = migrator.transform_rows_to_records(df, parsed_model_structure, "TestSheet")

        # Should have 2 records (skipped the one with error)
        assert len(records) == 2
        assert records[0]["name"] == "John"
        assert records[1]["name"] == "Bob"

        # Should have 1 failed parsing record in instance state
        failed_parsing = migrator.failed_records_by_sheet["TestSheet"]
        assert len(failed_parsing) == 1
        assert failed_parsing[0]["primary_field"] == "name"
        assert failed_parsing[0]["primary_field_value"] == "Jane"
        assert "Parsing error: Test error" in failed_parsing[0]["error"]
        assert failed_parsing[0]["row_number"] == 2

    def test_tracks_multiple_parsing_failures(self):
        """Test that multiple parsing failures are tracked"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Initialize instance state
        migrator.failed_records_by_sheet = {}
        migrator._current_sheet = "TestSheet"
        migrator.failed_records_by_sheet["TestSheet"] = []

        # Mock amplify_client
        migrator.amplify_client = MagicMock()
        migrator.amplify_client.get_primary_field_name.return_value = ("name", False, "String")

        # Mock to raise error for rows 2 and 4
        call_count = [0]

        def mock_transform(row, _, fk_cache):
            call_count[0] += 1
            if call_count[0] in [2, 4]:
                raise ValueError(f"Error in row {call_count[0]}")
            return {"name": row["name"]}

        migrator.transform_row_to_record = MagicMock(side_effect=mock_transform)

        df = pd.DataFrame({"name": ["Alice", "Bob", "Charlie", "David", "Eve"]})

        parsed_model_structure = {"fields": []}

        records, row_dict_by_primary = migrator.transform_rows_to_records(df, parsed_model_structure, "TestSheet")

        # Should have 3 successful records
        assert len(records) == 3
        assert records[0]["name"] == "Alice"
        assert records[1]["name"] == "Charlie"
        assert records[2]["name"] == "Eve"

        # Should have 2 failed parsing records in instance state
        failed_parsing = migrator.failed_records_by_sheet["TestSheet"]
        assert len(failed_parsing) == 2
        assert failed_parsing[0]["primary_field_value"] == "Bob"
        assert failed_parsing[0]["row_number"] == 2
        assert failed_parsing[1]["primary_field_value"] == "David"
        assert failed_parsing[1]["row_number"] == 4

    def test_uses_row_number_when_primary_field_missing(self):
        """Test that row number is used when primary field value is missing"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Initialize instance state
        migrator.failed_records_by_sheet = {}
        migrator._current_sheet = "TestSheet"
        migrator.failed_records_by_sheet["TestSheet"] = []

        # Mock amplify_client
        migrator.amplify_client = MagicMock()
        migrator.amplify_client.get_primary_field_name.return_value = ("name", False, "String")

        def mock_transform(row, _, fk_cache):
            raise ValueError("Missing required field")

        migrator.transform_row_to_record = MagicMock(side_effect=mock_transform)

        # DataFrame without the primary field
        df = pd.DataFrame({"otherField": ["value1"]})

        parsed_model_structure = {"fields": []}

        records, row_dict_by_primary = migrator.transform_rows_to_records(df, parsed_model_structure, "TestSheet")

        # Should have 1 failed parsing record with row number as fallback
        failed_parsing = migrator.failed_records_by_sheet["TestSheet"]
        assert len(failed_parsing) == 1
        assert failed_parsing[0]["primary_field_value"] == "Row 1"
        assert failed_parsing[0]["row_number"] == 1

    def test_stores_original_row_in_failure_records(self):
        """Test that original row data is stored when parsing fails"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Initialize instance state
        migrator.failed_records_by_sheet = {}
        migrator._current_sheet = "TestSheet"
        migrator.failed_records_by_sheet["TestSheet"] = []

        # Mock amplify_client
        migrator.amplify_client = MagicMock()
        migrator.amplify_client.get_primary_field_name.return_value = ("name", False, "String")

        def mock_transform(row, _, fk_cache):
            raise ValueError("Test error")

        migrator.transform_row_to_record = MagicMock(side_effect=mock_transform)

        df = pd.DataFrame({"name": ["John"], "email": ["john@example.com"], "age": [30]})

        parsed_model_structure = {"fields": []}

        records, row_dict_by_primary = migrator.transform_rows_to_records(df, parsed_model_structure, "TestSheet")

        # Verify original row is stored
        failed_parsing = migrator.failed_records_by_sheet["TestSheet"]
        assert len(failed_parsing) == 1
        assert "original_row" in failed_parsing[0]
        assert failed_parsing[0]["original_row"]["name"] == "John"
        assert failed_parsing[0]["original_row"]["email"] == "john@example.com"
        assert failed_parsing[0]["original_row"]["age"] == 30

    def test_builds_row_dict_by_primary_mapping(self):
        """Test that row_dict_by_primary mapping is correctly built"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Initialize instance state
        migrator.failed_records_by_sheet = {}
        migrator._current_sheet = "TestSheet"
        migrator.failed_records_by_sheet["TestSheet"] = []

        # Mock amplify_client
        migrator.amplify_client = MagicMock()
        migrator.amplify_client.get_primary_field_name.return_value = ("name", False, "String")

        # Mock transform_row_to_record
        migrator.transform_row_to_record = MagicMock(
            side_effect=[{"name": "John", "email": "john@example.com"}, {"name": "Jane", "email": "jane@example.com"}]
        )

        df = pd.DataFrame({"Name": ["John", "Jane"], "Email": ["john@example.com", "jane@example.com"]})

        parsed_model_structure = {"fields": []}

        records, row_dict_by_primary = migrator.transform_rows_to_records(df, parsed_model_structure, "TestSheet")

        # Verify row_dict_by_primary has correct mappings
        assert "John" in row_dict_by_primary
        assert "Jane" in row_dict_by_primary
        assert row_dict_by_primary["John"]["name"] == "John"
        assert row_dict_by_primary["John"]["email"] == "john@example.com"
        assert row_dict_by_primary["Jane"]["name"] == "Jane"
        assert row_dict_by_primary["Jane"]["email"] == "jane@example.com"


class TestWriteFailedRecordsToExcel:
    """Test _write_failed_records_to_excel method"""

    def test_writes_excel_with_original_row_data(self, tmp_path):
        """Test that Excel file is created with original row data"""
        excel_file = tmp_path / "test.xlsx"
        migrator = ExcelToAmplifyMigrator(str(excel_file))

        # Initialize instance state with failures
        migrator.failed_records_by_sheet = {
            "Sheet1": [
                {
                    "primary_field": "name",
                    "primary_field_value": "John",
                    "error": "Parsing error: Required field missing",
                    "row_number": 1,
                    "original_row": {"name": "John", "email": "john@example.com", "age": 30},
                },
                {
                    "primary_field": "name",
                    "primary_field_value": "Jane",
                    "error": "Upload error: GraphQL failed",
                    "original_row": {"name": "Jane", "email": "jane@example.com", "age": 25},
                },
            ]
        }

        # Write failed records to Excel
        output_path = migrator._write_failed_records_to_excel()

        # Verify file was created
        assert output_path is not None
        assert "test_failed_records.xlsx" in output_path

        # Read and verify Excel contents
        df = pd.read_excel(output_path, sheet_name="Sheet1")

        # Verify columns exist
        assert "ROW_NUMBER" in df.columns
        assert "name" in df.columns
        assert "email" in df.columns
        assert "age" in df.columns
        assert "ERROR" in df.columns

        # Verify data
        assert len(df) == 2
        assert df.loc[0, "name"] == "John"
        assert df.loc[0, "email"] == "john@example.com"
        assert df.loc[0, "age"] == 30
        assert df.loc[0, "ROW_NUMBER"] == 1
        assert "Required field missing" in df.loc[0, "ERROR"]

        assert df.loc[1, "name"] == "Jane"
        assert df.loc[1, "email"] == "jane@example.com"
        assert df.loc[1, "age"] == 25
        assert pd.isna(df.loc[1, "ROW_NUMBER"])  # Upload failures don't have row_number
        assert "GraphQL failed" in df.loc[1, "ERROR"]

    def test_returns_none_when_no_failures(self, tmp_path):
        """Test that None is returned when there are no failures"""
        excel_file = tmp_path / "test.xlsx"
        migrator = ExcelToAmplifyMigrator(str(excel_file))

        # Initialize with empty failures
        migrator.failed_records_by_sheet = {}

        output_path = migrator._write_failed_records_to_excel()

        assert output_path is None

    def test_returns_none_when_all_sheets_have_empty_failures(self, tmp_path):
        """Test that None is returned when all sheets have empty failure lists"""
        excel_file = tmp_path / "test.xlsx"
        migrator = ExcelToAmplifyMigrator(str(excel_file))

        # Initialize with empty failure lists
        migrator.failed_records_by_sheet = {"Sheet1": [], "Sheet2": []}

        output_path = migrator._write_failed_records_to_excel()

        assert output_path is None

    def test_handles_multiple_sheets(self, tmp_path):
        """Test that multiple sheets are written correctly"""
        excel_file = tmp_path / "test.xlsx"
        migrator = ExcelToAmplifyMigrator(str(excel_file))

        # Initialize with failures in multiple sheets
        migrator.failed_records_by_sheet = {
            "Users": [
                {
                    "primary_field": "name",
                    "primary_field_value": "John",
                    "error": "Error 1",
                    "row_number": 1,
                    "original_row": {"name": "John"},
                }
            ],
            "Posts": [
                {
                    "primary_field": "title",
                    "primary_field_value": "Post1",
                    "error": "Error 2",
                    "row_number": 5,
                    "original_row": {"title": "Post1"},
                }
            ],
        }

        output_path = migrator._write_failed_records_to_excel()

        # Verify both sheets were created
        assert output_path is not None

        df_users = pd.read_excel(output_path, sheet_name="Users")
        df_posts = pd.read_excel(output_path, sheet_name="Posts")

        assert len(df_users) == 1
        assert df_users.loc[0, "name"] == "John"

        assert len(df_posts) == 1
        assert df_posts.loc[0, "title"] == "Post1"


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

        row_dict = {"photographer": "John Doe"}
        field = {
            "name": "photographerId",
            "is_id": True,
            "is_required": True,
            "related_model": "Reporter",  # This should be used instead of inferring "Photographer"
        }
        parsed_model_structure = {"fields": []}
        fk_lookup_cache = {"Reporter": {"lookup": {"John Doe": "reporter-123"}}}

        result = migrator.parse_input(row_dict, field, parsed_model_structure, fk_lookup_cache)

        # Should use the lookup cache
        assert result == "reporter-123"

    def test_falls_back_to_field_name_inference(self):
        """Test that parse_input falls back to field name inference when related_model absent"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client
        mock_client = MagicMock()
        mock_client.get_record.return_value = {"id": "user-456"}
        migrator.amplify_client = mock_client

        row_dict = {"author": "Jane Smith"}
        field = {
            "name": "authorId",
            "is_id": True,
            "is_required": False,
            # No related_model property - should infer "Author" from "authorId"
        }
        parsed_model_structure = {"fields": []}
        fk_lookup_cache = {"Author": {"lookup": {"Jane Smith": "user-456"}}}

        result = migrator.parse_input(row_dict, field, parsed_model_structure, fk_lookup_cache)

        # Should use the lookup cache
        assert result == "user-456"

    def test_handles_missing_related_record(self):
        """Test handling when related record is not found"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client to return None
        mock_client = MagicMock()
        mock_client.get_record.return_value = None
        migrator.amplify_client = mock_client

        row_dict = {"photographer": "Unknown Person"}
        field = {"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}
        parsed_model_structure = {"fields": []}
        fk_lookup_cache = {"Reporter": {"lookup": {}}}  # Empty lookup - record not found

        with pytest.raises(ValueError, match="Reporter: Unknown Person does not exist"):
            migrator.parse_input(row_dict, field, parsed_model_structure, fk_lookup_cache)

    def test_handles_related_record_with_null_id(self):
        """Test handling when related record exists but has null ID"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client to return record with null id
        mock_client = MagicMock()
        mock_client.get_record.return_value = {"id": None}
        migrator.amplify_client = mock_client

        row_dict = {"photographer": "John Doe"}
        field = {"name": "photographerId", "is_id": True, "is_required": True, "related_model": "Reporter"}
        parsed_model_structure = {"fields": []}
        fk_lookup_cache = {"Reporter": {"lookup": {}}}  # Empty lookup

        # Should raise ValueError because field is required and ID is not in cache
        with pytest.raises(ValueError, match="Reporter: John Doe does not exist"):
            migrator.parse_input(row_dict, field, parsed_model_structure, fk_lookup_cache)

    def test_handles_optional_id_field_with_null(self):
        """Test handling optional ID field when related record ID is null"""
        migrator = ExcelToAmplifyMigrator("test.xlsx")

        # Mock amplify_client to return record with null id
        mock_client = MagicMock()
        mock_client.get_record.return_value = {"id": None}
        migrator.amplify_client = mock_client

        row_dict = {"photographer": "John Doe"}
        field = {
            "name": "photographerId",
            "is_id": True,
            "is_required": False,  # Optional field
            "related_model": "Reporter",
        }
        parsed_model_structure = {"fields": []}
        fk_lookup_cache = {"Reporter": {"lookup": {}}}  # Empty lookup

        result = migrator.parse_input(row_dict, field, parsed_model_structure, fk_lookup_cache)

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
        row_dict = {"title": "Breaking News", "photographer": "Alice Johnson", "content": "Story content here"}

        # Field definition with related_model
        photographer_id_field = {
            "name": "photographerId",
            "is_id": True,
            "is_required": True,
            "related_model": "Reporter",  # Comes from: photographer: a.belongsTo("Reporter", "photographerId")
        }

        parsed_model_structure = {"fields": []}
        fk_lookup_cache = {"Reporter": {"lookup": {"Alice Johnson": "reporter-abc-123"}}}

        result = migrator.parse_input(row_dict, photographer_id_field, parsed_model_structure, fk_lookup_cache)

        # Should use the lookup cache
        assert result == "reporter-abc-123"
