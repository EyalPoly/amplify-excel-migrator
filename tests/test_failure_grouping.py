from amplify_excel_migrator.migration.models import RecordFailure, FieldError
from amplify_excel_migrator.migration.failure_grouping import summarize_failures


def _fe(column, value, kind, message=None):
    return FieldError(column=column, value=value, kind=kind, message=message or f"{column}:{value}:{kind}")


def _failure(*field_errors):
    return RecordFailure(
        primary_field="k", primary_field_value=1, error="e", original_row={}, field_errors=list(field_errors)
    )


def test_groups_by_column_value_kind_with_counts():
    failures = [
        _failure(_fe("group", None, "missing_required")),
        _failure(_fe("group", None, "missing_required")),
        _failure(_fe("species", "#REF!", "fk_not_found")),
    ]

    result = summarize_failures(failures)

    assert result["total_failed_rows"] == 3
    assert result["distinct"] == 2
    assert result["groups"] == [
        {
            "column": "group",
            "value": None,
            "kind": "missing_required",
            "count": 2,
            "message": "group:None:missing_required",
            "closest_existing": [],
        },
        {
            "column": "species",
            "value": "#REF!",
            "kind": "fk_not_found",
            "count": 1,
            "message": "species:#REF!:fk_not_found",
            "closest_existing": [],
        },
    ]


def test_same_column_and_kind_but_different_value_are_distinct_groups():
    failures = [
        _failure(_fe("species", "#REF!", "fk_not_found")),
        _failure(_fe("species", "N/A", "fk_not_found")),
    ]

    result = summarize_failures(failures)

    assert result["distinct"] == 2


def test_row_with_two_field_errors_contributes_to_two_groups():
    failures = [_failure(_fe("group", None, "missing_required"), _fe("species", "#REF!", "fk_not_found"))]

    result = summarize_failures(failures)

    assert result["total_failed_rows"] == 1
    assert result["distinct"] == 2
    assert {(g["column"], g["kind"]) for g in result["groups"]} == {
        ("group", "missing_required"),
        ("species", "fk_not_found"),
    }


def test_groups_sorted_by_count_desc():
    failures = [
        _failure(_fe("rare", 1, "parse")),
        _failure(_fe("common", 2, "parse")),
        _failure(_fe("common", 2, "parse")),
        _failure(_fe("common", 2, "parse")),
    ]

    result = summarize_failures(failures)

    assert [g["column"] for g in result["groups"]] == ["common", "rare"]


def test_caps_at_max_groups_but_reports_true_totals():
    failures = [
        _failure(_fe("a", 1, "parse")),
        _failure(_fe("a", 1, "parse")),
        _failure(_fe("b", 1, "parse")),
        _failure(_fe("c", 1, "parse")),
    ]

    result = summarize_failures(failures, max_groups=1)

    assert len(result["groups"]) == 1
    assert result["groups"][0]["column"] == "a"
    assert result["groups"][0]["count"] == 2
    assert result["distinct"] == 3
    assert result["total_failed_rows"] == 4


def test_max_groups_zero_yields_empty_groups_but_keeps_totals():
    failures = [_failure(_fe("a", 1, "parse")), _failure(_fe("b", 1, "parse"))]

    result = summarize_failures(failures, max_groups=0)

    assert result["groups"] == []
    assert result["distinct"] == 2
    assert result["total_failed_rows"] == 2


def test_message_is_a_representative_instance():
    failures = [
        _failure(_fe("depth", "bad", "parse", message="'depth' could not be parsed as Float (value: 'bad')")),
        _failure(_fe("depth", "bad", "parse", message="'depth' could not be parsed as Float (value: 'bad')")),
    ]

    result = summarize_failures(failures)

    assert result["groups"][0]["message"] == "'depth' could not be parsed as Float (value: 'bad')"


def test_empty_input():
    assert summarize_failures([]) == {"total_failed_rows": 0, "distinct": 0, "groups": []}


def test_failure_with_no_field_errors_counts_as_row_but_no_groups():
    result = summarize_failures([_failure()])

    assert result["total_failed_rows"] == 1
    assert result["distinct"] == 0
    assert result["groups"] == []


def test_fk_group_carries_closest_existing_from_first_seen():
    candidates = [{"name": "Qiryat Hayyim Beach", "id": "site-1", "score": 0.72}]
    fe = FieldError(
        column="site",
        value="Kiryat Haim",
        kind="fk_not_found",
        message="'site': 'Kiryat Haim' does not exist",
        closest_existing=candidates,
    )

    result = summarize_failures([_failure(fe)])

    assert result["groups"][0]["closest_existing"] == candidates


def test_non_fk_group_has_empty_closest_existing():
    result = summarize_failures([_failure(_fe("depth", "bad", "parse"))])

    assert result["groups"][0]["closest_existing"] == []
