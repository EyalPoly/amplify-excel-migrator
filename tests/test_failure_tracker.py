"""Tests for FailureTracker class"""

import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import pandas as pd
from amplify_excel_migrator.migration.failure_tracker import FailureTracker


@pytest.fixture
def tracker():
    return FailureTracker()


class TestFailureTrackerInit:
    """Test FailureTracker initialization"""

    def test_initializes_with_empty_failures(self, tracker):
        assert tracker._failures_by_sheet == {}
        assert tracker._current_sheet is None


class TestSetCurrentSheet:
    """Test set_current_sheet method"""

    def test_sets_current_sheet_name(self, tracker):
        tracker.set_current_sheet("Users")
        assert tracker._current_sheet == "Users"

    def test_creates_empty_list_for_new_sheet(self, tracker):
        tracker.set_current_sheet("Users")
        assert "Users" in tracker._failures_by_sheet
        assert tracker._failures_by_sheet["Users"] == []

    def test_preserves_existing_failures_when_resetting_sheet(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Duplicate key")
        tracker.set_current_sheet("Users")
        assert len(tracker._failures_by_sheet["Users"]) == 1

    def test_can_switch_between_sheets(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user@example.com", "Error 1")
        tracker.set_current_sheet("Products")
        tracker.record_failure("sku", "ABC123", "Error 2")

        assert tracker._current_sheet == "Products"
        assert len(tracker._failures_by_sheet["Users"]) == 1
        assert len(tracker._failures_by_sheet["Products"]) == 1


class TestRecordFailure:
    """Test record_failure method"""

    def test_records_failure_with_required_fields(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Duplicate key")

        failures = tracker.get_failures("Users")
        assert len(failures) == 1
        assert failures[0]["primary_field"] == "email"
        assert failures[0]["primary_field_value"] == "test@example.com"
        assert failures[0]["error"] == "Duplicate key"

    def test_records_failure_with_original_row(self, tracker):
        tracker.set_current_sheet("Users")
        original_row = {"email": "test@example.com", "name": "John Doe"}
        tracker.record_failure("email", "test@example.com", "Error", original_row)

        failures = tracker.get_failures("Users")
        assert failures[0]["original_row"] == original_row

    def test_raises_error_when_no_sheet_set(self, tracker):
        with pytest.raises(RuntimeError, match="No current sheet set"):
            tracker.record_failure("email", "test@example.com", "Error")

    def test_records_multiple_failures_for_same_sheet(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user1@example.com", "Error 1")
        tracker.record_failure("email", "user2@example.com", "Error 2")

        failures = tracker.get_failures("Users")
        assert len(failures) == 2

    def test_records_failures_without_original_row(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Error")

        failures = tracker.get_failures("Users")
        assert "original_row" not in failures[0]


class TestGetFailures:
    """Test get_failures method"""

    def test_returns_failures_for_specific_sheet(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user@example.com", "Error 1")
        tracker.set_current_sheet("Products")
        tracker.record_failure("sku", "ABC123", "Error 2")

        user_failures = tracker.get_failures("Users")
        assert len(user_failures) == 1
        assert user_failures[0]["primary_field_value"] == "user@example.com"

    def test_returns_empty_list_for_nonexistent_sheet(self, tracker):
        failures = tracker.get_failures("NonexistentSheet")
        assert failures == []

    def test_returns_all_failures_when_no_sheet_specified(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user@example.com", "Error 1")
        tracker.set_current_sheet("Products")
        tracker.record_failure("sku", "ABC123", "Error 2")

        all_failures = tracker.get_failures()
        assert len(all_failures) == 2

    def test_returns_empty_list_when_no_failures_recorded(self, tracker):
        tracker.set_current_sheet("Users")
        failures = tracker.get_failures("Users")
        assert failures == []


class TestGetFailuresBySheet:
    """Test get_failures_by_sheet method"""

    def test_returns_dict_of_all_sheets_and_failures(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user@example.com", "Error 1")
        tracker.set_current_sheet("Products")
        tracker.record_failure("sku", "ABC123", "Error 2")

        failures_by_sheet = tracker.get_failures_by_sheet()
        assert len(failures_by_sheet) == 2
        assert "Users" in failures_by_sheet
        assert "Products" in failures_by_sheet

    def test_returns_copy_not_reference(self, tracker):
        tracker.set_current_sheet("Users")
        failures_by_sheet = tracker.get_failures_by_sheet()
        failures_by_sheet["NewSheet"] = []

        assert "NewSheet" not in tracker._failures_by_sheet

    def test_returns_empty_dict_when_no_failures(self, tracker):
        failures_by_sheet = tracker.get_failures_by_sheet()
        assert failures_by_sheet == {}


class TestGetTotalFailureCount:
    """Test get_total_failure_count method"""

    def test_returns_zero_when_no_failures(self, tracker):
        assert tracker.get_total_failure_count() == 0

    def test_counts_failures_across_all_sheets(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user1@example.com", "Error 1")
        tracker.record_failure("email", "user2@example.com", "Error 2")
        tracker.set_current_sheet("Products")
        tracker.record_failure("sku", "ABC123", "Error 3")

        assert tracker.get_total_failure_count() == 3

    def test_counts_only_recorded_failures(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user@example.com", "Error")
        tracker.set_current_sheet("Products")

        assert tracker.get_total_failure_count() == 1


class TestHasFailures:
    """Test has_failures method"""

    def test_returns_false_when_no_failures(self, tracker):
        assert tracker.has_failures() is False

    def test_returns_true_when_failures_exist(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user@example.com", "Error")
        assert tracker.has_failures() is True

    def test_returns_false_after_creating_empty_sheet(self, tracker):
        tracker.set_current_sheet("Users")
        assert tracker.has_failures() is False


class TestExportToExcel:
    """Test export_to_excel method"""

    def test_returns_none_when_no_failures(self, tracker):
        result = tracker.export_to_excel("/path/to/input.xlsx")
        assert result is None

    @patch("amplify_excel_migrator.migration.failure_tracker.pd.DataFrame")
    @patch("amplify_excel_migrator.migration.failure_tracker.pd.ExcelWriter")
    @patch("amplify_excel_migrator.migration.failure_tracker.datetime")
    def test_creates_excel_file_with_timestamp(self, mock_datetime, mock_writer, mock_df_class, tracker):
        mock_datetime.now.return_value.strftime.return_value = "20250101_120000"
        mock_writer_instance = MagicMock()
        mock_writer.return_value.__enter__.return_value = mock_writer_instance
        mock_df = MagicMock()
        mock_df_class.return_value = mock_df

        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Error", {"email": "test@example.com"})

        result = tracker.export_to_excel("/path/to/input.xlsx")

        assert result == "/path/to/input_failed_records_20250101_120000.xlsx"

    @patch("amplify_excel_migrator.migration.failure_tracker.pd.ExcelWriter")
    @patch("amplify_excel_migrator.migration.failure_tracker.pd.DataFrame")
    @patch("amplify_excel_migrator.migration.failure_tracker.datetime")
    def test_writes_failures_to_excel_sheets(self, mock_datetime, mock_df_class, mock_writer, tracker):
        mock_datetime.now.return_value.strftime.return_value = "20250101_120000"
        mock_writer_instance = MagicMock()
        mock_writer.return_value.__enter__.return_value = mock_writer_instance
        mock_df = MagicMock()
        mock_df_class.return_value = mock_df

        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Duplicate", {"email": "test@example.com", "name": "John"})

        tracker.export_to_excel("/path/to/input.xlsx")

        mock_df.to_excel.assert_called_once_with(mock_writer_instance, sheet_name="Users", index=False)

    @patch("amplify_excel_migrator.migration.failure_tracker.pd.ExcelWriter")
    @patch("amplify_excel_migrator.migration.failure_tracker.pd.DataFrame")
    @patch("amplify_excel_migrator.migration.failure_tracker.datetime")
    def test_adds_error_column_to_original_row(self, mock_datetime, mock_df_class, mock_writer, tracker):
        mock_datetime.now.return_value.strftime.return_value = "20250101_120000"
        mock_writer_instance = MagicMock()
        mock_writer.return_value.__enter__.return_value = mock_writer_instance

        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Duplicate", {"email": "test@example.com"})

        tracker.export_to_excel("/path/to/input.xlsx")

        call_args = mock_df_class.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["ERROR"] == "Duplicate"

    @patch("amplify_excel_migrator.migration.failure_tracker.pd.DataFrame")
    @patch("amplify_excel_migrator.migration.failure_tracker.pd.ExcelWriter")
    @patch("amplify_excel_migrator.migration.failure_tracker.datetime")
    def test_skips_sheets_with_no_failures(self, mock_datetime, mock_writer, mock_df_class, tracker):
        mock_datetime.now.return_value.strftime.return_value = "20250101_120000"
        mock_writer_instance = MagicMock()
        mock_writer.return_value.__enter__.return_value = mock_writer_instance
        mock_df = MagicMock()
        mock_df_class.return_value = mock_df

        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Error", {"email": "test@example.com"})
        tracker.set_current_sheet("Products")

        tracker.export_to_excel("/path/to/input.xlsx")

        mock_writer.assert_called_once()

    @patch("amplify_excel_migrator.migration.failure_tracker.pd.DataFrame")
    @patch("amplify_excel_migrator.migration.failure_tracker.pd.ExcelWriter")
    @patch("amplify_excel_migrator.migration.failure_tracker.datetime")
    def test_handles_input_filename_with_existing_failed_records_prefix(
        self, mock_datetime, mock_writer, mock_df_class, tracker
    ):
        mock_datetime.now.return_value.strftime.return_value = "20250101_120000"
        mock_writer_instance = MagicMock()
        mock_writer.return_value.__enter__.return_value = mock_writer_instance
        mock_df = MagicMock()
        mock_df_class.return_value = mock_df

        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Error", {"email": "test@example.com"})

        result = tracker.export_to_excel("/path/to/input_failed_records_20241231_100000.xlsx")

        assert result == "/path/to/input_failed_records_20250101_120000.xlsx"

    @patch("amplify_excel_migrator.migration.failure_tracker.pd.ExcelWriter")
    @patch("amplify_excel_migrator.migration.failure_tracker.pd.DataFrame")
    @patch("amplify_excel_migrator.migration.failure_tracker.datetime")
    def test_handles_failure_without_original_row(self, mock_datetime, mock_df_class, mock_writer, tracker):
        mock_datetime.now.return_value.strftime.return_value = "20250101_120000"
        mock_writer_instance = MagicMock()
        mock_writer.return_value.__enter__.return_value = mock_writer_instance

        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "test@example.com", "Error")

        tracker.export_to_excel("/path/to/input.xlsx")

        call_args = mock_df_class.call_args[0][0]
        assert call_args[0]["ERROR"] == "Error"


class TestClear:
    """Test clear method"""

    def test_clears_all_failures(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user@example.com", "Error")
        tracker.clear()

        assert tracker._failures_by_sheet == {}

    def test_resets_current_sheet(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.clear()

        assert tracker._current_sheet is None

    def test_allows_recording_after_clear(self, tracker):
        tracker.set_current_sheet("Users")
        tracker.record_failure("email", "user@example.com", "Error")
        tracker.clear()

        tracker.set_current_sheet("Products")
        tracker.record_failure("sku", "ABC123", "Error")

        assert len(tracker.get_failures("Products")) == 1
        assert len(tracker.get_failures("Users")) == 0
