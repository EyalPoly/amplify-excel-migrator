"""Tests for migration plan/result dataclasses."""

from amplify_excel_migrator.migration.models import (
    RecordFailure,
    FieldError,
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


def test_field_error_carries_column_value_kind_message():
    fe = FieldError(column="species", value="#REF!", kind="fk_not_found", message="'species': '#REF!' does not exist")
    assert fe.column == "species"
    assert fe.value == "#REF!"
    assert fe.kind == "fk_not_found"
    assert fe.message == "'species': '#REF!' does not exist"


def test_field_error_allows_none_column_and_value():
    fe = FieldError(column=None, value=None, kind="other", message="boom")
    assert fe.column is None
    assert fe.value is None


def test_record_failure_field_errors_defaults_to_empty_list():
    f = RecordFailure(primary_field="k", primary_field_value=1, error="e", original_row={})
    assert f.field_errors == []


def test_record_failure_carries_field_errors():
    fe = FieldError(column="group", value=None, kind="missing_required", message="Required field 'group' is missing")
    f = RecordFailure(primary_field="k", primary_field_value=1, error="e", original_row={}, field_errors=[fe])
    assert f.field_errors == [fe]


def test_field_error_closest_existing_defaults_to_empty_list():
    fe = FieldError(column="site", value="Kiryat Haim", kind="fk_not_found", message="m")
    assert fe.closest_existing == []


def test_field_error_carries_closest_existing():
    candidates = [{"name": "Qiryat Hayyim Beach", "id": "site-1", "score": 0.72}]
    fe = FieldError(column="site", value="Kiryat Haim", kind="fk_not_found", message="m", closest_existing=candidates)
    assert fe.closest_existing == candidates
