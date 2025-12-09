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
        all_sheets = pd.read_excel(self.file_path, sheet_name=None)
        logger.info(f"Loaded {len(all_sheets)} sheets from Excel")
        return all_sheets

    def read_sheet(self, sheet_name: str) -> pd.DataFrame:
        logger.info(f"Reading sheet '{sheet_name}' from Excel file: {self.file_path}")
        return pd.read_excel(self.file_path, sheet_name=sheet_name)
