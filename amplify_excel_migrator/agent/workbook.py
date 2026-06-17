"""In-memory editable workbook backing the agent's proposed changes."""

from typing import Any, Dict, List

import pandas as pd


class WorkbookEditor:
    def __init__(self, sheets: Dict[str, pd.DataFrame]):
        self._sheets = {name: df.copy() for name, df in sheets.items()}

    @classmethod
    def from_excel(cls, path: str) -> "WorkbookEditor":
        return cls(pd.read_excel(path, sheet_name=None))

    def sheet_names(self) -> List[str]:
        return list(self._sheets.keys())

    def sheets(self) -> Dict[str, pd.DataFrame]:
        return self._sheets

    def preview(self, sheet_name: str, max_rows: int = 20) -> Dict[str, Any]:
        df = self._sheets[sheet_name]
        head = df.head(max_rows).where(pd.notnull(df.head(max_rows)), "")
        return {
            "columns": list(df.columns),
            "row_count": int(len(df)),
            "rows": head.to_dict(orient="records"),
        }

    def cell(self, sheet_name: str, row: int, column: str) -> Any:
        return self._sheets[sheet_name].at[row, column]

    def apply_change(self, sheet_name: str, row: int, column: str, value: Any) -> None:
        df = self._sheets[sheet_name]
        if column not in df.columns:
            raise KeyError(f"Column '{column}' not in sheet '{sheet_name}'")
        df.at[row, column] = value

    def save(self, path_or_buffer: Any) -> None:
        # Accepts a filesystem path or a binary file-like object (e.g. io.BytesIO) — both work with openpyxl,
        # so the web layer can stream the workbook to a download without a temp file.
        with pd.ExcelWriter(path_or_buffer, engine="openpyxl") as writer:
            for name, df in self._sheets.items():
                df.to_excel(writer, sheet_name=name, index=False)
