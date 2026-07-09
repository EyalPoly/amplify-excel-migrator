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
    unmatched, uncovered = unmatched_headers(["By", "count"], ["byUserId", "count"])
    assert unmatched == ["By"]
    assert uncovered == ["byUserId"]


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
