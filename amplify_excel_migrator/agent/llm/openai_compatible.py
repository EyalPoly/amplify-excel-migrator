"""OpenAI-compatible chat-completions adapter (hosted or self-hosted endpoints)."""

import json
from typing import Any, Dict, List, Optional

from amplify_excel_migrator.agent.llm.base import (
    AssistantMessage,
    AssistantTurn,
    LLMProvider,
    Message,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)

MAX_TOKENS = 16000


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        client: Any = None,
        model: str = "",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        tool_choice: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = MAX_TOKENS,
        reasoning_effort: Optional[str] = None,
    ):
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=api_key)
        self._client = client
        self._model = model
        # Some self-hosted servers only emit tool calls when explicitly asked. Set "auto" or "required"
        # for those backends; forwarded only when tools are present. Default None = server default.
        self._tool_choice = tool_choice
        # Lower values (e.g. 0.0-0.2) make tool calls more reliable. Forwarded only when set; default
        # None leaves the server default. 0.0 is a valid value, so the guard is "is not None", not truthiness.
        self._temperature = temperature
        # Output-token ceiling. Configurable because thinking models (e.g. Gemini 2.5-flash) draw
        # their reasoning from this same budget, so the non-thinking default can be too small for them.
        self._max_tokens = max_tokens
        # Thinking-model control (e.g. "none" disables Gemini 2.5-flash thinking). Forwarded only when set.
        self._reasoning_effort = reasoning_effort

    def generate(self, system: str, messages: List[Message], tools: List[ToolSpec]) -> AssistantTurn:
        api_messages = [{"role": "system", "content": system}]
        api_messages.extend(self._message_to_api(m) for m in messages)

        kwargs: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": api_messages,
        }
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if self._reasoning_effort is not None:
            kwargs["reasoning_effort"] = self._reasoning_effort
        if tools:
            kwargs["tools"] = [self._tool_to_api(t) for t in tools]
            if self._tool_choice is not None:
                kwargs["tool_choice"] = self._tool_choice

        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        schemas_by_name = {t.name: t.input_schema for t in tools}
        tool_calls: List[ToolCall] = []
        for call in message.tool_calls or []:
            arguments = json.loads(call.function.arguments or "{}")
            schema = schemas_by_name.get(call.function.name)
            if schema is not None:
                arguments = self._coerce_string_encoded_containers(arguments, schema)
            tool_calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
        return AssistantTurn(text=message.content or "", tool_calls=tool_calls, raw=response)

    @staticmethod
    def _coerce_string_encoded_containers(arguments: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        # Some models/servers serialize nested array/object arguments as a JSON string. The tool schema
        # is the source of truth for which properties should be containers, so re-parse only those.
        if not isinstance(arguments, dict):
            return arguments
        for name, prop in schema.get("properties", {}).items():
            if prop.get("type") in ("array", "object") and isinstance(arguments.get(name), str):
                try:
                    parsed = json.loads(arguments[name])
                except (ValueError, TypeError):
                    continue
                if isinstance(parsed, (list, dict)):
                    arguments[name] = parsed
        return arguments

    @staticmethod
    def _tool_to_api(tool: ToolSpec) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }

    @staticmethod
    def _message_to_api(message: Message) -> Dict[str, Any]:
        if isinstance(message, UserMessage):
            return {"role": "user", "content": message.content}
        if isinstance(message, AssistantMessage):
            # Ollama's /v1 rejects content: null on tool-call turns; send "" instead of None.
            out: Dict[str, Any] = {"role": "assistant", "content": message.text or ""}
            if message.tool_calls:
                out["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.name,
                            "arguments": json.dumps(c.arguments),
                        },
                    }
                    for c in message.tool_calls
                ]
            return out
        if isinstance(message, ToolResultMessage):
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content,
            }
        raise TypeError(f"Unknown message type: {type(message)!r}")
