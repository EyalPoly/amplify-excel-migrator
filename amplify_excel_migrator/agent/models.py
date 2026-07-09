"""Structured proposal/approval/event types for the agent engine."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ProposedChange:
    id: str
    sheet_name: str
    row: int
    column: str
    current_value: Any
    proposed_value: Any
    rationale: str


@dataclass
class ChangeProposal:
    summary: str
    changes: List[ProposedChange]

    def change_ids(self) -> List[str]:
        return [c.id for c in self.changes]


@dataclass
class ColumnRename:
    id: str
    sheet_name: str
    current_name: str
    new_name: str
    rationale: str


@dataclass
class ColumnRenameProposal:
    summary: str
    renames: List[ColumnRename]

    def rename_ids(self) -> List[str]:
        return [r.id for r in self.renames]


@dataclass
class ValueMapping:
    id: str
    sheet_name: str
    column: str
    from_value: Any
    to_value: Any
    rationale: str


@dataclass
class ValueMappingProposal:
    summary: str
    mappings: List[ValueMapping]

    def mapping_ids(self) -> List[str]:
        return [m.id for m in self.mappings]


@dataclass
class ApprovalResult:
    approved_ids: List[str] = field(default_factory=list)
    rejected_ids: List[str] = field(default_factory=list)

    def is_approved(self, change_id: str) -> bool:
        return change_id in self.approved_ids


@dataclass
class AgentEvent:
    kind: str  # "message" | "tool_call" | "proposal" | "dry_run" | "question" | "upload_result" | "done" | "error"
    payload: Dict[str, Any]
