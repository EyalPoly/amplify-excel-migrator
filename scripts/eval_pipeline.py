"""Run the deterministic PreparationPipeline against a workbook and score it, mirroring
scripts/eval_agent_trajectory.py so the two approaches can be compared on the same data.

Example:
    .venv/bin/python scripts/eval_pipeline.py \
        --excel "/path/to/med data 1-5000.xlsx" \
        --sheet-as Observation --model qwen2.5-agent:7b \
        --out scripts/pipeline_output.json
"""

import argparse
import json
import logging
from getpass import getpass
from typing import Any, Dict, List

import pandas as pd

from amplify_excel_migrator.agent.pipeline import PreparationPipeline
from amplify_excel_migrator.agent.resolvers.fk import FkResolver
from amplify_excel_migrator.agent.resolvers.header import HeaderResolver
from amplify_excel_migrator.agent.workbook import WorkbookEditor
from amplify_excel_migrator.client import AmplifyClient
from amplify_excel_migrator.core import ConfigManager
from amplify_excel_migrator.data import DataTransformer, InMemoryExcelReader
from amplify_excel_migrator.migration import MigrationOrchestrator
from amplify_excel_migrator.schema import FieldParser

from eval_agent_trajectory import (  # sibling script; scripts/ is sys.path[0] when run directly
    DiscerningReviewer,
    MockUploader,
    _PacedProvider,
    build_field_enum_values,
    build_provider,
    build_schema_provider,
)


def score(events: List[Dict[str, Any]], report: Any) -> Dict[str, Any]:
    kinds = [e["kind"] for e in events]
    return {
        "finished": kinds[-1] == "report" if kinds else False,
        "uploaded": report.uploaded,
        "final_clean": report.final_clean,
        "counts": {
            "rename_batches": kinds.count("rename_proposal"),
            "value_mapping_batches": kinds.count("value_mapping_proposal"),
            "dry_runs": kinds.count("dry_run"),
            "upload_attempts": kinds.count("upload_result"),
        },
        "needs_create": report.needs_create,
        "needs_human": report.needs_human,
        "unresolved_headers": report.unresolved_headers,
        "remaining_groups": report.remaining_groups,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--excel", required=True)
    p.add_argument("--sheet", default=None)
    p.add_argument("--sheet-as", default="Observation")
    p.add_argument("--model", default="qwen2.5-agent:7b")
    p.add_argument("--base-url", default="http://localhost:11434/v1")
    p.add_argument("--api-key", default="ollama")
    p.add_argument("--temperature", type=float, default=0.1)
    p.add_argument("--reasoning-effort", default=None, choices=["none", "low", "medium", "high"])
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--max-rounds", type=int, default=5)
    p.add_argument("--turn-delay", type=float, default=0.0)
    p.add_argument("--out", default="scripts/pipeline_output.json")
    args = p.parse_args()

    logging.getLogger("amplify_excel_migrator").setLevel(logging.WARNING)

    cfg = ConfigManager().load()
    if not cfg:
        raise SystemExit("No config found. Run 'amplify-migrator config' first.")

    from amplify_auth import CognitoAuthProvider

    auth = CognitoAuthProvider(user_pool_id=cfg["user_pool_id"], client_id=cfg["client_id"], region=cfg["region"])
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
    orchestrator.set_sheets(workbook.sheets())

    provider: Any = build_provider(args)
    if args.turn_delay > 0:
        provider = _PacedProvider(provider, args.turn_delay)

    events: List[Dict[str, Any]] = []
    reviewer = DiscerningReviewer(field_enum_values)
    pipeline = PreparationPipeline(
        provider=provider,
        orchestrator=orchestrator,
        workbook=workbook,
        approval_handler=reviewer,
        schema_provider=schema_provider,
        event_sink=lambda e: events.append({"kind": e.kind, "payload": e.payload}),
        header_resolver=HeaderResolver(provider),
        fk_resolver=FkResolver(provider),
        max_rounds=args.max_rounds,
    )

    report = pipeline.run()
    out = {
        "model": args.model,
        "score": score(events, report),
        "events": events,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(out["score"], ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
