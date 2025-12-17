from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SchemaExporter:
    def __init__(self, client, field_parser):
        self.client = client
        self.field_parser = field_parser

    def export_to_markdown(self, output_path: str, models: Optional[List[str]] = None) -> None:
        logger.info(f"Exporting schema to {output_path}")

        if models is None:
            models = self._discover_models()

        markdown_content = self._generate_markdown(models)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"Schema exported successfully to {output_path}")

    def _discover_models(self) -> List[str]:
        logger.info("Discovering models from schema")
        all_types = self.client.get_all_types()

        if not all_types:
            logger.warning("Could not introspect schema types")
            return []

        query_structure = self.client.get_model_structure("Query")
        query_field_names = set()
        if query_structure and "fields" in query_structure:
            query_field_names = {field.get("name", "") for field in query_structure["fields"]}

        models = set()
        for type_info in all_types:
            type_name = type_info.get("name", "")
            type_kind = type_info.get("kind", "")

            if type_kind == "OBJECT":
                if (
                    not type_name.startswith("__")
                    and type_name not in ["Query", "Mutation", "Subscription"]
                    and not type_name.startswith("Model")
                    and not type_name.endswith("Connection")
                ):

                    has_list_query = any(
                        field_name.startswith("list")
                        and type_name.lower() in field_name.lower()
                        and "By" not in field_name
                        for field_name in query_field_names
                    )

                    if has_list_query:
                        models.add(type_name)

        return sorted(list(models))

    def _generate_markdown(self, models: List[str]) -> str:
        lines = [
            "# GraphQL Schema Reference",
            "",
            "This document provides a complete reference of your GraphQL schema for preparing Excel data migrations.",
            "",
            "## Table of Contents",
            "",
        ]
        for model in models:
            lines.append(f"- [{model}](#{model.lower()})")
        lines.append("")
        lines.append("---")
        lines.append("")

        enums = {}
        custom_types = {}

        for model in models:
            logger.info(f"Processing model: {model}")
            model_section = self._generate_model_section(model, enums, custom_types)
            if model_section:
                lines.extend(model_section)

        if enums:
            lines.append("---")
            lines.append("")
            lines.append("## Enums")
            lines.append("")
            for enum_name, enum_values in sorted(enums.items()):
                lines.append(f"### {enum_name}")
                lines.append("")
                for value in enum_values:
                    lines.append(f"- `{value}`")
                lines.append("")

        if custom_types:
            lines.append("---")
            lines.append("")
            lines.append("## Custom Types")
            lines.append("")
            for type_name, type_fields in sorted(custom_types.items()):
                lines.append(f"### {type_name}")
                lines.append("")
                lines.append("| Field Name | Type | Required |")
                lines.append("|------------|------|----------|")
                for field in type_fields:
                    required = "✅ Yes" if field["is_required"] else "❌ No"
                    type_display = self._format_type_display(field)
                    lines.append(f"| {field['name']} | {type_display} | {required} |")
                lines.append("")

        return "\n".join(lines)

    def _generate_model_section(self, model_name: str, enums: Dict, custom_types: Dict) -> Optional[List[str]]:
        raw_structure = self.client.get_model_structure(model_name)
        if not raw_structure:
            logger.warning(f"Could not get structure for model: {model_name}")
            return None

        parsed_model = self.field_parser.parse_model_structure(raw_structure)
        if not parsed_model or "fields" not in parsed_model:
            logger.warning(f"Could not parse model structure: {model_name}")
            return None

        lines = [f"## {model_name}", ""]

        if parsed_model.get("description"):
            lines.append(parsed_model["description"])
            lines.append("")

        lines.append("**Excel Sheet Name:** `" + model_name + "`")
        lines.append("")

        fields = [f for f in parsed_model["fields"] if f["name"] not in self.field_parser.metadata_fields]

        if not fields:
            lines.append("*No user-definable fields*")
            lines.append("")
            return lines

        lines.append("| Field Name | Type | Required | Description |")
        lines.append("|------------|------|----------|-------------|")

        for field in fields:
            field_name = field["name"]
            required = "✅ Yes" if field["is_required"] else "❌ No"
            type_display = self._format_type_display(field)
            description = field.get("description", "")

            if field["is_enum"]:
                enum_values = self._get_enum_values(field["type"])
                if enum_values:
                    enums[field["type"]] = enum_values

            if field["is_custom_type"]:
                custom_type_fields = self._get_custom_type_fields(field["type"])
                if custom_type_fields:
                    custom_types[field["type"]] = custom_type_fields

            if field.get("related_model"):
                fk_field = field.get("foreign_key", f"{field_name}Id")
                type_display += f" (FK → {field['related_model']})"
                description = f"Foreign key: Use `{fk_field}` column with ID from {field['related_model']} model"

            lines.append(f"| {field_name} | {type_display} | {required} | {description} |")

        lines.append("")
        lines.append("---")
        lines.append("")

        return lines

    @staticmethod
    def _format_type_display(field: Dict[str, Any]) -> str:
        base_type = field["type"]
        type_display = f"`{base_type}`"

        if field["is_list"]:
            type_display = f"`[{base_type}]`"

        if field["is_enum"]:
            type_display += " (Enum)"
        elif field["is_custom_type"]:
            type_display += " (Custom Type)"

        return type_display

    def _get_enum_values(self, enum_name: str) -> List[str]:
        enum_structure = self.client.get_model_structure(enum_name)
        if not enum_structure or "enumValues" not in enum_structure:
            return []

        return [ev["name"] for ev in enum_structure["enumValues"]]

    def _get_custom_type_fields(self, type_name: str) -> List[Dict[str, Any]]:
        type_structure = self.client.get_model_structure(type_name)
        if not type_structure:
            return []

        parsed = self.field_parser.parse_model_structure(type_structure)
        if not parsed or "fields" not in parsed:
            return []

        return [f for f in parsed["fields"] if f["name"] not in self.field_parser.metadata_fields]
