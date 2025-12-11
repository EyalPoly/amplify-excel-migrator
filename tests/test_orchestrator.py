"""Tests for MigrationOrchestrator class"""

import pytest
from unittest.mock import MagicMock, patch, call
import pandas as pd
from amplify_excel_migrator.migration.orchestrator import MigrationOrchestrator


@pytest.fixture
def mock_excel_reader():
    reader = MagicMock()
    reader.file_path = "/path/to/test.xlsx"
    return reader


@pytest.fixture
def mock_data_transformer():
    return MagicMock()


@pytest.fixture
def mock_amplify_client():
    return MagicMock()


@pytest.fixture
def mock_failure_tracker():
    tracker = MagicMock()
    tracker.has_failures.return_value = False
    tracker.get_failures.return_value = []
    tracker.get_failures_by_sheet.return_value = {}
    return tracker


@pytest.fixture
def mock_progress_reporter():
    return MagicMock()


@pytest.fixture
def mock_batch_uploader():
    return MagicMock()


@pytest.fixture
def mock_field_parser():
    return MagicMock()


@pytest.fixture
def orchestrator(
    mock_excel_reader,
    mock_data_transformer,
    mock_amplify_client,
    mock_failure_tracker,
    mock_progress_reporter,
    mock_batch_uploader,
    mock_field_parser,
):
    return MigrationOrchestrator(
        excel_reader=mock_excel_reader,
        data_transformer=mock_data_transformer,
        amplify_client=mock_amplify_client,
        failure_tracker=mock_failure_tracker,
        progress_reporter=mock_progress_reporter,
        batch_uploader=mock_batch_uploader,
        field_parser=mock_field_parser,
    )


class TestMigrationOrchestratorInit:
    """Test MigrationOrchestrator initialization"""

    def test_initializes_with_all_components(self, orchestrator, mock_excel_reader, mock_amplify_client):
        assert orchestrator.excel_reader == mock_excel_reader
        assert orchestrator.amplify_client == mock_amplify_client
        assert orchestrator.failure_tracker is not None
        assert orchestrator.progress_reporter is not None
        assert orchestrator.batch_uploader is not None
        assert orchestrator.field_parser is not None


class TestRun:
    """Test run method"""

    @patch("builtins.input", return_value="yes")
    def test_processes_all_sheets(self, mock_input, orchestrator, mock_excel_reader):
        df1 = pd.DataFrame({"name": ["Test1"]})
        df2 = pd.DataFrame({"name": ["Test2"]})
        mock_excel_reader.read_all_sheets.return_value = {"Sheet1": df1, "Sheet2": df2}

        orchestrator.process_sheet = MagicMock(side_effect=[5, 3])

        result = orchestrator.run()

        assert result == 8
        assert orchestrator.process_sheet.call_count == 2
        call_args_list = [call[0] for call in orchestrator.process_sheet.call_args_list]
        assert call_args_list[0][1] == "Sheet1"
        assert call_args_list[1][1] == "Sheet2"

    @patch("builtins.input", return_value="yes")
    def test_displays_summary_after_processing(
        self, mock_input, orchestrator, mock_excel_reader, mock_progress_reporter
    ):
        df = pd.DataFrame({"name": ["Test"]})
        mock_excel_reader.read_all_sheets.return_value = {"Sheet1": df}
        orchestrator.process_sheet = MagicMock(return_value=1)

        orchestrator.run()

        mock_progress_reporter.print_migration_summary.assert_called_once()

    @patch("builtins.input", return_value="yes")
    def test_returns_total_success_count(self, mock_input, orchestrator, mock_excel_reader):
        df1 = pd.DataFrame({"name": ["Test1"]})
        df2 = pd.DataFrame({"name": ["Test2"]})
        mock_excel_reader.read_all_sheets.return_value = {"Sheet1": df1, "Sheet2": df2}
        orchestrator.process_sheet = MagicMock(side_effect=[10, 15])

        result = orchestrator.run()

        assert result == 25


class TestProcessSheet:
    """Test process_sheet method"""

    @patch("builtins.input", return_value="yes")
    def test_sets_current_sheet_on_failure_tracker(self, mock_input, orchestrator, mock_failure_tracker):
        df = pd.DataFrame({"name": ["Test"]})
        orchestrator._get_parsed_model_structure = MagicMock(return_value={"fields": []})
        orchestrator._transform_rows_to_records = MagicMock(return_value=([], {}))
        orchestrator.batch_uploader.upload_records = MagicMock(return_value=(1, 0, []))

        orchestrator.process_sheet(df, "TestSheet")

        mock_failure_tracker.set_current_sheet.assert_called_once_with("TestSheet")

    @patch("builtins.input", return_value="no")
    def test_returns_zero_when_user_cancels(self, mock_input, orchestrator):
        df = pd.DataFrame({"name": ["Test"]})
        orchestrator._get_parsed_model_structure = MagicMock(return_value={"fields": []})
        orchestrator._transform_rows_to_records = MagicMock(return_value=([{"name": "Test"}], {}))

        result = orchestrator.process_sheet(df, "TestSheet")

        assert result == 0

    @patch("builtins.input", return_value="yes")
    def test_uploads_records_when_confirmed(self, mock_input, orchestrator, mock_batch_uploader):
        df = pd.DataFrame({"name": ["Test"]})
        parsed_model = {"fields": []}
        records = [{"name": "Test"}]

        orchestrator._get_parsed_model_structure = MagicMock(return_value=parsed_model)
        orchestrator._transform_rows_to_records = MagicMock(return_value=(records, {}))
        mock_batch_uploader.upload_records.return_value = (1, 0, [])

        orchestrator.process_sheet(df, "TestSheet")

        mock_batch_uploader.upload_records.assert_called_once_with(records, "TestSheet", parsed_model)

    @patch("builtins.input", return_value="yes")
    def test_records_upload_failures(self, mock_input, orchestrator, mock_failure_tracker):
        df = pd.DataFrame({"name": ["Test1", "Test2"]})
        parsed_model = {"fields": []}
        records = [{"name": "Test1"}, {"name": "Test2"}]
        row_dict = {"Test1": {"name": "Test1"}, "Test2": {"name": "Test2"}}
        failed_uploads = [{"primary_field": "name", "primary_field_value": "Test2", "error": "Upload failed"}]

        orchestrator._get_parsed_model_structure = MagicMock(return_value=parsed_model)
        orchestrator._transform_rows_to_records = MagicMock(return_value=(records, row_dict))
        orchestrator.batch_uploader.upload_records = MagicMock(return_value=(1, 1, failed_uploads))

        orchestrator.process_sheet(df, "TestSheet")

        mock_failure_tracker.record_failure.assert_called_once_with(
            primary_field="name",
            primary_field_value="Test2",
            error="Upload failed",
            original_row={"name": "Test2"},
        )

    @patch("builtins.input", return_value="yes")
    def test_prints_sheet_result(self, mock_input, orchestrator, mock_progress_reporter):
        df = pd.DataFrame({"name": ["Test1", "Test2", "Test3"]})
        parsed_model = {"fields": []}
        records = [{"name": "Test1"}, {"name": "Test2"}]

        orchestrator._get_parsed_model_structure = MagicMock(return_value=parsed_model)
        orchestrator._transform_rows_to_records = MagicMock(return_value=(records, {}))
        orchestrator.batch_uploader.upload_records = MagicMock(return_value=(2, 0, []))
        orchestrator.failure_tracker.get_failures.return_value = [{"error": "parse error"}]

        orchestrator.process_sheet(df, "TestSheet")

        mock_progress_reporter.print_sheet_result.assert_called_once_with(
            sheet_name="TestSheet",
            success_count=2,
            total_rows=3,
            parsing_failures=1,
            upload_failures=0,
        )

    @patch("builtins.input", return_value="yes")
    def test_returns_success_count(self, mock_input, orchestrator):
        df = pd.DataFrame({"name": ["Test"]})
        orchestrator._get_parsed_model_structure = MagicMock(return_value={"fields": []})
        orchestrator._transform_rows_to_records = MagicMock(return_value=([{"name": "Test"}], {}))
        orchestrator.batch_uploader.upload_records = MagicMock(return_value=(1, 0, []))

        result = orchestrator.process_sheet(df, "TestSheet")

        assert result == 1


class TestTransformRowsToRecords:
    """Test _transform_rows_to_records method"""

    def test_converts_columns_to_camel_case(self, orchestrator, mock_data_transformer):
        df = pd.DataFrame({"first_name": ["John"], "last_name": ["Doe"]})
        parsed_model = {"fields": []}

        mock_data_transformer.to_camel_case.side_effect = lambda x: x.replace("_", "").title()
        orchestrator.amplify_client.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        orchestrator.amplify_client.build_foreign_key_lookups = MagicMock(return_value={})
        mock_data_transformer.transform_rows_to_records = MagicMock(return_value=([], {}, []))

        orchestrator._transform_rows_to_records(df, parsed_model, "TestSheet")

        assert mock_data_transformer.to_camel_case.call_count == 2

    def test_builds_foreign_key_lookups(self, orchestrator, mock_amplify_client):
        df = pd.DataFrame({"name": ["Test"]})
        parsed_model = {"fields": []}

        orchestrator.amplify_client.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        mock_amplify_client.build_foreign_key_lookups = MagicMock(return_value={"Reporter": {"lookup": {}}})
        orchestrator.data_transformer.transform_rows_to_records = MagicMock(return_value=([], {}, []))

        orchestrator._transform_rows_to_records(df, parsed_model, "TestSheet")

        mock_amplify_client.build_foreign_key_lookups.assert_called_once_with(df, parsed_model)

    def test_transforms_rows_with_fk_lookups(self, orchestrator, mock_data_transformer):
        df = pd.DataFrame({"name": ["Test"]})
        parsed_model = {"fields": []}
        fk_cache = {"Reporter": {"lookup": {"John": "1"}}}

        orchestrator.amplify_client.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        orchestrator.amplify_client.build_foreign_key_lookups = MagicMock(return_value=fk_cache)
        mock_data_transformer.transform_rows_to_records = MagicMock(return_value=([], {}, []))

        orchestrator._transform_rows_to_records(df, parsed_model, "TestSheet")

        mock_data_transformer.transform_rows_to_records.assert_called_once()
        call_args = mock_data_transformer.transform_rows_to_records.call_args
        assert call_args[0][2] == "name"
        assert call_args[0][3] == fk_cache

    def test_records_transformation_failures(self, orchestrator, mock_failure_tracker):
        df = pd.DataFrame({"name": ["Test"]})
        parsed_model = {"fields": []}
        failed_rows = [
            {
                "primary_field": "name",
                "primary_field_value": "Test",
                "error": "Transform error",
                "original_row": {"name": "Test"},
            }
        ]

        orchestrator.amplify_client.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        orchestrator.amplify_client.build_foreign_key_lookups = MagicMock(return_value={})
        orchestrator.data_transformer.transform_rows_to_records = MagicMock(return_value=([], {}, failed_rows))

        orchestrator._transform_rows_to_records(df, parsed_model, "TestSheet")

        mock_failure_tracker.record_failure.assert_called_once_with(
            primary_field="name",
            primary_field_value="Test",
            error="Transform error",
            original_row={"name": "Test"},
        )

    def test_returns_records_and_row_dict(self, orchestrator):
        df = pd.DataFrame({"name": ["Test"]})
        parsed_model = {"fields": []}
        records = [{"name": "Test"}]
        row_dict = {"Test": {"name": "Test"}}

        orchestrator.amplify_client.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        orchestrator.amplify_client.build_foreign_key_lookups = MagicMock(return_value={})
        orchestrator.data_transformer.transform_rows_to_records = MagicMock(return_value=(records, row_dict, []))

        result_records, result_row_dict = orchestrator._transform_rows_to_records(df, parsed_model, "TestSheet")

        assert result_records == records
        assert result_row_dict == row_dict


class TestGetParsedModelStructure:
    """Test _get_parsed_model_structure method"""

    def test_gets_model_structure_from_client(self, orchestrator, mock_amplify_client):
        model_structure = {"fields": [{"name": "id"}]}
        mock_amplify_client.get_model_structure.return_value = model_structure
        orchestrator.field_parser.parse_model_structure = MagicMock(return_value={"parsed": True})

        orchestrator._get_parsed_model_structure("TestModel")

        mock_amplify_client.get_model_structure.assert_called_once_with("TestModel")

    def test_parses_model_structure(self, orchestrator, mock_field_parser):
        model_structure = {"fields": [{"name": "id"}]}
        orchestrator.amplify_client.get_model_structure = MagicMock(return_value=model_structure)
        mock_field_parser.parse_model_structure = MagicMock(return_value={"parsed": True})

        result = orchestrator._get_parsed_model_structure("TestModel")

        mock_field_parser.parse_model_structure.assert_called_once_with(model_structure)
        assert result == {"parsed": True}


class TestDisplaySummary:
    """Test _display_summary method"""

    def test_prints_migration_summary(self, orchestrator, mock_progress_reporter, mock_failure_tracker):
        failures_by_sheet = {"Sheet1": [{"error": "fail"}]}
        mock_failure_tracker.get_failures_by_sheet.return_value = failures_by_sheet

        orchestrator._display_summary(2, 10)

        mock_progress_reporter.print_migration_summary.assert_called_once_with(2, 10, failures_by_sheet)

    @patch("builtins.input", return_value="no")
    def test_skips_export_when_no_failures(self, mock_input, orchestrator, mock_failure_tracker):
        mock_failure_tracker.has_failures.return_value = False
        mock_failure_tracker.get_failures_by_sheet.return_value = {}

        orchestrator._display_summary(1, 5)

        mock_failure_tracker.export_to_excel.assert_not_called()

    @patch("builtins.input", return_value="yes")
    def test_exports_failures_when_confirmed(self, mock_input, orchestrator, mock_failure_tracker, mock_excel_reader):
        mock_failure_tracker.has_failures.return_value = True
        mock_failure_tracker.get_failures_by_sheet.return_value = {"Sheet1": [{"error": "fail"}]}
        mock_failure_tracker.export_to_excel.return_value = "/path/to/failures.xlsx"

        orchestrator._display_summary(1, 5)

        mock_failure_tracker.export_to_excel.assert_called_once_with(mock_excel_reader.file_path)

    @patch("builtins.input", side_effect=["yes", "yes"])
    @patch("amplify_excel_migrator.migration.orchestrator.ConfigManager")
    def test_updates_config_when_confirmed(self, mock_config_manager, mock_input, orchestrator, mock_failure_tracker):
        mock_failure_tracker.has_failures.return_value = True
        mock_failure_tracker.get_failures_by_sheet.return_value = {"Sheet1": [{"error": "fail"}]}
        mock_failure_tracker.export_to_excel.return_value = "/path/to/failures.xlsx"

        mock_config_instance = MagicMock()
        mock_config_manager.return_value = mock_config_instance

        orchestrator._display_summary(1, 5)

        mock_config_instance.update.assert_called_once_with({"excel_path": "/path/to/failures.xlsx"})

    @patch("builtins.input", side_effect=["yes", "no"])
    @patch("amplify_excel_migrator.migration.orchestrator.ConfigManager")
    def test_skips_config_update_when_declined(
        self, mock_config_manager, mock_input, orchestrator, mock_failure_tracker
    ):
        mock_failure_tracker.has_failures.return_value = True
        mock_failure_tracker.get_failures_by_sheet.return_value = {"Sheet1": [{"error": "fail"}]}
        mock_failure_tracker.export_to_excel.return_value = "/path/to/failures.xlsx"

        orchestrator._display_summary(1, 5)

        mock_config_manager.assert_not_called()

    @patch("builtins.input", return_value="no")
    def test_skips_export_when_declined(self, mock_input, orchestrator, mock_failure_tracker):
        mock_failure_tracker.has_failures.return_value = True
        mock_failure_tracker.get_failures_by_sheet.return_value = {"Sheet1": [{"error": "fail"}]}

        orchestrator._display_summary(1, 5)

        mock_failure_tracker.export_to_excel.assert_not_called()
