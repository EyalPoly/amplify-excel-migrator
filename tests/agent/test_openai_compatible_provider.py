import json
from unittest.mock import MagicMock
from amplify_excel_migrator.agent.llm.base import (
    ToolSpec,
    ToolCall,
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
)
from amplify_excel_migrator.agent.llm.openai_compatible import OpenAICompatibleProvider


def _completion(text, tool_calls=None):
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = tool_calls or []
    choice = MagicMock()
    choice.message = msg
    return MagicMock(choices=[choice])


def _api_tool_call(id_, name, args_dict):
    tc = MagicMock()
    tc.id = id_
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args_dict)
    return tc


def test_generate_parses_text_and_tool_calls():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion(
        "Inspecting.", [_api_tool_call("call_1", "read_sheet", {"sheet": "Reporter"})]
    )
    provider = OpenAICompatibleProvider(client=client, model="local-model")

    turn = provider.generate(
        system="agent",
        messages=[UserMessage(content="Start")],
        tools=[ToolSpec("read_sheet", "Read", {"type": "object", "properties": {}})],
    )

    assert turn.text == "Inspecting."
    assert turn.tool_calls == [ToolCall(id="call_1", name="read_sheet", arguments={"sheet": "Reporter"})]
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "local-model"
    assert kwargs["tools"][0]["function"]["name"] == "read_sheet"
    assert kwargs["messages"][0] == {"role": "system", "content": "agent"}


def test_messages_map_to_openai_shapes():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion("ok")
    provider = OpenAICompatibleProvider(client=client, model="local-model")

    provider.generate(
        system="s",
        messages=[
            UserMessage(content="start"),
            AssistantMessage(text="", tool_calls=[ToolCall("call_1", "read_sheet", {"sheet": "R"})]),
            ToolResultMessage(tool_call_id="call_1", content="cols", is_error=False),
        ],
        tools=[],
    )
    sent = client.chat.completions.create.call_args.kwargs["messages"]
    assert sent[1]["role"] == "user"
    assert sent[2]["role"] == "assistant"
    assert sent[2]["tool_calls"][0]["id"] == "call_1"
    assert json.loads(sent[2]["tool_calls"][0]["function"]["arguments"]) == {"sheet": "R"}
    assert sent[3] == {"role": "tool", "tool_call_id": "call_1", "content": "cols"}


def test_tool_choice_forwarded_only_when_set():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion("ok")
    spec = [ToolSpec("read_sheet", "Read", {"type": "object", "properties": {}})]

    OpenAICompatibleProvider(client=client, model="m").generate("s", [UserMessage("x")], spec)
    assert "tool_choice" not in client.chat.completions.create.call_args.kwargs

    OpenAICompatibleProvider(client=client, model="m", tool_choice="auto").generate("s", [UserMessage("x")], spec)
    assert client.chat.completions.create.call_args.kwargs["tool_choice"] == "auto"
