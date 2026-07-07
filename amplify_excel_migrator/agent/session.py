"""The human-in-the-loop agentic loop that prepares and migrates a workbook."""

import json
import logging
from typing import Any, Callable, Dict, List

from amplify_excel_migrator.agent.llm.base import (
    AssistantMessage,
    LLMProvider,
    ToolResultMessage,
    UserMessage,
)
from amplify_excel_migrator.agent.models import (
    AgentEvent,
    ChangeProposal,
    ColumnRename,
    ColumnRenameProposal,
    ProposedChange,
    ValueMapping,
    ValueMappingProposal,
)
from amplify_excel_migrator.agent.prompts import SYSTEM_PROMPT
from amplify_excel_migrator.agent.tools import TOOL_SPECS
from amplify_excel_migrator.agent.workbook import WorkbookEditor
from amplify_excel_migrator.migration.failure_grouping import summarize_failures

logger = logging.getLogger(__name__)

_NUDGE = (
    "You did not call any tool. If you intend to make a change, emit the actual tool call now "
    "(e.g. propose_column_renames, propose_changes, dry_run). If the migration is complete, call finish."
)


def _escalation_message(tool: str, count: int, last_error: str) -> str:
    return (
        f"You have called `{tool}` with identical arguments {count} times and it keeps failing with: "
        f"{last_error}. Do not repeat the same call — change the arguments, use a different tool "
        "(e.g. dry_run to see the real problems, or propose_column_renames to fix headers), or call finish."
    )


def _change_id(sheet: str, row: int, column: str) -> str:
    return f"{sheet}:{row}:{column}"


def _rename_id(sheet: str, current: str, new: str) -> str:
    return f"{sheet}:{current}->{new}"


def _mapping_id(sheet: str, column: str, from_value: Any, to_value: Any) -> str:
    return f"{sheet}:{column}:{from_value}->{to_value}"


def _json_safe(value: Any) -> Any:
    """Normalize a cell value to a JSON-serializable form (pandas NaN/NaT -> None, others -> str)."""
    try:
        import pandas as pd

        if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class AgentSession:
    def __init__(
        self,
        provider: LLMProvider,
        orchestrator: Any,
        workbook: WorkbookEditor,
        approval_handler: Any,
        schema_provider: Callable[..., Dict[str, Any]],
        event_sink: Callable[[AgentEvent], None],
        max_failure_groups: int = 50,
        max_nudges: int = 2,
    ):
        self.provider = provider
        self.orchestrator = orchestrator
        self.workbook = workbook
        self.approval = approval_handler
        self.schema_provider = schema_provider
        self.emit = event_sink
        self._max_failure_groups = max_failure_groups
        self._max_nudges = max_nudges

    def run(
        self,
        instruction: str,
        max_turns: int = 40,
        escalate_repeats: int = 3,
        abort_repeats: int = 5,
    ) -> None:
        messages: List[Any] = [UserMessage(content=instruction)]
        consecutive_nudges = 0
        last_error_sig = None
        repeat_count = 0
        for _ in range(max_turns):
            turn = self.provider.generate(SYSTEM_PROMPT, messages, TOOL_SPECS)
            if turn.text:
                self.emit(AgentEvent(kind="message", payload={"text": turn.text}))
            if not turn.has_tool_calls():
                consecutive_nudges += 1
                if consecutive_nudges > self._max_nudges:
                    self.emit(
                        AgentEvent(
                            kind="error",
                            payload={"message": f"Stopped after {consecutive_nudges} turns without a tool call."},
                        )
                    )
                    return
                messages.append(AssistantMessage(text=turn.text, tool_calls=[], raw=turn.raw))
                messages.append(UserMessage(content=_NUDGE))
                continue
            consecutive_nudges = 0

            messages.append(AssistantMessage(text=turn.text, tool_calls=turn.tool_calls, raw=turn.raw))
            escalation = None
            for call in turn.tool_calls:
                if call.name == "finish":
                    self.emit(AgentEvent(kind="done", payload={"summary": call.arguments.get("summary", "")}))
                    return
                self.emit(AgentEvent(kind="tool_call", payload={"name": call.name, "arguments": call.arguments}))
                result_text = self._dispatch(call.name, call.arguments)
                messages.append(
                    ToolResultMessage(
                        tool_call_id=call.id, content=result_text, is_error=result_text.startswith("ERROR:")
                    )
                )

                if not result_text.startswith("ERROR:"):
                    last_error_sig = None
                    repeat_count = 0
                    continue

                sig = (call.name, json.dumps(call.arguments, sort_keys=True, default=str))
                if sig == last_error_sig:
                    repeat_count += 1
                else:
                    last_error_sig = sig
                    repeat_count = 1

                if repeat_count >= abort_repeats:
                    self.emit(
                        AgentEvent(
                            kind="error",
                            payload={
                                "message": f"Aborted: '{call.name}' failed {repeat_count} times "
                                "with identical arguments."
                            },
                        )
                    )
                    return
                if repeat_count == escalate_repeats:
                    escalation = _escalation_message(call.name, repeat_count, result_text)

            if escalation:
                messages.append(UserMessage(content=escalation))

        self.emit(AgentEvent(kind="error", payload={"message": f"Stopped after {max_turns} turns without finishing."}))

    def _dispatch(self, name: str, args: Dict[str, Any]) -> str:
        try:
            if name == "inspect_schema":
                return json.dumps(self.schema_provider(model=args.get("model")))
            if name == "read_sheet":
                return json.dumps(self.workbook.preview(args["sheet"], args.get("max_rows", 20)), default=str)
            if name == "dry_run":
                return self._dry_run()
            if name == "propose_changes":
                return self._propose_changes(args)
            if name == "propose_column_renames":
                return self._propose_column_renames(args)
            if name == "propose_value_mappings":
                return self._propose_value_mappings(args)
            if name == "upload":
                return self._upload()
            return f"ERROR: unknown tool '{name}'"
        except Exception as e:  # surface tool errors to the model instead of crashing the loop
            logger.exception("Tool '%s' failed", name)
            return f"ERROR: {e}"

    def _orchestrator_for_current_workbook(self):
        """Point the shared orchestrator's reader at the editor's current frames and return it."""
        self.orchestrator.set_sheets(self.workbook.sheets())
        return self.orchestrator

    def _dry_run(self) -> str:
        orchestrator = self._orchestrator_for_current_workbook()
        plan = orchestrator.build_plan()
        report = {"sheets": [self._sheet_report(s) for s in plan.sheets]}
        self.emit(AgentEvent(kind="dry_run", payload=report))
        return json.dumps(report, default=str)

    def _sheet_report(self, sheet) -> Dict[str, Any]:
        summary = summarize_failures(sheet.parsing_failures, self._max_failure_groups)
        return {
            "sheet_name": sheet.sheet_name,
            "status": sheet.status,
            "skip_reason": sheet.skip_reason,
            "record_count": sheet.record_count,
            "total_failed_rows": summary["total_failed_rows"],
            "distinct_failure_groups": summary["distinct"],
            "failure_groups": summary["groups"],
        }

    _REQUIRED_CHANGE_KEYS = ("sheet_name", "row", "column", "proposed_value", "rationale")

    def _validate_changes(self, changes: List[Dict[str, Any]]) -> List[str]:
        sheets = self.workbook.sheets()
        problems: List[str] = []
        for i, c in enumerate(changes):
            missing = [k for k in self._REQUIRED_CHANGE_KEYS if k not in c]
            if missing:
                for k in missing:
                    problems.append(f"change #{i}: missing required '{k}' (row is a 0-based integer).")
                continue
            s = c["sheet_name"]
            if s not in sheets:
                problems.append(f"change #{i}: sheet '{s}' not found. Available: {sorted(sheets)}.")
                continue
            df = sheets[s]
            cols = list(df.columns)
            if c["column"] not in cols:
                problems.append(
                    f"change #{i}: column '{c['column']}' not found in sheet '{s}'. Columns: {cols}. "
                    "To fill or create a missing field, use propose_value_mappings (map from_value null to a "
                    "default). To rename an existing header, use propose_column_renames. Do not use propose_changes."
                )
                continue
            r = c["row"]
            n = len(df)
            if not isinstance(r, int) or isinstance(r, bool) or not (0 <= r < n):
                problems.append(f"change #{i}: row {r} out of range for '{s}' (valid 0..{n - 1}).")
        return problems

    def _propose_changes(self, args: Dict[str, Any]) -> str:
        problems = self._validate_changes(args["changes"])
        if problems:
            return "ERROR: " + " ".join(problems)

        changes = [
            ProposedChange(
                id=_change_id(c["sheet_name"], c["row"], c["column"]),
                sheet_name=c["sheet_name"],
                row=c["row"],
                column=c["column"],
                current_value=_json_safe(self.workbook.cell(c["sheet_name"], c["row"], c["column"])),
                proposed_value=c["proposed_value"],
                rationale=c["rationale"],
            )
            for c in args["changes"]
        ]
        proposal = ChangeProposal(summary=args["summary"], changes=changes)
        # vars(c) is JSON-safe: current_value passed through _json_safe; proposed_value comes from the LLM (JSON scalar).
        self.emit(
            AgentEvent(kind="proposal", payload={"summary": proposal.summary, "changes": [vars(c) for c in changes]})
        )

        result = self.approval.review_changes(proposal)  # blocks for human decision

        applied, skipped = [], []
        for change in changes:
            if result.is_approved(change.id):
                self.workbook.apply_change(change.sheet_name, change.row, change.column, change.proposed_value)
                applied.append(change.id)
            else:
                skipped.append(change.id)
        return json.dumps({"applied": applied, "rejected": skipped})

    def _propose_column_renames(self, args: Dict[str, Any]) -> str:
        renames = [r for r in args["renames"] if r["current_name"] != r["new_name"]]

        target_counts: Dict[tuple, int] = {}
        for r in renames:
            key = (r["sheet_name"], r["new_name"])
            target_counts[key] = target_counts.get(key, 0) + 1

        field_cache: Dict[str, set] = {}
        sheets = self.workbook.sheets()
        invalid: List[Dict[str, str]] = []
        valid: List[ColumnRename] = []

        for r in renames:
            sheet, current, new = r["sheet_name"], r["current_name"], r["new_name"]
            rid = _rename_id(sheet, current, new)

            if target_counts[(sheet, new)] > 1:
                invalid.append({"id": rid, "reason": "ambiguous target"})
                continue
            if sheet not in field_cache:
                schema = self.schema_provider(model=sheet) or {}
                field_cache[sheet] = {f.get("name") for f in (schema.get("fields") or [])}
            fields = field_cache[sheet]
            if not fields:
                invalid.append({"id": rid, "reason": "unknown model"})
                continue
            if new not in fields:
                invalid.append(
                    {"id": rid, "reason": f"'{new}' is not a field of model '{sheet}'; valid fields: {sorted(fields)}"}
                )
                continue
            columns = list(sheets[sheet].columns) if sheet in sheets else []
            if current not in columns:
                invalid.append({"id": rid, "reason": "no such column"})
                continue
            if new in columns:
                invalid.append({"id": rid, "reason": "target column already exists"})
                continue
            valid.append(
                ColumnRename(id=rid, sheet_name=sheet, current_name=current, new_name=new, rationale=r["rationale"])
            )

        applied: List[str] = []
        rejected: List[str] = []
        if valid:
            proposal = ColumnRenameProposal(summary=args["summary"], renames=valid)
            self.emit(
                AgentEvent(
                    kind="rename_proposal",
                    payload={"summary": proposal.summary, "renames": [vars(r) for r in valid]},
                )
            )
            result = self.approval.review_renames(proposal)  # blocks for human decision
            for rn in valid:
                if result.is_approved(rn.id):
                    self.workbook.rename_column(rn.sheet_name, rn.current_name, rn.new_name)
                    applied.append(rn.id)
                else:
                    rejected.append(rn.id)

        return json.dumps({"applied": applied, "rejected": rejected, "invalid": invalid})

    def _propose_value_mappings(self, args: Dict[str, Any]) -> str:
        mappings = [m for m in args["mappings"] if m["from_value"] != m["to_value"]]
        sheets = self.workbook.sheets()
        invalid: List[Dict[str, str]] = []
        valid: List[ValueMapping] = []

        for m in mappings:
            sheet, column = m["sheet_name"], m["column"]
            mid = _mapping_id(sheet, column, m["from_value"], m["to_value"])
            if sheet not in sheets:
                invalid.append({"id": mid, "reason": f"sheet '{sheet}' not found. Available: {sorted(sheets)}."})
                continue
            df = sheets[sheet]
            create = column not in df.columns
            if create:
                fields = {f.get("name") for f in (self.schema_provider(model=sheet) or {}).get("fields", [])}
                if m["from_value"] is not None or column not in fields:
                    invalid.append(
                        {
                            "id": mid,
                            "reason": (
                                f"column '{column}' not in sheet '{sheet}'. To create a missing scalar field, "
                                f"map from_value null to a default. Foreign keys with no column cannot be filled "
                                f"with a placeholder — ask the user for a valid id."
                            ),
                        }
                    )
                    continue
            else:
                series = df[column]
                present = series.isna().any() if m["from_value"] is None else (series == m["from_value"]).any()
                if not present:
                    invalid.append({"id": mid, "reason": f"value {m['from_value']!r} not present in column '{column}'"})
                    continue
            valid.append(
                ValueMapping(
                    id=mid,
                    sheet_name=sheet,
                    column=column,
                    from_value=m["from_value"],
                    to_value=m["to_value"],
                    rationale=m["rationale"],
                )
            )

        applied: List[str] = []
        rejected: List[str] = []
        if valid:
            proposal = ValueMappingProposal(summary=args["summary"], mappings=valid)
            self.emit(
                AgentEvent(
                    kind="value_mapping_proposal",
                    payload={"summary": proposal.summary, "mappings": [vars(m) for m in valid]},
                )
            )
            result = self.approval.review_value_mappings(proposal)  # blocks for human decision
            for m in valid:
                if result.is_approved(m.id):
                    if m.column in self.workbook.sheets()[m.sheet_name].columns:
                        self.workbook.apply_value_mapping(m.sheet_name, m.column, m.from_value, m.to_value)
                    else:
                        self.workbook.add_column(m.sheet_name, m.column, m.to_value)
                    applied.append(m.id)
                else:
                    rejected.append(m.id)

        return json.dumps({"applied": applied, "rejected": rejected, "invalid": invalid}, default=str)

    def _upload(self) -> str:
        orchestrator = self._orchestrator_for_current_workbook()
        plan = orchestrator.build_plan()
        ready = {s.sheet_name: s.record_count for s in plan.sheets if s.status == "ready"}

        selected = self.approval.review_upload(ready)  # blocks for human confirmation
        result = orchestrator.execute(plan, selected_sheets=selected)

        report = {
            "total_success": result.total_success,
            "sheets": [
                {
                    "sheet_name": s.sheet_name,
                    "success_count": s.success_count,
                    "failures": [{"row_key": _json_safe(f.primary_field_value), "error": f.error} for f in s.failures],
                }
                for s in result.sheets
            ],
        }
        self.emit(AgentEvent(kind="upload_result", payload=report))
        return json.dumps(report, default=str)
