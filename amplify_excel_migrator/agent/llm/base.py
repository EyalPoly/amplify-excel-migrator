"""Provider-agnostic LLM types and interface for the agent loop."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class AssistantTurn:
    text: str
    tool_calls: List[ToolCall]
    raw: Any = None

    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class UserMessage:
    content: str
    role: str = field(default="user", init=False)


@dataclass
class AssistantMessage:
    text: str
    tool_calls: List[ToolCall]
    raw: Any = None  # provider-native content (e.g. Claude content blocks incl. thinking) for verbatim round-trip
    role: str = field(default="assistant", init=False)


@dataclass
class ToolResultMessage:
    tool_call_id: str
    content: str
    is_error: bool
    role: str = field(default="tool", init=False)


Message = Any  # UserMessage | AssistantMessage | ToolResultMessage


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system: str, messages: List[Message], tools: List[ToolSpec]) -> AssistantTurn:
        """Run one model turn and return the assistant's text + any tool calls."""
        raise NotImplementedError
