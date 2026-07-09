"""Trajectory eval: run the real AgentSession loop against a local LLM on the raw
(wrong-header) workbook, end to end, and score the whole run.

Real pieces: OpenAICompatibleProvider (local qwen) + live AmplifyClient (schema +
FK lookups, read-only) + WorkbookEditor(raw file). Simulated pieces: a discerning
approval reviewer and a stateful mock uploader (no real writes).

Renames are scored against --ground-truth (evals/header_ground_truth.yaml), not against
any heuristic in this file, so the grader holds no answer key of its own.

Run it yourself in a real terminal (needs the Cognito password via getpass):
    .venv/bin/python scripts/eval_agent_trajectory.py \
        --excel "/mnt/c/Users/10eya/Downloads/med data 1-5000.xlsx" \
        --sheet-as Observation --model qwen2.5-agent:7b

Full trajectory + score are written to --out (default scripts/trajectory_output.json).
"""

import argparse
import json
import logging
import os
import time
from getpass import getpass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from amplify_excel_migrator.agent.llm.openai_compatible import OpenAICompatibleProvider
from amplify_excel_migrator.agent.models import (
    ApprovalResult,
    ChangeProposal,
    ColumnRenameProposal,
)
from amplify_excel_migrator.agent.session import AgentSession
from amplify_excel_migrator.agent.workbook import WorkbookEditor
from amplify_excel_migrator.client import AmplifyClient
from amplify_excel_migrator.core import ConfigManager
from amplify_excel_migrator.data import DataTransformer, InMemoryExcelReader
from amplify_excel_migrator.migration import MigrationOrchestrator
from amplify_excel_migrator.schema import FieldParser


class GroundTruth:
    """Header -> correct schema field (or None when no rename is correct), per sheet.

    Loaded from a fixture the grader does not otherwise inspect, so the grader can reject a
    wrong rename as readily as it approves a right one. A header the fixture doesn't cover is
    `unknown`: rejected, but counted apart, so a gap in the fixture reads as a gap rather than
    as agent error."""

    def __init__(self, by_sheet: Dict[str, Dict[str, Optional[str]]]):
        self._by_sheet = {s: {self._key(h): f for h, f in headers.items()} for s, headers in by_sheet.items()}

    @staticmethod
    def _key(header: str) -> str:
        return header.strip().lower()

    def lookup(self, sheet: str, header: str) -> "tuple[bool, Optional[str]]":
        """Return (known, expected_field)."""
        headers = self._by_sheet.get(sheet, {})
        key = self._key(header)
        if key not in headers:
            return False, None
        return True, headers[key]

    def judge(self, sheet: str, header: str, new_name: str) -> "tuple[str, str]":
        known, expected = self.lookup(sheet, header)
        if not known:
            return "unknown", f"no ground truth for header '{header}' in sheet '{sheet}'"
        if expected is None:
            return "rejected", f"no rename of '{header}' is correct"
        if expected == new_name:
            return "approved", f"matches ground truth '{expected}'"
        return "rejected", f"ground truth is '{expected}', not '{new_name}'"


def load_ground_truth(path: str) -> GroundTruth:
    try:
        import yaml
    except ImportError:
        raise SystemExit("PyYAML is required: `uv pip install --python .venv/bin/python pyyaml`")
    fixture = Path(path)
    if not fixture.is_file():
        raise SystemExit(f"Ground-truth fixture not found: {path}. Renames cannot be scored without it.")
    data = yaml.safe_load(fixture.read_text()) or {}
    return GroundTruth({sheet: headers or {} for sheet, headers in data.items()})


class DiscerningReviewer:
    """Approves proposals that look correct, rejects the rest, logging every decision.

    - renames: approved only when the target field matches the ground-truth fixture for that
      header. An uncovered header is rejected and counted as `unknown`, which biases the score
      low rather than high.
    - value changes: for enum fields, approved only if the value is a valid enum
      member; otherwise approved when non-empty. Invalid enum values are rejected,
      which exercises the agent's re-propose loop.
    - upload: approves every ready sheet so the mock uploader runs.
    """

    def __init__(self, field_enum_values: Dict[str, Set[str]], ground_truth: GroundTruth):
        self.field_enum_values = field_enum_values
        self.ground_truth = ground_truth
        self.log: List[Dict[str, Any]] = []

    def review_renames(self, proposal: ColumnRenameProposal) -> ApprovalResult:
        approved, rejected = [], []
        for r in proposal.renames:
            decision, reason = self.ground_truth.judge(r.sheet_name, r.current_name, r.new_name)
            (approved if decision == "approved" else rejected).append(r.id)
            self.log.append({"kind": "rename", "id": r.id, "decision": decision, "reason": reason})
        return ApprovalResult(approved_ids=approved, rejected_ids=rejected)

    def review_changes(self, proposal: ChangeProposal) -> ApprovalResult:
        approved, rejected = [], []
        for c in proposal.changes:
            ok, reason = self._judge_change(c.column, c.proposed_value)
            (approved if ok else rejected).append(c.id)
            self.log.append(
                {
                    "kind": "change",
                    "id": c.id,
                    "value": c.proposed_value,
                    "decision": "approved" if ok else "rejected",
                    "reason": reason,
                }
            )
        return ApprovalResult(approved_ids=approved, rejected_ids=rejected)

    def review_upload(self, ready: Dict[str, int]) -> Set[str]:
        self.log.append({"kind": "upload", "decision": "approved", "sheets": list(ready)})
        return set(ready)

    def review_value_mappings(self, proposal) -> ApprovalResult:
        approved, rejected = [], []
        for m in proposal.mappings:
            ok, reason = self._judge_change(m.column, m.to_value)
            (approved if ok else rejected).append(m.id)
            self.log.append(
                {
                    "kind": "value_mapping",
                    "id": m.id,
                    "to_value": m.to_value,
                    "decision": "approved" if ok else "rejected",
                    "reason": reason,
                }
            )
        return ApprovalResult(approved_ids=approved, rejected_ids=rejected)

    def _judge_change(self, column: str, value: Any):
        allowed = self.field_enum_values.get(column)
        if allowed is not None:
            if str(value) in allowed:
                return True, "valid enum value"
            return False, f"'{value}' not in enum {sorted(allowed)}"
        if value in (None, "", "nan"):
            return False, "empty value"
        return True, "non-enum, non-empty"


class MockUploader:
    """Stateful: first upload fails a couple of rows (to exercise retry); later uploads
    all succeed. No real backend writes."""

    def __init__(self, fail_first: int = 2):
        self.fail_first = fail_first
        self.attempts = 0

    def upload_records(
        self,
        records: List[Dict],
        sheet_name: str,
        parsed_model_structure: Dict[str, Any],
    ):
        self.attempts += 1
        if self.attempts == 1 and records:
            n = min(self.fail_first, len(records))
            failed = [
                {
                    "primary_field": "_row",
                    "primary_field_value": i,
                    "error": "SIMULATED: transient backend rejection (retry candidate)",
                }
                for i in range(n)
            ]
            return len(records) - n, n, failed
        return len(records), 0, []


def build_schema_provider(client: AmplifyClient, field_parser: FieldParser):
    enums = client.get_all_enums()

    def schema_provider(model=None):
        if model:
            try:
                parsed = field_parser.parse_model_structure(client.get_model_structure(model))
            except Exception:
                return {}
            parsed = dict(parsed)
            parsed["enums"] = enums
            return parsed
        return {
            "models": [t.get("name") for t in client.get_all_types()],
            "enums": enums,
        }

    return schema_provider, enums


def build_field_enum_values(
    client: AmplifyClient,
    field_parser: FieldParser,
    model: str,
    enums: Dict[str, List[str]],
):
    """Map field name -> set of valid enum values, for the model's enum-typed fields."""
    out: Dict[str, Set[str]] = {}
    try:
        parsed = field_parser.parse_model_structure(client.get_model_structure(model))
    except Exception:
        return out
    for f in parsed.get("fields", []):
        t = f.get("type")
        if t in enums:
            out[f["name"]] = set(enums[t])
    return out


def _exit_reason(events: List[Dict[str, Any]]) -> Any:
    """Label how a run ended, read off the final emitted error event (None if it finished cleanly)."""
    if not events or events[-1]["kind"] != "error":
        return None
    msg = events[-1].get("payload", {}).get("message", "")
    if "without a tool call" in msg:
        return "no_tool_call"
    if "identical arguments" in msg:
        return "repeated_failing_call"
    if "without finishing" in msg:
        return "max_turns"
    return "error"


def score(events: List[Dict[str, Any]], reviewer: DiscerningReviewer) -> Dict[str, Any]:
    kinds = [e["kind"] for e in events]
    tool_calls = [e["payload"]["name"] for e in events if e["kind"] == "tool_call"]

    def first(name):
        return tool_calls.index(name) if name in tool_calls else None

    renames = [e for e in events if e["kind"] == "rename_proposal"]
    proposals = [e for e in events if e["kind"] == "proposal"]
    dry_runs = [e for e in events if e["kind"] == "dry_run"]
    uploads = [e for e in events if e["kind"] == "upload_result"]

    last_dry_before_upload_clean = None
    if dry_runs:
        last = dry_runs[-1]["payload"]["sheets"]
        last_dry_before_upload_clean = all(s.get("total_failed_rows", 0) == 0 for s in last)

    rename_decisions = [d["decision"] for d in reviewer.log if d["kind"] == "rename"]

    return {
        "rename_accuracy": {
            "approved": rename_decisions.count("approved"),
            "rejected": rename_decisions.count("rejected"),
            "unknown": rename_decisions.count("unknown"),
        },
        "finished": kinds[-1] == "done" if kinds else False,
        "exit_reason": _exit_reason(events),
        "tool_call_sequence": tool_calls,
        "schema_inspected_before_edits": (
            first("inspect_schema") is not None
            and all(
                first("inspect_schema") < first(t)
                for t in ("propose_column_renames", "propose_changes")
                if first(t) is not None
            )
        ),
        "no_upload_before_dry_run": (
            first("upload") is None or (first("dry_run") is not None and first("dry_run") < first("upload"))
        ),
        "counts": {
            "inspect_schema": tool_calls.count("inspect_schema"),
            "read_sheet": tool_calls.count("read_sheet"),
            "dry_run": tool_calls.count("dry_run"),
            "rename_batches": len(renames),
            "change_batches": len(proposals),
            "value_mapping_batches": sum(1 for e in events if e["kind"] == "value_mapping_proposal"),
            "upload_attempts": len(uploads),
        },
        "final_dry_run_clean": last_dry_before_upload_clean,
        "review_decisions": reviewer.log,
    }


def build_provider(args) -> OpenAICompatibleProvider:
    kwargs: Dict[str, Any] = dict(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        tool_choice="auto",
        temperature=args.temperature,
    )
    if args.reasoning_effort:
        kwargs["reasoning_effort"] = args.reasoning_effort
    if args.max_tokens:
        kwargs["max_tokens"] = args.max_tokens
    return OpenAICompatibleProvider(**kwargs)


class _PacedProvider:
    """Wraps a provider to sleep before each generate(), to respect RPM limits."""

    def __init__(self, inner: Any, delay: float):
        self._inner = inner
        self._delay = delay

    def generate(self, system, messages, tools):
        time.sleep(self._delay)
        return self._inner.generate(system, messages, tools)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--excel", required=True)
    p.add_argument("--sheet", default=None, help="Source sheet to read (default: first).")
    p.add_argument("--sheet-as", default="Observation", help="Name the sheet after this model.")
    p.add_argument("--model", default="qwen2.5-agent:7b")
    p.add_argument("--base-url", default="http://localhost:11434/v1")
    p.add_argument(
        "--api-key",
        default=os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "ollama",
        help="LLM API key. Defaults to $GEMINI_API_KEY / $OPENAI_API_KEY, else 'ollama' for local.",
    )
    p.add_argument("--temperature", type=float, default=0.1)
    p.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["none", "low", "medium", "high"],
        help="Gemini/thinking models: 'none' disables thinking (fixes empty turns on 2.5-flash).",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Override the provider's output cap (default 16000).",
    )
    p.add_argument("--max-turns", type=int, default=40)
    p.add_argument("--out", default="scripts/trajectory_output.json")
    p.add_argument(
        "--ground-truth",
        default="evals/header_ground_truth.yaml",
        help="Fixture of correct header->field renames. Renames are scored against it alone.",
    )
    p.add_argument(
        "--turn-delay",
        type=float,
        default=0.0,
        help="Seconds to sleep before each LLM call, to pace RPM-limited providers (e.g. Gemini free tier).",
    )
    args = p.parse_args()

    # The agent's _dispatch logs caught tool errors via logger.exception (full tracebacks).
    # Those are expected here (they mean the LLM made a bad tool call) and captured in the
    # trajectory anyway, so quiet the noise; keep genuine warnings from the rest of the package.
    logging.getLogger("amplify_excel_migrator").setLevel(logging.WARNING)
    logging.getLogger("amplify_excel_migrator.agent.session").setLevel(logging.CRITICAL)

    ground_truth = load_ground_truth(args.ground_truth)

    cfg = ConfigManager().load()
    if not cfg:
        raise SystemExit("No config found. Run 'amplify-migrator config' first.")

    from amplify_auth import CognitoAuthProvider

    auth = CognitoAuthProvider(
        user_pool_id=cfg["user_pool_id"],
        client_id=cfg["client_id"],
        region=cfg["region"],
    )
    if not auth.authenticate(cfg["username"], getpass("Admin Password: ")):
        raise SystemExit("Authentication failed.")

    client = AmplifyClient(
        api_endpoint=cfg["api_endpoint"],
        auth_provider=auth,
        composite_unique_fields=cfg.get("composite_unique_fields", {}),
    )
    field_parser = FieldParser()
    schema_provider, enums = build_schema_provider(client, field_parser)
    field_enum_values = build_field_enum_values(client, field_parser, args.sheet_as, enums)

    df = pd.read_excel(args.excel, sheet_name=args.sheet) if args.sheet else pd.read_excel(args.excel)
    workbook = WorkbookEditor({args.sheet_as: df})

    orchestrator = MigrationOrchestrator(
        excel_reader=InMemoryExcelReader(),
        data_transformer=DataTransformer(
            field_parser,
            default_fk_values=cfg.get("default_fk_values", {}),
            fill_unknown=cfg.get("fill_unknown", False),
        ),
        amplify_client=client,
        field_parser=field_parser,
        batch_uploader=MockUploader(),
    )

    provider = build_provider(args)
    if args.turn_delay > 0:
        provider = _PacedProvider(provider, args.turn_delay)

    events: List[Dict[str, Any]] = []
    reviewer = DiscerningReviewer(field_enum_values, ground_truth)
    session = AgentSession(
        provider=provider,
        orchestrator=orchestrator,
        workbook=workbook,
        approval_handler=reviewer,
        schema_provider=schema_provider,
        event_sink=lambda e: events.append({"kind": e.kind, "payload": e.payload}),
    )

    instruction = (
        f"Migrate the uploaded workbook into Amplify. It has one sheet named "
        f"'{args.sheet_as}' whose headers may not match the schema yet. Inspect the "
        f"schema, reconcile the column names, fix any values dry_run reports, then upload."
    )
    run_error = None
    try:
        session.run(instruction, max_turns=args.max_turns)
    except Exception as e:  # rate limits, network, auth — still save what we captured so far
        run_error = f"{type(e).__name__}: {e}"

    result = {
        "model": args.model,
        "instruction": instruction,
        "error": run_error,
        "score": score(events, reviewer),
        "events": events,
    }
    out_path = os.path.abspath(args.out)
    with open(out_path, "w") as fh:
        json.dump(result, fh, indent=2, default=str)

    s = result["score"]
    print(f"model: {args.model}")
    print(f"finished: {s['finished']}  exit_reason: {s['exit_reason']}")
    print(f"tool sequence: {' -> '.join(s['tool_call_sequence'])}")
    print(f"counts: {s['counts']}")
    print(f"renames: {s['rename_accuracy']}")
    print(
        f"schema_before_edits: {s['schema_inspected_before_edits']}  no_upload_before_dry_run: {s['no_upload_before_dry_run']}  final_dry_run_clean: {s['final_dry_run_clean']}"
    )
    if run_error:
        print(f"RUN ERROR (partial trajectory saved): {run_error}")
    print(f"full trajectory written to: {out_path}")


if __name__ == "__main__":
    main()
