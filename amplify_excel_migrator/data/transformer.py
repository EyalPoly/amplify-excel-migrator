"""Data transformation from Excel rows to Amplify records."""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple

import pandas as pd

from amplify_excel_migrator.schema import FieldParser

logger = logging.getLogger(__name__)


class DataTransformer:
    def __init__(self, field_parser: FieldParser):
        self.field_parser = field_parser

    def transform_rows_to_records(
        self,
        df: pd.DataFrame,
        parsed_model_structure: Dict[str, Any],
        primary_field: str,
        fk_lookup_cache: Dict[str, Dict[str, str]],
    ) -> Tuple[List[Dict], Dict[str, Dict], List[Dict]]:
        records = []
        row_dict_by_primary = {}
        failed_rows = []
        row_count = 0

        for row_tuple in df.itertuples(index=False, name="Row"):
            row_count += 1
            row_dict = {col: getattr(row_tuple, col) for col in df.columns}
            primary_field_value = row_dict.get(primary_field, f"Row {row_count}")

            row_dict_by_primary[str(primary_field_value)] = row_dict.copy()

            try:
                record = self.transform_row_to_record(row_dict, parsed_model_structure, fk_lookup_cache)
                if record:
                    records.append(record)
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error transforming row {row_count} ({primary_field}={primary_field_value}): {error_msg}")
                failed_rows.append(
                    {
                        "primary_field": primary_field,
                        "primary_field_value": primary_field_value,
                        "error": f"Parsing error: {error_msg}",
                        "original_row": row_dict,
                    }
                )

        logger.info(f"Prepared {len(records)} records for upload")

        return records, row_dict_by_primary, failed_rows

    def transform_row_to_record(
        self, row_dict: Dict, parsed_model_structure: Dict[str, Any], fk_lookup_cache: Dict[str, Dict[str, str]]
    ) -> Optional[Dict]:
        model_record = {}

        for field in parsed_model_structure["fields"]:
            input_value = self.parse_input(row_dict, field, fk_lookup_cache)
            if input_value is not None:
                model_record[field["name"]] = input_value

        return model_record

    def parse_input(
        self,
        row_dict: Dict,
        field: Dict[str, Any],
        fk_lookup_cache: Dict[str, Dict[str, str]],
    ) -> Any:
        field_name = field["name"][:-2] if field["is_id"] else field["name"]

        if field_name not in row_dict or pd.isna(row_dict[field_name]):
            if field["is_required"]:
                raise ValueError(f"Required field '{field_name}' is missing")
            return None

        value = self.field_parser.clean_input(row_dict[field_name])

        if field["is_id"]:
            return self._resolve_foreign_key(field, value, fk_lookup_cache)
        elif field["is_list"] and field["is_scalar"]:
            return self.field_parser.parse_scalar_array(field, field_name, row_dict[field_name])
        else:
            return self.field_parser.parse_field_input(field, field_name, value)

    @staticmethod
    def _resolve_foreign_key(
        field: Dict[str, Any], value: Any, fk_lookup_cache: Dict[str, Dict[str, str]]
    ) -> Optional[str]:
        if "related_model" in field:
            related_model = field["related_model"]
        else:
            related_model = (temp := field["name"][:-2])[0].upper() + temp[1:]

        if related_model in fk_lookup_cache:
            lookup_dict = fk_lookup_cache[related_model]["lookup"]
            record_id = lookup_dict.get(str(value))

            if record_id:
                return record_id
            else:
                raise ValueError(f"{related_model}: {value} does not exist")
        else:
            raise ValueError(f"No pre-fetched data for {related_model}")

    @staticmethod
    def to_camel_case(s: str) -> str:
        s_with_spaces = re.sub(r"(?<!^)(?=[A-Z])", " ", s)
        parts = re.split(r"[\s_\-]+", s_with_spaces.strip())
        return parts[0].lower() + "".join(word.capitalize() for word in parts[1:])
