# scripts/bakeoff_local_llm.py
"""Compare local models on tool-calling reliability for the agent's workload.

Pull the candidates first (see the runbook), then:
    python scripts/bakeoff_local_llm.py
    python scripts/bakeoff_local_llm.py --trials 5 --base-url http://192.168.1.50:11434/v1

Scores each model by how often it emits a structurally valid tool call for a set
of representative prompts. Higher is better. Edit CASES to match your real data.
"""

import argparse

from amplify_excel_migrator.agent.llm.base import ToolSpec, UserMessage
from amplify_excel_migrator.agent.llm.openai_compatible import OpenAICompatibleProvider

CANDIDATES = ["qwen2.5:7b-instruct", "llama3.1:8b", "hermes3:8b"]

PROPOSE_CHANGES = ToolSpec(
    name="propose_changes",
    description="Propose edits to a spreadsheet for human approval.",
    input_schema={
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sheet_name": {"type": "string"},
                        "row": {"type": "integer"},
                        "column": {"type": "string"},
                        "proposed_value": {},
                        "rationale": {"type": "string"},
                    },
                    "required": ["sheet_name", "row", "column", "proposed_value", "rationale"],
                },
            },
        },
        "required": ["summary", "changes"],
    },
)

CASES = [
    {
        "name": "fill-missing-country",
        "prompt": "The 'Reporter' sheet row 1 has an empty 'country' cell but the city is 'Cairo'. "
        "Use propose_changes to set country to 'EG'.",
    },
    {
        "name": "fix-enum-casing",
        "prompt": "The 'Reporter' sheet row 3 'status' cell is 'ACTIVE' but the schema enum is 'active'. "
        "Use propose_changes to fix it.",
    },
]

REQUIRED = {"sheet_name", "row", "column", "proposed_value", "rationale"}


def is_valid_call(turn) -> bool:
    if not turn.tool_calls:
        return False
    call = turn.tool_calls[0]
    if call.name != "propose_changes":
        return False
    changes = call.arguments.get("changes")
    if not isinstance(changes, list) or not changes:
        return False
    return REQUIRED <= set(changes[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--models", nargs="*", default=CANDIDATES)
    args = parser.parse_args()

    print(f"{'model':28} {'score':>9}  per-case")
    for model in args.models:
        provider = OpenAICompatibleProvider(
            base_url=args.base_url,
            api_key="ollama",
            model=model,
            tool_choice="auto",
            temperature=0.1,
        )
        total_ok = total = 0
        per_case = []
        for case in CASES:
            ok = 0
            for _ in range(args.trials):
                total += 1
                try:
                    turn = provider.generate(
                        system="You are a careful data-migration assistant. Use tools when asked.",
                        messages=[UserMessage(content=case["prompt"])],
                        tools=[PROPOSE_CHANGES],
                    )
                    if is_valid_call(turn):
                        ok += 1
                        total_ok += 1
                except Exception as e:  # malformed JSON args / model not pulled / server error
                    print(f"  [{model}] {case['name']}: error {e}")
            per_case.append(f"{case['name']}={ok}/{args.trials}")
        print(f"{model:28} {total_ok}/{total:>7}  {'  '.join(per_case)}")


if __name__ == "__main__":
    main()
