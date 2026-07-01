from amplify_excel_migrator.agent.models import (
    ProposedChange,
    ChangeProposal,
    ApprovalResult,
    AgentEvent,
    ColumnRename,
    ColumnRenameProposal,
)


def _change(idx=0):
    return ProposedChange(
        id=f"chg-{idx}",
        sheet_name="Reporter",
        row=1,
        column="country",
        current_value="",
        proposed_value="EG",
        rationale="Filled missing country from city.",
    )


def test_proposal_groups_changes():
    proposal = ChangeProposal(summary="2 fixes", changes=[_change(0), _change(1)])
    assert len(proposal.changes) == 2
    assert proposal.change_ids() == ["chg-0", "chg-1"]


def test_approval_result_partitions_ids():
    result = ApprovalResult(approved_ids=["chg-0"], rejected_ids=["chg-1"])
    assert result.is_approved("chg-0") is True
    assert result.is_approved("chg-1") is False


def test_agent_event_carries_kind_and_payload():
    ev = AgentEvent(kind="message", payload={"text": "hi"})
    assert ev.kind == "message"
    assert ev.payload["text"] == "hi"


def _rename():
    return ColumnRename(
        id="Reporter:Report type->observationMethod",
        sheet_name="Reporter",
        current_name="Report type",
        new_name="observationMethod",
        rationale="header maps to schema field",
    )


def test_rename_proposal_groups_renames():
    proposal = ColumnRenameProposal(summary="1 rename", renames=[_rename()])
    assert len(proposal.renames) == 1
    assert proposal.rename_ids() == ["Reporter:Report type->observationMethod"]
