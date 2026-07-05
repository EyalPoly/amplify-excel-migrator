"""Group dry-run parsing failures by the individual field-error (column, value, kind)
so an agent perceives a handful of distinct problems instead of thousands of
individually-failing rows, and can act on a specific (column, value)."""

from typing import Any, Dict, List, Tuple

from amplify_excel_migrator.migration.models import RecordFailure


def summarize_failures(failures: List[RecordFailure], max_groups: int = 50) -> Dict[str, Any]:
    """Flatten every failure's field_errors and group them by (column, value, kind).

    Returns {"total_failed_rows": <len(failures)>, "distinct": <distinct groups>,
    "groups": [{"column", "value", "kind", "count", "message"}, ...]} sorted by count
    desc (ties keep first-seen order), capped at max_groups. max_groups <= 0 yields an
    empty groups list (totals still reported). "distinct" is the true count regardless
    of the cap. "message" is a representative instance for the group.
    """
    groups: Dict[Tuple[Any, Any, str], Dict[str, Any]] = {}
    for failure in failures:
        for fe in failure.field_errors:
            key = (fe.column, fe.value, fe.kind)
            group = groups.get(key)
            if group is None:
                groups[key] = {
                    "column": fe.column,
                    "value": fe.value,
                    "kind": fe.kind,
                    "count": 1,
                    "message": fe.message,
                }
            else:
                group["count"] += 1

    ordered = sorted(groups.values(), key=lambda g: g["count"], reverse=True)
    capped = ordered[:max_groups] if max_groups > 0 else []
    return {"total_failed_rows": len(failures), "distinct": len(groups), "groups": capped}
