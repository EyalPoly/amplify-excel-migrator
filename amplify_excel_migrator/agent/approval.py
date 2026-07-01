"""Approval boundary: the agent never edits or uploads without going through this."""

from typing import Dict, List, Protocol, Set

from amplify_excel_migrator.agent.models import ApprovalResult, ChangeProposal, ColumnRenameProposal


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


class RecordingApprovalHandler:
    """Test double: returns scripted decisions and records what it was asked."""

    def __init__(
        self,
        change_results: List[ApprovalResult],
        upload_selections: List[Set[str]],
        rename_results: List[ApprovalResult] = None,
    ):
        self._change_results = list(change_results)
        self._upload_selections = list(upload_selections)
        self._rename_results = list(rename_results or [])
        self.seen_proposals: List[ChangeProposal] = []
        self.seen_upload_summaries: List[Dict[str, int]] = []
        self.seen_rename_proposals: List[ColumnRenameProposal] = []

    def review_changes(self, proposal: ChangeProposal) -> ApprovalResult:
        self.seen_proposals.append(proposal)
        return self._change_results.pop(0)

    def review_upload(self, plan_summary: Dict[str, int]) -> Set[str]:
        self.seen_upload_summaries.append(plan_summary)
        return self._upload_selections.pop(0)

    def review_renames(self, proposal: ColumnRenameProposal) -> ApprovalResult:
        self.seen_rename_proposals.append(proposal)
        return self._rename_results.pop(0)
