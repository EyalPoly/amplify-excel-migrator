from unittest.mock import MagicMock
from amplify_excel_migrator.agent.llm.base import (
    ToolSpec,
    ToolCall,
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
)
from amplify_excel_migrator.agent.llm.claude import ClaudeProvider


def _block(type_, **kw):
    b = MagicMock()
    b.type = type_
    for k, v in kw.items():
        setattr(b, k, v)
    return b


def test_generate_parses_text_and_tool_calls():
    client = MagicMock()
    response = MagicMock()
    response.content = [
        _block("text", text="Inspecting."),
        _block("tool_use", id="toolu_1", name="read_sheet", input={"sheet": "Reporter"}),
    ]
    client.messages.create.return_value = response

    provider = ClaudeProvider(client=client, model="claude-opus-4-8")
    turn = provider.generate(
        system="You are a migration agent.",
        messages=[UserMessage(content="Start")],
        tools=[ToolSpec("read_sheet", "Read a sheet", {"type": "object", "properties": {}})],
    )

    assert turn.text == "Inspecting."
    assert turn.tool_calls == [ToolCall(id="toolu_1", name="read_sheet", arguments={"sheet": "Reporter"})]

    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == "claude-opus-4-8"
    assert kwargs["tools"][0]["name"] == "read_sheet"
    assert kwargs["tools"][0]["input_schema"] == {"type": "object", "properties": {}}


def test_tool_result_message_maps_to_user_tool_result_block():
    client = MagicMock()
    client.messages.create.return_value = MagicMock(content=[_block("text", text="ok")])
    provider = ClaudeProvider(client=client, model="claude-opus-4-8")

    provider.generate(
        system="s",
        messages=[
            UserMessage(content="start"),
            AssistantMessage(text="", tool_calls=[ToolCall("toolu_1", "read_sheet", {})]),
            ToolResultMessage(tool_call_id="toolu_1", content="cols: a,b", is_error=False),
        ],
        tools=[],
    )

    sent = client.messages.create.call_args.kwargs["messages"]
    # assistant turn carries a tool_use block; tool result is a user message with a tool_result block
    assert sent[1]["role"] == "assistant"
    assert sent[1]["content"][0]["type"] == "tool_use"
    assert sent[2]["role"] == "user"
    assert sent[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": "cols: a,b",
        "is_error": False,
    }


def test_assistant_raw_content_is_round_tripped_verbatim():
    # When an AssistantMessage carries raw provider blocks (e.g. thinking + tool_use), send them unchanged.
    client = MagicMock()
    client.messages.create.return_value = MagicMock(content=[_block("text", text="ok")])
    provider = ClaudeProvider(client=client, model="claude-opus-4-8")
    raw_blocks = [
        {"type": "thinking", "thinking": "..."},
        {"type": "tool_use", "id": "toolu_1", "name": "dry_run", "input": {}},
    ]

    provider.generate(
        system="s",
        messages=[
            UserMessage(content="start"),
            AssistantMessage(text="", tool_calls=[ToolCall("toolu_1", "dry_run", {})], raw=raw_blocks),
        ],
        tools=[],
    )

    sent = client.messages.create.call_args.kwargs["messages"]
    assert sent[1] == {"role": "assistant", "content": raw_blocks}
