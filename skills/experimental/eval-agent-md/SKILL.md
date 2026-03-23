---
name: eval-agent-md
description: >
  Behavioral compliance testing for any CLAUDE.md or agent definition file.
  Auto-generates test scenarios from your rules, runs them via LLM-as-judge
  scoring, and reports compliance. Optionally improves failing rules via
  automated mutation loop.
metadata:
  category: assistant
  tags: [testing, compliance, agent-md, behavioral, meta, quality]
  status: experimental
---

# eval-agent-md — Behavioral Compliance Testing

## What This Does

1. Reads a CLAUDE.md (or agent .md file)
2. Auto-generates behavioral test scenarios for each rule it finds
3. Runs each scenario via `claude -p` with LLM-as-judge scoring
4. Reports a compliance score with per-rule pass/fail breakdown
5. Optionally runs an automated mutation loop to improve failing rules

## Workflow

### Step 1: Locate the target file

Find the CLAUDE.md to test. Priority order:
1. If user provided a path argument (e.g., `/eval-agent-md ./CLAUDE.md`), use that
2. If a project-level CLAUDE.md exists in the current working directory, use that
3. Fall back to `~/.claude/CLAUDE.md` (user global)
4. If none found, ask the user

Read the file and confirm with the user: "I found your CLAUDE.md at [path] ([N] lines). Testing this file."

### Step 2: Generate test scenarios

Run the scenario generator script bundled with this skill:

```bash
[SKILL_DIR]/scripts/generate-scenarios.py [TARGET_FILE]
```

The script auto-detects the repository name from git and saves to `/tmp/eval-agent-md-<repo>-scenarios.yaml` (e.g., `/tmp/eval-agent-md-my-project-scenarios.yaml`). Override with `--repo-name NAME` or `-o PATH`.

This uses `claude -p --model sonnet` to analyze the CLAUDE.md and generate test scenarios. It typically takes 30-60 seconds.

After generation, read the output file and show the user a summary:
- How many scenarios were generated
- Which rules each scenario tests
- A brief preview of each scenario's prompt

Ask the user: "Generated [N] test scenarios. Ready to run? (Or edit/skip any?)"

### Step 3: Run behavioral tests

```bash
[SKILL_DIR]/scripts/eval-behavioral.py \
  --scenarios-file /tmp/eval-agent-md-<repo>-scenarios.yaml \
  --claude-md [TARGET_FILE] \
  --runs 1 \
  --model sonnet
```

Options the user can control:
- `--runs N` — runs per scenario for majority vote (default: 1, recommend 3 for reliability)
- `--model MODEL` — model for test subject (default: sonnet)
- `--compare-models` — run across haiku/sonnet/opus and show comparison matrix

### Step 4: Report results

Print a compliance report:

```
## Compliance Report — [filename]

Score: 8/10 (80%)

| Scenario | Rule | Verdict | Evidence |
|----------|------|---------|----------|
| gate1_think | GATE-1 | PASS | Lists assumptions before code |
| ... | ... | ... | ... |

### Failing Rules
- [rule]: [what went wrong] — suggested fix: [brief suggestion]
```

### Step 5: Improve (optional)

If the user says "improve", "fix", or passed `--improve`:

```bash
[SKILL_DIR]/scripts/mutate-loop.py \
  --target [TARGET_FILE] \
  --scenarios-file /tmp/eval-agent-md-<repo>-scenarios.yaml \
  --max-iterations 3 \
  --runs 3 \
  --model sonnet
```

This is always dry-run by default. Show the user each suggested mutation and ask before applying.

## Arguments

Parse the user's `/eval-agent-md` invocation for these optional arguments:

- `[path]` — target file (positional, e.g., `/eval-agent-md ./CLAUDE.md`)
- `--improve` — run mutation loop after testing
- `--runs N` — runs per scenario (default: 1)
- `--model MODEL` — model for test subject (default: sonnet)
- `--compare-models` — cross-model comparison (haiku/sonnet/opus)
- `--agent` — hint that the target is an agent definition file (adjusts generation style)

## Notes

- All scripts use `uv run --script` — no pip install needed
- The judge always uses haiku (cheap, fast, reliable for scoring)
- Generated scenarios are ephemeral (temp dir) — they adapt to the current file state
- For agent .md files, the generator creates role-boundary scenarios (e.g., "does the reviewer avoid writing code?")
- Scripts are in this skill's `scripts/` directory
