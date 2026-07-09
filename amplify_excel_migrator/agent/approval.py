"""Approval boundary: the agent never edits or uploads without going through this."""

from typing import Dict, List, Optional, Protocol, Set

from amplify_excel_migrator.agent.models import (
    ApprovalResult,
    ChangeProposal,
    ColumnRenameProposal,
    ValueMappingProposal,
)


class ApprovalHandler(Protocol):
    def review_changes(self, proposal: ChangeProposal) -> ApprovalResult:
        """Block until the human approves/rejects each change; return the partition."""
        ...

    def review_upload(self, plan_summary: Dict[str, int]) -> Set[str]:
        """Block until the human chooses which sheets to upload; return their names."""
        ...

    def review_renames(self, proposal: ColumnRenameProposal) -> ApprovalResult:
        """Block until the human approves/rejects each rename; return the partition."""
        ...

    def review_value_mappings(self, proposal: ValueMappingProposal) -> ApprovalResult:
        """Block until the human approves/rejects each value mapping; return the partition."""
        ...

    def answer(self, question: str) -> str:
        """Block until the human answers a free-form question; return the answer text."""
        ...


class RecordingApprovalHandler:
    """Test double: returns scripted decisions and records what it was asked."""

    def __init__(
        self,
        change_results: List[ApprovalResult],
        upload_selections: List[Set[str]],
        rename_results: Optional[List[ApprovalResult]] = None,
        value_mapping_results: Optional[List[ApprovalResult]] = None,
        answers: Optional[List[str]] = None,
    ):
        self._change_results = list(change_results)
        self._upload_selections = list(upload_selections)
        self._rename_results = list(rename_results or [])
        self._value_mapping_results = list(value_mapping_results or [])
        self._answers = list(answers or [])
        self.seen_proposals: List[ChangeProposal] = []
        self.seen_upload_summaries: List[Dict[str, int]] = []
        self.seen_rename_proposals: List[ColumnRenameProposal] = []
        self.seen_value_mapping_proposals: List[ValueMappingProposal] = []
        self.seen_questions: List[str] = []

    def review_changes(self, proposal: ChangeProposal) -> ApprovalResult:
        self.seen_proposals.append(proposal)
        return self._change_results.pop(0)

    def review_upload(self, plan_summary: Dict[str, int]) -> Set[str]:
        self.seen_upload_summaries.append(plan_summary)
        return self._upload_selections.pop(0)

    def review_renames(self, proposal: ColumnRenameProposal) -> ApprovalResult:
        self.seen_rename_proposals.append(proposal)
        return self._rename_results.pop(0)

    def review_value_mappings(self, proposal: ValueMappingProposal) -> ApprovalResult:
        self.seen_value_mapping_proposals.append(proposal)
        return self._value_mapping_results.pop(0)

    def answer(self, question: str) -> str:
        self.seen_questions.append(question)
        return self._answers.pop(0)
