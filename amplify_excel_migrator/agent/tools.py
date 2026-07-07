"""Tool specifications exposed to the agent."""

from typing import List, Set

from amplify_excel_migrator.agent.llm.base import ToolSpec

GATED_TOOLS: Set[str] = {"propose_changes", "upload", "propose_column_renames", "propose_value_mappings"}

TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="inspect_schema",
        description="Return the target GraphQL schema: models, their fields, types, required flags, and enum values. Call this before proposing changes so edits match the schema.",
        input_schema={
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Optional model/sheet name to scope the result."},
            },
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="read_sheet",
        description="Return the columns, row count, and a sample of rows for one sheet of the uploaded workbook.",
        input_schema={
            "type": "object",
            "properties": {
                "sheet": {"type": "string"},
                "max_rows": {"type": "integer", "description": "Sample size (default 20)."},
            },
            "required": ["sheet"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="dry_run",
        description="Build a migration plan WITHOUT uploading. Returns, per sheet: matched model, count of records ready, and the rows that could not be built with their error messages. Use this to discover what still needs fixing.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="propose_changes",
        description="Propose edits to the workbook for human approval. NEVER edits anything directly — each change is reviewed and only approved changes are applied. Use this for any value you would change, especially judgment calls (missing data, guessed values, ambiguous mappings).",
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "One-line summary of this batch."},
                "changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sheet_name": {"type": "string"},
                            "row": {"type": "integer", "description": "0-based row index in the sheet."},
                            "column": {"type": "string"},
                            "proposed_value": {"description": "New value (string/number/bool/null)."},
                            "rationale": {"type": "string", "description": "Why this change, and any assumption made."},
                        },
                        "required": ["sheet_name", "row", "column", "proposed_value", "rationale"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "changes"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="upload",
        description="Upload sheets to Amplify for real. Requires human confirmation of which sheets to upload. Returns success counts and any per-row failures so you can propose fixes and retry.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="propose_column_renames",
        description="Propose 1:1 header renames that remap an existing column to a valid schema field name, for human approval. NEVER renames anything directly — only approved renames are applied. This tool renames existing headers only; it never adds, removes, or merges columns. Use it when read_sheet shows a header that does not match any schema field.",
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "One-line summary of this batch."},
                "renames": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sheet_name": {"type": "string"},
                            "current_name": {"type": "string", "description": "Existing header to rename."},
                            "new_name": {
                                "type": "string",
                                "description": "Target schema field name (exact, camelCase).",
                            },
                            "rationale": {"type": "string", "description": "Why this header maps to that field."},
                        },
                        "required": ["sheet_name", "current_name", "new_name", "rationale"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "renames"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="propose_value_mappings",
        description=(
            "Propose value replacements at the (column, value) level for human approval: 'in column C, "
            "map from_value X to to_value Y', which rewrites EVERY row where C == X. NEVER edits directly "
            "— only approved mappings are applied. Use this to fix a whole dry_run failure group at once "
            "(read column and value straight off the failure group). Set from_value to null to fill blank/"
            "missing cells, or to create and fill a missing required scalar field named after the schema. "
            "Use propose_changes only for genuine one-off single-cell edits."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "One-line summary of this batch."},
                "mappings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sheet_name": {"type": "string"},
                            "column": {"type": "string"},
                            "from_value": {
                                "description": "Existing value to replace (string/number/bool/null). "
                                "null matches blank/missing cells."
                            },
                            "to_value": {"description": "Replacement value (string/number/bool/null)."},
                            "rationale": {"type": "string", "description": "Why this mapping, and any assumption made."},
                        },
                        "required": ["sheet_name", "column", "from_value", "to_value", "rationale"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "mappings"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="finish",
        description="Call when the migration is complete and nothing remains to fix. This ends the session.",
        input_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Short final summary of what was done."},
            },
            "additionalProperties": False,
        },
    ),
]


def tool_names() -> List[str]:
    return [s.name for s in TOOL_SPECS]
