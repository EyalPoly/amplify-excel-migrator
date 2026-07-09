from typing import Any, Dict, List, Optional

from amplify_excel_migrator.agent.llm.base import AssistantTurn, ToolCall, ToolSpec
from amplify_excel_migrator.agent.resolvers.base import structured_call

_TOOL = ToolSpec(name="submit", description="", input_schema={"type": "object"})


class SequenceProvider:
    """Returns scripted turns in order; records how many times generate was called."""

    def __init__(self, turns: List[AssistantTurn]):
        self._turns = list(turns)
        self.calls = 0

    def generate(self, system, messages, tools) -> AssistantTurn:
        self.calls += 1
        return self._turns.pop(0)


def _turn_with(args: Dict[str, Any], name: str = "submit") -> AssistantTurn:
    return AssistantTurn(text="", tool_calls=[ToolCall(id="1", name=name, arguments=args)])


def _empty_turn() -> AssistantTurn:
    return AssistantTurn(text="no call", tool_calls=[])


def test_returns_arguments_of_matching_tool_call():
    provider = SequenceProvider([_turn_with({"x": 1})])
    assert structured_call(provider, "sys", "user", _TOOL) == {"x": 1}
    assert provider.calls == 1


def test_no_tool_call_retries_then_returns_none():
    provider = SequenceProvider([_empty_turn(), _empty_turn()])
    assert structured_call(provider, "sys", "user", _TOOL, max_retries=1) is None
    assert provider.calls == 2


def test_wrong_tool_name_is_not_accepted():
    provider = SequenceProvider([_turn_with({"x": 1}, name="other"), _empty_turn()])
    assert structured_call(provider, "sys", "user", _TOOL, max_retries=1) is None


def test_validate_failure_retries_then_succeeds():
    provider = SequenceProvider([_turn_with({"x": 1}), _turn_with({"x": 2})])

    def validate(args: Dict[str, Any]) -> Optional[str]:
        return None if args.get("x") == 2 else "x must be 2"

    assert structured_call(provider, "sys", "user", _TOOL, validate=validate, max_retries=1) == {"x": 2}
    assert provider.calls == 2
