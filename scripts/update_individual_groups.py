#!/usr/bin/env python3
"""
Patch existing Observation records to add individualGroups.

Reads test_files/data-observations.xlsx, builds individualGroups from the
Stage / Sex / Condition / Length / Disk length / Width columns, then updates
each record concurrently using a thread pool.

Requires the migrator to already be configured (amplify-migrator config).
"""

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amplify_excel_migrator.client import AmplifyClient
from amplify_excel_migrator.core import ConfigManager
from amplify_excel_migrator.data.transformer import DataTransformer
from amplify_excel_migrator.schema import FieldParser
from amplify_auth import CognitoAuthProvider

WORKERS = 20  # concurrent HTTP requests
PROGRESS_FILE = Path(__file__).resolve().parent / "update_ig_progress.json"


def load_progress() -> set:
    if PROGRESS_FILE.exists():
        return set(json.loads(PROGRESS_FILE.read_text()))
    return set()


def save_progress(done: set) -> None:
    PROGRESS_FILE.write_text(json.dumps(sorted(done)))


STAGE_MAP = {
    "Adult": "ADULT",
    "Ad": "ADULT",
    "Juvenile": "JUVENILE",
    "Juv": "JUVENILE",
    "Subadult": "SUBADULT",
    "Sub-adult": "SUBADULT",
    "Eggcase": "EGG",
    "Egg": "EGG",
    "Mix": "MIX",
    "Both": "MIX",
}

SEX_MAP = {
    "Female": "FEMALE",
    "Male": "MALE",
    "Both": "BOTH",
    "F": "FEMALE",
    "M": "MALE",
    "Adult": "NA",  # data entry error in one row
}

CONDITION_MAP = {
    "Alive": "ALIVE_AND_FREE",
    "Dead": "FOUND_DEAD",
    "Fished": "FISHED_UNKNOWN",
    "Released": "CAUGHT_AND_RELEASED",
    "Injured": "FOUND_INJURED",
}


def main():
    config_manager = ConfigManager()
    config = config_manager.load()

    if not config:
        print("No configuration found. Run 'amplify-migrator config' first.")
        sys.exit(1)

    password = config_manager.prompt_for_value("Admin Password", secret=True)

    auth_provider = CognitoAuthProvider(
        user_pool_id=config["user_pool_id"],
        client_id=config["client_id"],
        region=config["region"],
    )
    if not auth_provider.authenticate(config["username"], password):
        print("Authentication failed.")
        sys.exit(1)

    amplify_client = AmplifyClient(
        api_endpoint=config["api_endpoint"],
        auth_provider=auth_provider,
    )
    field_parser = FieldParser()

    print("\nFetching IndividualGroup schema...")
    raw_ig = amplify_client.get_model_structure("IndividualGroup")
    ig_parsed = field_parser.parse_model_structure(raw_ig)
    custom_type_fields = ig_parsed["fields"]
    print(f"  IndividualGroup fields: {[f['name'] for f in custom_type_fields]}")

    print("\nFetching existing Observation records (sequentialId → id)...")
    records, _ = amplify_client.get_model_records("Observation", field_parser)
    id_map = {str(r["sequentialId"]): r["id"] for r in records if "sequentialId" in r and "id" in r}
    print(f"  {len(id_map)} records found.")

    print("\nReading test_files/data-observations.xlsx...")
    df = pd.read_excel(Path(__file__).resolve().parent.parent / "test_files" / "data-observations.xlsx")

    def remap(series, mapping):
        return series.map(lambda v: mapping.get(str(v), str(v)) if pd.notna(v) else v)

    df["Stage"] = remap(df["Stage"], STAGE_MAP)
    df["Sex"] = remap(df["Sex"], SEX_MAP)
    df["Condition"] = remap(df["Condition"], CONDITION_MAP)

    transformer = DataTransformer(field_parser)
    df.columns = [transformer.to_camel_case(c) for c in df.columns]

    already_done = load_progress()
    if already_done:
        print(f"\n  Resuming: {len(already_done)} records already updated, skipping them.")

    # Build the list of (seq_id, record_id, groups) to update — parsing is fast, do it upfront
    tasks = []
    skipped_no_record = 0
    skipped_no_groups = 0
    skipped_already_done = 0
    parse_failed = 0

    for _, row in df.iterrows():
        seq_id = str(int(row["sequentialId"])) if pd.notna(row.get("sequentialId")) else None
        if not seq_id:
            skipped_no_record += 1
            continue

        if seq_id in already_done:
            skipped_already_done += 1
            continue

        record_id = id_map.get(seq_id)
        if not record_id:
            print(f"  ⚠️  No Amplify record for sequentialId={seq_id}")
            skipped_no_record += 1
            continue

        try:
            groups = field_parser.build_custom_type_from_columns(row, custom_type_fields, "IndividualGroup")
        except ValueError as e:
            print(f"  ❌ Parse error for sequentialId={seq_id}: {e}")
            parse_failed += 1
            continue

        if not groups:
            skipped_no_groups += 1
            continue

        tasks.append((seq_id, record_id, groups))

    print(
        f"\n  {len(tasks)} records to update ({skipped_no_groups} have no group data, "
        f"{skipped_no_record} not in Amplify, {skipped_already_done} already done, "
        f"{parse_failed} parse errors)"
    )
    print(f"  Running {WORKERS} concurrent workers...\n")

    success = 0
    update_failed = 0
    lock = threading.Lock()

    def update_one(seq_id, record_id, groups):
        amplify_client.update_record("Observation", record_id, {"individualGroups": groups})
        return seq_id

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(update_one, seq_id, record_id, groups): seq_id for seq_id, record_id, groups in tasks
        }

        for future in as_completed(futures):
            seq_id = futures[future]
            try:
                future.result()
                with lock:
                    success += 1
                    already_done.add(seq_id)
                    save_progress(already_done)
                    if success % 100 == 0:
                        print(f"  ✅ {success}/{len(tasks)} updated...")
            except Exception as e:
                with lock:
                    update_failed += 1
                print(f"  ❌ Update failed for sequentialId={seq_id}: {e}")

    print(f"\n{'='*54}")
    print(f"  Updated this run:     {success}")
    print(f"  Already done:         {skipped_already_done}")
    print(f"  Skipped (no groups):  {skipped_no_groups}")
    print(f"  Skipped (no record):  {skipped_no_record}")
    print(f"  Parse errors:         {parse_failed}")
    print(f"  Update failures:      {update_failed}")
    print(f"{'='*54}")
    if update_failed:
        print(f"\n  Re-run the script to retry the {update_failed} failed updates.")


if __name__ == "__main__":
    main()
