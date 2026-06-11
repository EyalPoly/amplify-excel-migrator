"""Tests for the relocated interactive migration flow in the CLI."""

from unittest.mock import MagicMock, patch

from amplify_excel_migrator.cli.commands import run_interactive_migration
from amplify_excel_migrator.migration.models import (
    MigrationPlan,
    MigrationResult,
    RecordFailure,
    SheetPlan,
    SheetResult,
)


def _ready_plan(sheet_name="Reporter", record_count=2, parsing_failures=None, total_rows=2):
    return SheetPlan(
        sheet_name=sheet_name,
        status="ready",
        skip_reason=None,
        total_rows=total_rows,
        record_count=record_count,
        records=[{"name": "x"}] * record_count,
        parsing_failures=parsing_failures or [],
        parsed_model_structure={"fields": []},
        row_dict_by_primary={},
    )


@patch("builtins.input", return_value="yes")
def test_confirms_and_executes_each_ready_sheet(mock_input):
    orchestrator = MagicMock()
    orchestrator.build_plan.return_value = MigrationPlan(sheets=[_ready_plan("Reporter")])
    orchestrator.execute.return_value = MigrationResult(
        sheets=[SheetResult("Reporter", success_count=2, failures=[])], total_success=2
    )
    progress = MagicMock()

    run_interactive_migration(orchestrator, progress, "/path/to/data.xlsx")

    orchestrator.execute.assert_called_once()
    _, kwargs = orchestrator.execute.call_args
    assert kwargs["selected_sheets"] == {"Reporter"}


@patch("builtins.input", return_value="no")
def test_declined_sheet_is_not_selected(mock_input):
    orchestrator = MagicMock()
    orchestrator.build_plan.return_value = MigrationPlan(sheets=[_ready_plan("Reporter")])
    orchestrator.execute.return_value = MigrationResult(sheets=[], total_success=0)
    progress = MagicMock()

    run_interactive_migration(orchestrator, progress, "/path/to/data.xlsx")

    _, kwargs = orchestrator.execute.call_args
    assert kwargs["selected_sheets"] == set()


@patch("builtins.input", return_value="yes")
def test_skipped_sheet_prints_warning_and_is_not_prompted(mock_input, capsys):
    skipped = SheetPlan(
        sheet_name="Unknown",
        status="skipped",
        skip_reason="x",
        total_rows=1,
        record_count=0,
        records=[],
        parsing_failures=[],
        parsed_model_structure=None,
        row_dict_by_primary={},
    )
    orchestrator = MagicMock()
    orchestrator.build_plan.return_value = MigrationPlan(sheets=[skipped])
    orchestrator.execute.return_value = MigrationResult(sheets=[], total_success=0)

    run_interactive_migration(orchestrator, MagicMock(), "/path/to/data.xlsx")

    captured = capsys.readouterr()
    assert "Skipping sheet 'Unknown'" in captured.out
    mock_input.assert_not_called()


@patch("builtins.input", side_effect=["yes", "no"])
def test_reconstructs_parse_and_upload_breakdown_for_sheet_result(mock_input):
    parse_failure = RecordFailure("name", "p1", "parse", {"name": "p1"})
    upload_failure = RecordFailure("name", "u1", "upload", {"name": "u1"})
    orchestrator = MagicMock()
    orchestrator.build_plan.return_value = MigrationPlan(
        sheets=[_ready_plan("Reporter", record_count=3, parsing_failures=[parse_failure], total_rows=4)]
    )
    orchestrator.execute.return_value = MigrationResult(
        sheets=[SheetResult("Reporter", success_count=2, failures=[parse_failure, upload_failure])],
        total_success=2,
    )
    progress = MagicMock()

    run_interactive_migration(orchestrator, progress, "/path/to/data.xlsx")

    progress.print_sheet_result.assert_called_once_with(
        sheet_name="Reporter",
        success_count=2,
        total_rows=4,
        parsing_failures=1,
        upload_failures=1,
    )


@patch("builtins.input", side_effect=["yes", "yes", "no"])
def test_exports_failures_when_confirmed(mock_input):
    failure = RecordFailure("name", "u1", "upload", {"name": "u1"})
    orchestrator = MagicMock()
    orchestrator.build_plan.return_value = MigrationPlan(sheets=[_ready_plan("Reporter")])
    orchestrator.execute.return_value = MigrationResult(
        sheets=[SheetResult("Reporter", success_count=1, failures=[failure])], total_success=1
    )

    with patch("amplify_excel_migrator.cli.commands.FailureTracker") as mock_tracker_cls:
        tracker_instance = MagicMock()
        tracker_instance.export_to_excel.return_value = "/path/to/data_failed_records.xlsx"
        mock_tracker_cls.from_failures_by_sheet.return_value = tracker_instance

        run_interactive_migration(orchestrator, MagicMock(), "/path/to/data.xlsx")

        mock_tracker_cls.from_failures_by_sheet.assert_called_once()
        tracker_instance.export_to_excel.assert_called_once_with("/path/to/data.xlsx")
