---
name: ts-linter
description: >
  Set up and enforce a strict, production-grade ESLint configuration for TypeScript projects,
  then systematically fix all linting issues. Use this skill whenever the user asks to add a
  linter or ESLint, enforce code quality rules, fix linting errors, clean up code style, or
  add type-aware linting. Trigger on: "lint", "eslint", "code quality", "static analysis",
  "strict linting", "make it stricter", "make the code stricter", "add better rules", "clean
  up the codebase", "enforce standards", or "fix all the warnings". Handles detection, config
  generation, dependency installation, auto-fix, and manual remediation. Do NOT use for Biome
  or Rome projects, Prettier-only formatting, non-TypeScript/JavaScript projects, writing
  custom ESLint rules or plugins, husky/lint-staged/pre-commit hook setup, or when the user
  just wants to run an existing linter without changing its configuration.
metadata:
  category: universal
  extends: core-coding-standards
  tags:
    - eslint
    - typescript
    - linting
    - code-quality
    - static-analysis
  status: ready
  version: 1
---

# TypeScript Linter Skill

This skill introduces a strict, comprehensive ESLint configuration into a TypeScript project
and then systematically resolves every linting issue — auto-fixing what it can and manually
rewriting what it can't. The goal is zero lint errors with zero broken functionality.

## Before Starting

Recommend the user commits their current state before any changes:
```bash
git add -A && git commit -m "checkpoint: before linter setup"
```
This gives a clean rollback point. If the project doesn't use git, warn that there is no
undo — proceed carefully, fix in small batches.

## Workflow Overview

1. **Detect** the project type by running `scripts/detect-project.sh`
2. **Generate** a tailored `eslint.config.mjs` from `references/eslint-config-reference.mjs`
3. **Validate** the config actually loads before proceeding
4. **Install** all required dependencies using `scripts/generate-install-cmd.sh`
5. **Auto-fix** using `eslint --fix` in batches
6. **Categorize** remaining errors using `scripts/categorize-errors.js`
7. **Manually fix** every remaining issue, verifying after each batch
8. **Verify** the project compiles and tests pass
9. *(Optional, Claude Code only)* Set up hooks — see `references/claude-code-integration.md`

Steps 1-8 are platform-agnostic and work identically on Claude.ai, Claude Code, and the API.
This skill only handles ESLint for TypeScript/JavaScript. It does not conflict with other
skills (e.g., frontend-design, docx) since it only activates for linting-related requests.

---

## Step 1: Project Detection

Run the detection script to determine what the project uses:

```bash
bash <skill-path>/scripts/detect-project.sh .
```

This scans `package.json`, lockfiles, and directory structure, then outputs a JSON object
with boolean flags for each module (React, React Native, Drizzle, Vitest, Playwright, etc.),
the detected package manager, existing ESLint config type, and file globs for server/native/db/e2e
directories.

If the script is unavailable, run the detection manually:

```bash
cat package.json | grep -E "react-native|expo|next|@tanstack|drizzle-orm|vitest|jest|playwright|@testing-library"
ls tsconfig*.json
ls -d apps/ packages/ src/ server/ api/ native/ e2e/ 2>/dev/null
ls eslint.config.* .eslintrc* 2>/dev/null
ls pnpm-lock.yaml yarn.lock package-lock.json bun.lockb 2>/dev/null
```

Based on the results, determine which config sections to include:

| Detected Signal | Config Section |
|---|---|
| `react` or `react-dom` in deps | React (web) |
| `react-native` or `expo` in deps | React Native |
| `@tanstack/react-query` in deps | TanStack Query |
| `drizzle-orm` in deps | Drizzle ORM |
| `vitest` in devDeps | Vitest |
| `playwright` or `@playwright/test` in devDeps | Playwright |
| `@testing-library/react` in devDeps | Testing Library |
| `server/`, `api/`, or backend directories | Node.js backend |
| Monorepo (`apps/`, `packages/`, workspaces) | Per-app overrides |

If a signal is absent, omit that entire section. Do not include commented-out blocks.

---

## Step 2: Generate the ESLint Config

Read the full reference config at `references/eslint-config-reference.mjs`.

Generate `eslint.config.mjs` using only the sections relevant to the detected project.
Every config MUST include these core sections (framework-agnostic):

- Global ignores
- `eslint-plugin-only-error` (all warnings become errors)
- `@eslint/js` recommended + `typescript-eslint` recommendedTypeChecked
- `eslint-plugin-de-morgan`, `unicorn`, `promise`, `security`, `sonarjs`, `regexp`
- `@eslint-community/eslint-plugin-eslint-comments`
- TypeScript type-aware linting parserOptions
- Core rule customizations (see reference config for exact values)
- Test/config file relaxations
- Unicorn customizations (filename-case with framework routing exceptions)
- `eslint-config-prettier` as the LAST entry (disables formatting rules)

Adapt file globs to match the actual project structure (e.g., `src/server/` instead of
`server/`). The detection output includes discovered globs — use them.

If the project already has an ESLint config, read it first. Do not blindly overwrite —
merge the new rules into the existing structure. If it's `.eslintrc.*` (legacy format),
offer to migrate to flat config. Preserve project-specific rules. Show the user a diff.

---

## Step 3: Validate the Config

After writing the config, immediately verify it loads. Find any `.ts` or `.tsx` file in the
project to test against — do not assume `src/index.ts` exists:

```bash
TEST_FILE=$(find src apps packages lib . -name '*.ts' -o -name '*.tsx' 2>/dev/null | grep -v node_modules | head -1)
npx eslint --print-config "$TEST_FILE" > /dev/null 2>&1
echo $?
```

Exit 0 = config loaded. Exit 2 = config/parse error. Do not proceed to auto-fix with a
broken config. See the Troubleshooting section for common config failures.

---

## Step 4: Install Dependencies

Run the install command generator:

```bash
bash <skill-path>/scripts/detect-project.sh . | bash <skill-path>/scripts/generate-install-cmd.sh
```

This reads the detection JSON and outputs the exact install command for the detected
package manager, split by category. Review the output, then run the install command.

If the script is unavailable, install manually. Core packages (always needed):

```
eslint @eslint/js typescript-eslint globals eslint-config-prettier
eslint-plugin-only-error eslint-plugin-de-morgan eslint-plugin-unicorn
eslint-plugin-promise eslint-plugin-security eslint-plugin-sonarjs
eslint-plugin-regexp @eslint-community/eslint-plugin-eslint-comments
```

Conditional packages: `eslint-plugin-react` + `eslint-plugin-react-hooks` +
`eslint-plugin-react-you-might-not-need-an-effect` (React), `eslint-plugin-react-native`
(RN), `@tanstack/eslint-plugin-query` (TanStack), `eslint-plugin-drizzle` (Drizzle),
`eslint-plugin-n` (Node), `@vitest/eslint-plugin` (Vitest), `eslint-plugin-playwright`
(Playwright), `eslint-plugin-testing-library` (Testing Library).

Install as devDependencies. Show the user what was added.

---

## Step 5: Auto-Fix

```bash
npx eslint . --fix 2>&1 | head -100
```

For large projects (>500 files), fix by directory to keep diffs manageable.

After auto-fix, categorize remaining errors:

```bash
npx eslint . --format json 2>/dev/null | node <skill-path>/scripts/categorize-errors.js
```

This groups errors by rule, shows which are auto-fixable vs manual, and suggests a
prioritized fix order. If the script is unavailable, run `npx eslint . --format compact`
and group errors manually by rule name.

---

## Step 6: Manual Fix — Systematic Remediation

Work through remaining errors by category, not by file. Fix order (highest-impact,
lowest-risk first):

1. **Unused imports/variables** (`@typescript-eslint/no-unused-vars`) — remove unused
   imports. Check for side-effect imports before removing.
2. **Type safety** (`no-explicit-any`, `no-unsafe-*`) — replace `any` with proper types.
   Use `unknown` with type guards for complex cases. Test files are already relaxed.
3. **Deprecated APIs** (`@typescript-eslint/no-deprecated`) — look up replacements.
4. **Unicorn rules** — mechanical transforms. Do filename renames last, in a separate batch.
5. **Promise handling** — add `.catch()` or convert to async/await with try/catch.
6. **Cognitive complexity** — extract helpers, split conditionals into named booleans.
7. **Max-lines** — split files over 300 lines. Update all affected imports.
8. **React-specific** — extract nested/multi components into separate files.

### Fix Principles

- Never use `eslint-disable` unless genuinely a false positive. Always include a comment.
- Check `tsc --noEmit` and tests after every batch of fixes.
- Fix in batches of 5 files max, then verify. If tests break, revert and redo one at a time.
- Never rename files and fix lint in the same batch — renames touch every import site.
- If the same error comes back 3 times, add `eslint-disable` with a TODO and move on.
- If two consecutive batches don't reduce the error count, stop and report to the user.

### Progress Reporting

Fixing a large codebase takes many turns. After each batch of fixes, report progress so
the user can track status and decide whether to continue:

```
📊 Progress: 47 errors remaining (down from 83)
   Fixed this batch: 12 errors across 5 files (unused imports)
   Next: 18 type safety errors (@typescript-eslint/no-explicit-any)
   ✅ tsc --noEmit: clean | ✅ Tests: 42 passed
```

If the remaining errors are all in one category that requires significant refactoring,
ask the user whether to proceed or stop and accept the current state with eslint-disable
comments on the remaining violations.

---

## Step 7: Verification

```bash
npx eslint .
npx tsc --noEmit
# Run tests (vitest run, jest, etc.)
```

Report: `✅ Linting: 0 errors | ✅ TypeScript: clean | ✅ Tests: X passed, 0 failed`

If anything fails, diagnose and fix before declaring done.

### Monorepos

Place `eslint.config.mjs` at the root. Scope rules with file globs (`apps/web/**/*.tsx`).
Install dependencies at root. Adapt per-app overrides to actual app names.

---

## Step 8: Claude Code Integration (Optional, Claude Code Only)

If the user wants Claude Code hooks to auto-lint after every edit, read
`references/claude-code-integration.md` for the full setup including:

- TypeScript LSP plugin installation (`/plugin install typescript-lsp@claude-plugins-official`)
- PostToolUse hook (per-file lint via `scripts/lint-typecheck-hook.sh`)
- Stop hook (full project lint + typecheck)
- Self-test validation (`scripts/validate-setup.sh`)
- Hook reliability details (circuit breaker, graceful degradation, output truncation)

---

## Examples

**Example 1: Greenfield setup**
Input: "Add eslint to this project"
Detection: React + Vitest + pnpm monorepo
Output: Generates config with React/Vitest/monorepo sections, installs 18 devDependencies
via pnpm, runs auto-fix (fixes 47 errors), manually fixes 12 remaining, verifies clean.

**Example 2: Fix existing warnings**
Input: "Fix all the linting warnings in our codebase"
Detection: Existing `eslint.config.mjs` already present
Output: Reads existing config, runs `categorize-errors.js` (finds 83 errors across 6 rules),
fixes in priority order, verifies `tsc` and `vitest run` pass after each batch.

**Example 3: Strict upgrade**
Input: "Make our linter stricter, we have too many any types"
Detection: React Native + Expo + Drizzle + existing loose config
Output: Merges strict rules into existing config (adds sonarjs, unicorn, security, type-aware
checking), installs 8 new plugins, auto-fixes 120 errors, manually replaces 34 `any` types,
renames 7 files to kebab-case in a separate batch, verifies clean.

---

## Troubleshooting

- Error: ESLint config crashes on load (exit 2)
- Cause: Missing plugin import
- Solution: Check that the plugin package is installed and the import name matches

- Error: `Cannot find tsconfig`
- Cause: Wrong `tsconfigRootDir` or missing `allowDefaultProject` entry
- Solution: Set `tsconfigRootDir: import.meta.dirname` and add root JS config files to `allowDefaultProject`

- Error: `Definition for rule X was not found`
- Cause: Plugin uses legacy format, not flat config
- Solution: Use the plugin's `flat/recommended` export instead of the legacy extends syntax

- Error: `tsc --noEmit` fails after fixes
- Cause: A fix removed a needed import or broke a type
- Solution: Revert the last batch (`git stash`), redo one file at a time to isolate

- Error: Auto-fix introduces new errors
- Cause: Rule conflict between plugins (e.g., unicorn vs react)
- Solution: Check which rule is new, add an override in the rules section to disable the conflicting one

- Error: Hook fires but Claude ignores output
- Cause: Missing `"decision": "block"` in JSON
- Solution: Ensure the hook outputs `{"decision": "block", "reason": "..."}` — without this field, Claude discards it

- Error: Hook doesn't fire
- Cause: Matcher is case-sensitive
- Solution: Use `Edit|Write|MultiEdit` (PascalCase), not `edit|write|multiedit`

- Error: Hook script crashes
- Cause: Shell profile prints output on startup
- Solution: The bundled script avoids sourcing profiles; if using a custom script, wrap noisy `.zshrc` lines in `[[ $- == *i* ]]`

- Error: Circuit breaker tripped (hook stops blocking)
- Cause: 5 consecutive failures on same file
- Solution: The issue needs human intervention. Fix manually, then delete `$TMPDIR/claude-lint-breaker/` (or `/tmp/claude-lint-breaker/` if `$TMPDIR` is unset) to reset

- Error: ESLint is extremely slow (>30s)
- Cause: Type-aware rules on a huge codebase
- Solution: Scope `recommendedTypeChecked` to `src/` only, or use `recommended` (no type info) for faster runs

---

## Bundled Files Reference

| File | Purpose | When to use |
|---|---|---|
| `scripts/detect-project.sh` | Parses package.json with Node.js, outputs JSON with module flags, commands, globs | Step 1 (detection) |
| `scripts/generate-install-cmd.sh` | Takes detection JSON, outputs categorized install command | Step 4 (install) |
| `scripts/categorize-errors.js` | Groups ESLint JSON output by rule, shows fix priority (Node.js, no Python needed) | Step 5 (after auto-fix) |
| `scripts/lint-typecheck-hook.sh` | Claude Code PostToolUse hook with circuit breaker | Step 8 (Claude Code only) |
| `scripts/validate-setup.sh` | Runs 19 checks to verify the entire setup works | Step 8 (after hook setup) |
| `references/eslint-config-reference.mjs` | Full ESLint config template with all sections | Step 2 (config generation) |
| `references/claude-code-settings.json` | Template `.claude/settings.json` with hook config | Step 8 (Claude Code only) |
| `references/claude-code-integration.md` | Full Claude Code setup guide (LSP, hooks, self-test) | Step 8 (Claude Code only) |
