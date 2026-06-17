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
    ):
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=api_key)
        self._client = client
        self._model = model
        # Some self-hosted servers only emit tool calls when explicitly asked. Set "auto" or "required"
        # for those backends; forwarded only when tools are present. Default None = server default.
        self._tool_choice = tool_choice

    def generate(self, system: str, messages: List[Message], tools: List[ToolSpec]) -> AssistantTurn:
        api_messages = [{"role": "system", "content": system}]
        api_messages.extend(self._message_to_api(m) for m in messages)

        kwargs: Dict[str, Any] = {"model": self._model, "max_tokens": MAX_TOKENS, "messages": api_messages}
        if tools:
            kwargs["tools"] = [self._tool_to_api(t) for t in tools]
            if self._tool_choice is not None:
                kwargs["tool_choice"] = self._tool_choice

        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        tool_calls: List[ToolCall] = []
        for call in message.tool_calls or []:
            tool_calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=json.loads(call.function.arguments or "{}"),
                )
            )
        return AssistantTurn(text=message.content or "", tool_calls=tool_calls, raw=response)

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
            out: Dict[str, Any] = {"role": "assistant", "content": message.text or None}
            if message.tool_calls:
                out["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in message.tool_calls
                ]
            return out
        if isinstance(message, ToolResultMessage):
            return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
        raise TypeError(f"Unknown message type: {type(message)!r}")
