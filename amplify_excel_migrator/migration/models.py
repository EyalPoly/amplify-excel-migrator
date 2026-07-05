"""Structured plan and result objects for the headless migration engine."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldError:
    column: Optional[str]
    value: Any
    kind: str
    message: str


@dataclass
class RecordFailure:
    primary_field: str
    primary_field_value: Any
    error: str
    original_row: Dict[str, Any]
    field_errors: List[FieldError] = field(default_factory=list)


@dataclass
class SheetPlan:
    sheet_name: str
    status: str  # "ready" | "skipped"
    skip_reason: Optional[str]
    total_rows: int
    record_count: int
    records: List[Any]
    parsing_failures: List[RecordFailure]
    parsed_model_structure: Optional[Dict[str, Any]]
    row_dict_by_primary: Dict[str, Dict[str, Any]]


@dataclass
class MigrationPlan:
    sheets: List[SheetPlan] = field(default_factory=list)


@dataclass
class SheetResult:
    sheet_name: str
    success_count: int
    failures: List[RecordFailure]


@dataclass
class MigrationResult:
    sheets: List[SheetResult]
    total_success: int

    def all_failures(self) -> List[RecordFailure]:
        return [failure for sheet in self.sheets for failure in sheet.failures]
