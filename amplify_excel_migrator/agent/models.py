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
class ApprovalResult:
    approved_ids: List[str] = field(default_factory=list)
    rejected_ids: List[str] = field(default_factory=list)

    def is_approved(self, change_id: str) -> bool:
        return change_id in self.approved_ids


@dataclass
class AgentEvent:
    kind: str  # "message" | "tool_call" | "proposal" | "dry_run" | "upload_result" | "done" | "error"
    payload: Dict[str, Any]
