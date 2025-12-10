"""Main migration orchestrator that coordinates the entire migration process."""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd

from amplify_excel_migrator.client import AmplifyClient
from amplify_excel_migrator.data import ExcelReader, DataTransformer
from amplify_excel_migrator.schema import FieldParser
from amplify_excel_migrator.migration import FailureTracker, ProgressReporter, BatchUploader
from amplify_excel_migrator.core import ConfigManager

logger = logging.getLogger(__name__)


class MigrationOrchestrator:
    def __init__(
        self,
        excel_reader: ExcelReader,
        data_transformer: DataTransformer,
        amplify_client: AmplifyClient,
        failure_tracker: FailureTracker,
        progress_reporter: ProgressReporter,
        batch_uploader: BatchUploader,
        field_parser: FieldParser,
    ):
        self.excel_reader = excel_reader
        self.data_transformer = data_transformer
        self.amplify_client = amplify_client
        self.failure_tracker = failure_tracker
        self.progress_reporter = progress_reporter
        self.batch_uploader = batch_uploader
        self.field_parser = field_parser

    def run(self) -> int:
        all_sheets = self.excel_reader.read_all_sheets()

        total_success = 0

        for sheet_name, df in all_sheets.items():
            logger.info(f"Processing {sheet_name} sheet with {len(df)} rows")
            total_success += self.process_sheet(df, sheet_name)

        self._display_summary(len(all_sheets), total_success)

        return total_success

    def process_sheet(self, df: pd.DataFrame, sheet_name: str) -> int:
        self.failure_tracker.set_current_sheet(sheet_name)

        parsed_model_structure = self._get_parsed_model_structure(sheet_name)

        records, row_dict_by_primary = self._transform_rows_to_records(df, parsed_model_structure, sheet_name)

        confirm = input(f"\nUpload {len(records)} records of {sheet_name} to Amplify? (yes/no): ")
        if confirm.lower() != "yes":
            logger.info(f"Upload cancelled for {sheet_name} sheet")
            return 0

        success_count, upload_error_count, failed_uploads = self.batch_uploader.upload_records(
            records, sheet_name, parsed_model_structure
        )

        for failed_upload in failed_uploads:
            primary_value = str(failed_upload["primary_field_value"])
            original_row = row_dict_by_primary.get(primary_value, {})

            self.failure_tracker.record_failure(
                primary_field=failed_upload["primary_field"],
                primary_field_value=failed_upload["primary_field_value"],
                error=failed_upload["error"],
                original_row=original_row,
            )

        failures = self.failure_tracker.get_failures(sheet_name)
        parsing_failures = len(failures) - upload_error_count

        self.progress_reporter.print_sheet_result(
            sheet_name=sheet_name,
            success_count=success_count,
            total_rows=len(df),
            parsing_failures=parsing_failures,
            upload_failures=upload_error_count,
        )

        return success_count

    def _transform_rows_to_records(
        self,
        df: pd.DataFrame,
        parsed_model_structure: Dict[str, Any],
        sheet_name: str,
    ) -> tuple[list[Any], Dict[str, Dict]]:
        df.columns = [self.data_transformer.to_camel_case(c) for c in df.columns]
        primary_field, _, _ = self.amplify_client.get_primary_field_name(sheet_name, parsed_model_structure)

        fk_lookup_cache = {}
        if self.amplify_client:
            logger.info("🚀 Pre-fetching foreign key lookups...")
            fk_lookup_cache = self.amplify_client.build_foreign_key_lookups(df, parsed_model_structure)

        records, row_dict_by_primary, failed_rows = self.data_transformer.transform_rows_to_records(
            df, parsed_model_structure, primary_field, fk_lookup_cache
        )

        for failed_row in failed_rows:
            self.failure_tracker.record_failure(
                primary_field=failed_row["primary_field"],
                primary_field_value=failed_row["primary_field_value"],
                error=failed_row["error"],
                original_row=failed_row["original_row"],
            )

        return records, row_dict_by_primary

    def _get_parsed_model_structure(self, sheet_name: str) -> Dict[str, Any]:
        model_structure = self.amplify_client.get_model_structure(sheet_name)
        return self.field_parser.parse_model_structure(model_structure)

    def _display_summary(self, sheets_processed: int, total_success: int) -> None:
        failures_by_sheet = self.failure_tracker.get_failures_by_sheet()

        self.progress_reporter.print_migration_summary(sheets_processed, total_success, failures_by_sheet)

        if self.failure_tracker.has_failures():
            export_confirm = input("\nExport failed records to Excel? (yes/no): ")
            if export_confirm.lower() == "yes":
                failed_records_file = self.failure_tracker.export_to_excel(self.excel_reader.file_path)
                if failed_records_file:
                    print(f"📁 Failed records exported to: {failed_records_file}")
                    print("=" * 60)

                    update_config = input("\nUpdate config to use this failed records file for next run? (yes/no): ")
                    if update_config.lower() == "yes":
                        config_manager = ConfigManager()
                        config_manager.update({"excel_path": failed_records_file})
                        print(f"✅ Config updated! Next 'migrate' will use: {Path(failed_records_file).name}")
                        print("=" * 60)
            else:
                print("Failed records export skipped.")
                print("=" * 60)
