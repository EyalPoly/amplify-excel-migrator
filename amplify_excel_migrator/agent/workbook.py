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
        """Return the live frame dict by reference (no copy); callers must treat the frames as read-only."""
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

    def rename_column(self, sheet_name: str, current: str, new: str) -> None:
        df = self._sheets[sheet_name]
        if current not in df.columns:
            raise KeyError(f"Column '{current}' not in sheet '{sheet_name}'")
        if new in df.columns:
            raise ValueError(f"Column '{new}' already exists in sheet '{sheet_name}'")
        self._sheets[sheet_name] = df.rename(columns={current: new})

    def apply_value_mapping(self, sheet_name: str, column: str, from_value: Any, to_value: Any) -> int:
        df = self._sheets[sheet_name]
        if column not in df.columns:
            raise KeyError(f"Column '{column}' not in sheet '{sheet_name}'")
        mask = df[column].isna() if from_value is None else df[column] == from_value
        if not mask.any():
            raise ValueError(f"Value {from_value!r} not present in column '{column}' of sheet '{sheet_name}'")
        df.loc[mask, column] = to_value
        return int(mask.sum())

    def add_column(self, sheet_name: str, column: str, value: Any) -> int:
        df = self._sheets[sheet_name]
        if column in df.columns:
            raise ValueError(f"Column '{column}' already exists in sheet '{sheet_name}'")
        df[column] = value
        return int(len(df))

    def save(self, path_or_buffer: Any) -> None:
        # Accepts a filesystem path or a binary file-like object (e.g. io.BytesIO) — both work with openpyxl,
        # so the web layer can stream the workbook to a download without a temp file.
        with pd.ExcelWriter(path_or_buffer, engine="openpyxl") as writer:
            for name, df in self._sheets.items():
                df.to_excel(writer, sheet_name=name, index=False)
