# scripts/check_local_llm.py
"""Manual smoke test: confirm the local LLM answers and can call a tool.

Run with the Ollama server up and qwen2.5:7b-instruct pulled:
    python scripts/check_local_llm.py
    python scripts/check_local_llm.py --base-url http://192.168.1.50:11434/v1   # remote GPU box
"""

import argparse
import sys

from amplify_excel_migrator.agent.llm.base import ToolSpec, UserMessage
from amplify_excel_migrator.agent.llm.openai_compatible import OpenAICompatibleProvider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    args = parser.parse_args()

    provider = OpenAICompatibleProvider(
        base_url=args.base_url,
        api_key="ollama",          # any non-empty string; Ollama ignores it
        model=args.model,
        tool_choice="auto",        # nudge Ollama to emit tool calls
    )

    tools = [ToolSpec(
        name="get_weather",
        description="Get the current weather for a city",
        input_schema={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    )]

    turn = provider.generate(
        system="You are a helpful assistant. Use tools when asked.",
        messages=[UserMessage(content="What is the weather in Tel Aviv? Use the get_weather tool.")],
        tools=tools,
    )

    print("text:", repr(turn.text))
    print("tool_calls:", turn.tool_calls)

    if not turn.tool_calls:
        print("\nFAIL: model did not emit a tool call. See Task 6 Step 2.")
        return 1
    call = turn.tool_calls[0]
    if call.name != "get_weather" or "city" not in call.arguments:
        print(f"\nFAIL: unexpected tool call {call!r}")
        return 1

    print("\nPASS: local model is reachable and tool-calling works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
