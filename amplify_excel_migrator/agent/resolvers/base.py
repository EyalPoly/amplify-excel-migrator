"""A resolver turns one decision into one stateless structured-output round-trip."""

from typing import Any, Callable, Dict, List, Optional

from amplify_excel_migrator.agent.llm.base import (
    AssistantMessage,
    LLMProvider,
    ToolSpec,
    UserMessage,
)

Validator = Callable[[Dict[str, Any]], Optional[str]]


def structured_call(
    provider: LLMProvider,
    system: str,
    user: str,
    tool: ToolSpec,
    validate: Optional[Validator] = None,
    max_retries: int = 1,
) -> Optional[Dict[str, Any]]:
    messages: List[Any] = [UserMessage(content=user)]
    for _ in range(max_retries + 1):
        turn = provider.generate(system, messages, [tool])
        call = turn.tool_calls[0] if turn.tool_calls else None
        if call is not None and call.name == tool.name:
            error = validate(call.arguments) if validate else None
            if error is None:
                return call.arguments
            nudge = error
        else:
            nudge = f"You must call the `{tool.name}` tool with the required fields. Do it now."
        messages.append(AssistantMessage(text=turn.text, tool_calls=turn.tool_calls, raw=turn.raw))
        messages.append(UserMessage(content=nudge))
    return None
