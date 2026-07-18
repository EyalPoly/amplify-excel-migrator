"""Excel file reading functionality."""

import logging
import warnings
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@contextmanager
def _suppress_openpyxl_extension_warning() -> Iterator[None]:
    # openpyxl warns about drawing/validation extensions it can't parse; they don't
    # affect the cell values we read, so silence just that noise.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Unknown extension is not supported and will be removed",
            category=UserWarning,
        )
        yield


class ExcelReader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def read_all_sheets(self) -> Dict[str, pd.DataFrame]:
        logger.info(f"Reading Excel file: {self.file_path}")
        try:
            with _suppress_openpyxl_extension_warning():
                all_sheets: Dict[str, pd.DataFrame] = pd.read_excel(self.file_path, sheet_name=None)
        except FileNotFoundError:
            raise FileNotFoundError(f"Excel file not found: {self.file_path}")
        logger.info(f"Loaded {len(all_sheets)} sheets from Excel")
        return all_sheets

    def read_sheet(self, sheet_name: str) -> pd.DataFrame:
        logger.info(f"Reading sheet '{sheet_name}' from Excel file: {self.file_path}")
        try:
            with _suppress_openpyxl_extension_warning():
                return pd.read_excel(self.file_path, sheet_name=sheet_name)
        except FileNotFoundError:
            raise FileNotFoundError(f"Excel file not found: {self.file_path}")


class InMemoryExcelReader:
    """Feeds in-memory DataFrames to the orchestrator without round-tripping through disk.

    Shares ExcelReader's read surface so the orchestrator is agnostic to its source. Frames may be
    handed in by reference because build_plan() is read-only with respect to them.
    """

    def __init__(self, sheets: Optional[Dict[str, pd.DataFrame]] = None):
        self._sheets: Dict[str, pd.DataFrame] = sheets if sheets is not None else {}

    def set_sheets(self, sheets: Dict[str, pd.DataFrame]) -> None:
        self._sheets = sheets

    def read_all_sheets(self) -> Dict[str, pd.DataFrame]:
        return self._sheets

    def read_sheet(self, sheet_name: str) -> pd.DataFrame:
        return self._sheets[sheet_name]
