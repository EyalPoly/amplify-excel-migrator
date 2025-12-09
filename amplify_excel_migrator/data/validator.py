"""Record validation functionality."""

import logging
from typing import Dict, Any, List

import pandas as pd

logger = logging.getLogger(__name__)


class RecordValidator:
    @staticmethod
    def validate_required_fields(row_dict: Dict, parsed_model_structure: Dict[str, Any]) -> List[str]:
        errors = []

        for field in parsed_model_structure["fields"]:
            if not field["is_required"]:
                continue

            field_name = field["name"][:-2] if field["is_id"] else field["name"]

            if field_name not in row_dict or pd.isna(row_dict[field_name]):
                errors.append(f"Required field '{field_name}' is missing")

        return errors

    @staticmethod
    def validate_foreign_key(
        field: Dict[str, Any], value: Any, fk_lookup_cache: Dict[str, Dict[str, str]]
    ) -> List[str]:
        errors = []

        if "related_model" in field:
            related_model = field["related_model"]
        else:
            related_model = (temp := field["name"][:-2])[0].upper() + temp[1:]

        if related_model not in fk_lookup_cache:
            if field["is_required"]:
                errors.append(f"No pre-fetched data for required foreign key {related_model}")
            return errors

        lookup_dict = fk_lookup_cache[related_model]["lookup"]
        if str(value) not in lookup_dict:
            if field["is_required"]:
                errors.append(f"{related_model}: {value} does not exist")

        return errors
