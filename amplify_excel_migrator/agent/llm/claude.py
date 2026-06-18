"""Claude (Anthropic SDK) adapter for the LLMProvider interface."""

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

DEFAULT_MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000


class ClaudeProvider(LLMProvider):
    def __init__(
        self,
        client: Any = None,
        model: str = DEFAULT_MODEL,
        effort: str = "high",
        temperature: Optional[float] = None,
    ):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self._model = model
        self._effort = effort
        # Forwarded only when set; default None leaves the API default. Note: with adaptive thinking
        # enabled the Anthropic API only accepts temperature=1, so a custom value is mainly useful if
        # the deployment is reconfigured without thinking. 0.0 is valid, so the guard is "is not None".
        self._temperature = temperature

    def generate(self, system: str, messages: List[Message], tools: List[ToolSpec]) -> AssistantTurn:
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self._effort},
            "system": system,
            "tools": [self._tool_to_api(t) for t in tools],
            "messages": [self._message_to_api(m) for m in messages],
        }
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        response = self._client.messages.create(**kwargs)
        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
        # raw carries the original content blocks (incl. thinking) for verbatim multi-turn round-trip.
        return AssistantTurn(text="".join(text_parts), tool_calls=tool_calls, raw=response.content)

    @staticmethod
    def _tool_to_api(tool: ToolSpec) -> Dict[str, Any]:
        return {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}

    @staticmethod
    def _message_to_api(message: Message) -> Dict[str, Any]:
        if isinstance(message, UserMessage):
            return {"role": "user", "content": message.content}
        if isinstance(message, AssistantMessage):
            if message.raw is not None:
                # Verbatim round-trip of the original content blocks (preserves thinking blocks).
                return {"role": "assistant", "content": message.raw}
            content: List[Dict[str, Any]] = []
            if message.text:
                content.append({"type": "text", "text": message.text})
            for call in message.tool_calls:
                content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
            return {"role": "assistant", "content": content}
        if isinstance(message, ToolResultMessage):
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": message.tool_call_id,
                        "content": message.content,
                        "is_error": message.is_error,
                    }
                ],
            }
        raise TypeError(f"Unknown message type: {type(message)!r}")
