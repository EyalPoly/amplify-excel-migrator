"""Group dry-run parsing failures by cause so an agent perceives a handful of
distinct problems instead of thousands of individually-failing rows."""

from collections import Counter
from typing import Any, Dict, List

from amplify_excel_migrator.migration.models import RecordFailure


def summarize_failures(failures: List[RecordFailure], max_groups: int = 50) -> Dict[str, Any]:
    """Collapse failures into count-ranked groups keyed by the exact error string.

    Returns {"total": <all failures>, "distinct": <distinct error strings>,
    "groups": [{"error", "count"}, ...]} sorted by count desc, capped at max_groups.
    max_groups <= 0 yields an empty groups list (totals still reported).
    """
    counts = Counter(f.error for f in failures)
    groups = [{"error": error, "count": count} for error, count in counts.most_common(max_groups)]
    return {"total": len(failures), "distinct": len(counts), "groups": groups}
