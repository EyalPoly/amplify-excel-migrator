"""FK resolver: decide how to handle a foreign-key value that matches no existing entity."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from amplify_excel_migrator.agent.llm.base import LLMProvider, ToolSpec
from amplify_excel_migrator.agent.resolvers.base import structured_call

_ACTIONS = {"map", "create", "ask_human"}

_SYSTEM = (
    "A foreign-key value in a spreadsheet matches no existing record. You are given the value and "
    "the closest existing records. Decide: 'map' if the value is a typo/variant of one candidate "
    "(set to_value to that candidate's exact name); 'create' if it is clearly a real new entity that "
    "does not exist yet and should be added; 'ask_human' if it is ambiguous or unusable."
)

_TOOL = ToolSpec(
    name="submit_fk_resolution",
    description="Decide how to resolve one unmatched foreign-key value.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["map", "create", "ask_human"]},
            "to_value": {"type": ["string", "null"], "description": "On 'map', the candidate name; else null."},
            "confidence": {"type": "number"},
            "rationale": {"type": "string"},
        },
        "required": ["action", "to_value", "confidence", "rationale"],
        "additionalProperties": False,
    },
)


@dataclass
class FkResolution:
    action: str
    to_value: Optional[str]
    confidence: float
    rationale: str


class FkResolver:
    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def resolve(
        self,
        sheet_name: str,
        column: str,
        bad_value: Any,
        closest_existing: List[Dict[str, Any]],
    ) -> Optional[FkResolution]:
        names = {c["name"] for c in closest_existing}
        user = json.dumps(
            {"sheet": sheet_name, "column": column, "value": bad_value, "candidates": closest_existing},
            default=str,
        )

        def validate(args: Dict[str, Any]) -> Optional[str]:
            if args.get("action") not in _ACTIONS:
                return "action must be one of map, create, ask_human."
            if args["action"] == "map" and args.get("to_value") not in names:
                return "On 'map', to_value must be exactly one of the candidate names."
            return None

        args = structured_call(self._provider, _SYSTEM, user, _TOOL, validate=validate)
        if args is None:
            return None
        return FkResolution(
            action=args["action"],
            to_value=args.get("to_value"),
            confidence=float(args.get("confidence", 0.0)),
            rationale=str(args.get("rationale", "")),
        )
