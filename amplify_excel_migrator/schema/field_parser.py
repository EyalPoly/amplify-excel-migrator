from typing import Dict, Any
import logging
import pandas as pd
import unicodedata
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class FieldParser:
    """Parse GraphQL model fields from introspection results"""

    def __init__(self):
        self.scalar_types = {
            "String",
            "Int",
            "Float",
            "Boolean",
            "AWSDate",
            "AWSTime",
            "AWSDateTime",
            "AWSTimestamp",
            "AWSEmail",
            "AWSJSON",
            "AWSURL",
            "AWSPhone",
            "AWSIPAddress",
        }
        self.metadata_fields = {"id", "createdAt", "updatedAt", "owner"}

    def parse_model_structure(self, introspection_result: Dict) -> Dict[str, Any]:
        if not introspection_result:
            logger.error("Empty introspection result received", exc_info=True)
            raise ValueError("Introspection result cannot be empty")

        if "data" in introspection_result and "__type" in introspection_result["data"]:
            type_data = introspection_result["data"]["__type"]
        else:
            type_data = introspection_result

        model_info = {
            "name": type_data.get("name"),
            "kind": type_data.get("kind"),
            "description": type_data.get("description"),
            "fields": [],
        }

        relationships = {}
        relationship_field_names = set()

        if type_data.get("fields"):
            all_field_names = {field.get("name") for field in type_data["fields"]}

            for field in type_data["fields"]:
                rel_info = self._extract_relationship_info(field)
                if rel_info:
                    relationships[rel_info["foreign_key"]] = rel_info["target_model"]
                    if rel_info["foreign_key"] in all_field_names:
                        relationship_field_names.add(field.get("name"))

            for field in type_data["fields"]:
                if field.get("name") in relationship_field_names:
                    continue

                parsed_field = self._parse_field(field)
                if parsed_field:
                    if parsed_field["name"] in relationships:
                        parsed_field["related_model"] = relationships[parsed_field["name"]]
                    model_info["fields"].append(parsed_field)

        return model_info

    def _extract_relationship_info(self, field: Dict) -> Dict[str, str] | None:
        base_type = self.get_base_type_name(field.get("type", {}))
        type_kind = self._get_type_kind(field.get("type", {}))
        field_name = field.get("name", "")

        if type_kind != "OBJECT" or "Connection" in base_type or field_name in self.metadata_fields:
            return None

        inferred_foreign_key = f"{field_name}Id"
        return {"target_model": base_type, "foreign_key": inferred_foreign_key}

    def _parse_field(self, field: Dict) -> Dict[str, Any]:
        base_type = self.get_base_type_name(field.get("type", {}))
        type_kind = self._get_type_kind(field.get("type", {}))

        if "Connection" in base_type or field.get("name") in self.metadata_fields or type_kind == "INTERFACE":
            return {}

        field_info = {
            "name": field.get("name"),
            "description": field.get("description"),
            "type": base_type,
            "is_required": self._is_required_field(field.get("type", {})),
            "is_list": self._is_list_type(field.get("type", {})),
            "is_scalar": base_type in self.scalar_types,
            "is_id": base_type == "ID",
            "is_enum": field.get("type", {}).get("kind") == "ENUM",
            "is_custom_type": type_kind == "OBJECT",
        }

        return field_info

    def get_base_type_name(self, type_obj: Dict) -> str:
        """
        Get the base type name, unwrapping NON_NULL and LIST wrappers
        """

        if not type_obj:
            return "Unknown"

        if type_obj.get("name"):
            return type_obj["name"]

        if type_obj.get("ofType"):
            return self.get_base_type_name(type_obj["ofType"])

        return "Unknown"

    def _get_type_kind(self, type_obj: Dict) -> str:
        if not type_obj:
            return "UNKNOWN"

        if type_obj["kind"] in ["NON_NULL", "LIST"] and type_obj.get("ofType"):
            return self._get_type_kind(type_obj["ofType"])

        return type_obj.get("kind", "UNKNOWN")

    @staticmethod
    def _is_required_field(type_obj: Dict) -> bool:
        return type_obj and type_obj.get("kind") == "NON_NULL"

    def _is_list_type(self, type_obj: Dict) -> bool:
        if not type_obj:
            return False

        if type_obj["kind"] == "LIST":
            return True

        if type_obj.get("ofType"):
            return self._is_list_type(type_obj["ofType"])

        return False

    def build_custom_type_from_columns(self, row: pd.Series, custom_type_fields: list, custom_type_name: str) -> list:
        """Build custom type objects from Excel columns, handling multi-value fields"""

        field_values, max_count = self._collect_custom_type_fields_values(row, custom_type_fields)

        custom_type_objects = self._build_custom_type_objects(
            row, custom_type_fields, custom_type_name, field_values, max_count
        )

        return custom_type_objects if custom_type_objects else None

    @staticmethod
    def _collect_custom_type_fields_values(row: pd.Series, custom_type_fields: list) -> tuple[Dict[str, list], int]:
        field_values = {}
        max_count = 1

        for custom_field in custom_type_fields:
            custom_field_name = custom_field["name"]
            if custom_field_name in row.index and pd.notna(row[custom_field_name]):
                value = row[custom_field_name]

                if isinstance(value, str) and "-" in str(value):
                    parts = [p.strip() for p in str(value).split("-") if p.strip()]
                    if len(parts) > 1:
                        field_values[custom_field_name] = parts
                        max_count = max(max_count, len(parts))
                    else:
                        field_values[custom_field_name] = [None]
                else:
                    field_values[custom_field_name] = [value]
            else:
                field_values[custom_field_name] = [None]

        return field_values, max_count

    def _build_custom_type_objects(
        self,
        row: pd.Series,
        custom_type_fields: list,
        custom_type_name: str,
        field_values: Dict[str, list],
        max_count: int,
    ) -> list:
        custom_type_objects = []

        for i in range(max_count):
            obj = {}

            for custom_field in custom_type_fields:
                custom_field_name = custom_field["name"]
                values_list = field_values.get(custom_field_name, [None])

                if i < len(values_list):
                    value = values_list[i]
                elif len(values_list) == 1:
                    value = values_list[0]
                else:
                    value = None

                if value is None or pd.isna(value):
                    if custom_field["is_required"]:
                        raise ValueError(
                            f"Required field '{custom_field_name}' is missing in custom type '{custom_type_name}' "
                            f"for row {row.name}, group {i + 1}"
                        )
                    continue

                parsed_value = self.parse_field_input(custom_field, custom_field_name, value)
                if parsed_value is not None:
                    obj[custom_field_name] = parsed_value

            if obj:
                custom_type_objects.append(obj)

        return custom_type_objects

    def _convert_single_value(
        self,
        field: Dict[str, Any],
        field_name: str,
        input_value: Any,
        use_dash_notation: bool = False,
        index: int = None,
    ) -> Any:
        if field["type"] in ["Int", "Integer"]:
            if use_dash_notation:
                parsed_value = self.parse_number_dash_notation(input_value)
                return int(parsed_value)
            return int(input_value)
        elif field["type"] == "Float":
            if use_dash_notation:
                parsed_value = self.parse_number_dash_notation(input_value)
                return float(parsed_value)
            return float(input_value)
        elif field["type"] == "Boolean":
            if isinstance(input_value, bool):
                return input_value
            input_str = str(input_value).strip().lower()
            if input_str in ["true", "1", "v", "y", "yes"]:
                return True
            elif input_str in ["false", "0", "n", "x", "no"]:
                return False
            else:
                context = f"array '{field_name}[{index}]'" if index is not None else f"field '{field_name}'"
                logger.error(f"Invalid Boolean value for {context}: {input_value}")
                return None
        elif field.get("is_enum", False):
            return str(input_value).strip().replace(" ", "_").upper()
        elif field["type"] in ["AWSDate", "AWSDateTime"]:
            return self.parse_date(input_value)
        else:
            return str(input_value).strip()

    def parse_field_input(self, field: Dict[str, Any], field_name: str, input_value: Any) -> Any:
        """Parse a single field value from Excel"""
        try:
            return self._convert_single_value(field, field_name, input_value, use_dash_notation=True)
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Failed to parse field '{field_name}' with value '{input_value}' (type: {type(input_value).__name__}) "
                f"for field type '{field['type']}': {e}",
                exc_info=True,
            )
            return None

    def parse_scalar_array(self, field: Dict[str, Any], field_name: str, input_value: Any) -> list | None:
        """
        Parse scalar array from Excel cell supporting multiple formats:
        - JSON: ["value1", "value2", "value3"]
        - Semicolon: value1; value2; value3
        - Comma: value1, value2, value3
        - Space: value1 value2 value3
        """
        if pd.isna(input_value):
            return None

        input_str = str(input_value).strip()
        if not input_str:
            return None

        if input_str.startswith("[") and input_str.endswith("]"):
            try:
                import json

                parsed_json = json.loads(input_str)
                if isinstance(parsed_json, list):
                    return self._convert_array_elements(field, field_name, parsed_json)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON array for field '{field_name}': {input_str}")

        if ";" in input_str:
            values = [v.strip() for v in input_str.split(";") if v.strip()]
            return self._convert_array_elements(field, field_name, values)

        if "," in input_str:
            values = [v.strip() for v in input_str.split(",") if v.strip()]
            return self._convert_array_elements(field, field_name, values)

        values = [v.strip() for v in input_str.split() if v.strip()]
        if len(values) > 1:
            return self._convert_array_elements(field, field_name, values)

        return self._convert_array_elements(field, field_name, [input_str])

    def _convert_array_elements(self, field: Dict[str, Any], field_name: str, values: list) -> list:
        converted = []
        for i, value in enumerate(values):
            cleaned_value = self.clean_input(value)

            if not cleaned_value or (isinstance(cleaned_value, str) and not cleaned_value.strip()):
                continue

            try:
                result = self._convert_single_value(field, field_name, cleaned_value, use_dash_notation=False, index=i)
                if result is not None:
                    converted.append(result)
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to convert array element '{field_name}[{i}]' with value '{cleaned_value}' "
                    f"to type '{field['type']}': {e}"
                )
                continue

        return converted if converted else None

    @staticmethod
    def parse_number_dash_notation(input_value: Any) -> int | float:
        """
        Parse number-dash notation like "2-2" to sum (4).
        Handles cases where pandas auto-converted "2-2" to datetime.

        Examples:
        - "2-2" -> 4
        - "2-2-2" -> 6
        - datetime(2025, 2, 2) -> 4 (extracts month and day)
        """

        if isinstance(input_value, (pd.Timestamp, datetime)):
            input_value = str(input_value)

        # Handle datetime strings that pandas created from "2-2" -> "2025-02-02 00:00:00"
        if isinstance(input_value, str) and " " in input_value and ":" in input_value:
            date_part = input_value.split(" ")[0]
            if "-" in date_part:
                parts = date_part.split("-")
                if len(parts) == 3:
                    return sum([int(parts[1]), int(parts[2])])
                else:
                    return sum([int(p) for p in parts])

        if isinstance(input_value, str) and "-" in str(input_value):
            return sum([int(p.strip()) for p in str(input_value).split("-") if p.strip()])

        return input_value

    @staticmethod
    def clean_input(input_value: Any) -> Any:
        if isinstance(input_value, str):
            input_value = input_value.strip()

            input_value = "".join(
                char
                for char in input_value
                if unicodedata.category(char) not in ("Cf", "Cc") or char in ("\n", "\r", "\t")
            )

        return input_value

    @staticmethod
    def parse_date(input: Any) -> str | None:
        if isinstance(input, (pd.Timestamp, datetime)):
            return input.date().isoformat()

        input_str = str(input).strip()

        try:
            return pd.to_datetime(input_str, format="%d/%m/%Y").date().isoformat()
        except (ValueError, OverflowError):
            try:
                return pd.to_datetime(input_str, format="%d-%m-%Y").date().isoformat()
            except (ValueError, OverflowError):
                try:
                    return pd.to_datetime(input_str).date().isoformat()
                except (ValueError, OverflowError) as e:
                    logger.error(f"Failed to parse date '{input}': {e}")
                    return None
