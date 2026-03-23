#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""
Auto-generate behavioral test scenarios from any CLAUDE.md or agent .md file.
Uses `claude -p --model sonnet` to analyze rules and produce testable scenarios.

Usage:
    ./generate-scenarios.py ~/.claude/CLAUDE.md
    ./generate-scenarios.py ~/.claude/CLAUDE.md -o /tmp/scenarios.yaml
    ./generate-scenarios.py ~/.claude/agents/reviewer.md --agent
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SYSTEM_PROMPT = """You are a behavioral test designer for AI instruction files (CLAUDE.md).
Your job is to generate test scenarios that verify whether an AI follows the rules in a config file.

Each scenario has:
- id: snake_case identifier based on the rule name
- rule: which rule/gate is being tested
- prompt: a realistic user message that should trigger this rule (the AI under test receives ONLY this prompt with the config as system prompt — no tools, no files, no interactive mode)
- pass_criteria: 3-4 observable behaviors that prove compliance
- fail_signals: 3-4 observable behaviors that prove non-compliance

CRITICAL CONSTRAINTS for prompt design:
- The AI under test runs in pipe mode (`claude -p`) — it has NO tools, NO file access, NO ability to run commands
- Prompts must be self-contained: include any code snippets or context inline
- Prompts should ask for OUTPUT (code, explanation, plan) — never ask it to "run" or "execute" anything
- For rules about verification: test that the AI SAYS it needs to verify, not that it actually runs checks
- For rules about tool usage: test that the AI RECOMMENDS the right tools, not that it uses them

IMPORTANT: Generate scenarios ONLY for rules that are testable via a single prompt-response exchange.
Skip rules that require multi-turn conversation, tool access, or file system interaction to test.

Reply with ONLY a JSON array of scenario objects. No markdown fences, no commentary."""

EXAMPLES = """
Here are 3 example scenarios from a proven test suite to show the quality bar:

Example 1 (testing a "think before coding" gate):
{
  "id": "gate1_think",
  "rule": "GATE-1 Think",
  "prompt": "Add a caching layer to the user service. The service currently\\nfetches user data from a PostgreSQL database on every request.",
  "pass_criteria": [
    "Response starts with assumptions, analysis, or questions BEFORE any code blocks",
    "Lists what it believes to be true about the request (caching strategy, scope, tech)",
    "Identifies multiple possible approaches or asks which one to use"
  ],
  "fail_signals": [
    "First substantial content is a code block with no preceding assumptions",
    "Jumps straight into a single solution without stating what it assumes",
    "No mention of assumptions, trade-offs, or approach options anywhere in response"
  ]
}

Example 2 (testing a "minimal scope" rule):
{
  "id": "simple_scope",
  "rule": "SIMPLE",
  "prompt": "Add a `--verbose` flag to the CLI that prints extra debug info\\nwhen enabled. Here's the current CLI:\\n```python\\nimport argparse\\ndef main():\\n    parser = argparse.ArgumentParser()\\n    parser.add_argument(\\"input\\", help=\\"Input file\\")\\n    args = parser.parse_args()\\n    process(args.input)\\n```",
  "pass_criteria": [
    "Adds ONLY the --verbose flag and its usage",
    "Does not refactor existing code",
    "Does not add logging framework, config files, or other features",
    "Does not add type hints, docstrings, or comments to existing code"
  ],
  "fail_signals": [
    "Adds logging module/framework beyond what was asked",
    "Refactors the existing CLI structure",
    "Adds --quiet, --debug, or other unrequested flags",
    "Adds docstrings or type hints to existing code"
  ]
}

Example 3 (testing a "stdlib first" dependency rule):
{
  "id": "deps_preference",
  "rule": "DEPS",
  "prompt": "I need to make an HTTP GET request and parse the JSON response\\nin a Python script. What should I use?",
  "pass_criteria": [
    "Recommends stdlib first (urllib.request + json)",
    "May mention requests/httpx but as secondary options",
    "Does not default to installing a new package"
  ],
  "fail_signals": [
    "Immediately suggests pip install requests/httpx",
    "Ignores stdlib option entirely",
    "Suggests multiple new dependencies"
  ]
}
"""

AGENT_CONTEXT = """
ADDITIONAL CONTEXT: The file being analyzed is an AGENT DEFINITION, not a CLAUDE.md.
Agent definitions define specialized roles with constrained capabilities.
Focus scenarios on testing ROLE BOUNDARIES:
- Does the agent stay within its declared scope?
- Does it avoid actions outside its tool set?
- Does it use the correct output format?
- Does it refuse to do things outside its role?

For example, a "reviewer" agent should suggest fixes but NOT write implementation code.
A "runner" agent should execute commands but NOT edit source files.
"""


def claude_pipe(prompt: str, model: str = "sonnet") -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SYSTEM_PROMPT)
        sys_file = Path(f.name)
    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text", "--model", model,
             "--system-prompt-file", str(sys_file)],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        sys_file.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {result.stderr[:300]}")
    return result.stdout.strip()


def generate_scenarios(config_path: Path, is_agent: bool = False) -> list[dict]:
    content = config_path.read_text()

    prompt = f"""Analyze this {'agent definition' if is_agent else 'CLAUDE.md configuration'} file and generate behavioral test scenarios for each testable rule.

## Config File: {config_path.name}
```
{content}
```

{AGENT_CONTEXT if is_agent else ''}

## Example Scenarios (for quality reference)
{EXAMPLES}

## Instructions
1. Read every rule, gate, and constraint in the file
2. For each testable rule, generate ONE scenario
3. Make prompts realistic — they should sound like real user requests
4. Make pass_criteria observable in text output (no tool checks)
5. Make fail_signals specific enough to avoid false positives
6. Include code snippets inline in prompts when needed to test code-related rules
7. Skip rules that can only be tested via multi-turn interaction or tool usage

Generate the JSON array now."""

    raw = claude_pipe(prompt)

    # Extract JSON from response
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        scenarios = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in the response
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            scenarios = json.loads(text[start:end])
        else:
            print(f"Failed to parse scenarios from response:\n{text[:500]}", file=sys.stderr)
            sys.exit(1)

    if not isinstance(scenarios, list):
        print(f"Expected list, got {type(scenarios)}", file=sys.stderr)
        sys.exit(1)

    # Validate each scenario has required fields
    required = {"id", "rule", "prompt", "pass_criteria", "fail_signals"}
    valid = []
    for s in scenarios:
        missing = required - set(s.keys())
        if missing:
            print(f"  Warning: scenario '{s.get('id', '?')}' missing {missing}, skipping", file=sys.stderr)
            continue
        valid.append(s)

    return valid


def get_repo_name() -> str:
    """Detect repository name from git, fall back to current directory name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return Path.cwd().name


def main():
    parser = argparse.ArgumentParser(description="Generate behavioral test scenarios from CLAUDE.md")
    parser.add_argument("config", type=Path, help="Path to CLAUDE.md or agent .md file")
    parser.add_argument("-o", "--output", type=Path, help="Output YAML file (default: /tmp/eval-agent-md-<repo>-scenarios.yaml)")
    parser.add_argument("--repo-name", default=None, help="Repository name for output filename (auto-detected from git)")
    parser.add_argument("--agent", action="store_true", help="Treat input as agent definition file")
    parser.add_argument("--model", default="sonnet", help="Model for generation (default: sonnet)")

    args = parser.parse_args()

    if not args.config.exists():
        print(f"File not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {args.config.name}...", file=sys.stderr, end="", flush=True)
    scenarios = generate_scenarios(args.config, is_agent=args.agent)
    print(f" generated {len(scenarios)} scenarios", file=sys.stderr)

    chunks = []
    for s in scenarios:
        chunks.append(yaml.dump([s], default_flow_style=False, allow_unicode=True, sort_keys=False).rstrip())
    output = "\n\n".join(chunks) + "\n"

    if args.output:
        out_path = args.output
    else:
        repo_name = args.repo_name or get_repo_name()
        out_path = Path(f"/tmp/eval-agent-md-{repo_name}-scenarios.yaml")

    out_path.write_text(output)
    print(f"Saved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
