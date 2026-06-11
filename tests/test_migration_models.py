"""Tests for migration plan/result dataclasses."""

from amplify_excel_migrator.migration.models import (
    RecordFailure,
    SheetPlan,
    MigrationPlan,
    SheetResult,
    MigrationResult,
)


def _failure(value="r1", error="bad"):
    return RecordFailure(
        primary_field="name",
        primary_field_value=value,
        error=error,
        original_row={"name": value},
    )


def test_all_failures_flattens_across_sheets():
    result = MigrationResult(
        sheets=[
            SheetResult(sheet_name="A", success_count=1, failures=[_failure("a1")]),
            SheetResult(sheet_name="B", success_count=0, failures=[_failure("b1"), _failure("b2")]),
        ],
        total_success=1,
    )

    all_failures = result.all_failures()

    assert [f.primary_field_value for f in all_failures] == ["a1", "b1", "b2"]


def test_all_failures_empty_when_no_failures():
    result = MigrationResult(
        sheets=[SheetResult(sheet_name="A", success_count=3, failures=[])],
        total_success=3,
    )

    assert result.all_failures() == []


def test_sheet_plan_holds_records_and_parse_failures():
    plan = SheetPlan(
        sheet_name="A",
        status="ready",
        skip_reason=None,
        total_rows=3,
        record_count=2,
        records=[{"name": "a1"}, {"name": "a2"}],
        parsing_failures=[_failure("a3")],
        parsed_model_structure={"fields": []},
        row_dict_by_primary={"a1": {"name": "a1"}},
    )

    assert plan.record_count == 2
    assert len(plan.parsing_failures) == 1
    assert MigrationPlan(sheets=[plan]).sheets[0].sheet_name == "A"


def test_skipped_sheet_plan_carries_reason():
    plan = SheetPlan(
        sheet_name="Unknown",
        status="skipped",
        skip_reason="no matching model",
        total_rows=5,
        record_count=0,
        records=[],
        parsing_failures=[],
        parsed_model_structure=None,
        row_dict_by_primary={},
    )

    assert plan.status == "skipped"
    assert plan.skip_reason == "no matching model"
