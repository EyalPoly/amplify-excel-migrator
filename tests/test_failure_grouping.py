from amplify_excel_migrator.migration.models import RecordFailure
from amplify_excel_migrator.migration.failure_grouping import summarize_failures


def _f(error):
    return RecordFailure(primary_field="k", primary_field_value=1, error=error, original_row={})


def test_identical_errors_collapse_with_counts():
    result = summarize_failures([_f("E1"), _f("E1"), _f("E1"), _f("E2")])
    assert result["total"] == 4
    assert result["distinct"] == 2
    assert result["groups"] == [{"error": "E1", "count": 3}, {"error": "E2", "count": 1}]


def test_groups_sorted_by_count_desc():
    result = summarize_failures([_f("rare"), _f("common"), _f("common"), _f("common")])
    assert [g["error"] for g in result["groups"]] == ["common", "rare"]


def test_caps_at_max_groups_but_reports_true_totals():
    failures = [_f("A"), _f("A"), _f("B"), _f("C")]  # 3 distinct, 4 total
    result = summarize_failures(failures, max_groups=1)
    assert len(result["groups"]) == 1
    assert result["groups"][0] == {"error": "A", "count": 2}
    assert result["distinct"] == 3
    assert result["total"] == 4


def test_empty_input():
    assert summarize_failures([]) == {"total": 0, "distinct": 0, "groups": []}
