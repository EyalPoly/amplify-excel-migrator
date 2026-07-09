"""Header resolver: map each unmatched workbook header to a schema field with its own call.

One small single-object call per header, not one batched array — small local models reliably
emit a single object but fail to produce a large batched array in one structured output."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from amplify_excel_migrator.agent.llm.base import LLMProvider, ToolSpec
from amplify_excel_migrator.agent.resolvers.base import structured_call

_SYSTEM = (
    "You reconcile one spreadsheet column header to a GraphQL schema. Choose the single schema "
    "field this header should be renamed to, using the field names, types, and the sample values. "
    "If no field is a plausible match, return field=null. Never invent a field name."
)

_TOOL = ToolSpec(
    name="submit_header_mapping",
    description="Return the schema field this header should be renamed to, or null if none fits.",
    input_schema={
        "type": "object",
        "properties": {
            "field": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "rationale": {"type": "string"},
        },
        "required": ["field", "confidence", "rationale"],
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
        field_names = {f["name"] for f in candidate_fields}

        def validate(args: Dict[str, Any]) -> Optional[str]:
            field = args.get("field")
            if field is not None and field not in field_names:
                return "field must be exactly one of the given schema field names, or null."
            return None

        result: List[HeaderMapping] = []
        for header in unmatched_headers:
            user = json.dumps(
                {
                    "sheet": sheet_name,
                    "header": header,
                    "samples": samples.get(header, []),
                    "schema_fields": candidate_fields,
                },
                default=str,
            )
            args = structured_call(self._provider, _SYSTEM, user, _TOOL, validate=validate)
            if args is None:
                result.append(HeaderMapping(header, None, 0.0, "resolver produced no output"))
                continue
            field = args.get("field")
            result.append(
                HeaderMapping(
                    header=header,
                    field=field if isinstance(field, str) and field else None,
                    confidence=float(args.get("confidence", 0.0)),
                    rationale=str(args.get("rationale", "")),
                )
            )
        return result
