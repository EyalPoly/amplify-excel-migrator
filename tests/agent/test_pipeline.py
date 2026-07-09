import pandas as pd

from amplify_excel_migrator.agent.models import ApprovalResult
from amplify_excel_migrator.agent.pipeline import PreparationPipeline, unmatched_headers
from amplify_excel_migrator.agent.resolvers.header import HeaderMapping
from amplify_excel_migrator.agent.workbook import WorkbookEditor


class FakeHeaderResolver:
    def __init__(self, mappings):
        self._mappings = mappings

    def resolve(self, sheet_name, unmatched, candidate_fields, samples):
        return self._mappings


def _schema_provider(model=None):
    return {
        "fields": [
            {"name": "byUserId", "type": "ID", "is_required": True},
            {"name": "count", "type": "Int", "is_required": True},
        ]
    }


def _pipeline(workbook, approval, header_resolver):
    return PreparationPipeline(
        provider=None,
        orchestrator=None,
        workbook=workbook,
        approval_handler=approval,
        schema_provider=_schema_provider,
        event_sink=lambda e: None,
        header_resolver=header_resolver,
        fk_resolver=None,
    )


class ApprovingHandler:
    def __init__(self):
        self.seen_rename_proposals = []

    def review_renames(self, proposal):
        self.seen_rename_proposals.append(proposal)
        return ApprovalResult(approved_ids=[r.id for r in proposal.renames], rejected_ids=[])


def test_unmatched_headers_uses_camel_case():
    fields = [
        {"name": "byUserId", "type": "ID", "is_required": True, "is_id": True},
        {"name": "count", "type": "Int", "is_required": True, "is_id": False},
    ]
    unmatched, uncovered = unmatched_headers(["By", "count"], fields)
    assert unmatched == ["By"]
    assert uncovered == ["byUserId"]


def test_unmatched_headers_matches_fk_column_by_id_stripping():
    # A 'Reporter' column resolves the is_id field 'reporterId' via Id-stripping — no rename needed,
    # so it must NOT be reported as unmatched, and 'reporterId' must NOT be offered as a rename target.
    fields = [
        {"name": "reporterId", "type": "ID", "is_required": True, "is_id": True},
        {"name": "count", "type": "Int", "is_required": True, "is_id": False},
    ]
    unmatched, uncovered = unmatched_headers(["Reporter", "count"], fields)
    assert unmatched == []
    assert "reporterId" not in uncovered


def test_unmatched_headers_ignores_field_named_only_id():
    # 'Id'[:-2] is '', which must not become a stripped-FK key that a blank column header matches.
    fields = [{"name": "Id", "type": "ID", "is_required": True, "is_id": True}]
    unmatched, uncovered = unmatched_headers([""], fields)
    assert unmatched == [""]
    assert uncovered == ["Id"]


def test_reconcile_rejects_rename_onto_field_a_column_already_covers():
    # 'Reporter' already feeds reporterId via Id-stripping, so renaming 'Notes' onto reporterId
    # would leave two columns writing the same field.
    def schema_provider(model=None):
        return {
            "fields": [
                {"name": "reporterId", "type": "ID", "is_required": True, "is_id": True},
                {"name": "count", "type": "Int", "is_required": True, "is_id": False},
            ]
        }

    wb = WorkbookEditor({"Observation": pd.DataFrame({"Reporter": ["x"], "Notes": ["y"]})})
    approval = ApprovingHandler()
    pipe = PreparationPipeline(
        provider=None,
        orchestrator=None,
        workbook=wb,
        approval_handler=approval,
        schema_provider=schema_provider,
        event_sink=lambda e: None,
        header_resolver=FakeHeaderResolver([HeaderMapping("Notes", "reporterId", 0.9, "wrong")]),
        fk_resolver=None,
    )

    unresolved = pipe._reconcile_headers()

    assert list(wb.sheets()["Observation"].columns) == ["Reporter", "Notes"]
    assert unresolved == [{"sheet": "Observation", "header": "Notes", "samples": ["y"]}]
    assert approval.seen_rename_proposals == []


def test_reconcile_renames_approved_header():
    wb = WorkbookEditor({"Observation": pd.DataFrame({"By": ["u1"], "count": [3]})})
    approval = ApprovingHandler()
    resolver = FakeHeaderResolver([HeaderMapping("By", "byUserId", 0.8, "author")])
    pipe = _pipeline(wb, approval, resolver)

    unresolved = pipe._reconcile_headers()

    assert "byUserId" in wb.sheets()["Observation"].columns
    assert unresolved == []
    assert len(approval.seen_rename_proposals) == 1


def test_reconcile_records_unresolved_header():
    wb = WorkbookEditor({"Observation": pd.DataFrame({"Mystery": ["x"], "count": [3]})})
    approval = ApprovingHandler()
    resolver = FakeHeaderResolver([HeaderMapping("Mystery", None, 0.0, "no idea")])
    pipe = _pipeline(wb, approval, resolver)

    unresolved = pipe._reconcile_headers()

    assert unresolved == [{"sheet": "Observation", "header": "Mystery", "samples": ["x"]}]
    assert approval.seen_rename_proposals == []  # nothing valid to propose


def test_reconcile_drops_mapping_to_nonexistent_field():
    wb = WorkbookEditor({"Observation": pd.DataFrame({"By": ["u1"], "count": [3]})})
    approval = ApprovingHandler()
    resolver = FakeHeaderResolver([HeaderMapping("By", "notAField", 0.9, "wrong")])
    pipe = _pipeline(wb, approval, resolver)

    unresolved = pipe._reconcile_headers()

    assert {"sheet": "Observation", "header": "By", "samples": ["u1"]} in unresolved
    assert "By" in wb.sheets()["Observation"].columns  # not renamed


from amplify_excel_migrator.agent.pipeline import fk_workbook_column
from amplify_excel_migrator.agent.resolvers.fk import FkResolution
from amplify_excel_migrator.migration.models import FieldError, MigrationPlan, RecordFailure, SheetPlan


class FakeOrchestrator:
    """Returns scripted plans in order; records execute() calls."""

    def __init__(self, plans):
        self._plans = list(plans)
        self.executed = []

    def build_plan(self):
        return self._plans.pop(0) if len(self._plans) > 1 else self._plans[0]

    def execute(self, plan, selected_sheets=None):
        self.executed.append(selected_sheets)
        raise AssertionError("execute not expected in these tests")


class FakeFkResolver:
    def __init__(self, resolutions):
        self._resolutions = list(resolutions)
        self.calls = 0

    def resolve(self, sheet_name, column, bad_value, closest_existing):
        self.calls += 1
        return self._resolutions.pop(0)


class ApprovingValueHandler(ApprovingHandler):
    def __init__(self):
        super().__init__()
        self.seen_value_mapping_proposals = []

    def review_value_mappings(self, proposal):
        self.seen_value_mapping_proposals.append(proposal)
        return ApprovalResult(approved_ids=[m.id for m in proposal.mappings], rejected_ids=[])


def _fk_failure(column, value, candidates):
    fe = FieldError(column=column, value=value, kind="fk_not_found", message="x", closest_existing=candidates)
    return RecordFailure(primary_field="k", primary_field_value=1, error="e", original_row={}, field_errors=[fe])


def _plan(sheet_name, failures):
    return MigrationPlan(
        sheets=[
            SheetPlan(
                sheet_name=sheet_name,
                status="ready",
                skip_reason=None,
                total_rows=1,
                record_count=0,
                records=[],
                parsing_failures=failures,
                parsed_model_structure={"fields": []},
                row_dict_by_primary={},
            )
        ]
    )


def test_fk_workbook_column_prefers_id_suffix():
    df = pd.DataFrame({"reporterId": ["דודו"], "count": [1]})
    assert fk_workbook_column(df, "reporter", "דודו") == "reporterId"


def test_fk_workbook_column_falls_back_to_value_scan():
    df = pd.DataFrame({"who": ["דודו"], "count": [1]})
    assert fk_workbook_column(df, "reporter", "דודו") == "who"


def test_resolve_loop_maps_fk_group():
    wb = WorkbookEditor({"Observation": pd.DataFrame({"reporterId": ["Drorr"], "count": [1]})})
    candidates = [{"name": "Dror Gilat", "id": "id-1", "score": 0.7}]
    clean = _plan("Observation", [])
    orch = FakeOrchestrator([_plan("Observation", [_fk_failure("reporter", "Drorr", candidates)]), clean])
    approval = ApprovingValueHandler()
    fk = FakeFkResolver([FkResolution("map", "Dror Gilat", 0.7, "typo")])
    pipe = PreparationPipeline(None, orch, wb, approval, _schema_provider, lambda e: None, None, fk)
    pipe._needs_create, pipe._needs_human = [], []

    pipe._resolve_failures()

    assert wb.sheets()["Observation"]["reporterId"].tolist() == ["Dror Gilat"]
    assert len(approval.seen_value_mapping_proposals) == 1


def test_resolve_loop_records_create_and_stops():
    wb = WorkbookEditor({"Observation": pd.DataFrame({"reporterId": ["New Person"], "count": [1]})})
    candidates = [{"name": "Dror Gilat", "id": "id-1", "score": 0.3}]
    failing = _plan("Observation", [_fk_failure("reporter", "New Person", candidates)])
    orch = FakeOrchestrator([failing])  # same plan every round → stall guard must stop it
    approval = ApprovingValueHandler()
    fk = FakeFkResolver([FkResolution("create", None, 0.9, "new"), FkResolution("create", None, 0.9, "new")])
    pipe = PreparationPipeline(None, orch, wb, approval, _schema_provider, lambda e: None, None, fk)
    pipe._needs_create, pipe._needs_human = [], []

    pipe._resolve_failures()

    assert pipe._needs_create == [{"sheet": "Observation", "column": "reporter", "value": "New Person"}]
    assert fk.calls == 1  # stopped after the zero-progress round; no duplicate recording


from amplify_excel_migrator.migration.models import MigrationResult, SheetResult


class UploadingOrchestrator:
    def __init__(self, plans, total_success):
        self._plans = list(plans)
        self._total_success = total_success
        self.executed_selected = None

    def build_plan(self):
        return self._plans.pop(0) if len(self._plans) > 1 else self._plans[0]

    def execute(self, plan, selected_sheets=None):
        self.executed_selected = selected_sheets
        return MigrationResult(
            sheets=[SheetResult(sheet_name="Observation", success_count=self._total_success, failures=[])],
            total_success=self._total_success,
        )


class FullHandler(ApprovingValueHandler):
    def review_upload(self, ready):
        return set(ready)


def test_run_end_to_end_uploads_when_clean():
    wb = WorkbookEditor({"Observation": pd.DataFrame({"byUserId": ["u1"], "count": [1]})})
    clean = _plan("Observation", [])
    clean.sheets[0].record_count = 1
    orch = UploadingOrchestrator([clean], total_success=1)
    approval = FullHandler()
    pipe = PreparationPipeline(
        None,
        orch,
        wb,
        approval,
        _schema_provider,
        lambda e: None,
        FakeHeaderResolver([]),
        FakeFkResolver([]),
    )

    report = pipe.run()

    assert report.final_clean is True
    assert report.uploaded == 1
    assert orch.executed_selected == {"Observation"}


def test_reconcile_emits_header_resolution_event():
    wb = WorkbookEditor({"Observation": pd.DataFrame({"By": ["u1"], "count": [3]})})
    approval = ApprovingHandler()
    resolver = FakeHeaderResolver([HeaderMapping("By", "byUserId", 0.8, "author")])
    events = []
    pipe = PreparationPipeline(
        provider=None,
        orchestrator=None,
        workbook=wb,
        approval_handler=approval,
        schema_provider=_schema_provider,
        event_sink=events.append,
        header_resolver=resolver,
        fk_resolver=None,
    )

    pipe._reconcile_headers()

    header_events = [e for e in events if e.kind == "header_resolution"]
    assert len(header_events) == 1
    assert header_events[0].payload["sheet"] == "Observation"
    assert header_events[0].payload["mappings"] == [
        {"header": "By", "field": "byUserId", "confidence": 0.8, "rationale": "author"}
    ]


def test_resolve_loop_emits_fk_resolution_event():
    wb = WorkbookEditor({"Observation": pd.DataFrame({"reporterId": ["Drorr"], "count": [1]})})
    candidates = [{"name": "Dror Gilat", "id": "id-1", "score": 0.7}]
    clean = _plan("Observation", [])
    orch = FakeOrchestrator([_plan("Observation", [_fk_failure("reporter", "Drorr", candidates)]), clean])
    approval = ApprovingValueHandler()
    fk = FakeFkResolver([FkResolution("map", "Dror Gilat", 0.7, "typo")])
    events = []
    pipe = PreparationPipeline(None, orch, wb, approval, _schema_provider, events.append, None, fk)
    pipe._needs_create, pipe._needs_human = [], []

    pipe._resolve_failures()

    fk_events = [e for e in events if e.kind == "fk_resolution"]
    assert len(fk_events) == 1
    assert fk_events[0].payload["action"] == "map"
    assert fk_events[0].payload["to_value"] == "Dror Gilat"
    assert fk_events[0].payload["column"] == "reporter"
    assert fk_events[0].payload["value"] == "Drorr"
