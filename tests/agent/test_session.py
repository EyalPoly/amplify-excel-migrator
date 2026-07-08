import json

import pandas as pd

from amplify_excel_migrator.agent.llm.base import AssistantTurn, LLMProvider, ToolCall
from amplify_excel_migrator.agent.workbook import WorkbookEditor
from amplify_excel_migrator.agent.approval import RecordingApprovalHandler
from amplify_excel_migrator.agent.models import ApprovalResult
from amplify_excel_migrator.agent.session import AgentSession, _DRY_RUN_REQUIRED
from amplify_excel_migrator.migration.models import (
    MigrationPlan,
    MigrationResult,
    RecordFailure,
    SheetPlan,
    SheetResult,
    FieldError,
)


class ScriptedProvider(LLMProvider):
    """Returns a fixed list of turns, one per generate() call."""

    def __init__(self, turns):
        self._turns = list(turns)

    def generate(self, system, messages, tools):
        return self._turns.pop(0)


class RepeatingRecorder(LLMProvider):
    """Always returns the same failing turn; records the messages passed to each generate()."""

    def __init__(self, turn):
        self._turn = turn
        self.seen_messages = []

    def generate(self, system, messages, tools):
        self.seen_messages.append(list(messages))
        return self._turn


def _failing_propose_turn():
    return AssistantTurn(
        text="",
        tool_calls=[
            ToolCall(
                "c1",
                "propose_changes",
                {
                    "summary": "x",
                    "changes": [
                        {"sheet_name": "Reporter", "column": "country", "proposed_value": "EG", "rationale": "r"}
                    ],
                },
            )
        ],
    )


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


class RecordingOrchestrator:
    """Fake orchestrator that logs call order and the frames it is handed."""

    def __init__(self):
        self.calls = []
        self.set_sheets_args = []

    def set_sheets(self, sheets):
        self.calls.append("set_sheets")
        self.set_sheets_args.append(sheets)

    def build_plan(self):
        self.calls.append("build_plan")
        return _ready_plan()

    def execute(self, plan, selected_sheets=None):
        self.calls.append("execute")
        return MigrationResult(sheets=[SheetResult("Reporter", success_count=2, failures=[])], total_success=2)


def _make_session(provider, handler, events, max_nudges=2):
    workbook = WorkbookEditor({"Reporter": pd.DataFrame({"name": ["a", "b"], "country": ["IL", ""]})})

    return AgentSession(
        provider=provider,
        orchestrator=RecordingOrchestrator(),
        workbook=workbook,
        approval_handler=handler,
        schema_provider=lambda model=None: {"models": ["Reporter"]},
        event_sink=events.append,
        max_nudges=max_nudges,
    )


def _rename_workbook():
    return WorkbookEditor({"Reporter": pd.DataFrame({"name": ["a", "b"], "Report type": ["x", "y"]})})


def _rename_schema(model=None):
    fields = {"Reporter": ["name", "country", "observationMethod"]}.get(model, [])
    return {"fields": [{"name": f} for f in fields]}


def _make_rename_session(turns, handler, events, workbook=None, schema_provider=None):
    return AgentSession(
        provider=ScriptedProvider(turns),
        orchestrator=RecordingOrchestrator(),
        workbook=workbook or _rename_workbook(),
        approval_handler=handler,
        schema_provider=schema_provider or _rename_schema,
        event_sink=events.append,
    )


def _rename_turn(renames, call_id="r1"):
    return AssistantTurn(
        text="",
        tool_calls=[ToolCall(call_id, "propose_column_renames", {"summary": "fix headers", "renames": renames})],
    )


def _mapping_workbook():
    return WorkbookEditor({"Reporter": pd.DataFrame({"species": ["#REF!", "cat", "#REF!"], "site": [None, "x", None]})})


def _make_mapping_session(turns, handler, events, workbook=None):
    return AgentSession(
        provider=ScriptedProvider(turns),
        orchestrator=RecordingOrchestrator(),
        workbook=workbook or _mapping_workbook(),
        approval_handler=handler,
        schema_provider=lambda model=None: {"models": ["Reporter"]},
        event_sink=events.append,
    )


def _mapping_turn(mappings, call_id="m1"):
    return AssistantTurn(
        text="",
        tool_calls=[ToolCall(call_id, "propose_value_mappings", {"summary": "fix values", "mappings": mappings})],
    )


def _finish_turn():
    return AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})])


def _dry_run_turn(call_id="d0"):
    return AssistantTurn(text="", tool_calls=[ToolCall(call_id, "dry_run", {})])


def test_approved_value_mapping_rewrites_all_matching_rows():
    turns = [
        _dry_run_turn(),
        _mapping_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "column": "species",
                    "from_value": "#REF!",
                    "to_value": "UNKNOWN",
                    "rationale": "r",
                }
            ]
        ),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=["Reporter:species:#REF!->UNKNOWN"], rejected_ids=[])],
    )
    events = []
    session = _make_mapping_session(turns, handler, events)

    session.run("go")

    assert list(session.workbook.sheets()["Reporter"]["species"]) == ["UNKNOWN", "cat", "UNKNOWN"]
    assert "value_mapping_proposal" in [e.kind for e in events]


def test_null_from_value_fills_blank_cells():
    turns = [
        _dry_run_turn(),
        _mapping_turn(
            [{"sheet_name": "Reporter", "column": "site", "from_value": None, "to_value": "UNKNOWN", "rationale": "r"}]
        ),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=["Reporter:site:None->UNKNOWN"], rejected_ids=[])],
    )
    events = []
    session = _make_mapping_session(turns, handler, events)

    session.run("go")

    assert list(session.workbook.sheets()["Reporter"]["site"]) == ["UNKNOWN", "x", "UNKNOWN"]


def test_rejected_value_mapping_is_not_applied():
    turns = [
        _dry_run_turn(),
        _mapping_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "column": "species",
                    "from_value": "#REF!",
                    "to_value": "UNKNOWN",
                    "rationale": "r",
                }
            ]
        ),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=[], rejected_ids=["Reporter:species:#REF!->UNKNOWN"])],
    )
    events = []
    session = _make_mapping_session(turns, handler, events)

    session.run("go")

    assert list(session.workbook.sheets()["Reporter"]["species"]) == ["#REF!", "cat", "#REF!"]


def test_unknown_column_mapping_never_reaches_human():
    turns = [
        _dry_run_turn(),
        _mapping_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "column": "nope",
                    "from_value": "#REF!",
                    "to_value": "UNKNOWN",
                    "rationale": "r",
                }
            ]
        ),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], value_mapping_results=[])
    events = []
    session = _make_mapping_session(turns, handler, events)

    session.run("go")

    assert handler.seen_value_mapping_proposals == []
    assert "value_mapping_proposal" not in [e.kind for e in events]


def test_absent_from_value_is_invalid_and_never_reaches_human():
    turns = [
        _dry_run_turn(),
        _mapping_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "column": "species",
                    "from_value": "NOPE",
                    "to_value": "UNKNOWN",
                    "rationale": "r",
                }
            ]
        ),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], value_mapping_results=[])
    events = []
    session = _make_mapping_session(turns, handler, events)

    session.run("go")

    assert handler.seen_value_mapping_proposals == []


def test_noop_mapping_is_dropped_before_the_gate():
    turns = [
        _dry_run_turn(),
        _mapping_turn(
            [{"sheet_name": "Reporter", "column": "species", "from_value": "cat", "to_value": "cat", "rationale": "r"}]
        ),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], value_mapping_results=[])
    events = []
    session = _make_mapping_session(turns, handler, events)

    session.run("go")

    assert handler.seen_value_mapping_proposals == []
    assert list(session.workbook.sheets()["Reporter"]["species"]) == ["#REF!", "cat", "#REF!"]


def test_missing_scalar_field_is_created_and_filled():
    wb = WorkbookEditor({"Reporter": pd.DataFrame({"name": ["a", "b"]})})
    turns = [
        _dry_run_turn(),
        _mapping_turn(
            [{"sheet_name": "Reporter", "column": "count", "from_value": None, "to_value": 1, "rationale": "r"}]
        ),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=["Reporter:count:None->1"], rejected_ids=[])],
    )
    events = []
    session = AgentSession(
        provider=ScriptedProvider(turns),
        orchestrator=RecordingOrchestrator(),
        workbook=wb,
        approval_handler=handler,
        schema_provider=lambda model=None: {"fields": [{"name": "count"}]},
        event_sink=events.append,
    )
    session.run("go")
    assert list(session.workbook.sheets()["Reporter"]["count"]) == [1, 1]


def test_missing_column_not_a_schema_field_is_invalid():
    wb = WorkbookEditor({"Reporter": pd.DataFrame({"name": ["a"]})})
    turns = [
        _dry_run_turn(),
        _mapping_turn(
            [{"sheet_name": "Reporter", "column": "group", "from_value": None, "to_value": "x", "rationale": "r"}]
        ),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], value_mapping_results=[])
    events = []
    session = AgentSession(
        provider=ScriptedProvider(turns),
        orchestrator=RecordingOrchestrator(),
        workbook=wb,
        approval_handler=handler,
        schema_provider=lambda model=None: {"fields": [{"name": "count"}]},
        event_sink=events.append,
    )
    session.run("go")
    assert handler.seen_value_mapping_proposals == []
    assert "group" not in session.workbook.sheets()["Reporter"].columns


def test_session_applies_approved_changes_then_uploads():
    turns = [
        _dry_run_turn(),
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
        AssistantTurn(text="All done.", tool_calls=[ToolCall("fin", "finish", {})]),
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
        _dry_run_turn(),
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
        AssistantTurn(text="ok", tool_calls=[ToolCall("fin", "finish", {})]),
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


def test_set_sheets_hands_live_frames_before_each_build_plan():
    turns = [
        AssistantTurn(text="", tool_calls=[ToolCall("c1", "dry_run", {})]),
        AssistantTurn(text="", tool_calls=[ToolCall("c2", "upload", {})]),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[{"Reporter"}])
    events = []
    session = _make_session(ScriptedProvider(turns), handler, events)

    session.run("go")

    orchestrator = session.orchestrator
    # one shared orchestrator handled both engine calls; sheets re-fed before every build_plan
    assert orchestrator.calls == ["set_sheets", "build_plan", "set_sheets", "build_plan", "execute"]
    # frames are handed by reference (the editor's live dict), not a copy
    assert orchestrator.set_sheets_args[0] is session.workbook.sheets()
    assert orchestrator.set_sheets_args[1] is session.workbook.sheets()


def test_dry_run_does_not_mutate_workbook_columns():
    from unittest.mock import MagicMock

    from amplify_excel_migrator.data import DataTransformer, InMemoryExcelReader
    from amplify_excel_migrator.migration import MigrationOrchestrator
    from amplify_excel_migrator.schema import FieldParser

    workbook = WorkbookEditor({"Reporter": pd.DataFrame({"Reporter Name": ["a"], "ERROR": ["x"]})})
    original_columns = list(workbook.sheets()["Reporter"].columns)

    client = MagicMock()
    client.get_primary_field_name.return_value = ("name", False, "String")
    client.build_foreign_key_lookups.return_value = {}
    orchestrator = MigrationOrchestrator(
        excel_reader=InMemoryExcelReader(),
        data_transformer=DataTransformer(FieldParser()),
        amplify_client=client,
        field_parser=FieldParser(),
        batch_uploader=MagicMock(),
    )
    orchestrator._get_parsed_model_structure = MagicMock(return_value={"fields": []})

    turns = [
        AssistantTurn(text="", tool_calls=[ToolCall("c1", "dry_run", {})]),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    session = AgentSession(
        provider=ScriptedProvider(turns),
        orchestrator=orchestrator,
        workbook=workbook,
        approval_handler=RecordingApprovalHandler([], []),
        schema_provider=lambda model=None: {},
        event_sink=[].append,
    )

    session.run("go")

    assert list(workbook.sheets()["Reporter"].columns) == original_columns


def test_approved_rename_is_applied_and_visible_to_dry_run():
    turns = [
        _rename_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "current_name": "Report type",
                    "new_name": "observationMethod",
                    "rationale": "header maps to schema field",
                }
            ]
        ),
        AssistantTurn(text="", tool_calls=[ToolCall("d1", "dry_run", {})]),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        rename_results=[ApprovalResult(approved_ids=["Reporter:Report type->observationMethod"], rejected_ids=[])],
    )
    events = []
    session = _make_rename_session(turns, handler, events)

    session.run("go")

    cols = list(session.workbook.sheets()["Reporter"].columns)
    assert "observationMethod" in cols and "Report type" not in cols
    assert "observationMethod" in session.orchestrator.set_sheets_args[-1]["Reporter"].columns
    assert "rename_proposal" in [e.kind for e in events]


def test_rejected_rename_is_not_applied():
    turns = [
        _rename_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "current_name": "Report type",
                    "new_name": "observationMethod",
                    "rationale": "guess",
                }
            ]
        ),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        rename_results=[ApprovalResult(approved_ids=[], rejected_ids=["Reporter:Report type->observationMethod"])],
    )
    events = []
    session = _make_rename_session(turns, handler, events)

    session.run("go")

    assert list(session.workbook.sheets()["Reporter"].columns) == ["name", "Report type"]


def test_invalid_target_field_never_reaches_human():
    turns = [
        _rename_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "current_name": "Report type",
                    "new_name": "bogusField",
                    "rationale": "wrong",
                }
            ]
        ),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], rename_results=[])
    events = []
    session = _make_rename_session(turns, handler, events)

    session.run("go")

    assert handler.seen_rename_proposals == []
    assert list(session.workbook.sheets()["Reporter"].columns) == ["name", "Report type"]
    assert "rename_proposal" not in [e.kind for e in events]


def test_missing_source_column_is_invalid():
    turns = [
        _rename_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "current_name": "Missing",
                    "new_name": "observationMethod",
                    "rationale": "x",
                }
            ]
        ),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], rename_results=[])
    events = []
    session = _make_rename_session(turns, handler, events)

    session.run("go")

    assert handler.seen_rename_proposals == []


def test_collision_with_existing_column_is_invalid():
    turns = [
        _rename_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "current_name": "Report type",
                    "new_name": "name",
                    "rationale": "x",
                }
            ]
        ),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], rename_results=[])
    events = []
    session = _make_rename_session(turns, handler, events)

    session.run("go")

    assert handler.seen_rename_proposals == []
    assert list(session.workbook.sheets()["Reporter"].columns) == ["name", "Report type"]


def test_ambiguous_in_batch_targets_are_both_invalid():
    turns = [
        _rename_turn(
            [
                {
                    "sheet_name": "Reporter",
                    "current_name": "Report type",
                    "new_name": "observationMethod",
                    "rationale": "a",
                },
                {
                    "sheet_name": "Reporter",
                    "current_name": "name",
                    "new_name": "observationMethod",
                    "rationale": "b",
                },
            ]
        ),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], rename_results=[])
    events = []
    session = _make_rename_session(turns, handler, events)

    session.run("go")

    assert handler.seen_rename_proposals == []
    assert list(session.workbook.sheets()["Reporter"].columns) == ["name", "Report type"]


def _plan_with_field_errors(rows):
    """rows: list of rows, each a list of (column, value, kind) tuples."""
    failures = []
    for i, row in enumerate(rows):
        field_errors = [FieldError(column=c, value=v, kind=k, message=f"{c}:{v}:{k}") for c, v, k in row]
        failures.append(
            RecordFailure(
                primary_field="k",
                primary_field_value=i,
                error=" | ".join(fe.message for fe in field_errors),
                original_row={},
                field_errors=field_errors,
            )
        )
    return MigrationPlan(
        sheets=[
            SheetPlan(
                sheet_name="Observation",
                status="ready",
                skip_reason=None,
                total_rows=len(rows),
                record_count=0,
                records=[],
                parsing_failures=failures,
                parsed_model_structure={"fields": []},
                row_dict_by_primary={},
            )
        ]
    )


class _FailingOrchestrator:
    def __init__(self, plan):
        self._plan = plan

    def set_sheets(self, sheets):
        pass

    def build_plan(self):
        return self._plan


def _dry_run_session(plan, events, max_failure_groups=50):
    turns = [
        AssistantTurn(text="", tool_calls=[ToolCall("c1", "dry_run", {})]),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    return AgentSession(
        provider=ScriptedProvider(turns),
        orchestrator=_FailingOrchestrator(plan),
        workbook=WorkbookEditor({"Observation": pd.DataFrame({"a": [1]})}),
        approval_handler=RecordingApprovalHandler([], []),
        schema_provider=lambda model=None: {},
        event_sink=events.append,
        max_failure_groups=max_failure_groups,
    )


def test_dry_run_groups_failures_by_field_error():
    events = []
    rows = [
        [("group", None, "missing_required")],
        [("group", None, "missing_required")],
        [("species", "#REF!", "fk_not_found")],
    ]
    _dry_run_session(_plan_with_field_errors(rows), events).run("go")
    sheet = next(e for e in events if e.kind == "dry_run").payload["sheets"][0]
    assert sheet["total_failed_rows"] == 3
    assert sheet["distinct_failure_groups"] == 2
    assert sheet["failure_groups"] == [
        {
            "column": "group",
            "value": None,
            "kind": "missing_required",
            "count": 2,
            "message": "group:None:missing_required",
        },
        {
            "column": "species",
            "value": "#REF!",
            "kind": "fk_not_found",
            "count": 1,
            "message": "species:#REF!:fk_not_found",
        },
    ]
    assert "total_parsing_failures" not in sheet
    assert "parsing_failures" not in sheet


def test_dry_run_honors_max_failure_groups():
    events = []
    rows = [
        [("a", 1, "parse")],
        [("a", 1, "parse")],
        [("b", 1, "parse")],
        [("c", 1, "parse")],
    ]
    _dry_run_session(_plan_with_field_errors(rows), events, max_failure_groups=1).run("go")
    sheet = next(e for e in events if e.kind == "dry_run").payload["sheets"][0]
    assert len(sheet["failure_groups"]) == 1
    assert sheet["failure_groups"][0]["column"] == "a"
    assert sheet["failure_groups"][0]["count"] == 2
    assert sheet["distinct_failure_groups"] == 3
    assert sheet["total_failed_rows"] == 4


def test_finish_tool_ends_run_with_summary():
    turns = [AssistantTurn(text="", tool_calls=[ToolCall("f1", "finish", {"summary": "all clean"})])]
    events = []
    session = _make_session(ScriptedProvider(turns), RecordingApprovalHandler([], []), events)

    session.run("go")

    done = [e for e in events if e.kind == "done"]
    assert len(done) == 1
    assert done[0].payload == {"summary": "all clean"}


def test_text_only_turn_nudges_then_continues():
    turns = [
        AssistantTurn(text="Here is my diagnosis. I will fix it.", tool_calls=[]),
        AssistantTurn(text="", tool_calls=[ToolCall("d1", "dry_run", {})]),
        AssistantTurn(text="", tool_calls=[ToolCall("f1", "finish", {"summary": "fixed"})]),
    ]
    events = []
    session = _make_session(ScriptedProvider(turns), RecordingApprovalHandler([], []), events)

    session.run("go")

    kinds = [e.kind for e in events]
    assert "message" in kinds  # narration surfaced
    assert "dry_run" in kinds  # loop continued past the narration and ran the tool
    assert kinds[-1] == "done"  # finish ended it, not the narration


def test_exceeding_max_nudges_stops_with_error():
    turns = [
        AssistantTurn(text="just talking", tool_calls=[]),
        AssistantTurn(text="still talking", tool_calls=[]),
    ]
    events = []
    session = _make_session(ScriptedProvider(turns), RecordingApprovalHandler([], []), events, max_nudges=1)

    session.run("go")

    assert events[-1].kind == "error"
    assert "without a tool call" in events[-1].payload["message"]


def test_propose_changes_missing_row_returns_instructive_error():
    events = []
    session = _make_session(ScriptedProvider([]), RecordingApprovalHandler([], []), events)
    session._dry_run_current = True

    result = session._dispatch(
        "propose_changes",
        {
            "summary": "x",
            "changes": [{"sheet_name": "Reporter", "column": "country", "proposed_value": "EG", "rationale": "r"}],
        },
    )

    assert result.startswith("ERROR:")
    assert "row" in result
    assert "change #0" in result
    assert "proposal" not in [e.kind for e in events]


def test_propose_changes_unknown_column_hints_at_renames():
    events = []
    session = _make_session(ScriptedProvider([]), RecordingApprovalHandler([], []), events)
    session._dry_run_current = True

    result = session._dispatch(
        "propose_changes",
        {
            "summary": "x",
            "changes": [
                {
                    "sheet_name": "Reporter",
                    "row": 0,
                    "column": "Observation:Common name Hebrew",
                    "proposed_value": "v",
                    "rationale": "r",
                }
            ],
        },
    )

    assert result.startswith("ERROR:")
    assert "Observation:Common name Hebrew" in result
    assert "propose_column_renames" in result
    assert "propose_value_mappings" in result
    assert "proposal" not in [e.kind for e in events]


def test_propose_changes_unknown_sheet_lists_available():
    events = []
    session = _make_session(ScriptedProvider([]), RecordingApprovalHandler([], []), events)
    session._dry_run_current = True

    result = session._dispatch(
        "propose_changes",
        {
            "summary": "x",
            "changes": [{"sheet_name": "Nope", "row": 0, "column": "name", "proposed_value": "v", "rationale": "r"}],
        },
    )

    assert result.startswith("ERROR:")
    assert "Nope" in result and "Reporter" in result


def test_propose_changes_row_out_of_range_is_rejected():
    events = []
    session = _make_session(ScriptedProvider([]), RecordingApprovalHandler([], []), events)
    session._dry_run_current = True

    result = session._dispatch(
        "propose_changes",
        {
            "summary": "x",
            "changes": [
                {"sheet_name": "Reporter", "row": 99, "column": "country", "proposed_value": "v", "rationale": "r"}
            ],
        },
    )

    assert result.startswith("ERROR:")
    assert "99" in result and "out of range" in result


def test_propose_changes_valid_batch_still_emits_proposal():
    turns = [
        _dry_run_turn(),
        AssistantTurn(
            text="",
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
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    handler = RecordingApprovalHandler(
        change_results=[ApprovalResult(approved_ids=["Reporter:1:country"], rejected_ids=[])],
        upload_selections=[],
    )
    events = []
    session = _make_session(ScriptedProvider(turns), handler, events)

    session.run("go")

    assert "proposal" in [e.kind for e in events]
    assert session.workbook.cell("Reporter", 1, "country") == "EG"


def test_repeated_identical_failure_escalates_then_aborts():
    from amplify_excel_migrator.agent.llm.base import UserMessage

    # A non-proposal failing tool isolates the identical-args guard: the no-progress guard ignores
    # non-proposal tools, so this exercises the identical-args escalate/abort path on its own.
    failing_read = AssistantTurn(text="", tool_calls=[ToolCall("c1", "read_sheet", {"sheet": "Nope"})])
    provider = RepeatingRecorder(failing_read)
    events = []
    session = _make_session(provider, RecordingApprovalHandler([], []), events)

    session.run("go", escalate_repeats=2, abort_repeats=3)

    assert events[-1].kind == "error"
    assert "Aborted" in events[-1].payload["message"]
    assert "read_sheet" in events[-1].payload["message"]
    assert "identical arguments" in events[-1].payload["message"]
    # ended well before max_turns (only 3 generate() calls happened)
    assert len(provider.seen_messages) == 3
    # the escalation UserMessage was injected before the final generate()
    injected = [
        m for m in provider.seen_messages[-1] if isinstance(m, UserMessage) and "identical arguments" in m.content
    ]
    assert injected


def test_counter_resets_on_a_different_successful_call():
    turns = [
        _failing_propose_turn(),
        _failing_propose_turn(),
        AssistantTurn(text="", tool_calls=[ToolCall("r1", "read_sheet", {"sheet": "Reporter"})]),
        _failing_propose_turn(),
        _failing_propose_turn(),
        AssistantTurn(text="done", tool_calls=[ToolCall("fin", "finish", {})]),
    ]
    events = []
    session = _make_session(ScriptedProvider(turns), RecordingApprovalHandler([], []), events)

    session.run("go", escalate_repeats=2, abort_repeats=3)

    assert not any(e.kind == "error" and "Aborted" in e.payload.get("message", "") for e in events)
    assert events[-1].kind == "done"


def test_propose_changes_blocked_before_dry_run():
    events = []
    session = _make_session(ScriptedProvider([]), RecordingApprovalHandler([], []), events)

    result = session._dispatch(
        "propose_changes",
        {
            "summary": "x",
            "changes": [
                {"sheet_name": "Reporter", "row": 1, "column": "country", "proposed_value": "EG", "rationale": "r"}
            ],
        },
    )

    assert result == _DRY_RUN_REQUIRED
    assert session.workbook.cell("Reporter", 1, "country") == ""  # nothing mutated
    assert "proposal" not in [e.kind for e in events]


def test_propose_value_mappings_blocked_before_dry_run():
    handler = RecordingApprovalHandler([], [])
    events = []
    session = _make_mapping_session([], handler, events)

    result = session._dispatch(
        "propose_value_mappings",
        {
            "summary": "x",
            "mappings": [
                {
                    "sheet_name": "Reporter",
                    "column": "species",
                    "from_value": "#REF!",
                    "to_value": "UNKNOWN",
                    "rationale": "r",
                }
            ],
        },
    )

    assert result == _DRY_RUN_REQUIRED
    assert list(session.workbook.sheets()["Reporter"]["species"]) == ["#REF!", "cat", "#REF!"]
    assert handler.seen_value_mapping_proposals == []


def test_value_fix_allowed_after_dry_run():
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=["Reporter:species:#REF!->UNKNOWN"], rejected_ids=[])],
    )
    events = []
    session = _make_mapping_session([], handler, events)

    session._dispatch("dry_run", {})
    result = session._dispatch(
        "propose_value_mappings",
        {
            "summary": "fix",
            "mappings": [
                {
                    "sheet_name": "Reporter",
                    "column": "species",
                    "from_value": "#REF!",
                    "to_value": "UNKNOWN",
                    "rationale": "r",
                }
            ],
        },
    )

    assert result != _DRY_RUN_REQUIRED
    assert list(session.workbook.sheets()["Reporter"]["species"]) == ["UNKNOWN", "cat", "UNKNOWN"]


def test_mutation_invalidates_dry_run():
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=["Reporter:species:#REF!->UNKNOWN"], rejected_ids=[])],
    )
    events = []
    session = _make_mapping_session([], handler, events)

    session._dispatch("dry_run", {})
    first = session._dispatch(
        "propose_value_mappings",
        {
            "summary": "fix",
            "mappings": [
                {
                    "sheet_name": "Reporter",
                    "column": "species",
                    "from_value": "#REF!",
                    "to_value": "UNKNOWN",
                    "rationale": "r",
                }
            ],
        },
    )
    second = session._dispatch(
        "propose_value_mappings",
        {
            "summary": "again",
            "mappings": [
                {
                    "sheet_name": "Reporter",
                    "column": "species",
                    "from_value": "cat",
                    "to_value": "DOG",
                    "rationale": "r",
                }
            ],
        },
    )

    assert first != _DRY_RUN_REQUIRED  # first applied while fresh
    assert second == _DRY_RUN_REQUIRED  # the applied mutation consumed freshness


def test_rejected_proposal_preserves_freshness():
    handler = RecordingApprovalHandler(
        change_results=[ApprovalResult(approved_ids=[], rejected_ids=["Reporter:0:species"])],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=["Reporter:species:#REF!->UNKNOWN"], rejected_ids=[])],
    )
    events = []
    session = _make_mapping_session([], handler, events)

    session._dispatch("dry_run", {})
    session._dispatch(
        "propose_changes",
        {
            "summary": "x",
            "changes": [
                {"sheet_name": "Reporter", "row": 0, "column": "species", "proposed_value": "cat", "rationale": "r"}
            ],
        },
    )
    result = session._dispatch(
        "propose_value_mappings",
        {
            "summary": "fix",
            "mappings": [
                {
                    "sheet_name": "Reporter",
                    "column": "species",
                    "from_value": "#REF!",
                    "to_value": "UNKNOWN",
                    "rationale": "r",
                }
            ],
        },
    )

    assert result != _DRY_RUN_REQUIRED  # nothing was applied, so the dry_run is still fresh
    assert list(session.workbook.sheets()["Reporter"]["species"]) == ["UNKNOWN", "cat", "UNKNOWN"]


def test_rename_is_ungated_but_invalidates():
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        rename_results=[
            ApprovalResult(approved_ids=["Reporter:Report type->observationMethod"], rejected_ids=[]),
            ApprovalResult(approved_ids=["Reporter:name->country"], rejected_ids=[]),
        ],
    )
    events = []
    session = _make_rename_session([], handler, events)

    # ungated: a rename applies with no prior dry_run
    session._dispatch(
        "propose_column_renames",
        {
            "summary": "fix headers",
            "renames": [
                {
                    "sheet_name": "Reporter",
                    "current_name": "Report type",
                    "new_name": "observationMethod",
                    "rationale": "r",
                }
            ],
        },
    )
    assert "observationMethod" in session.workbook.sheets()["Reporter"].columns

    # a fresh dry_run followed by an applied rename re-invalidates freshness
    session._dispatch("dry_run", {})
    session._dispatch(
        "propose_column_renames",
        {
            "summary": "more headers",
            "renames": [{"sheet_name": "Reporter", "current_name": "name", "new_name": "country", "rationale": "r"}],
        },
    )
    blocked = session._dispatch(
        "propose_changes",
        {
            "summary": "x",
            "changes": [
                {"sheet_name": "Reporter", "row": 0, "column": "country", "proposed_value": "v", "rationale": "r"}
            ],
        },
    )

    assert blocked == _DRY_RUN_REQUIRED  # the applied rename made the value-fix stale again


def test_made_no_progress_helper():
    from amplify_excel_migrator.agent.session import _made_no_progress

    # proposal that applied nothing -> True
    assert _made_no_progress("propose_value_mappings", '{"applied": [], "rejected": [], "invalid": []}') is True
    # proposal with an ERROR result -> True
    assert _made_no_progress("propose_changes", "ERROR: blocked") is True
    # proposal that applied at least one item -> False
    assert _made_no_progress("propose_value_mappings", '{"applied": ["Reporter:species:#REF!->UNKNOWN"]}') is False
    # non-proposal tools never count as no-progress
    assert _made_no_progress("dry_run", '{"sheets": []}') is False
    assert _made_no_progress("read_sheet", '{"rows": []}') is False
    # a proposal whose result is not JSON -> False (don't guess)
    assert _made_no_progress("propose_changes", "not json at all") is False


class RecordingScriptedProvider(LLMProvider):
    """Pops a fixed list of turns and records the messages seen on each generate()."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.seen_messages = []

    def generate(self, system, messages, tools):
        self.seen_messages.append(list(messages))
        return self._turns.pop(0)


def _invalid_mapping_turn(rationale, call_id):
    # from_value null into 'group' (no column, not a schema field) -> rejected as invalid, applies nothing
    return _mapping_turn(
        [
            {
                "sheet_name": "Reporter",
                "column": "group",
                "from_value": None,
                "to_value": "Unknown",
                "rationale": rationale,
            }
        ],
        call_id=call_id,
    )


def _apply_species_mapping_turn(call_id):
    return _mapping_turn(
        [
            {
                "sheet_name": "Reporter",
                "column": "species",
                "from_value": "#REF!",
                "to_value": "UNKNOWN",
                "rationale": "r",
            }
        ],
        call_id=call_id,
    )


def test_aborts_after_consecutive_unproductive_proposals():
    turns = [
        _dry_run_turn(),
        _invalid_mapping_turn("rationale one", "m1"),
        _invalid_mapping_turn("rationale two", "m2"),
        _invalid_mapping_turn("rationale three", "m3"),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], value_mapping_results=[])
    events = []
    session = _make_mapping_session(turns, handler, events)

    session.run("go", escalate_repeats=2, abort_repeats=3)

    assert events[-1].kind == "error"
    msg = events[-1].payload["message"]
    assert "Aborted" in msg and "no changes" in msg
    assert "done" not in [e.kind for e in events]  # aborted before reaching finish


def test_escalation_message_after_three_unproductive():
    from amplify_excel_migrator.agent.llm.base import UserMessage

    turns = [
        _dry_run_turn(),
        _invalid_mapping_turn("one", "m1"),
        _invalid_mapping_turn("two", "m2"),
        _invalid_mapping_turn("three", "m3"),
        _finish_turn(),
    ]
    provider = RecordingScriptedProvider(turns)
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], value_mapping_results=[])
    events = []
    session = AgentSession(
        provider=provider,
        orchestrator=RecordingOrchestrator(),
        workbook=_mapping_workbook(),
        approval_handler=handler,
        schema_provider=lambda model=None: {"models": ["Reporter"]},
        event_sink=events.append,
    )

    session.run("go", escalate_repeats=3, abort_repeats=5)

    # by the final generate() (the finish turn) a no-progress guidance UserMessage has been injected
    injected = [
        m for m in provider.seen_messages[-1] if isinstance(m, UserMessage) and "applied no changes" in m.content
    ]
    assert injected
    assert events[-1].kind == "done"  # escalation nudges, it does not abort


def test_applied_mapping_resets_no_progress():
    turns = [
        _dry_run_turn(),
        _invalid_mapping_turn("one", "m1"),
        _invalid_mapping_turn("two", "m2"),
        _apply_species_mapping_turn("m3"),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(
        change_results=[],
        upload_selections=[],
        value_mapping_results=[ApprovalResult(approved_ids=["Reporter:species:#REF!->UNKNOWN"], rejected_ids=[])],
    )
    events = []
    session = _make_mapping_session(turns, handler, events)

    session.run("go", escalate_repeats=2, abort_repeats=3)

    assert not any(e.kind == "error" and "Aborted" in e.payload.get("message", "") for e in events)
    assert events[-1].kind == "done"


def test_dry_run_between_failures_resets_no_progress():
    turns = [
        _dry_run_turn("d0"),
        _invalid_mapping_turn("one", "m1"),
        _dry_run_turn("d1"),
        _invalid_mapping_turn("two", "m2"),
        _finish_turn(),
    ]
    handler = RecordingApprovalHandler(change_results=[], upload_selections=[], value_mapping_results=[])
    events = []
    session = _make_mapping_session(turns, handler, events)

    # abort_repeats=2: without the interleaved dry_run, m1+m2 would be 2 consecutive -> abort
    session.run("go", escalate_repeats=5, abort_repeats=2)

    assert not any(e.kind == "error" and "Aborted" in e.payload.get("message", "") for e in events)
    assert events[-1].kind == "done"
