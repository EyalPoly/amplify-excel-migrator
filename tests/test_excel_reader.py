"""Tests for ExcelReader class"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from amplify_excel_migrator.data.excel_reader import ExcelReader


class TestExcelReaderInit:
    """Test ExcelReader initialization"""

    def test_initializes_with_file_path(self):
        reader = ExcelReader(file_path="/path/to/file.xlsx")
        assert reader.file_path == "/path/to/file.xlsx"


class TestReadAllSheets:
    """Test read_all_sheets method"""

    @patch("amplify_excel_migrator.data.excel_reader.pd.read_excel")
    def test_reads_all_sheets_from_excel(self, mock_read_excel):
        df1 = pd.DataFrame({"name": ["John"]})
        df2 = pd.DataFrame({"title": ["Manager"]})
        mock_read_excel.return_value = {"Sheet1": df1, "Sheet2": df2}

        reader = ExcelReader(file_path="/path/to/file.xlsx")
        result = reader.read_all_sheets()

        mock_read_excel.assert_called_once_with("/path/to/file.xlsx", sheet_name=None)
        assert len(result) == 2
        assert "Sheet1" in result
        assert "Sheet2" in result

    @patch("amplify_excel_migrator.data.excel_reader.pd.read_excel")
    def test_returns_empty_dict_for_no_sheets(self, mock_read_excel):
        mock_read_excel.return_value = {}

        reader = ExcelReader(file_path="/path/to/file.xlsx")
        result = reader.read_all_sheets()

        assert result == {}

    @patch("amplify_excel_migrator.data.excel_reader.pd.read_excel")
    def test_logs_file_path_and_sheet_count(self, mock_read_excel):
        mock_read_excel.return_value = {"Sheet1": pd.DataFrame(), "Sheet2": pd.DataFrame()}

        reader = ExcelReader(file_path="/path/to/test.xlsx")
        result = reader.read_all_sheets()

        assert len(result) == 2


class TestReadSheet:
    """Test read_sheet method"""

    @patch("amplify_excel_migrator.data.excel_reader.pd.read_excel")
    def test_reads_specific_sheet(self, mock_read_excel):
        df = pd.DataFrame({"name": ["John"], "age": [25]})
        mock_read_excel.return_value = df

        reader = ExcelReader(file_path="/path/to/file.xlsx")
        result = reader.read_sheet("Sheet1")

        mock_read_excel.assert_called_once_with("/path/to/file.xlsx", sheet_name="Sheet1")
        assert result.equals(df)

    @patch("amplify_excel_migrator.data.excel_reader.pd.read_excel")
    def test_reads_different_sheet_names(self, mock_read_excel):
        df = pd.DataFrame({"data": [1, 2, 3]})
        mock_read_excel.return_value = df

        reader = ExcelReader(file_path="/path/to/file.xlsx")
        result = reader.read_sheet("CustomSheet")

        mock_read_excel.assert_called_once_with("/path/to/file.xlsx", sheet_name="CustomSheet")
        assert result.equals(df)
