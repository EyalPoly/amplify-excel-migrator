from amplify_excel_migrator.agent.approval import RecordingApprovalHandler
from amplify_excel_migrator.agent.models import ChangeProposal, ProposedChange, ApprovalResult


def test_recording_handler_returns_scripted_results():
    proposal = ChangeProposal(
        summary="s",
        changes=[
            ProposedChange("a", "Reporter", 0, "country", "", "EG", "r"),
        ],
    )
    handler = RecordingApprovalHandler(
        change_results=[ApprovalResult(approved_ids=["a"], rejected_ids=[])],
        upload_selections=[{"Reporter"}],
    )

    result = handler.review_changes(proposal)
    selection = handler.review_upload({"Reporter": 5})

    assert result.approved_ids == ["a"]
    assert selection == {"Reporter"}
    assert handler.seen_proposals == [proposal]
    assert handler.seen_upload_summaries == [{"Reporter": 5}]
