"""Deterministic driver: reconcile headers and resolve FK failures via single-shot LLM
resolvers, with a human approving every proposal. No agentic loop."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from amplify_excel_migrator.agent.models import (
    AgentEvent,
    ApprovalResult,
    ColumnRename,
    ColumnRenameProposal,
)
from amplify_excel_migrator.agent.workbook import WorkbookEditor
from amplify_excel_migrator.data.transformer import DataTransformer


def unmatched_headers(columns: List[str], field_names: List[str]) -> Tuple[List[str], List[str]]:
    """Split columns into those whose camelCase form is a schema field and those that are not."""
    fields = set(field_names)
    covered = {DataTransformer.to_camel_case(c) for c in columns if DataTransformer.to_camel_case(c) in fields}
    unmatched = [c for c in columns if DataTransformer.to_camel_case(c) not in fields]
    uncovered = [f for f in field_names if f not in covered]
    return unmatched, uncovered


@dataclass
class PipelineReport:
    uploaded: int = 0
    final_clean: bool = False
    needs_create: List[Dict[str, Any]] = field(default_factory=list)
    needs_human: List[Dict[str, Any]] = field(default_factory=list)
    unresolved_headers: List[Dict[str, Any]] = field(default_factory=list)
    remaining_groups: List[Dict[str, Any]] = field(default_factory=list)


def _rename_id(sheet: str, current: str, new: str) -> str:
    return f"{sheet}:{current}->{new}"


class PreparationPipeline:
    def __init__(
        self,
        provider: Any,
        orchestrator: Any,
        workbook: WorkbookEditor,
        approval_handler: Any,
        schema_provider: Callable[..., Dict[str, Any]],
        event_sink: Callable[[AgentEvent], None],
        header_resolver: Any,
        fk_resolver: Any,
        max_rounds: int = 5,
        max_failure_groups: int = 50,
    ):
        self.provider = provider
        self.orchestrator = orchestrator
        self.workbook = workbook
        self.approval = approval_handler
        self.schema_provider = schema_provider
        self.emit = event_sink
        self.header_resolver = header_resolver
        self.fk_resolver = fk_resolver
        self.max_rounds = max_rounds
        self.max_failure_groups = max_failure_groups

    def _fields_for(self, sheet_name: str) -> List[Dict[str, Any]]:
        fields: List[Dict[str, Any]] = (self.schema_provider(model=sheet_name) or {}).get("fields", [])
        return fields

    def _reconcile_headers(self) -> List[Dict[str, Any]]:
        unresolved: List[Dict[str, Any]] = []
        for sheet_name, df in self.workbook.sheets().items():
            fields = self._fields_for(sheet_name)
            field_names = [f["name"] for f in fields]
            headers, uncovered = unmatched_headers(list(df.columns), field_names)
            if not headers:
                continue
            candidate_fields = [
                {"name": f["name"], "type": f.get("type"), "required": f.get("is_required", False)}
                for f in fields
                if f["name"] in uncovered
            ]
            samples = {h: [v for v in df[h].dropna().unique().tolist()[:5]] for h in headers}
            mappings = self.header_resolver.resolve(sheet_name, headers, candidate_fields, samples)

            seen_targets: set = set()
            valid: List[ColumnRename] = []
            columns = list(df.columns)
            for m in mappings:
                if m.field is None or m.field not in field_names or m.field in columns or m.field in seen_targets:
                    unresolved.append({"sheet": sheet_name, "header": m.header, "samples": samples.get(m.header, [])})
                    continue
                seen_targets.add(m.field)
                valid.append(
                    ColumnRename(
                        id=_rename_id(sheet_name, m.header, m.field),
                        sheet_name=sheet_name,
                        current_name=m.header,
                        new_name=m.field,
                        rationale=m.rationale,
                    )
                )

            if valid:
                proposal = ColumnRenameProposal(
                    summary=f"Reconcile {len(valid)} header(s) in {sheet_name}", renames=valid
                )
                self.emit(
                    AgentEvent(
                        kind="rename_proposal",
                        payload={"summary": proposal.summary, "renames": [vars(r) for r in valid]},
                    )
                )
                result: ApprovalResult = self.approval.review_renames(proposal)
                for rn in valid:
                    if result.is_approved(rn.id):
                        self.workbook.rename_column(rn.sheet_name, rn.current_name, rn.new_name)
        return unresolved
