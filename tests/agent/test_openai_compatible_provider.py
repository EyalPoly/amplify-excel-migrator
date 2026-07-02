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


def test_temperature_forwarded_only_when_set():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion("ok")

    OpenAICompatibleProvider(client=client, model="m").generate("s", [UserMessage("x")], [])
    assert "temperature" not in client.chat.completions.create.call_args.kwargs

    # 0.0 is a meaningful value (deterministic) and must be forwarded despite being falsy.
    OpenAICompatibleProvider(client=client, model="m", temperature=0.0).generate("s", [UserMessage("x")], [])
    assert client.chat.completions.create.call_args.kwargs["temperature"] == 0.0


def test_string_encoded_array_arg_is_reparsed():
    # Some models (e.g. llama3.1 via Ollama) return a nested array argument as a JSON *string*.
    # When the tool schema declares the property an array, recover the real list.
    changes = [
        {
            "sheet_name": "Reporter",
            "row": 0,
            "column": "country",
            "proposed_value": "EG",
            "rationale": "r",
        }
    ]
    client = MagicMock()
    client.chat.completions.create.return_value = _completion(
        "",
        [
            _api_tool_call(
                "c1",
                "propose_changes",
                {"summary": "s", "changes": json.dumps(changes)},
            )
        ],
    )
    spec = ToolSpec(
        "propose_changes",
        "Propose",
        {
            "type": "object",
            "properties": {"summary": {"type": "string"}, "changes": {"type": "array"}},
        },
    )

    turn = OpenAICompatibleProvider(client=client, model="m").generate("s", [UserMessage("x")], [spec])

    assert turn.tool_calls[0].arguments["changes"] == changes


def test_string_encoded_object_arg_is_reparsed():
    payload = {"a": 1, "b": [2, 3]}
    client = MagicMock()
    client.chat.completions.create.return_value = _completion(
        "", [_api_tool_call("c1", "obj_tool", {"payload": json.dumps(payload)})]
    )
    spec = ToolSpec(
        "obj_tool",
        "Obj",
        {"type": "object", "properties": {"payload": {"type": "object"}}},
    )

    turn = OpenAICompatibleProvider(client=client, model="m").generate("s", [UserMessage("x")], [spec])

    assert turn.tool_calls[0].arguments["payload"] == payload


def test_string_arg_with_string_schema_is_left_alone():
    # A genuine string field whose value happens to be valid JSON must NOT be coerced.
    client = MagicMock()
    client.chat.completions.create.return_value = _completion(
        "", [_api_tool_call("c1", "note_tool", {"note": "[1, 2]"})]
    )
    spec = ToolSpec(
        "note_tool",
        "Note",
        {"type": "object", "properties": {"note": {"type": "string"}}},
    )

    turn = OpenAICompatibleProvider(client=client, model="m").generate("s", [UserMessage("x")], [spec])

    assert turn.tool_calls[0].arguments["note"] == "[1, 2]"


def test_unparseable_string_for_array_arg_is_left_alone():
    # If an array-typed property arrives as a non-JSON string, leave it untouched (no crash).
    client = MagicMock()
    client.chat.completions.create.return_value = _completion(
        "", [_api_tool_call("c1", "propose_changes", {"changes": "not json"})]
    )
    spec = ToolSpec(
        "propose_changes",
        "P",
        {"type": "object", "properties": {"changes": {"type": "array"}}},
    )

    turn = OpenAICompatibleProvider(client=client, model="m").generate("s", [UserMessage("x")], [spec])

    assert turn.tool_calls[0].arguments["changes"] == "not json"


def test_max_tokens_defaults_to_16000():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion("ok")

    OpenAICompatibleProvider(client=client, model="m").generate("s", [UserMessage("x")], [])
    assert client.chat.completions.create.call_args.kwargs["max_tokens"] == 16000


def test_max_tokens_is_configurable():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion("ok")

    OpenAICompatibleProvider(client=client, model="m", max_tokens=60000).generate("s", [UserMessage("x")], [])
    assert client.chat.completions.create.call_args.kwargs["max_tokens"] == 60000


def test_reasoning_effort_forwarded_only_when_set():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion("ok")

    # Default: thinking models decide for themselves; we don't send the param.
    OpenAICompatibleProvider(client=client, model="m").generate("s", [UserMessage("x")], [])
    assert "reasoning_effort" not in client.chat.completions.create.call_args.kwargs

    # When set (e.g. "none" to disable Gemini 2.5-flash thinking), forward it.
    OpenAICompatibleProvider(client=client, model="m", reasoning_effort="none").generate("s", [UserMessage("x")], [])
    assert client.chat.completions.create.call_args.kwargs["reasoning_effort"] == "none"
