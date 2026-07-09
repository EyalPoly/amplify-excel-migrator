from amplify_excel_migrator.agent.llm.base import AssistantTurn, ToolCall
from amplify_excel_migrator.agent.resolvers.header import HeaderMapping, HeaderResolver


class OneCallProvider:
    def __init__(self, args):
        self._args = args
        self.seen_user = None

    def generate(self, system, messages, tools):
        self.seen_user = messages[0].content
        return AssistantTurn(
            text="", tool_calls=[ToolCall(id="1", name="submit_header_mappings", arguments=self._args)]
        )


class NoCallProvider:
    def generate(self, system, messages, tools):
        return AssistantTurn(text="nope", tool_calls=[])


CANDIDATES = [
    {"name": "byUserId", "type": "ID", "required": True},
    {"name": "observationMethod", "type": "String", "required": False},
]


def test_maps_headers_to_fields():
    provider = OneCallProvider(
        {
            "mappings": [
                {"header": "By", "field": "byUserId", "confidence": 0.8, "rationale": "author id"},
                {"header": "Report type", "field": "observationMethod", "confidence": 0.7, "rationale": "method"},
            ]
        }
    )
    result = HeaderResolver(provider).resolve(
        "Observation", ["By", "Report type"], CANDIDATES, {"By": ["u1"], "Report type": ["camera"]}
    )
    assert result == [
        HeaderMapping(header="By", field="byUserId", confidence=0.8, rationale="author id"),
        HeaderMapping(header="Report type", field="observationMethod", confidence=0.7, rationale="method"),
    ]


def test_unmappable_header_returns_none_field():
    provider = OneCallProvider(
        {"mappings": [{"header": "Mystery", "field": None, "confidence": 0.0, "rationale": "no idea"}]}
    )
    result = HeaderResolver(provider).resolve("Observation", ["Mystery"], CANDIDATES, {"Mystery": ["x"]})
    assert result == [HeaderMapping(header="Mystery", field=None, confidence=0.0, rationale="no idea")]


def test_missing_header_in_model_output_becomes_none():
    provider = OneCallProvider({"mappings": []})
    result = HeaderResolver(provider).resolve("Observation", ["By"], CANDIDATES, {"By": ["u1"]})
    assert result == [HeaderMapping(header="By", field=None, confidence=0.0, rationale="no mapping returned")]


def test_no_tool_call_yields_all_none():
    result = HeaderResolver(NoCallProvider()).resolve("Observation", ["By"], CANDIDATES, {"By": ["u1"]})
    assert result == [HeaderMapping(header="By", field=None, confidence=0.0, rationale="resolver produced no output")]
