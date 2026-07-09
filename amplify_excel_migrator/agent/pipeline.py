"""Deterministic driver: reconcile headers and resolve FK failures via single-shot LLM
resolvers, with a human approving every proposal. No agentic loop."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from amplify_excel_migrator.agent.models import (
    AgentEvent,
    ApprovalResult,
    ColumnRename,
    ColumnRenameProposal,
    ValueMapping,
    ValueMappingProposal,
)
from amplify_excel_migrator.agent.workbook import WorkbookEditor
from amplify_excel_migrator.data.transformer import DataTransformer
from amplify_excel_migrator.migration.failure_grouping import summarize_failures


def fk_workbook_column(df: Any, group_column: str, bad_value: Any) -> Optional[str]:
    for cand in (group_column, f"{group_column}Id"):
        if cand in df.columns:
            return cand
    for col in df.columns:
        try:
            if (df[col] == bad_value).any():
                return str(col)
        except Exception:
            continue
    return None


def unmatched_headers(columns: List[str], fields: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    """Split columns into those the transformer already matches to a schema field and those it does not.

    The transformer matches a column when its camelCase form equals a field name, OR (for is_id
    foreign-key fields like 'reporterId') when the camelCase form equals the field name minus 'Id' —
    so a 'Reporter' column resolves 'reporterId' with no rename. `uncovered` returns the field names
    left unmatched, offered to the resolver as rename targets."""
    field_names = {f["name"] for f in fields}
    id_field_by_stripped = {f["name"][:-2]: f["name"] for f in fields if f.get("is_id") and f["name"].endswith("Id")}

    covered_field_names: set = set()
    unmatched: List[str] = []
    for col in columns:
        camel = DataTransformer.to_camel_case(col)
        if camel in field_names:
            covered_field_names.add(camel)
        elif camel in id_field_by_stripped:
            covered_field_names.add(id_field_by_stripped[camel])
        else:
            unmatched.append(col)
    uncovered = [f["name"] for f in fields if f["name"] not in covered_field_names]
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


def _mapping_id(sheet: str, column: str, from_value: Any, to_value: Any) -> str:
    return f"{sheet}:{column}:{from_value}->{to_value}"


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
        self._needs_create: List[Dict[str, Any]] = []
        self._needs_human: List[Dict[str, Any]] = []

    def run(self) -> PipelineReport:
        self._needs_create = []
        self._needs_human = []
        unresolved_headers = self._reconcile_headers()
        self._resolve_failures()

        final_plan = self.orchestrator.build_plan()
        ready = {s.sheet_name: s.record_count for s in final_plan.sheets if s.status == "ready" and s.record_count}
        uploaded = 0
        if ready:
            selected = self.approval.review_upload(ready)
            result = self.orchestrator.execute(final_plan, selected_sheets=selected)
            uploaded = result.total_success
            self.emit(AgentEvent(kind="upload_result", payload={"total_success": uploaded}))

        remaining_groups: List[Dict[str, Any]] = []
        failed_total = 0
        for sheet in final_plan.sheets:
            summary = summarize_failures(sheet.parsing_failures, self.max_failure_groups)
            failed_total += summary["total_failed_rows"]
            for group in summary["groups"]:
                if not (group["kind"] == "fk_not_found" and group["closest_existing"]):
                    remaining_groups.append({"sheet": sheet.sheet_name, **group})

        report = PipelineReport(
            uploaded=uploaded,
            final_clean=failed_total == 0,
            needs_create=self._needs_create,
            needs_human=self._needs_human,
            unresolved_headers=unresolved_headers,
            remaining_groups=remaining_groups,
        )
        self.emit(AgentEvent(kind="report", payload=vars(report)))
        return report

    def _fields_for(self, sheet_name: str) -> List[Dict[str, Any]]:
        fields: List[Dict[str, Any]] = (self.schema_provider(model=sheet_name) or {}).get("fields", [])
        return fields

    def _reconcile_headers(self) -> List[Dict[str, Any]]:
        unresolved: List[Dict[str, Any]] = []
        for sheet_name, df in self.workbook.sheets().items():
            fields = self._fields_for(sheet_name)
            field_names = [f["name"] for f in fields]
            headers, uncovered = unmatched_headers(list(df.columns), fields)
            if not headers:
                continue
            candidate_fields = [
                {"name": f["name"], "type": f.get("type"), "required": f.get("is_required", False)}
                for f in fields
                if f["name"] in uncovered
            ]
            samples = {h: [v for v in df[h].dropna().unique().tolist()[:5]] for h in headers}
            mappings = self.header_resolver.resolve(sheet_name, headers, candidate_fields, samples)
            self.emit(
                AgentEvent(
                    kind="header_resolution",
                    payload={"sheet": sheet_name, "mappings": [vars(m) for m in mappings]},
                )
            )

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

    def _resolve_failures(self) -> None:
        seen_unresolved: set = set()
        prev_total: Optional[int] = None
        for _ in range(self.max_rounds):
            plan = self.orchestrator.build_plan()
            sheets = self.workbook.sheets()
            total = 0
            actionable: List[Tuple[str, Dict[str, Any]]] = []
            for sheet in plan.sheets:
                summary = summarize_failures(sheet.parsing_failures, self.max_failure_groups)
                total += summary["total_failed_rows"]
                for group in summary["groups"]:
                    if group["kind"] == "fk_not_found" and group["closest_existing"]:
                        actionable.append((sheet.sheet_name, group))
            self.emit(AgentEvent(kind="dry_run", payload={"total_failed_rows": total}))

            if total == 0:
                return
            if prev_total is not None and total >= prev_total:
                return
            prev_total = total

            progressed = False
            for sheet_name, group in actionable:
                key = (sheet_name, group["column"], str(group["value"]))
                res = self.fk_resolver.resolve(sheet_name, group["column"], group["value"], group["closest_existing"])
                self.emit(
                    AgentEvent(
                        kind="fk_resolution",
                        payload={
                            "sheet": sheet_name,
                            "column": group["column"],
                            "value": group["value"],
                            "action": res.action if res else "no_output",
                            "to_value": res.to_value if res else None,
                            "rationale": res.rationale if res else "",
                        },
                    )
                )
                if res is None:
                    continue
                if res.action == "map":
                    if self._apply_fk_map(sheet_name, group, res, sheets):
                        progressed = True
                elif key not in seen_unresolved:
                    seen_unresolved.add(key)
                    record = {"sheet": sheet_name, "column": group["column"], "value": group["value"]}
                    (self._needs_create if res.action == "create" else self._needs_human).append(record)
            if not progressed:
                return

    def _apply_fk_map(self, sheet_name: str, group: Dict[str, Any], res: Any, sheets: Dict[str, Any]) -> bool:
        column = fk_workbook_column(sheets[sheet_name], group["column"], group["value"])
        if column is None:
            self._needs_human.append({"sheet": sheet_name, "column": group["column"], "value": group["value"]})
            return False
        mid = _mapping_id(sheet_name, column, group["value"], res.to_value)
        proposal = ValueMappingProposal(
            summary=f"Map {group['value']!r} → {res.to_value!r} in {sheet_name}.{column}",
            mappings=[
                ValueMapping(
                    id=mid,
                    sheet_name=sheet_name,
                    column=column,
                    from_value=group["value"],
                    to_value=res.to_value,
                    rationale=res.rationale,
                )
            ],
        )
        self.emit(
            AgentEvent(
                kind="value_mapping_proposal",
                payload={"summary": proposal.summary, "mappings": [vars(m) for m in proposal.mappings]},
            )
        )
        result = self.approval.review_value_mappings(proposal)
        if result.is_approved(mid):
            self.workbook.apply_value_mapping(sheet_name, column, group["value"], res.to_value)
            return True
        return False
