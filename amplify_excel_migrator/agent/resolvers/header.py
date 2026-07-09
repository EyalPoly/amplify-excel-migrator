"""Header resolver: map unmatched workbook headers to schema fields in one batched call."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from amplify_excel_migrator.agent.llm.base import LLMProvider, ToolSpec
from amplify_excel_migrator.agent.resolvers.base import structured_call

_SYSTEM = (
    "You reconcile spreadsheet column headers to a GraphQL schema. For each header, choose the "
    "single schema field it should be renamed to, using the field names, types, and the sample "
    "values. If no field is a plausible match, return field=null. Never invent a field name."
)

_TOOL = ToolSpec(
    name="submit_header_mappings",
    description="Return, for every header, the schema field to rename it to (or null if none fits).",
    input_schema={
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "header": {"type": "string"},
                        "field": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["header", "field", "confidence", "rationale"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["mappings"],
        "additionalProperties": False,
    },
)


@dataclass
class HeaderMapping:
    header: str
    field: Optional[str]
    confidence: float
    rationale: str


class HeaderResolver:
    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def resolve(
        self,
        sheet_name: str,
        unmatched_headers: List[str],
        candidate_fields: List[Dict[str, Any]],
        samples: Dict[str, List[Any]],
    ) -> List[HeaderMapping]:
        user = json.dumps(
            {
                "sheet": sheet_name,
                "schema_fields": candidate_fields,
                "headers": [{"header": h, "samples": samples.get(h, [])} for h in unmatched_headers],
            },
            default=str,
        )

        def validate(args: Dict[str, Any]) -> Optional[str]:
            if not isinstance(args.get("mappings"), list):
                return "Return a 'mappings' array, one item per header."
            return None

        args = structured_call(self._provider, _SYSTEM, user, _TOOL, validate=validate)
        if args is None:
            return [HeaderMapping(h, None, 0.0, "resolver produced no output") for h in unmatched_headers]

        by_header = {m.get("header"): m for m in args["mappings"] if isinstance(m, dict)}
        result: List[HeaderMapping] = []
        for header in unmatched_headers:
            m = by_header.get(header)
            if m is None:
                result.append(HeaderMapping(header, None, 0.0, "no mapping returned"))
                continue
            field = m.get("field")
            result.append(
                HeaderMapping(
                    header=header,
                    field=field if isinstance(field, str) and field else None,
                    confidence=float(m.get("confidence", 0.0)),
                    rationale=str(m.get("rationale", "")),
                )
            )
        return result
