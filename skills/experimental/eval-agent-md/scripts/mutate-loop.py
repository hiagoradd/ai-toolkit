#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""
Automated CLAUDE.md mutation loop.
Iteratively generates targeted wording changes, runs A/B behavioral tests,
and keeps improvements (delta > 0).

Usage:
    ./mutate-loop.py --target ~/.claude/CLAUDE.md --scenarios-file /tmp/scenarios.yaml
    ./mutate-loop.py --target config.md --scenarios-file s.yaml --max-iterations 3
    ./mutate-loop.py --target config.md --scenarios-file s.yaml --apply
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).parent
EVAL_SCRIPT = SKILL_DIR / "eval-behavioral.py"
RESULTS_DIR = SKILL_DIR / "results"

MUTATION_PROMPT_TEMPLATE = """You are a prompt engineer specializing in AI instruction tuning.

## Current Config File
```
{config_content}
```

## Failing Scenario
- ID: {scenario_id}
- Rule: {scenario_rule}
- Prompt sent to AI: {scenario_prompt}
- Pass criteria: {pass_criteria}
- Fail signals: {fail_signals}
- Recent failure evidence: {failure_evidence}

## Task
Suggest a MINIMAL, TARGETED wording change to the config file that would make the AI pass this scenario without breaking other rules.

## Constraints
- Change as few words as possible — surgical edits only
- Do NOT restructure the file or add new sections
- Do NOT remove existing rules — only refine wording
- The change must be specific to this failure, not a general rewrite
- Consider interactions with other rules that might break

## Output Format
Reply with ONLY a JSON object (no markdown fences):
{{"section": "which rule/gate", "change_description": "what to change and why", "old_text": "exact text to find in the file", "new_text": "replacement text"}}"""


def claude_pipe(prompt: str, model: str = "sonnet", timeout: int = 120) -> str:
    system = "You are a prompt engineering assistant. Reply with only the requested JSON."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(system)
        sys_file = Path(f.name)
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text", "--model", model,
             "--system-prompt-file", str(sys_file)],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        sys_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {result.stderr[:300]}")
    return result.stdout.strip()


def _count_scenarios(scenarios_file: Path, scenario_ids: list[str] | None) -> int:
    scenarios = yaml.safe_load(scenarios_file.read_text())
    if scenario_ids:
        return len([s for s in scenarios if s["id"] in scenario_ids])
    return len(scenarios)


def run_eval(target: Path, scenarios_file: Path, scenario_ids: list[str] | None, runs: int, model: str) -> dict:
    cmd = [str(EVAL_SCRIPT), "--runs", str(runs), "--model", model,
           "--claude-md", str(target), "--scenarios-file", str(scenarios_file)]
    if scenario_ids:
        cmd.extend(scenario_ids)
    n = _count_scenarios(scenarios_file, scenario_ids)
    timeout = max(300, n * runs * 60 + 120)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"  Eval stderr: {result.stderr[:300]}", file=sys.stderr)
    results_dir = SKILL_DIR / "results"
    files = sorted(results_dir.glob("eval-*.json"), key=lambda p: p.name, reverse=True)
    if not files:
        raise RuntimeError("No results file found after eval run")
    return json.loads(files[0].read_text())


def run_ab(baseline: Path, mutated: Path, scenarios_file: Path,
           scenario_ids: list[str] | None, runs: int, model: str) -> tuple:
    cmd = [str(EVAL_SCRIPT), "--runs", str(runs), "--model", model,
           "--claude-md", str(baseline), "--mutate", str(mutated),
           "--scenarios-file", str(scenarios_file)]
    if scenario_ids:
        cmd.extend(scenario_ids)
    n = _count_scenarios(scenarios_file, scenario_ids)
    timeout = max(300, n * runs * 60 * 2 + 120)  # 2x for baseline + mutated
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result, result.stdout


def find_failing_scenarios(results: dict) -> list[dict]:
    return [s for s in results.get("scenarios", []) if s["final_verdict"] == "FAIL"]


def generate_mutation(config_content: str, scenario: dict, scenarios_file: Path) -> dict | None:
    evidence = "No evidence available"
    for detail in scenario.get("details", []):
        if detail.get("verdict") == "FAIL":
            evidence = detail.get("evidence", evidence)
            break

    all_scenarios = yaml.safe_load(scenarios_file.read_text())
    scenario_def = next((s for s in all_scenarios if s["id"] == scenario["id"]), None)
    if not scenario_def:
        return None

    prompt = MUTATION_PROMPT_TEMPLATE.format(
        config_content=config_content,
        scenario_id=scenario["id"],
        scenario_rule=scenario["rule"],
        scenario_prompt=scenario_def["prompt"],
        pass_criteria=yaml.dump(scenario_def["pass_criteria"], default_flow_style=False),
        fail_signals=yaml.dump(scenario_def["fail_signals"], default_flow_style=False),
        failure_evidence=evidence,
    )

    line_count = len(config_content.splitlines())
    timeout = max(120, line_count // 5)
    raw = claude_pipe(prompt, model="sonnet", timeout=timeout)
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  Mutation generation returned non-JSON: {text[:200]}", file=sys.stderr)
        return None


def apply_mutation(config_content: str, mutation: dict) -> str | None:
    old_text = mutation.get("old_text", "")
    new_text = mutation.get("new_text", "")
    if not old_text or old_text not in config_content:
        return None
    return config_content.replace(old_text, new_text, 1)


def main():
    parser = argparse.ArgumentParser(description="Automated CLAUDE.md mutation loop")
    parser.add_argument("--target", type=Path, required=True, help="Config file to mutate")
    parser.add_argument("--scenarios-file", type=Path, required=True, help="Path to scenarios YAML")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max mutation attempts")
    parser.add_argument("--runs", type=int, default=3, help="Runs per scenario for majority vote")
    parser.add_argument("--model", default="sonnet", help="Model for behavioral tests")
    parser.add_argument("--scenarios", nargs="*", help="Scenario IDs to focus on")
    parser.add_argument("--apply", action="store_true", help="Apply winning mutations (default: dry-run)")

    args = parser.parse_args()
    RESULTS_DIR.mkdir(exist_ok=True)

    mode = "APPLY" if args.apply else "DRY-RUN"
    backup_path = None
    if args.apply:
        backup_path = args.target.with_suffix(args.target.suffix + ".bak")
        shutil.copy2(args.target, backup_path)

    print(f"Mutation loop — {mode} mode")
    if backup_path:
        print(f"Backup: {backup_path}")
    print(f"Target: {args.target}")
    print(f"Scenarios: {args.scenarios_file}")
    print(f"Max iterations: {args.max_iterations}")
    print(f"Runs per scenario: {args.runs}")
    print(f"Model: {args.model}")

    print(f"\n{'=' * 60}")
    print("  Baseline evaluation")
    print(f"{'=' * 60}")
    baseline_results = run_eval(args.target, args.scenarios_file, args.scenarios, args.runs, args.model)
    baseline_passed = baseline_results["summary"]["passed"]
    baseline_total = baseline_results["summary"]["total"]
    print(f"  Baseline: {baseline_passed}/{baseline_total}")

    failing = find_failing_scenarios(baseline_results)
    if not failing:
        print("\n  All scenarios passing — nothing to mutate.")
        return

    print(f"  Failing: {', '.join(s['id'] for s in failing)}")

    iteration_log = []
    current_content = args.target.read_text()

    for i in range(1, args.max_iterations + 1):
        if not failing:
            print(f"\n  All scenarios passing after {i - 1} iterations.")
            break

        target_scenario = failing[0]
        print(f"\n{'=' * 60}")
        print(f"  Iteration {i}/{args.max_iterations} — targeting: {target_scenario['id']}")
        print(f"{'=' * 60}")

        print("  Generating mutation...", end="", flush=True)
        t0 = time.time()
        mutation = generate_mutation(current_content, target_scenario, args.scenarios_file)
        elapsed = time.time() - t0
        print(f" done ({elapsed:.1f}s)")

        if not mutation:
            print("  Failed to generate valid mutation. Skipping.")
            iteration_log.append({"iteration": i, "target": target_scenario["id"],
                                  "result": "generation_failed"})
            failing = failing[1:]
            continue

        print(f"  Section: {mutation.get('section', 'unknown')}")
        print(f"  Change: {mutation.get('change_description', 'no description')}")

        mutated_content = apply_mutation(current_content, mutation)
        if mutated_content is None:
            print(f"  old_text not found in config. Skipping.")
            iteration_log.append({"iteration": i, "target": target_scenario["id"],
                                  "result": "text_not_found", "mutation": mutation})
            failing = failing[1:]
            continue

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(mutated_content)
            mutated_path = Path(f.name)

        try:
            print("  Running A/B comparison...", flush=True)
            ab_result, ab_stdout = run_ab(args.target, mutated_path, args.scenarios_file,
                                          args.scenarios, args.runs, args.model)
            print(ab_stdout)

            delta_line = [l for l in ab_stdout.split("\n") if "Delta:" in l]
            delta = 0
            if delta_line:
                try:
                    delta = int(delta_line[0].split("Delta:")[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass

            entry = {
                "iteration": i,
                "target": target_scenario["id"],
                "mutation": mutation,
                "delta": delta,
                "result": "keep" if delta > 0 else ("neutral" if delta == 0 else "revert"),
            }
            iteration_log.append(entry)

            if delta > 0:
                print(f"  KEEP — delta: {delta:+d}")
                if args.apply:
                    args.target.write_text(mutated_content)
                    current_content = mutated_content
                    print(f"  Applied mutation to {args.target}")
                else:
                    print(f"  (dry-run — mutation NOT applied)")
                    current_content = mutated_content
            elif delta == 0:
                print(f"  NEUTRAL — delta: 0 (not keeping)")
            else:
                print(f"  REVERT — delta: {delta:+d}")
        finally:
            mutated_path.unlink(missing_ok=True)

        if args.apply and delta > 0:
            reeval = run_eval(args.target, args.scenarios_file, args.scenarios, args.runs, args.model)
            failing = find_failing_scenarios(reeval)
        else:
            failing = failing[1:]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_path = RESULTS_DIR / f"mutation-log-{ts}.json"
    log_data = {
        "timestamp": ts,
        "target": str(args.target),
        "model": args.model,
        "mode": mode,
        "iterations": iteration_log,
        "summary": {
            "total_iterations": len(iteration_log),
            "kept": sum(1 for e in iteration_log if e["result"] == "keep"),
            "reverted": sum(1 for e in iteration_log if e["result"] == "revert"),
            "neutral": sum(1 for e in iteration_log if e["result"] == "neutral"),
            "failed": sum(1 for e in iteration_log if e["result"] in ("generation_failed", "text_not_found")),
        },
    }
    log_path.write_text(json.dumps(log_data, indent=2))
    print(f"\n  Mutation log saved: {log_path}")
    print(f"  Summary: {log_data['summary']}")


if __name__ == "__main__":
    main()
