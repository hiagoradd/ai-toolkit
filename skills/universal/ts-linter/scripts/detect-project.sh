#!/usr/bin/env bash
# detect-project.sh — Scans a project and outputs which ESLint modules to enable.
# Usage: bash detect-project.sh [project-root]
#
# Uses Node.js to parse package.json (guaranteed available in any TS project)
# instead of grep-based substring matching.
# Outputs a JSON object with boolean flags for each module.

set -uo pipefail

ROOT="${1:-.}"
PKG="$ROOT/package.json"

if [[ ! -f "$PKG" ]]; then
  echo "❌ No package.json found in $ROOT" >&2
  exit 1
fi

# Verify node is available
if ! command -v node &>/dev/null; then
  echo "❌ Node.js is required but not found in PATH" >&2
  exit 1
fi

# Helper: check if directory exists
has_dir() {
  [[ -d "$ROOT/$1" ]]
}

# --- Parse package.json with Node for accurate dependency detection ---
# This avoids grep substring false positives (e.g., "react" matching "react-native").

DEP_FLAGS=$(node -e "
const pkg = JSON.parse(require('fs').readFileSync('$PKG', 'utf8'));
const all = { ...pkg.dependencies, ...pkg.devDependencies, ...pkg.peerDependencies };
const has = (name) => name in all;

const flags = {
  react: has('react') || has('react-dom') || has('next'),
  reactNative: has('react-native') || has('expo'),
  tanstackQuery: has('@tanstack/react-query'),
  drizzle: has('drizzle-orm'),
  vitest: has('vitest'),
  jest: has('jest'),
  playwright: has('@playwright/test') || has('playwright'),
  testingLibrary: has('@testing-library/react'),
  prettier: has('prettier'),
  next: has('next'),
  expo: has('expo'),
};

// React Native implies React
if (flags.reactNative) flags.react = true;

// Detect lint/typecheck/test scripts
const scripts = pkg.scripts || {};
const scriptInfo = {
  lintCmd: null,
  typecheckCmd: null,
  testCmd: null,
};

for (const [key, val] of Object.entries(scripts)) {
  if (/^lint(:|$)/.test(key) && !scriptInfo.lintCmd) scriptInfo.lintCmd = 'npm run ' + key;
  if (/^(typecheck|type-check|tsc)$/.test(key) && !scriptInfo.typecheckCmd) scriptInfo.typecheckCmd = 'npm run ' + key;
  if (/^test(:|$)/.test(key) && !key.includes('e2e') && !scriptInfo.testCmd) scriptInfo.testCmd = 'npm run ' + key;
}

// Detect workspaces
const hasWorkspaces = !!(pkg.workspaces || (Array.isArray(pkg.workspaces) && pkg.workspaces.length > 0));

console.log(JSON.stringify({ ...flags, hasWorkspaces, scripts: scriptInfo }));
" 2>/dev/null)

if [[ -z "$DEP_FLAGS" ]]; then
  echo "❌ Failed to parse package.json with Node.js" >&2
  exit 1
fi

# Extract values from the Node output
get_flag() {
  echo "$DEP_FLAGS" | node -e "
    let d=''; process.stdin.on('data',c=>d+=c); process.stdin.on('end',()=>{
      const obj=JSON.parse(d); console.log(obj['$1'] || false);
    });
  "
}

HAS_REACT=$(get_flag react)
HAS_REACT_NATIVE=$(get_flag reactNative)
HAS_TANSTACK_QUERY=$(get_flag tanstackQuery)
HAS_DRIZZLE=$(get_flag drizzle)
HAS_VITEST=$(get_flag vitest)
HAS_JEST=$(get_flag jest)
HAS_PLAYWRIGHT=$(get_flag playwright)
HAS_TESTING_LIBRARY=$(get_flag testingLibrary)
HAS_PRETTIER=$(get_flag prettier)
HAS_NEXT=$(get_flag next)
HAS_EXPO=$(get_flag expo)
HAS_WORKSPACES=$(get_flag hasWorkspaces)

# Prettier config files (Node might not detect .prettierrc)
if [[ "$HAS_PRETTIER" == "false" ]]; then
  for f in .prettierrc .prettierrc.json .prettierrc.yml .prettierrc.js prettier.config.mjs prettier.config.js; do
    if [[ -f "$ROOT/$f" ]]; then
      HAS_PRETTIER=true
      break
    fi
  done
fi

# --- Directory-based detection ---

HAS_NODE_BACKEND=false
for dir in server api src/server src/api packages/api apps/api apps/server; do
  if has_dir "$dir"; then
    HAS_NODE_BACKEND=true
    break
  fi
done

HAS_MONOREPO=false
if has_dir "apps" || has_dir "packages" || [[ -f "$ROOT/pnpm-workspace.yaml" ]] || [[ -f "$ROOT/lerna.json" ]] || [[ "$HAS_WORKSPACES" == "true" ]]; then
  HAS_MONOREPO=true
fi

# --- Detect package manager ---

PKG_MANAGER="npm"
if [[ -f "$ROOT/pnpm-lock.yaml" ]]; then
  PKG_MANAGER="pnpm"
elif [[ -f "$ROOT/yarn.lock" ]]; then
  PKG_MANAGER="yarn"
elif [[ -f "$ROOT/bun.lockb" ]]; then
  PKG_MANAGER="bun"
fi

# --- Detect existing ESLint config ---

EXISTING_CONFIG="none"
if [[ -f "$ROOT/eslint.config.mjs" ]]; then
  EXISTING_CONFIG="flat-mjs"
elif [[ -f "$ROOT/eslint.config.js" ]]; then
  EXISTING_CONFIG="flat-js"
elif [[ -f "$ROOT/eslint.config.ts" ]]; then
  EXISTING_CONFIG="flat-ts"
elif [[ -f "$ROOT/.eslintrc.js" ]] || [[ -f "$ROOT/.eslintrc.json" ]] || [[ -f "$ROOT/.eslintrc.yml" ]] || [[ -f "$ROOT/.eslintrc" ]]; then
  EXISTING_CONFIG="legacy"
fi

# --- Discover file globs ---

build_glob_array() {
  local dirs=("$@")
  local result="["
  local first=true
  for dir in "${dirs[@]}"; do
    if has_dir "$dir"; then
      $first || result+=","
      result+="\"**/${dir}/**/*.ts\",\"**/${dir}/**/*.tsx\""
      first=false
    fi
  done
  result+="]"
  echo "$result"
}

SERVER_GLOBS=$(build_glob_array server api src/server src/api packages/api apps/api apps/server)
NATIVE_GLOBS=$(build_glob_array native apps/native apps/mobile packages/native packages/mobile)
DB_GLOBS=$(build_glob_array db src/db packages/db apps/api/db server/db)
E2E_GLOBS=$(build_glob_array e2e tests/e2e test/e2e apps/web/e2e packages/e2e)

# --- Extract detected commands ---

LINT_CMD=$(echo "$DEP_FLAGS" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const o=JSON.parse(d);console.log(o.scripts?.lintCmd||'')})")
TSC_CMD=$(echo "$DEP_FLAGS" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const o=JSON.parse(d);console.log(o.scripts?.typecheckCmd||'')})")
TEST_CMD=$(echo "$DEP_FLAGS" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const o=JSON.parse(d);console.log(o.scripts?.testCmd||'')})")

# --- Output ---

cat <<EOF
{
  "modules": {
    "react": $HAS_REACT,
    "reactNative": $HAS_REACT_NATIVE,
    "tanstackQuery": $HAS_TANSTACK_QUERY,
    "drizzle": $HAS_DRIZZLE,
    "vitest": $HAS_VITEST,
    "jest": $HAS_JEST,
    "playwright": $HAS_PLAYWRIGHT,
    "testingLibrary": $HAS_TESTING_LIBRARY,
    "nodeBackend": $HAS_NODE_BACKEND,
    "monorepo": $HAS_MONOREPO,
    "prettier": $HAS_PRETTIER,
    "next": $HAS_NEXT,
    "expo": $HAS_EXPO
  },
  "packageManager": "$PKG_MANAGER",
  "existingConfig": "$EXISTING_CONFIG",
  "detectedCommands": {
    "lint": "${LINT_CMD:-}",
    "typecheck": "${TSC_CMD:-}",
    "test": "${TEST_CMD:-}"
  },
  "globs": {
    "server": $SERVER_GLOBS,
    "native": $NATIVE_GLOBS,
    "db": $DB_GLOBS,
    "e2e": $E2E_GLOBS
  }
}
EOF
