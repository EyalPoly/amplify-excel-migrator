from amplify_excel_migrator.agent.llm.base import AssistantTurn, ToolCall
from amplify_excel_migrator.agent.resolvers.fk import FkResolution, FkResolver

CANDIDATES = [
    {"name": "Dror Gilat", "id": "id-1", "score": 0.65},
    {"name": "Arik", "id": "id-2", "score": 0.5},
]


class OneCallProvider:
    def __init__(self, args):
        self._args = args

    def generate(self, system, messages, tools):
        return AssistantTurn(text="", tool_calls=[ToolCall(id="1", name="submit_fk_resolution", arguments=self._args)])


class SequenceProvider:
    def __init__(self, args_list):
        self._args_list = list(args_list)
        self.calls = 0

    def generate(self, system, messages, tools):
        self.calls += 1
        args = self._args_list.pop(0)
        calls = [] if args is None else [ToolCall(id="1", name="submit_fk_resolution", arguments=args)]
        return AssistantTurn(text="", tool_calls=calls)


class NoCallProvider:
    def generate(self, system, messages, tools):
        return AssistantTurn(text="nope", tool_calls=[])


def test_map_to_candidate_name():
    provider = OneCallProvider({"action": "map", "to_value": "Dror Gilat", "confidence": 0.7, "rationale": "typo"})
    res = FkResolver(provider).resolve("Observation", "reporter", "Drorr Gilat", CANDIDATES)
    assert res == FkResolution(action="map", to_value="Dror Gilat", confidence=0.7, rationale="typo")


def test_create_verdict_passes_through():
    provider = OneCallProvider({"action": "create", "to_value": None, "confidence": 0.9, "rationale": "new person"})
    res = FkResolver(provider).resolve("Observation", "reporter", "Brand New", CANDIDATES)
    assert res.action == "create" and res.to_value is None


def test_map_with_unknown_to_value_retries_then_none():
    provider = SequenceProvider(
        [
            {"action": "map", "to_value": "Not A Candidate", "confidence": 0.6, "rationale": "x"},
            {"action": "map", "to_value": "Still Wrong", "confidence": 0.6, "rationale": "x"},
        ]
    )
    res = FkResolver(provider).resolve("Observation", "reporter", "v", CANDIDATES)
    assert res is None and provider.calls == 2


def test_no_tool_call_returns_none():
    assert FkResolver(NoCallProvider()).resolve("Observation", "reporter", "v", CANDIDATES) is None
