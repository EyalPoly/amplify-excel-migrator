"""The human-in-the-loop agentic loop that prepares and migrates a workbook."""

import contextlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List

from amplify_excel_migrator.agent.llm.base import (
    AssistantMessage,
    LLMProvider,
    ToolResultMessage,
    UserMessage,
)
from amplify_excel_migrator.agent.models import AgentEvent, ChangeProposal, ProposedChange
from amplify_excel_migrator.agent.prompts import SYSTEM_PROMPT
from amplify_excel_migrator.agent.tools import TOOL_SPECS
from amplify_excel_migrator.agent.workbook import WorkbookEditor

logger = logging.getLogger(__name__)


def _change_id(sheet: str, row: int, column: str) -> str:
    return f"{sheet}:{row}:{column}"


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
        orchestrator_factory: Callable[[str], Any],
        workbook: WorkbookEditor,
        approval_handler: Any,
        schema_provider: Callable[..., Dict[str, Any]],
        event_sink: Callable[[AgentEvent], None],
    ):
        self.provider = provider
        self.orchestrator_factory = orchestrator_factory
        self.workbook = workbook
        self.approval = approval_handler
        self.schema_provider = schema_provider
        self.emit = event_sink

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
            if name == "upload":
                return self._upload()
            return f"ERROR: unknown tool '{name}'"
        except Exception as e:  # surface tool errors to the model instead of crashing the loop
            logger.exception("Tool '%s' failed", name)
            return f"ERROR: {e}"

    @contextlib.contextmanager
    def _orchestrator_for_current_workbook(self):
        """Save the current workbook to a temp file and build an orchestrator for it. Cleans up on exit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "workbook.xlsx")
            self.workbook.save(path)
            yield self.orchestrator_factory(path)

    def _dry_run(self) -> str:
        with self._orchestrator_for_current_workbook() as orchestrator:
            plan = orchestrator.build_plan()
            report = {
                "sheets": [
                    {
                        "sheet_name": s.sheet_name,
                        "status": s.status,
                        "skip_reason": s.skip_reason,
                        "record_count": s.record_count,
                        "parsing_failures": [
                            {"row_key": _json_safe(f.primary_field_value), "error": f.error} for f in s.parsing_failures
                        ],
                    }
                    for s in plan.sheets
                ]
            }
        self.emit(AgentEvent(kind="dry_run", payload=report))
        return json.dumps(report, default=str)

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

    def _upload(self) -> str:
        # Keep the orchestrator (and its temp file) alive across the approval wait, then execute on it.
        with self._orchestrator_for_current_workbook() as orchestrator:
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
