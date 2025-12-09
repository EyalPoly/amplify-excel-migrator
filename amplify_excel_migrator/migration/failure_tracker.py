"""Tracks and manages failed records during migration."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class FailureTracker:
    def __init__(self):
        self._failures_by_sheet: Dict[str, List[Dict]] = {}
        self._current_sheet: Optional[str] = None

    def set_current_sheet(self, sheet_name: str) -> None:
        self._current_sheet = sheet_name
        if sheet_name not in self._failures_by_sheet:
            self._failures_by_sheet[sheet_name] = []

    def record_failure(
        self,
        primary_field: str,
        primary_field_value: str,
        error: str,
        original_row: Optional[Dict] = None,
    ) -> None:
        if self._current_sheet is None:
            raise RuntimeError("No current sheet set. Call set_current_sheet() first.")

        failure_record = {
            "primary_field": primary_field,
            "primary_field_value": primary_field_value,
            "error": error,
        }

        if original_row is not None:
            failure_record["original_row"] = original_row

        self._failures_by_sheet[self._current_sheet].append(failure_record)

    def get_failures(self, sheet_name: Optional[str] = None) -> List[Dict]:
        if sheet_name:
            return self._failures_by_sheet.get(sheet_name, [])
        return [failure for failures in self._failures_by_sheet.values() for failure in failures]

    def get_failures_by_sheet(self) -> Dict[str, List[Dict]]:
        return self._failures_by_sheet.copy()

    def get_total_failure_count(self) -> int:
        return sum(len(failures) for failures in self._failures_by_sheet.values())

    def has_failures(self) -> bool:
        return any(len(failures) > 0 for failures in self._failures_by_sheet.values())

    def export_to_excel(self, original_excel_path: str) -> Optional[str]:
        if not self.has_failures():
            return None

        input_path = Path(original_excel_path)
        base_name = input_path.stem
        if "_failed_records_" in base_name:
            base_name = base_name.split("_failed_records_")[0]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{base_name}_failed_records_{timestamp}.xlsx"
        output_path = input_path.parent / output_filename

        logger.info(f"Writing failed records to {output_path}")

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            for sheet_name, failed_records in self._failures_by_sheet.items():
                if not failed_records:
                    continue

                rows_data = []
                for record in failed_records:
                    row_data = record.get("original_row", {}).copy()
                    row_data["ERROR"] = record["error"]
                    rows_data.append(row_data)

                df = pd.DataFrame(rows_data)
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        logger.info(f"Successfully wrote failed records to {output_path}")
        return str(output_path)

    def clear(self) -> None:
        self._failures_by_sheet.clear()
        self._current_sheet = None
