from typing import Dict, List, Any, Optional
import logging

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

logger = logging.getLogger(__name__)

_HEADER_FILL = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid")
_HEADER_FONT = Font(bold=True)


def _write_header(ws, columns: List[str]) -> None:
    ws.append(columns)
    for cell in ws[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center")


def _auto_size_columns(ws) -> None:
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=0)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)


class SchemaExporter:
    def __init__(self, client, field_parser):
        self.client = client
        self.field_parser = field_parser

    def export_to_markdown(self, output_path: str, models: Optional[List[str]] = None) -> None:
        logger.info(f"Exporting schema to {output_path}")

        if models is None:
            models = self.discover_models()

        markdown_content = self._generate_markdown(models)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"Schema exported successfully to {output_path}")

    def export_to_excel(self, output_path: str, models: Optional[List[str]] = None) -> None:
        logger.info(f"Exporting schema to {output_path}")

        if models is None:
            models = self.discover_models()

        enums: Dict[str, List[str]] = {}
        custom_types: Dict[str, List[Dict[str, Any]]] = {}

        wb = openpyxl.Workbook()
        wb.remove(wb.active)  # remove default empty sheet

        for model_name in models:
            logger.info(f"Processing model: {model_name}")
            rows = self._parse_model_fields(model_name, enums, custom_types)
            if rows is None:
                continue
            ws = wb.create_sheet(title=self._truncate_sheet_name(model_name))
            _write_header(ws, ["Field Name", "Type", "Required", "Description"])
            for row in rows:
                ws.append(
                    [
                        row["field_name"],
                        row["type_display"],
                        "✅" if row["is_required"] else "❌",
                        row["description"] or "",
                    ]
                )
            _auto_size_columns(ws)

        if enums:
            ws = wb.create_sheet(title="Enums")
            _write_header(ws, ["Enum Name", "Allowed Values"])
            for enum_name, values in sorted(enums.items()):
                ws.append([enum_name, ", ".join(values)])
            _auto_size_columns(ws)

        if custom_types:
            ws = wb.create_sheet(title="Custom Types")
            _write_header(ws, ["Type Name", "Field Name", "Type", "Required"])
            for type_name, fields in sorted(custom_types.items()):
                for f in fields:
                    ws.append([type_name, f["name"], self._format_type_display(f), "✅" if f["is_required"] else "❌"])
            _auto_size_columns(ws)

        wb.save(output_path)
        logger.info(f"Schema exported successfully to {output_path}")

    def discover_models(self) -> List[str]:
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

        enums: Dict[str, List[str]] = {}
        custom_types: Dict[str, List[Dict[str, Any]]] = {}

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
        rows = self._parse_model_fields(model_name, enums, custom_types)
        if rows is None:
            return None

        raw_structure = self.client.get_model_structure(model_name)
        parsed_model = self.field_parser.parse_model_structure(raw_structure)

        lines = [f"## {model_name}", ""]

        if parsed_model.get("description"):
            lines.append(parsed_model["description"])
            lines.append("")

        lines.append("**Excel Sheet Name:** `" + model_name + "`")
        lines.append("")

        if not rows:
            lines.append("*No user-definable fields*")
            lines.append("")
            return lines

        lines.append("| Field Name | Type | Required | Description |")
        lines.append("|------------|------|----------|-------------|")

        for row in rows:
            required = "✅ Yes" if row["is_required"] else "❌ No"
            lines.append(f"| {row['field_name']} | {row['type_display']} | {required} | {row['description']} |")

        lines.append("")
        lines.append("---")
        lines.append("")

        return lines

    def _parse_model_fields(self, model_name: str, enums: Dict, custom_types: Dict) -> Optional[List[Dict[str, Any]]]:
        raw_structure = self.client.get_model_structure(model_name)
        if not raw_structure:
            logger.warning(f"Could not get structure for model: {model_name}")
            return None

        parsed_model = self.field_parser.parse_model_structure(raw_structure)
        if not parsed_model or "fields" not in parsed_model:
            logger.warning(f"Could not parse model structure: {model_name}")
            return None

        fields = [f for f in parsed_model["fields"] if f["name"] not in self.field_parser.metadata_fields]
        rows = []

        for field in fields:
            field_name = field["name"]
            type_display = self._format_type_display(field)
            description = field.get("description") or ""

            if field["is_enum"]:
                enum_values = self._get_enum_values(field["type"])
                if enum_values:
                    enums[field["type"]] = enum_values

            if field["is_custom_type"]:
                custom_type_fields = self._get_custom_type_fields(field["type"])
                if custom_type_fields:
                    custom_types[field["type"]] = custom_type_fields

            if field.get("related_model"):
                field_name = field_name[:-2] if field_name.endswith("Id") else field_name
                type_display += f" (FK → {field['related_model']})"
                description = f"Enter the primary identifier (e.g. name) of the {field['related_model']} record"

            rows.append(
                {
                    "field_name": field_name,
                    "type_display": type_display,
                    "is_required": field["is_required"],
                    "description": description,
                }
            )

        return rows

    @staticmethod
    def _truncate_sheet_name(name: str) -> str:
        return name[:31]

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
