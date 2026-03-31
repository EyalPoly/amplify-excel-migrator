"""Excel file reading functionality."""

import logging
from typing import Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)


class ExcelReader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def read_all_sheets(self) -> Dict[str, pd.DataFrame]:
        logger.info(f"Reading Excel file: {self.file_path}")
        try:
            all_sheets: Dict[str, pd.DataFrame] = pd.read_excel(self.file_path, sheet_name=None)
        except FileNotFoundError:
            raise FileNotFoundError(f"Excel file not found: {self.file_path}")
        logger.info(f"Loaded {len(all_sheets)} sheets from Excel")
        return all_sheets

    def read_sheet(self, sheet_name: str) -> pd.DataFrame:
        logger.info(f"Reading sheet '{sheet_name}' from Excel file: {self.file_path}")
        try:
            return pd.read_excel(self.file_path, sheet_name=sheet_name)
        except FileNotFoundError:
            raise FileNotFoundError(f"Excel file not found: {self.file_path}")
