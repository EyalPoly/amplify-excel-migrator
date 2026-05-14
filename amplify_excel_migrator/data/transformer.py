"""Data transformation from Excel rows to Amplify records."""

import logging
import re
from typing import Dict, Any, Optional, List, Tuple

import pandas as pd

from amplify_excel_migrator.schema import FieldParser

logger = logging.getLogger(__name__)


class DataTransformer:
    def __init__(
        self,
        field_parser: FieldParser,
        default_fk_values: Optional[Dict[str, str]] = None,
        fill_unknown: bool = False,
    ):
        self.field_parser = field_parser
        self.default_fk_values = default_fk_values or {}
        self.fill_unknown = fill_unknown

    def transform_rows_to_records(
        self,
        df: pd.DataFrame,
        parsed_model_structure: Dict[str, Any],
        primary_field: str,
        fk_lookup_cache: Dict[str, Dict[str, Any]],
    ) -> Tuple[List[Dict], Dict[str, Dict], List[Dict]]:
        records = []
        row_dict_by_primary = {}
        failed_rows = []
        row_count = 0

        for row_dict in df.to_dict("records"):
            row_count += 1
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
        self,
        row_dict: Dict,
        parsed_model_structure: Dict[str, Any],
        fk_lookup_cache: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict]:
        model_record = {}
        field_errors = []

        for field in parsed_model_structure["fields"]:
            try:
                input_value = self.parse_input(row_dict, field, fk_lookup_cache)
                if input_value is not None:
                    model_record[field["name"]] = input_value
            except ValueError as e:
                field_errors.append(str(e))

        if field_errors:
            raise ValueError(" | ".join(field_errors))

        return model_record

    def parse_input(
        self,
        row_dict: Dict,
        field: Dict[str, Any],
        fk_lookup_cache: Dict[str, Dict[str, Any]],
    ) -> Any:
        field_name = field["name"][:-2] if field["is_id"] else field["name"]

        # Also accept the full field name with Id suffix (e.g. reporterId as well as reporter)
        if field["is_id"] and field_name not in row_dict and field["name"] in row_dict:
            field_name = field["name"]

        if field.get("is_custom_type"):
            custom_type_fields = field.get("custom_type_fields", [])
            return self.field_parser.build_custom_type_from_columns(
                pd.Series(row_dict), custom_type_fields, field["type"]
            )

        if field_name not in row_dict or pd.isna(row_dict[field_name]):
            if field["is_required"]:
                if field["is_id"] and self.default_fk_values:
                    related_model = self._get_related_model(field)
                    if related_model in self.default_fk_values:
                        return self.default_fk_values[related_model]
                elif self.fill_unknown and not field["is_id"]:
                    return self._default_for_field(field)
                raise ValueError(f"Required field '{field_name}' is missing")
            return None

        value = self.field_parser.clean_input(row_dict[field_name])

        if field["is_id"]:
            return self._resolve_foreign_key(field, value, fk_lookup_cache)
        elif field["is_list"] and field["is_scalar"]:
            return self.field_parser.parse_scalar_array(field, field_name, row_dict[field_name])
        else:
            result = self.field_parser.parse_field_input(field, field_name, value)
            if result is None:
                raise ValueError(f"'{field_name}' could not be parsed as {field['type']} (value: '{value}')")
            return result

    @staticmethod
    def _get_related_model(field: Dict[str, Any]) -> str:
        if "related_model" in field:
            return str(field["related_model"])
        temp = str(field["name"])[:-2]
        return temp[0].upper() + temp[1:]

    @staticmethod
    def _default_for_field(field: Dict[str, Any]) -> Any:
        field_type = field["type"]
        if field_type in ("Int", "Integer", "AWSTimestamp"):
            return 0
        if field_type == "Float":
            return 0.0
        if field_type == "Boolean":
            return False
        if field_type == "AWSDate":
            return "1970-01-01"
        if field_type == "AWSDateTime":
            return "1970-01-01T00:00:00.000Z"
        return "UNKNOWN"

    @staticmethod
    def _resolve_foreign_key(
        field: Dict[str, Any], value: Any, fk_lookup_cache: Dict[str, Dict[str, Any]]
    ) -> Optional[str]:
        related_model = DataTransformer._get_related_model(field)
        column_name = field["name"][:-2] if field["name"].endswith("Id") else field["name"]

        if related_model in fk_lookup_cache:
            lookup_dict: Dict[str, str] = fk_lookup_cache[related_model]["lookup"]
            record_id = lookup_dict.get(str(value))

            if record_id:
                return record_id
            else:
                raise ValueError(f"'{column_name}': '{value}' does not exist")
        else:
            raise ValueError(f"No pre-fetched data for '{column_name}'")

    @staticmethod
    def to_camel_case(s: str) -> str:
        s_with_spaces = re.sub(r"(?<!^)(?=[A-Z])", " ", s)
        parts = re.split(r"[\s_\-]+", s_with_spaces.strip())
        return parts[0].lower() + "".join(word.capitalize() for word in parts[1:])
