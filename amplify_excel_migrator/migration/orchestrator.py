"""Headless migration engine: builds an inspectable plan and executes uploads."""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from amplify_excel_migrator.migration.models import (
    MigrationPlan,
    MigrationResult,
    RecordFailure,
    SheetPlan,
    SheetResult,
)

logger = logging.getLogger(__name__)


class MigrationOrchestrator:
    def __init__(
        self,
        excel_reader,
        data_transformer,
        amplify_client,
        field_parser,
        batch_uploader,
    ):
        self.excel_reader = excel_reader
        self.data_transformer = data_transformer
        self.amplify_client = amplify_client
        self.field_parser = field_parser
        self.batch_uploader = batch_uploader

    def set_sheets(self, sheets: Dict[str, pd.DataFrame]) -> None:
        """Re-target the engine at in-memory frames (requires an InMemoryExcelReader)."""
        self.excel_reader.set_sheets(sheets)

    def build_plan(self) -> MigrationPlan:
        all_sheets = self.excel_reader.read_all_sheets()
        sheets = [self._plan_sheet(df, sheet_name) for sheet_name, df in all_sheets.items()]
        return MigrationPlan(sheets=sheets)

    def _plan_sheet(self, df: pd.DataFrame, sheet_name: str) -> SheetPlan:
        total_rows = len(df)
        try:
            parsed_model_structure = self._get_parsed_model_structure(sheet_name)
        except ValueError as e:
            logger.warning(f"Skipping sheet '{sheet_name}': {e}")
            return SheetPlan(
                sheet_name=sheet_name,
                status="skipped",
                skip_reason=str(e),
                total_rows=total_rows,
                record_count=0,
                records=[],
                parsing_failures=[],
                parsed_model_structure=None,
                row_dict_by_primary={},
            )

        records, row_dict_by_primary, parsing_failures = self._transform_rows_to_records(
            df, parsed_model_structure, sheet_name
        )
        return SheetPlan(
            sheet_name=sheet_name,
            status="ready",
            skip_reason=None,
            total_rows=total_rows,
            record_count=len(records),
            records=records,
            parsing_failures=parsing_failures,
            parsed_model_structure=parsed_model_structure,
            row_dict_by_primary=row_dict_by_primary,
        )

    def execute(self, plan: MigrationPlan, selected_sheets: Optional[Set[str]] = None) -> MigrationResult:
        sheet_results: List[SheetResult] = []
        total_success = 0
        for sheet_plan in plan.sheets:
            if sheet_plan.status != "ready":
                continue
            if selected_sheets is not None and sheet_plan.sheet_name not in selected_sheets:
                continue
            sheet_result = self._execute_sheet(sheet_plan)
            sheet_results.append(sheet_result)
            total_success += sheet_result.success_count
        return MigrationResult(sheets=sheet_results, total_success=total_success)

    def _execute_sheet(self, sheet_plan: SheetPlan) -> SheetResult:
        failures: List[RecordFailure] = list(sheet_plan.parsing_failures)

        success_count, _upload_error_count, failed_uploads = self.batch_uploader.upload_records(
            sheet_plan.records, sheet_plan.sheet_name, sheet_plan.parsed_model_structure
        )

        for failed_upload in failed_uploads:
            primary_value = str(failed_upload["primary_field_value"])
            original_row = sheet_plan.row_dict_by_primary.get(primary_value, {})
            failures.append(
                RecordFailure(
                    primary_field=failed_upload["primary_field"],
                    primary_field_value=failed_upload["primary_field_value"],
                    error=failed_upload["error"],
                    original_row=original_row,
                )
            )

        return SheetResult(
            sheet_name=sheet_plan.sheet_name,
            success_count=success_count,
            failures=failures,
        )

    def _transform_rows_to_records(
        self,
        df: pd.DataFrame,
        parsed_model_structure: Dict[str, Any],
        sheet_name: str,
    ) -> Tuple[List[Any], Dict[str, Dict], List[RecordFailure]]:
        df = df.drop(columns=["ERROR"], errors="ignore").rename(columns=self.data_transformer.to_camel_case)
        primary_field, _, _ = self.amplify_client.get_primary_field_name(sheet_name, parsed_model_structure)

        fk_lookup_cache: Dict[str, Any] = {}
        if self.amplify_client:
            logger.info("🚀 Pre-fetching foreign key lookups...")
            fk_lookup_cache = self.amplify_client.build_foreign_key_lookups(df, parsed_model_structure)

        records, row_dict_by_primary, failed_rows = self.data_transformer.transform_rows_to_records(
            df, parsed_model_structure, primary_field, fk_lookup_cache
        )

        parsing_failures = [
            RecordFailure(
                primary_field=failed_row["primary_field"],
                primary_field_value=failed_row["primary_field_value"],
                error=failed_row["error"],
                original_row=failed_row.get("original_row", {}),
            )
            for failed_row in failed_rows
        ]

        return records, row_dict_by_primary, parsing_failures

    def _get_parsed_model_structure(self, sheet_name: str) -> Dict[str, Any]:
        model_structure = self.amplify_client.get_model_structure(sheet_name)
        parsed_structure: Dict[str, Any] = self.field_parser.parse_model_structure(model_structure)

        for field in parsed_structure["fields"]:
            if field.get("is_custom_type"):
                try:
                    custom_type_raw = self.amplify_client.get_model_structure(field["type"])
                    custom_type_parsed = self.field_parser.parse_model_structure(custom_type_raw)
                    field["custom_type_fields"] = custom_type_parsed["fields"]
                except ValueError:
                    raise ValueError(
                        f"Custom type '{field['type']}' not found in schema (referenced by '{sheet_name}')"
                    )

        return parsed_structure
