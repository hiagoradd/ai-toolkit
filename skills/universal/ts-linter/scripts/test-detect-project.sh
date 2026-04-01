#!/usr/bin/env bash
# test-detect-project.sh — Tests for detect-project.sh
# Usage: bash test-detect-project.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT="$SCRIPT_DIR/detect-project.sh"
TMPDIR_BASE=$(mktemp -d)
PASS=0
FAIL=0

cleanup() { rm -rf "$TMPDIR_BASE"; }
trap cleanup EXIT

# Helper: extract a field from JSON output
get_json() {
  local json_file="$1" path="$2"
  node -e "
    const obj=JSON.parse(require('fs').readFileSync('$json_file','utf8'));
    const val = '$path'.split('.').reduce((o,k)=>o!=null?o[k]:undefined, obj);
    console.log(val === undefined ? 'undefined' : typeof val === 'string' ? val : JSON.stringify(val));
  "
}

# Helper: run detect and save output to a temp file, return the path
run_detect() {
  local dir="$1"
  local out_file="$TMPDIR_BASE/output-$(basename "$dir").json"
  bash "$DETECT" "$dir" > "$out_file"
  echo "$out_file"
}

assert_eq() {
  local label="$1" actual="$2" expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    echo "  ✓ $label"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $label — expected '$expected', got '$actual'"
    FAIL=$((FAIL + 1))
  fi
}

# ─── Fixture A: Flat single-package repo ───

echo "=== Fixture A: Flat repo with Next.js + Prettier ==="
DIR_A="$TMPDIR_BASE/flat-repo"
mkdir -p "$DIR_A"
cat > "$DIR_A/package.json" <<'APKG'
{
  "name": "flat-app",
  "dependencies": { "next": "14.0.0", "react": "18.0.0", "react-dom": "18.0.0" },
  "devDependencies": { "prettier": "3.0.0", "typescript": "5.0.0" },
  "scripts": { "lint": "eslint .", "typecheck": "tsc --noEmit" }
}
APKG

OUT_A=$(run_detect "$DIR_A")
assert_eq "next=true"       "$(get_json "$OUT_A" modules.next)"       "true"
assert_eq "react=true"      "$(get_json "$OUT_A" modules.react)"      "true"
assert_eq "prettier=true"   "$(get_json "$OUT_A" modules.prettier)"   "true"
assert_eq "monorepo=false"  "$(get_json "$OUT_A" modules.monorepo)"   "false"
assert_eq "nestjs=false"    "$(get_json "$OUT_A" modules.nestjs)"     "false"
assert_eq "buildTool=none"  "$(get_json "$OUT_A" buildTool)"          "none"

# ─── Fixture B: pnpm monorepo with Next.js + NestJS + Turbo ───

echo ""
echo "=== Fixture B: pnpm monorepo (Next.js in apps/web, NestJS in apps/api, Turbo) ==="
DIR_B="$TMPDIR_BASE/pnpm-monorepo"
mkdir -p "$DIR_B/apps/web" "$DIR_B/apps/api/src"

cat > "$DIR_B/package.json" <<'BPKG'
{
  "name": "monorepo-root",
  "private": true,
  "devDependencies": { "typescript": "5.0.0", "prettier": "3.0.0" },
  "scripts": { "lint": "turbo run lint" }
}
BPKG

cat > "$DIR_B/pnpm-workspace.yaml" <<'BWORK'
packages:
  - 'apps/*'
BWORK

cat > "$DIR_B/apps/web/package.json" <<'BWEB'
{
  "name": "web",
  "dependencies": { "next": "14.0.0", "react": "18.0.0", "react-dom": "18.0.0" }
}
BWEB

cat > "$DIR_B/apps/api/package.json" <<'BAPI'
{
  "name": "api",
  "dependencies": { "@nestjs/core": "10.0.0", "@nestjs/common": "10.0.0" }
}
BAPI

touch "$DIR_B/turbo.json"
touch "$DIR_B/pnpm-lock.yaml"

OUT_B=$(run_detect "$DIR_B")
assert_eq "next=true"         "$(get_json "$OUT_B" modules.next)"         "true"
assert_eq "nestjs=true"       "$(get_json "$OUT_B" modules.nestjs)"       "true"
assert_eq "react=true"        "$(get_json "$OUT_B" modules.react)"        "true"
assert_eq "monorepo=true"     "$(get_json "$OUT_B" modules.monorepo)"     "true"
assert_eq "nodeBackend=true"  "$(get_json "$OUT_B" modules.nodeBackend)"  "true"
assert_eq "prettier=true"     "$(get_json "$OUT_B" modules.prettier)"     "true"
assert_eq "buildTool=turbo"   "$(get_json "$OUT_B" buildTool)"            "turbo"
assert_eq "pkgManager=pnpm"   "$(get_json "$OUT_B" packageManager)"       "pnpm"

# ─── Fixture C: npm workspaces monorepo ───

echo ""
echo "=== Fixture C: npm workspaces monorepo (React in packages/ui) ==="
DIR_C="$TMPDIR_BASE/npm-workspaces"
mkdir -p "$DIR_C/packages/ui"

cat > "$DIR_C/package.json" <<'CPKG'
{
  "name": "npm-mono",
  "private": true,
  "workspaces": ["packages/*"],
  "devDependencies": { "typescript": "5.0.0" }
}
CPKG

cat > "$DIR_C/packages/ui/package.json" <<'CUI'
{
  "name": "ui",
  "dependencies": { "react": "18.0.0", "react-dom": "18.0.0" }
}
CUI

OUT_C=$(run_detect "$DIR_C")
assert_eq "react=true"       "$(get_json "$OUT_C" modules.react)"      "true"
assert_eq "monorepo=true"    "$(get_json "$OUT_C" modules.monorepo)"   "true"
assert_eq "buildTool=none"   "$(get_json "$OUT_C" buildTool)"          "none"
assert_eq "nestjs=false"     "$(get_json "$OUT_C" modules.nestjs)"     "false"

# ─── Summary ───

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] || exit 1
