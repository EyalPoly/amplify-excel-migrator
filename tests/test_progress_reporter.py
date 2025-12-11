"""Tests for ProgressReporter class"""

import pytest
from io import StringIO
from unittest.mock import patch
from amplify_excel_migrator.migration.progress_reporter import ProgressReporter


class TestPrintSheetResult:
    """Test print_sheet_result method"""

    @patch("sys.stdout", new_callable=StringIO)
    def test_prints_success_and_failure_counts(self, mock_stdout):
        ProgressReporter.print_sheet_result(
            sheet_name="Users", success_count=10, total_rows=15, parsing_failures=3, upload_failures=2
        )

        output = mock_stdout.getvalue()
        assert "Users" in output
        assert "✅ Success: 10" in output
        assert "❌ Failed: 5" in output
        assert "Parsing: 3" in output
        assert "Upload: 2" in output
        assert "📊 Total: 15" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_prints_sheet_name_in_header(self, mock_stdout):
        ProgressReporter.print_sheet_result(
            sheet_name="Products", success_count=5, total_rows=5, parsing_failures=0, upload_failures=0
        )

        output = mock_stdout.getvalue()
        assert "Products" in output
        assert "Complete" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_handles_zero_failures(self, mock_stdout):
        ProgressReporter.print_sheet_result(
            sheet_name="Orders", success_count=20, total_rows=20, parsing_failures=0, upload_failures=0
        )

        output = mock_stdout.getvalue()
        assert "❌ Failed: 0" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_sums_parsing_and_upload_failures(self, mock_stdout):
        ProgressReporter.print_sheet_result(
            sheet_name="Test", success_count=0, total_rows=10, parsing_failures=7, upload_failures=3
        )

        output = mock_stdout.getvalue()
        assert "❌ Failed: 10" in output


class TestPrintMigrationSummary:
    """Test print_migration_summary method"""

    @patch("sys.stdout", new_callable=StringIO)
    def test_prints_basic_summary(self, mock_stdout):
        failures = {}
        ProgressReporter.print_migration_summary(sheets_processed=2, total_success=15, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "MIGRATION SUMMARY" in output
        assert "📊 Sheets processed: 2" in output
        assert "✅ Total successful: 15" in output
        assert "❌ Total failed: 0" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_calculates_success_rate(self, mock_stdout):
        failures = {"Sheet1": [{"error": "test"}]}
        ProgressReporter.print_migration_summary(sheets_processed=1, total_success=9, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "📈 Success rate: 90.0%" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_shows_no_failures_message_when_all_succeed(self, mock_stdout):
        failures = {}
        ProgressReporter.print_migration_summary(sheets_processed=3, total_success=100, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "✨ No failed records!" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_prints_failed_records_details(self, mock_stdout):
        failures = {
            "Users": [
                {"primary_field_value": "john@example.com", "error": "Duplicate key"},
                {"primary_field_value": "jane@example.com", "error": "Invalid format"},
            ]
        }
        ProgressReporter.print_migration_summary(sheets_processed=1, total_success=10, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "FAILED RECORDS DETAILS" in output
        assert "📄 Users:" in output
        assert "john@example.com" in output
        assert "Duplicate key" in output
        assert "jane@example.com" in output
        assert "Invalid format" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_prints_multiple_sheets_with_failures(self, mock_stdout):
        failures = {
            "Users": [{"primary_field_value": "user1", "error": "Error 1"}],
            "Products": [{"primary_field_value": "prod1", "error": "Error 2"}],
        }
        ProgressReporter.print_migration_summary(sheets_processed=2, total_success=20, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "📄 Users:" in output
        assert "user1" in output
        assert "Error 1" in output
        assert "📄 Products:" in output
        assert "prod1" in output
        assert "Error 2" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_skips_sheets_with_empty_failures_list(self, mock_stdout):
        failures = {"Users": [{"error": "test"}], "Products": []}
        ProgressReporter.print_migration_summary(sheets_processed=2, total_success=10, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "📄 Users:" in output
        assert "📄 Products:" not in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_shows_na_for_zero_total_records(self, mock_stdout):
        failures = {}
        ProgressReporter.print_migration_summary(sheets_processed=0, total_success=0, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "📈 Success rate: N/A" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_handles_missing_primary_field_value(self, mock_stdout):
        failures = {"Users": [{"error": "Some error"}]}
        ProgressReporter.print_migration_summary(sheets_processed=1, total_success=5, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "Unknown" in output
        assert "Some error" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_handles_missing_error_field(self, mock_stdout):
        failures = {"Users": [{"primary_field_value": "test@example.com"}]}
        ProgressReporter.print_migration_summary(sheets_processed=1, total_success=5, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "test@example.com" in output
        assert "Unknown error" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_counts_total_failures_across_sheets(self, mock_stdout):
        failures = {
            "Sheet1": [{"error": "e1"}, {"error": "e2"}],
            "Sheet2": [{"error": "e3"}],
            "Sheet3": [{"error": "e4"}, {"error": "e5"}, {"error": "e6"}],
        }
        ProgressReporter.print_migration_summary(sheets_processed=3, total_success=10, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "❌ Total failed: 6" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_prints_divider_lines(self, mock_stdout):
        failures = {}
        ProgressReporter.print_migration_summary(sheets_processed=1, total_success=5, failures_by_sheet=failures)

        output = mock_stdout.getvalue()
        assert "=" * 60 in output
