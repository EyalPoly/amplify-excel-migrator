"""Tests for the headless MigrationOrchestrator (plan/execute)."""

import pytest
from unittest.mock import MagicMock
import pandas as pd

from amplify_excel_migrator.migration.orchestrator import MigrationOrchestrator
from amplify_excel_migrator.migration.models import RecordFailure


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
    mock_field_parser,
    mock_batch_uploader,
):
    return MigrationOrchestrator(
        excel_reader=mock_excel_reader,
        data_transformer=mock_data_transformer,
        amplify_client=mock_amplify_client,
        field_parser=mock_field_parser,
        batch_uploader=mock_batch_uploader,
    )


class TestBuildPlan:
    def test_builds_ready_sheet_with_record_count(self, orchestrator, mock_excel_reader):
        df = pd.DataFrame({"name": ["a", "b"]})
        mock_excel_reader.read_all_sheets.return_value = {"Reporter": df}
        orchestrator._get_parsed_model_structure = MagicMock(return_value={"fields": []})
        orchestrator._transform_rows_to_records = MagicMock(
            return_value=([{"name": "a"}, {"name": "b"}], {"a": {"name": "a"}}, [])
        )

        plan = orchestrator.build_plan()

        assert len(plan.sheets) == 1
        sheet = plan.sheets[0]
        assert sheet.sheet_name == "Reporter"
        assert sheet.status == "ready"
        assert sheet.record_count == 2
        assert sheet.total_rows == 2

    def test_captures_parsing_failures_in_plan(self, orchestrator, mock_excel_reader):
        df = pd.DataFrame({"name": ["a"]})
        mock_excel_reader.read_all_sheets.return_value = {"Reporter": df}
        failure = RecordFailure("name", "a", "bad", {"name": "a"})
        orchestrator._get_parsed_model_structure = MagicMock(return_value={"fields": []})
        orchestrator._transform_rows_to_records = MagicMock(return_value=([], {}, [failure]))

        plan = orchestrator.build_plan()

        assert plan.sheets[0].parsing_failures == [failure]

    def test_marks_sheet_skipped_when_model_not_found(self, orchestrator, mock_excel_reader):
        df = pd.DataFrame({"name": ["a"]})
        mock_excel_reader.read_all_sheets.return_value = {"Unknown": df}
        orchestrator._get_parsed_model_structure = MagicMock(
            side_effect=ValueError("Introspection result cannot be empty")
        )

        plan = orchestrator.build_plan()

        sheet = plan.sheets[0]
        assert sheet.status == "skipped"
        assert "Introspection result cannot be empty" in sheet.skip_reason
        assert sheet.record_count == 0

    def test_does_not_upload_during_planning(self, orchestrator, mock_excel_reader, mock_batch_uploader):
        df = pd.DataFrame({"name": ["a"]})
        mock_excel_reader.read_all_sheets.return_value = {"Reporter": df}
        orchestrator._get_parsed_model_structure = MagicMock(return_value={"fields": []})
        orchestrator._transform_rows_to_records = MagicMock(return_value=([{"name": "a"}], {}, []))

        orchestrator.build_plan()

        mock_batch_uploader.upload_records.assert_not_called()

    def test_does_not_mutate_input_frames(
        self, orchestrator, mock_excel_reader, mock_amplify_client, mock_data_transformer
    ):
        df = pd.DataFrame({"Reporter Name": ["a"], "ERROR": ["x"]})
        original = df.copy()
        mock_excel_reader.read_all_sheets.return_value = {"Reporter": df}
        orchestrator._get_parsed_model_structure = MagicMock(return_value={"fields": []})
        mock_amplify_client.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        mock_amplify_client.build_foreign_key_lookups = MagicMock(return_value={})
        mock_data_transformer.to_camel_case = lambda s: s.replace(" ", "").lower()
        mock_data_transformer.transform_rows_to_records = MagicMock(return_value=([], {}, []))

        orchestrator.build_plan()

        pd.testing.assert_frame_equal(df, original)


def _ready_sheet_plan(sheet_name="Reporter", records=None, parsing_failures=None, row_dict=None):
    from amplify_excel_migrator.migration.models import SheetPlan

    records = records if records is not None else [{"name": "a"}]
    return SheetPlan(
        sheet_name=sheet_name,
        status="ready",
        skip_reason=None,
        total_rows=len(records) + (len(parsing_failures) if parsing_failures else 0),
        record_count=len(records),
        records=records,
        parsing_failures=parsing_failures or [],
        parsed_model_structure={"fields": []},
        row_dict_by_primary=row_dict or {},
    )


class TestExecute:
    def test_uploads_selected_sheet_and_counts_success(self, orchestrator, mock_batch_uploader):
        from amplify_excel_migrator.migration.models import MigrationPlan

        plan = MigrationPlan(sheets=[_ready_sheet_plan(records=[{"name": "a"}, {"name": "b"}])])
        mock_batch_uploader.upload_records.return_value = (2, 0, [])

        result = orchestrator.execute(plan, selected_sheets={"Reporter"})

        assert result.total_success == 2
        assert result.sheets[0].success_count == 2
        mock_batch_uploader.upload_records.assert_called_once_with(
            [{"name": "a"}, {"name": "b"}], "Reporter", {"fields": []}
        )

    def test_skips_unselected_sheets(self, orchestrator, mock_batch_uploader):
        from amplify_excel_migrator.migration.models import MigrationPlan

        plan = MigrationPlan(sheets=[_ready_sheet_plan("Reporter"), _ready_sheet_plan("Article")])
        mock_batch_uploader.upload_records.return_value = (1, 0, [])

        result = orchestrator.execute(plan, selected_sheets={"Reporter"})

        assert [s.sheet_name for s in result.sheets] == ["Reporter"]
        assert mock_batch_uploader.upload_records.call_count == 1

    def test_none_selection_uploads_all_ready_sheets(self, orchestrator, mock_batch_uploader):
        from amplify_excel_migrator.migration.models import MigrationPlan

        plan = MigrationPlan(sheets=[_ready_sheet_plan("Reporter"), _ready_sheet_plan("Article")])
        mock_batch_uploader.upload_records.return_value = (1, 0, [])

        result = orchestrator.execute(plan)

        assert {s.sheet_name for s in result.sheets} == {"Reporter", "Article"}

    def test_empty_selection_uploads_nothing(self, orchestrator, mock_batch_uploader):
        from amplify_excel_migrator.migration.models import MigrationPlan

        plan = MigrationPlan(sheets=[_ready_sheet_plan("Reporter")])

        result = orchestrator.execute(plan, selected_sheets=set())

        assert result.sheets == []
        assert result.total_success == 0
        mock_batch_uploader.upload_records.assert_not_called()

    def test_skipped_sheets_are_never_executed(self, orchestrator, mock_batch_uploader):
        from amplify_excel_migrator.migration.models import MigrationPlan, SheetPlan

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
        plan = MigrationPlan(sheets=[skipped])

        result = orchestrator.execute(plan)

        assert result.sheets == []
        mock_batch_uploader.upload_records.assert_not_called()

    def test_merges_parsing_and_upload_failures(self, orchestrator, mock_batch_uploader):
        from amplify_excel_migrator.migration.models import MigrationPlan

        parse_failure = RecordFailure("name", "p1", "parse error", {"name": "p1"})
        sheet = _ready_sheet_plan(
            records=[{"name": "u1"}],
            parsing_failures=[parse_failure],
            row_dict={"u1": {"name": "u1"}},
        )
        plan = MigrationPlan(sheets=[sheet])
        mock_batch_uploader.upload_records.return_value = (
            0,
            1,
            [{"primary_field": "name", "primary_field_value": "u1", "error": "upload error"}],
        )

        result = orchestrator.execute(plan)

        failures = result.sheets[0].failures
        assert [f.error for f in failures] == ["parse error", "upload error"]
        assert failures[1].original_row == {"name": "u1"}


class TestTransformRowsToRecords:
    def test_returns_parse_failures_as_record_failures(self, orchestrator, mock_data_transformer):
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
        mock_data_transformer.transform_rows_to_records = MagicMock(return_value=([], {}, failed_rows))

        records, row_dict, parsing_failures = orchestrator._transform_rows_to_records(df, parsed_model, "TestSheet")

        assert records == []
        assert len(parsing_failures) == 1
        assert parsing_failures[0].error == "Transform error"
        assert parsing_failures[0].original_row == {"name": "Test"}

    def test_builds_foreign_key_lookups(self, orchestrator, mock_amplify_client):
        df = pd.DataFrame({"name": ["Test"]})
        parsed_model = {"fields": []}
        orchestrator.data_transformer.to_camel_case = lambda s: s
        orchestrator.amplify_client.get_primary_field_name = MagicMock(return_value=("name", False, "String"))
        mock_amplify_client.build_foreign_key_lookups = MagicMock(return_value={"Reporter": {}})
        orchestrator.data_transformer.transform_rows_to_records = MagicMock(return_value=([], {}, []))

        orchestrator._transform_rows_to_records(df, parsed_model, "TestSheet")

        mock_amplify_client.build_foreign_key_lookups.assert_called_once()
        passed_df, passed_model = mock_amplify_client.build_foreign_key_lookups.call_args[0]
        pd.testing.assert_frame_equal(passed_df, df)
        assert passed_df is not df  # planning works on a copy, never the caller's frame
        assert passed_model is parsed_model


class TestGetParsedModelStructure:
    def test_gets_model_structure_from_client(self, orchestrator, mock_amplify_client):
        mock_amplify_client.get_model_structure.return_value = {"fields": [{"name": "id"}]}
        orchestrator.field_parser.parse_model_structure = MagicMock(return_value={"fields": [{"name": "id"}]})

        orchestrator._get_parsed_model_structure("TestModel")

        mock_amplify_client.get_model_structure.assert_called_once_with("TestModel")

    def test_embeds_custom_type_sub_fields_into_field(self, orchestrator, mock_amplify_client, mock_field_parser):
        mock_amplify_client.get_model_structure.side_effect = [{"name": "Observation"}, {"name": "IndividualGroup"}]
        mock_field_parser.parse_model_structure.side_effect = [
            {
                "name": "Observation",
                "fields": [
                    {"name": "individualGroups", "type": "IndividualGroup", "is_custom_type": True},
                    {"name": "date", "type": "AWSDate", "is_custom_type": False},
                ],
            },
            {"name": "IndividualGroup", "fields": [{"name": "length", "type": "Float", "is_required": False}]},
        ]

        result = orchestrator._get_parsed_model_structure("Observation")

        groups_field = next(f for f in result["fields"] if f["name"] == "individualGroups")
        assert groups_field["custom_type_fields"] == [{"name": "length", "type": "Float", "is_required": False}]

    def test_raises_clear_error_when_custom_type_not_in_schema(
        self, orchestrator, mock_amplify_client, mock_field_parser
    ):
        mock_amplify_client.get_model_structure.return_value = {"name": "Observation"}
        mock_field_parser.parse_model_structure.side_effect = [
            {
                "name": "Observation",
                "fields": [{"name": "individualGroups", "type": "IndividualGroup", "is_custom_type": True}],
            },
            ValueError("Introspection result cannot be empty"),
        ]

        with pytest.raises(ValueError, match="IndividualGroup"):
            orchestrator._get_parsed_model_structure("Observation")
