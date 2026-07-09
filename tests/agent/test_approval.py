from amplify_excel_migrator.agent.approval import RecordingApprovalHandler
from amplify_excel_migrator.agent.models import (
    ChangeProposal,
    ProposedChange,
    ApprovalResult,
    ColumnRename,
    ColumnRenameProposal,
    ValueMapping,
    ValueMappingProposal,
)


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


def test_recording_handler_returns_scripted_rename_results():
    proposal = ColumnRenameProposal(
        summary="s",
        renames=[
            ColumnRename(
                "Reporter:Report type->observationMethod",
                "Reporter",
                "Report type",
                "observationMethod",
                "r",
            )
        ],
    )
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        rename_results=[ApprovalResult(approved_ids=["Reporter:Report type->observationMethod"], rejected_ids=[])],
    )

    result = handler.review_renames(proposal)

    assert result.approved_ids == ["Reporter:Report type->observationMethod"]
    assert handler.seen_rename_proposals == [proposal]


def test_recording_handler_returns_scripted_value_mapping_results():
    proposal = ValueMappingProposal(
        summary="s",
        mappings=[
            ValueMapping("Reporter:species:#REF!->UNKNOWN", "Reporter", "species", "#REF!", "UNKNOWN", "r"),
        ],
    )
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=["Reporter:species:#REF!->UNKNOWN"], rejected_ids=[])],
    )

    result = handler.review_value_mappings(proposal)

    assert result.approved_ids == ["Reporter:species:#REF!->UNKNOWN"]
    assert handler.seen_value_mapping_proposals == [proposal]


def test_value_mapping_proposal_lists_ids():
    proposal = ValueMappingProposal(
        summary="s",
        mappings=[
            ValueMapping("Reporter:species:#REF!->UNKNOWN", "Reporter", "species", "#REF!", "UNKNOWN", "r"),
            ValueMapping("Reporter:species:None->UNKNOWN", "Reporter", "species", None, "UNKNOWN", "r"),
        ],
    )
    assert proposal.mapping_ids() == ["Reporter:species:#REF!->UNKNOWN", "Reporter:species:None->UNKNOWN"]


def test_recording_handler_answers_and_records_questions():
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        answers=["group-42"],
    )

    answer = handler.answer("What is a valid group id?")

    assert answer == "group-42"
    assert handler.seen_questions == ["What is a valid group id?"]
