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
)
from amplify_excel_migrator.agent.prompts import SYSTEM_PROMPT
from amplify_excel_migrator.agent.tools import TOOL_SPECS
from amplify_excel_migrator.agent.workbook import WorkbookEditor
from amplify_excel_migrator.migration.failure_grouping import summarize_failures

logger = logging.getLogger(__name__)


def _change_id(sheet: str, row: int, column: str) -> str:
    return f"{sheet}:{row}:{column}"


def _rename_id(sheet: str, current: str, new: str) -> str:
    return f"{sheet}:{current}->{new}"


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
    ):
        self.provider = provider
        self.orchestrator = orchestrator
        self.workbook = workbook
        self.approval = approval_handler
        self.schema_provider = schema_provider
        self.emit = event_sink
        self._max_failure_groups = max_failure_groups

    def run(self, instruction: str, max_turns: int = 40) -> None:
        messages: List[Any] = [UserMessage(content=instruction)]
        for _ in range(max_turns):
            turn = self.provider.generate(SYSTEM_PROMPT, messages, TOOL_SPECS)
            if turn.text:
                self.emit(AgentEvent(kind="message", payload={"text": turn.text}))
            if not turn.has_tool_calls():
                self.emit(AgentEvent(kind="done", payload={}))
                return

            messages.append(AssistantMessage(text=turn.text, tool_calls=turn.tool_calls, raw=turn.raw))
            for call in turn.tool_calls:
                self.emit(AgentEvent(kind="tool_call", payload={"name": call.name, "arguments": call.arguments}))
                result_text = self._dispatch(call.name, call.arguments)
                messages.append(
                    ToolResultMessage(
                        tool_call_id=call.id, content=result_text, is_error=result_text.startswith("ERROR:")
                    )
                )

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

    def _propose_changes(self, args: Dict[str, Any]) -> str:
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
