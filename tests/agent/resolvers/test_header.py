from amplify_excel_migrator.agent.llm.base import AssistantTurn, ToolCall
from amplify_excel_migrator.agent.resolvers.header import HeaderMapping, HeaderResolver

CANDIDATES = [
    {"name": "byUserId", "type": "ID", "required": True},
    {"name": "observationMethod", "type": "String", "required": False},
]


class SequenceProvider:
    """Returns one scripted single-object tool call per generate(); None => no tool call."""

    def __init__(self, args_list):
        self._args_list = list(args_list)
        self.calls = 0

    def generate(self, system, messages, tools):
        self.calls += 1
        args = self._args_list.pop(0)
        calls = [] if args is None else [ToolCall(id="1", name="submit_header_mapping", arguments=args)]
        return AssistantTurn(text="", tool_calls=calls)


def test_resolves_each_header_with_its_own_call():
    provider = SequenceProvider(
        [
            {"field": "byUserId", "confidence": 0.8, "rationale": "author id"},
            {"field": "observationMethod", "confidence": 0.7, "rationale": "method"},
        ]
    )
    result = HeaderResolver(provider).resolve(
        "Observation", ["By", "Report type"], CANDIDATES, {"By": ["u1"], "Report type": ["camera"]}
    )
    assert result == [
        HeaderMapping(header="By", field="byUserId", confidence=0.8, rationale="author id"),
        HeaderMapping(header="Report type", field="observationMethod", confidence=0.7, rationale="method"),
    ]
    assert provider.calls == 2  # one call per header, not one batched call


def test_unmappable_header_returns_none_field():
    provider = SequenceProvider([{"field": None, "confidence": 0.0, "rationale": "no idea"}])
    result = HeaderResolver(provider).resolve("Observation", ["Mystery"], CANDIDATES, {"Mystery": ["x"]})
    assert result == [HeaderMapping(header="Mystery", field=None, confidence=0.0, rationale="no idea")]


def test_hallucinated_field_retried_then_none():
    provider = SequenceProvider(
        [
            {"field": "notAField", "confidence": 0.9, "rationale": "x"},
            {"field": "alsoNot", "confidence": 0.9, "rationale": "x"},
        ]
    )
    result = HeaderResolver(provider).resolve("Observation", ["By"], CANDIDATES, {"By": ["u1"]})
    assert result == [HeaderMapping(header="By", field=None, confidence=0.0, rationale="resolver produced no output")]
    assert provider.calls == 2  # invalid field triggers one retry, then gives up


def test_no_tool_call_yields_none_for_that_header():
    provider = SequenceProvider([None, None])
    result = HeaderResolver(provider).resolve("Observation", ["By"], CANDIDATES, {"By": ["u1"]})
    assert result == [HeaderMapping(header="By", field=None, confidence=0.0, rationale="resolver produced no output")]
