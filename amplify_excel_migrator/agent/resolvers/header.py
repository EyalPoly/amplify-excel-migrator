"""Header resolver: map each unmatched workbook header to a schema field with its own call.

One small single-object call per header, not one batched array — small local models reliably
emit a single object but fail to produce a large batched array in one structured output. The
prompt is prose, not a JSON blob: a JSON input is echo bait — qwen 7B parrots the input keys
back as the tool arguments instead of filling the output schema."""

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


def _prompt(header: str, samples: List[Any], candidate_fields: List[Dict[str, Any]]) -> str:
    lines = [f'Column header to classify: "{header}"']
    if samples:
        lines.append("Sample values from that column: " + ", ".join(str(s) for s in samples))
    lines.append("Candidate schema fields (name : type):")
    for c in candidate_fields:
        lines.append(f"- {c['name']} : {c.get('type')}")
    lines.append(
        "Call submit_header_mapping with field = the single best-matching field name (or null if "
        "none fits), a confidence between 0 and 1, and a short rationale."
    )
    return "\n".join(lines)


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
            if "field" not in args:
                return "Return the result as field, confidence, rationale. 'field' is a field name or null."
            field = args.get("field")
            if field is not None and field not in field_names:
                return "field must be exactly one of the given schema field names, or null."
            return None

        result: List[HeaderMapping] = []
        for header in unmatched_headers:
            user = _prompt(header, samples.get(header, []), candidate_fields)
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
