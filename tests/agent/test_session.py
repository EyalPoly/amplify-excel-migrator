import pandas as pd

from amplify_excel_migrator.agent.llm.base import AssistantTurn, LLMProvider, ToolCall
from amplify_excel_migrator.agent.workbook import WorkbookEditor
from amplify_excel_migrator.agent.approval import RecordingApprovalHandler
from amplify_excel_migrator.agent.models import ApprovalResult
from amplify_excel_migrator.agent.session import AgentSession
from amplify_excel_migrator.migration.models import (
    MigrationPlan,
    MigrationResult,
    SheetPlan,
    SheetResult,
)


class ScriptedProvider(LLMProvider):
    """Returns a fixed list of turns, one per generate() call."""

    def __init__(self, turns):
        self._turns = list(turns)

    def generate(self, system, messages, tools):
        return self._turns.pop(0)


def _ready_plan():
    return MigrationPlan(
        sheets=[
            SheetPlan(
                sheet_name="Reporter",
                status="ready",
                skip_reason=None,
                total_rows=2,
                record_count=2,
                records=[{"name": "a"}, {"name": "b"}],
                parsing_failures=[],
                parsed_model_structure={"fields": []},
                row_dict_by_primary={},
            )
        ]
    )


def _make_session(provider, handler, events):
    workbook = WorkbookEditor({"Reporter": pd.DataFrame({"name": ["a", "b"], "country": ["IL", ""]})})

    orchestrator = type("O", (), {})()
    orchestrator.build_plan = lambda: _ready_plan()
    orchestrator.execute = lambda plan, selected_sheets=None: MigrationResult(
        sheets=[SheetResult("Reporter", success_count=2, failures=[])], total_success=2
    )

    return AgentSession(
        provider=provider,
        orchestrator_factory=lambda path: orchestrator,
        workbook=workbook,
        approval_handler=handler,
        schema_provider=lambda model=None: {"models": ["Reporter"]},
        event_sink=events.append,
    )


def test_session_applies_approved_changes_then_uploads():
    turns = [
        AssistantTurn(
            text="I'll fill the missing country.",
            tool_calls=[
                ToolCall(
                    "c1",
                    "propose_changes",
                    {
                        "summary": "fill country",
                        "changes": [
                            {
                                "sheet_name": "Reporter",
                                "row": 1,
                                "column": "country",
                                "proposed_value": "EG",
                                "rationale": "missing",
                            }
                        ],
                    },
                )
            ],
        ),
        AssistantTurn(text="Uploading.", tool_calls=[ToolCall("c2", "upload", {})]),
        AssistantTurn(text="All done.", tool_calls=[]),
    ]
    handler = RecordingApprovalHandler(
        change_results=[ApprovalResult(approved_ids=["Reporter:1:country"], rejected_ids=[])],
        upload_selections=[{"Reporter"}],
    )
    events = []
    session = _make_session(ScriptedProvider(turns), handler, events)

    session.run("Migrate this workbook.")

    # approved change was applied to the workbook
    assert session.workbook.cell("Reporter", 1, "country") == "EG"
    # the human saw the proposal and the upload summary
    assert handler.seen_proposals[0].changes[0].proposed_value == "EG"
    assert handler.seen_upload_summaries == [{"Reporter": 2}]
    # an upload_result event was emitted and the run finished
    kinds = [e.kind for e in events]
    assert "proposal" in kinds and "upload_result" in kinds and kinds[-1] == "done"


def test_rejected_change_is_not_applied():
    turns = [
        AssistantTurn(
            text="",
            tool_calls=[
                ToolCall(
                    "c1",
                    "propose_changes",
                    {
                        "summary": "x",
                        "changes": [
                            {
                                "sheet_name": "Reporter",
                                "row": 1,
                                "column": "country",
                                "proposed_value": "EG",
                                "rationale": "guess",
                            }
                        ],
                    },
                )
            ],
        ),
        AssistantTurn(text="ok", tool_calls=[]),
    ]
    handler = RecordingApprovalHandler(
        change_results=[ApprovalResult(approved_ids=[], rejected_ids=["Reporter:1:country"])],
        upload_selections=[],
    )
    events = []
    session = _make_session(ScriptedProvider(turns), handler, events)

    session.run("go")

    assert session.workbook.cell("Reporter", 1, "country") == ""  # unchanged


def test_max_turns_guard_stops_runaway_loop():
    # provider always asks to read a sheet, never ends
    class Loop(LLMProvider):
        def generate(self, system, messages, tools):
            return AssistantTurn(text="", tool_calls=[ToolCall("c", "read_sheet", {"sheet": "Reporter"})])

    events = []
    session = _make_session(Loop(), RecordingApprovalHandler([], []), events)
    session.run("go", max_turns=3)

    assert sum(1 for e in events if e.kind == "tool_call") == 3
    assert events[-1].kind == "error"
