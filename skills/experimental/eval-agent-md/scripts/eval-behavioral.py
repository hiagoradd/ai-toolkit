#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""
Behavioral test suite for CLAUDE.md compliance.
Uses `claude -p` (pipe mode) with --system-prompt-file for isolated testing.
Judge calls use `claude -p --model haiku` for cheap scoring.

Usage:
    ./eval-behavioral.py --scenarios-file scenarios.yaml --claude-md ~/.claude/CLAUDE.md
    ./eval-behavioral.py --scenarios-file s.yaml --claude-md config.md --runs 3
    ./eval-behavioral.py --scenarios-file s.yaml --claude-md config.md --compare-models
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

RESULTS_DIR = Path(__file__).parent / "results"

JUDGE_SYSTEM = """You are a strict compliance judge. Score AI responses as PASS or FAIL.
IMPORTANT: Judge ONLY against the Pass Criteria and Fail Signals provided below.
Do NOT use any other rules, system instructions, or CLAUDE.md content for judging.
Be strict — partial compliance is a FAIL.
Reply with ONLY valid JSON, no markdown fences, no commentary.
Keep the "evidence" field under 100 characters.
Format: {"verdict":"PASS","evidence":"...","triggered_criteria":[],"triggered_fail_signals":[]}"""


def claude_pipe(
    prompt: str,
    model: str | None = None,
    system_file: Path | None = None,
    timeout: int = 120,
) -> str:
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])
    if system_file:
        cmd.extend(["--system-prompt-file", str(system_file)])
    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude -p failed (rc={result.returncode}):\n"
            f"  stderr: {result.stderr[:500]}\n"
            f"  stdout: {result.stdout[:500]}"
        )
    return result.stdout.strip()


def load_scenarios(path: Path, ids: list[str] | None = None) -> list[dict]:
    scenarios = yaml.safe_load(path.read_text())
    if ids:
        scenarios = [s for s in scenarios if s["id"] in ids]
        found = {s["id"] for s in scenarios}
        missing = set(ids) - found
        if missing:
            print(f"Warning: scenarios not found: {', '.join(missing)}", file=sys.stderr)
    else:
        agent_excluded = [s for s in scenarios if s.get("agent_md")]
        scenarios = [s for s in scenarios if not s.get("agent_md")]
        if agent_excluded:
            names = ", ".join(s["id"] for s in agent_excluded)
            print(f"Note: skipping {len(agent_excluded)} agent scenarios: {names}")
    return scenarios


def judge(scenario: dict, response: str) -> dict:
    judge_prompt = f"""## Rule Being Tested
{scenario['rule']}

## Prompt Sent
{scenario['prompt']}

## Assistant Response
{response}

## Pass Criteria
{yaml.dump(scenario['pass_criteria'], default_flow_style=False)}

## Fail Signals
{yaml.dump(scenario['fail_signals'], default_flow_style=False)}"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(JUDGE_SYSTEM)
        judge_file = Path(f.name)
    try:
        raw = claude_pipe(judge_prompt, model="haiku", system_file=judge_file)
    finally:
        judge_file.unlink(missing_ok=True)

    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "verdict": "ERROR",
            "evidence": f"Judge returned non-JSON: {text[:200]}",
            "triggered_criteria": [],
            "triggered_fail_signals": [],
        }


def run_scenario(model: str, system_file: Path, scenario: dict, runs: int) -> dict:
    effective_file = system_file
    if scenario.get("agent_md"):
        agent_path = Path(scenario["agent_md"]).expanduser()
        if agent_path.exists():
            effective_file = agent_path
        else:
            print(f"\n  Warning: agent_md not found: {agent_path}", file=sys.stderr)
    verdicts = []
    for r in range(runs):
        response = claude_pipe(scenario["prompt"], model=model, system_file=effective_file)
        result = judge(scenario, response)
        result["response_preview"] = response[:500]
        result["run"] = r + 1
        verdicts.append(result)

    passes = sum(1 for v in verdicts if v["verdict"] == "PASS")
    return {
        "id": scenario["id"],
        "rule": scenario["rule"],
        "runs": runs,
        "passes": passes,
        "fails": runs - passes,
        "final_verdict": "PASS" if passes > runs / 2 else "FAIL",
        "details": verdicts,
    }


def print_results(results: list[dict], label: str = ""):
    if label:
        print(f"\n{'=' * 60}")
        print(f"  {label}")
        print(f"{'=' * 60}")

    total = len(results)
    passed = sum(1 for r in results if r["final_verdict"] == "PASS")

    for r in results:
        icon = "PASS" if r["final_verdict"] == "PASS" else "FAIL"
        votes = f"{r['passes']}/{r['runs']}"
        print(f"  [{icon}] {r['id']:<25} ({r['rule']:<20}) votes: {votes}")
        for d in r["details"]:
            print(f"         run {d['run']}: {d['verdict']} — {d.get('evidence', 'no evidence')}")

    print(f"\n  Score: {passed}/{total} ({passed / total * 100:.0f}%)")
    return passed, total


def save_results(results: list[dict], model: str, label: str = ""):
    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = {
        "timestamp": ts,
        "model": model,
        "label": label,
        "scenarios": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["final_verdict"] == "PASS"),
        },
    }
    path = RESULTS_DIR / f"eval-{ts}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\n  Results saved: {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="Behavioral compliance tests for CLAUDE.md")
    parser.add_argument("scenarios", nargs="*", help="Scenario IDs to run (default: all)")
    parser.add_argument("--runs", type=int, default=1, help="Runs per scenario for majority vote")
    parser.add_argument("--model", default="sonnet", help="Model for test subject (default: sonnet)")
    parser.add_argument("--claude-md", type=Path, required=True, help="CLAUDE.md or agent .md to test")
    parser.add_argument("--mutate", type=Path, help="Mutated config for A/B comparison")
    parser.add_argument("--compare-models", action="store_true", help="Run across haiku/sonnet/opus")
    parser.add_argument("--scenarios-file", type=Path, required=True, help="Path to scenarios YAML")

    args = parser.parse_args()
    scenarios = load_scenarios(args.scenarios_file, args.scenarios or None)

    if not scenarios:
        print("No scenarios to run.", file=sys.stderr)
        sys.exit(1)

    print(f"Testing {len(scenarios)} scenarios x {args.runs} run(s)")
    print(f"Subject: claude -p --model {args.model}")
    print(f"Judge:   claude -p --model haiku")
    print(f"Config:  {args.claude_md}")

    if args.compare_models:
        models = ["haiku", "sonnet", "opus"]
        all_model_results = {}
        for model in models:
            print(f"\n{'=' * 60}")
            print(f"  Model: {model}")
            print(f"{'=' * 60}")
            model_results = []
            for i, s in enumerate(scenarios, 1):
                print(f"\n[{i}/{len(scenarios)}] {s['id']}...", end="", flush=True)
                t0 = time.time()
                r = run_scenario(model, args.claude_md, s, args.runs)
                elapsed = time.time() - t0
                print(f" {r['final_verdict']} ({elapsed:.1f}s)")
                model_results.append(r)
            print_results(model_results, f"Results — {model}")
            all_model_results[model] = model_results

        comparison = {}
        sensitive = []
        for s in scenarios:
            sid = s["id"]
            verdicts = {m: next(r["final_verdict"] for r in rs if r["id"] == sid)
                        for m, rs in all_model_results.items()}
            comparison[sid] = verdicts
            if len(set(verdicts.values())) > 1:
                sensitive.append(sid)

        print(f"\n{'=' * 60}")
        print("  Cross-Model Comparison")
        print(f"{'=' * 60}")
        header = f"  {'scenario':<25} " + " ".join(f"{m:<8}" for m in models)
        print(header)
        print("  " + "-" * len(header.strip()))
        for sid, verdicts in comparison.items():
            row = f"  {sid:<25} " + " ".join(f"{v:<8}" for v in verdicts.values())
            flag = " ** MODEL-SENSITIVE" if sid in sensitive else ""
            print(row + flag)

        if sensitive:
            print(f"\n  Model-sensitive scenarios: {', '.join(sensitive)}")
        else:
            print("\n  No model-sensitive scenarios found.")

        RESULTS_DIR.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        out = {
            "timestamp": ts,
            "label": "cross-model",
            "models": models,
            "model_comparison": comparison,
            "model_sensitive": sensitive,
            "per_model": {m: [{"id": r["id"], "final_verdict": r["final_verdict"],
                               "passes": r["passes"], "runs": r["runs"]}
                              for r in rs]
                          for m, rs in all_model_results.items()},
        }
        path = RESULTS_DIR / f"eval-compare-{ts}.json"
        path.write_text(json.dumps(out, indent=2))
        print(f"\n  Comparison saved: {path}")
        sys.exit(0)

    results = []
    for i, s in enumerate(scenarios, 1):
        print(f"\n[{i}/{len(scenarios)}] {s['id']}...", end="", flush=True)
        t0 = time.time()
        r = run_scenario(args.model, args.claude_md, s, args.runs)
        elapsed = time.time() - t0
        print(f" {r['final_verdict']} ({elapsed:.1f}s)")
        results.append(r)

    base_passed, _ = print_results(results, f"Results — {args.claude_md.name}")
    save_results(results, args.model, "baseline")

    if args.mutate:
        print(f"\nRunning mutated config: {args.mutate}")
        mutated_results = []
        for i, s in enumerate(scenarios, 1):
            print(f"\n[{i}/{len(scenarios)}] {s['id']}...", end="", flush=True)
            t0 = time.time()
            r = run_scenario(args.model, args.mutate, s, args.runs)
            elapsed = time.time() - t0
            print(f" {r['final_verdict']} ({elapsed:.1f}s)")
            mutated_results.append(r)

        print_results(results, f"Baseline — {args.claude_md.name}")
        mut_passed, _ = print_results(mutated_results, f"Mutated — {args.mutate.name}")
        save_results(mutated_results, args.model, "mutated")

        delta = mut_passed - base_passed
        print(f"\n  Delta: {delta:+d} scenarios")
        if delta > 0:
            print("  Recommendation: KEEP mutation")
        elif delta < 0:
            print("  Recommendation: REVERT mutation")
        else:
            print("  Recommendation: NEUTRAL — check token count for tiebreak")


if __name__ == "__main__":
    main()
