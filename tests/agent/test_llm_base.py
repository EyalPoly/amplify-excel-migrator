from amplify_excel_migrator.agent.llm.base import (
    ToolSpec,
    ToolCall,
    AssistantTurn,
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
)


def test_tool_spec_holds_json_schema():
    spec = ToolSpec(
        name="read_sheet",
        description="Read a sheet",
        input_schema={"type": "object", "properties": {"sheet": {"type": "string"}}},
    )
    assert spec.name == "read_sheet"
    assert spec.input_schema["type"] == "object"


def test_assistant_turn_reports_tool_calls():
    turn = AssistantTurn(
        text="Looking at the sheet.",
        tool_calls=[ToolCall(id="c1", name="read_sheet", arguments={"sheet": "Reporter"})],
    )
    assert turn.has_tool_calls() is True
    assert turn.tool_calls[0].name == "read_sheet"


def test_assistant_turn_without_tool_calls():
    assert AssistantTurn(text="Done.", tool_calls=[]).has_tool_calls() is False


def test_message_roles_are_distinct():
    assert UserMessage(content="hi").role == "user"
    assert AssistantMessage(text="ok", tool_calls=[]).role == "assistant"
    assert ToolResultMessage(tool_call_id="c1", content="result", is_error=False).role == "tool"
