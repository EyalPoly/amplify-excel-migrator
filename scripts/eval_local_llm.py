# scripts/eval_local_llm.py
"""Graded tool-calling eval harness for the migration agent's local-LLM backends.

Upgrades the bake-off (pass/fail on structure) into a multi-axis eval scored
against *expected outputs*, producing a per-model reliability mark and a
go/no-go gate. It presents the agent's real five tools (agent/tools.py) so it
tests genuine tool *selection*, not just one tool's structure.

Axes (see runbook Task 11):
  - schema validity      did it emit a well-formed call (or correctly none)?
  - tool selection       did it pick the right tool among all 5 TOOL_SPECS?
  - argument correctness field-level match of arguments vs expected
  - reliability          pass^k: does it succeed on ALL k trials (not just one)?

Usage (Ollama up, models pulled, .venv active):
    python scripts/eval_local_llm.py --trials 5
    python scripts/eval_local_llm.py --models qwen2.5:7b-instruct hermes3:8b
    python scripts/eval_local_llm.py --cases evals/cases.yaml --json-out evals/results
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    sys.exit("PyYAML is required: `uv pip install --python .venv/bin/python pyyaml`")

from amplify_excel_migrator.agent.llm.base import UserMessage
from amplify_excel_migrator.agent.llm.openai_compatible import OpenAICompatibleProvider
from amplify_excel_migrator.agent.tools import TOOL_SPECS

# --- tunable scoring config (see runbook Task 11) ---------------------------
WEIGHTS = {"schema": 0.40, "tool_select": 0.20, "arg_acc": 0.25, "passk": 0.15}
GATE = {"schema_min": 0.98, "passk_min": 0.90}  # usable-unattended threshold
CRITICAL_CHANGE_FIELDS = ("sheet_name", "row", "column", "proposed_value")  # rationale/summary excluded
DEFAULT_MODELS = ["qwen2.5:7b-instruct", "llama3.1:8b", "hermes3:8b"]
SYSTEM = (
    "You are a careful data-migration assistant for an Excel-to-Amplify tool. "
    "Use the provided tools when the task calls for one; answer in plain text when no tool applies."
)

SPEC_BY_NAME = {s.name: s for s in TOOL_SPECS}


# --- structural validity (generic JSON-schema-ish check vs the tool spec) ----
def _valid_against_schema(value, schema: dict) -> bool:
    t = schema.get("type")
    if t == "object":
        if not isinstance(value, dict):
            return False
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value or not _valid_against_schema(value[req], props.get(req, {})):
                return False
        return True
    if t == "array":
        if not isinstance(value, list):
            return False
        item_schema = schema.get("items", {})
        return all(_valid_against_schema(it, item_schema) for it in value)
    return True  # scalar / unconstrained -> accept


def _is_well_formed(call) -> bool:
    spec = SPEC_BY_NAME.get(call.name)
    return spec is not None and _valid_against_schema(call.arguments, spec.input_schema)


# --- field-level argument matching ------------------------------------------
def _norm(v):
    return v.strip().lower() if isinstance(v, str) else v


def _field_match(expected, actual, policy: str = "exact") -> bool:
    if policy == "ci":
        return _norm(expected) == _norm(actual)
    if policy == "numeric":
        try:
            return abs(float(expected) - float(actual)) <= 1e-9
        except (TypeError, ValueError):
            return False
    return expected == actual


def _expects_args(expect: dict) -> bool:
    return "changes" in expect or "args" in expect


def _arg_accuracy(call, expect: dict):
    """Return field-level accuracy in [0,1], or None when no args are expected."""
    policy = expect.get("match", {})
    if "changes" in expect:
        got = call.arguments.get("changes")
        if not isinstance(got, list) or not got:
            return 0.0
        scores = []
        for ec in expect["changes"]:
            fields = [f for f in CRITICAL_CHANGE_FIELDS if f in ec]
            best = 0.0
            for gc in got:  # best-matching proposed change (order-independent)
                if not isinstance(gc, dict):
                    continue
                hits = sum(_field_match(ec[f], gc.get(f), policy.get(f, "exact")) for f in fields)
                best = max(best, hits / len(fields) if fields else 1.0)
            scores.append(best)
        return sum(scores) / len(scores)
    if "args" in expect:
        exp = expect["args"]
        got = call.arguments
        if not exp:
            return 1.0
        hits = sum(_field_match(v, got.get(k), policy.get(k, "exact")) for k, v in exp.items())
        return hits / len(exp)
    return None


# --- per-trial scoring -------------------------------------------------------
def score_turn(turn, expect: dict):
    """Return (schema_ok: bool, tool_ok: bool, arg_acc: float|None)."""
    exp_tool = expect.get("tool", "none")
    calls = turn.tool_calls
    if exp_tool == "none":
        schema_ok = all(_is_well_formed(c) for c in calls)  # True if no calls
        return schema_ok, len(calls) == 0, None
    if not calls:
        return False, False, (0.0 if _expects_args(expect) else None)
    call = calls[0]
    schema_ok = _is_well_formed(call)
    tool_ok = call.name == exp_tool
    arg_acc = _arg_accuracy(call, expect) if tool_ok else (0.0 if _expects_args(expect) else None)
    return schema_ok, tool_ok, arg_acc


def trial_is_correct(schema_ok, tool_ok, arg_acc) -> bool:
    return bool(schema_ok and tool_ok and (arg_acc is None or arg_acc >= 1.0))


# --- run ---------------------------------------------------------------------
def evaluate_model(provider, cases, trials: int):
    schema_hits, tool_hits = [], []
    arg_scores = []  # only cases that expect args
    case_passk = []  # pass^k per case
    per_case = {}
    for case in cases:
        expect = case["expect"]
        corrects = []
        for _ in range(trials):
            try:
                turn = provider.generate(
                    system=SYSTEM,
                    messages=[UserMessage(content=case["prompt"])],
                    tools=TOOL_SPECS,
                )
                s_ok, t_ok, a_acc = score_turn(turn, expect)
            except Exception as e:  # malformed args / server error -> total miss
                print(f"  [{case['name']}] error: {e}", file=sys.stderr)
                s_ok, t_ok, a_acc = False, False, (0.0 if _expects_args(expect) else None)
            schema_hits.append(s_ok)
            tool_hits.append(t_ok)
            if a_acc is not None:
                arg_scores.append(a_acc)
            corrects.append(trial_is_correct(s_ok, t_ok, a_acc))
        case_passk.append(all(corrects))
        per_case[case["name"]] = f"{sum(corrects)}/{trials}"

    def mean(xs, default=1.0):
        return sum(xs) / len(xs) if xs else default

    schema = mean(schema_hits)
    tool = mean(tool_hits)
    arg = mean(arg_scores)
    passk = mean(case_passk)
    mark = 100 * (
        WEIGHTS["schema"] * schema + WEIGHTS["tool_select"] * tool + WEIGHTS["arg_acc"] * arg + WEIGHTS["passk"] * passk
    )
    gate = "UNATTENDED" if schema >= GATE["schema_min"] and passk >= GATE["passk_min"] else "HUMAN-GATED"
    return {
        "schema_valid_rate": round(schema, 3),
        "tool_selection_acc": round(tool, 3),
        "argument_field_acc": round(arg, 3),
        "passk_consistency": round(passk, 3),
        "mark": round(mark, 1),
        "gate": gate,
        "per_case": per_case,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--cases", default="evals/cases.yaml")
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--json-out", default=None, help="Directory to write a timestamped results JSON.")
    args = parser.parse_args()

    cases = yaml.safe_load(Path(args.cases).read_text())
    if not cases:
        return print("No cases loaded.", file=sys.stderr) or 1

    results = {}
    print(f"{'model':24} {'mark':>5}  {'gate':<11} {'schema':>6} {'tool':>5} {'arg':>5} {'pass^k':>6}  per-case")
    for model in args.models:
        provider = OpenAICompatibleProvider(
            base_url=args.base_url,
            api_key="ollama",
            model=model,
            tool_choice="auto",
            temperature=args.temperature,
        )
        r = evaluate_model(provider, cases, args.trials)
        results[model] = r
        pc = "  ".join(f"{k}={v}" for k, v in r["per_case"].items())
        print(
            f"{model:24} {r['mark']:>5} {r['gate']:<11} {r['schema_valid_rate']:>6} "
            f"{r['tool_selection_acc']:>5} {r['argument_field_acc']:>5} {r['passk_consistency']:>6}  {pc}"
        )

    if args.json_out:
        out_dir = Path(args.json_out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(
            json.dumps(
                {
                    "trials": args.trials,
                    "temperature": args.temperature,
                    "weights": WEIGHTS,
                    "gate": GATE,
                    "results": results,
                },
                indent=2,
            )
        )
        print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
