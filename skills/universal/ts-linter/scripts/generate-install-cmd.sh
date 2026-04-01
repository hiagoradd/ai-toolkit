#!/usr/bin/env bash
# generate-install-cmd.sh — Given detection JSON (stdin or file), outputs the install command.
# Usage: bash detect-project.sh /path/to/project | bash generate-install-cmd.sh
#   or:  bash generate-install-cmd.sh < detection.json

set -euo pipefail

INPUT=$(cat)

# Parse JSON with Node.js (portable, no jq needed)
# Checks modules.* first (detect-project.sh nests flags), then top-level (packageManager)
get_field() {
  node -e "const d=JSON.parse(require('fs').readFileSync('/dev/stdin','utf8'));const v=d.modules?.['$1']??d['$1']??'';process.stdout.write(String(v))" <<< "$INPUT"
}

PKG_MANAGER=$(get_field "packageManager")
REACT=$(get_field "react")
REACT_NATIVE=$(get_field "reactNative")
TANSTACK=$(get_field "tanstackQuery")
DRIZZLE=$(get_field "drizzle")
VITEST=$(get_field "vitest")
PLAYWRIGHT=$(get_field "playwright")
TESTING_LIB=$(get_field "testingLibrary")
NODE_BACKEND=$(get_field "nodeBackend")
PRETTIER=$(get_field "prettier")

# --- Core packages (always installed) ---
CORE_PKGS=(
  "eslint"
  "@eslint/js"
  "typescript-eslint"
  "@eslint-community/eslint-plugin-eslint-comments"
  "eslint-plugin-de-morgan"
  "eslint-plugin-promise"
  "eslint-plugin-regexp"
  "eslint-plugin-security"
  "eslint-plugin-sonarjs"
  "eslint-plugin-unicorn"
  "globals"
)

REACT_PKGS=()
NATIVE_PKGS=()
QUERY_PKGS=()
DRIZZLE_PKGS=()
TEST_PKGS=()
NODE_PKGS=()
PRETTIER_PKGS=()

# --- Conditional packages ---

if [[ "$REACT" == "true" ]]; then
  REACT_PKGS=(
    "eslint-plugin-react"
    "eslint-plugin-react-hooks"
    "eslint-plugin-react-you-might-not-need-an-effect"
  )
fi

if [[ "$REACT_NATIVE" == "true" ]]; then
  NATIVE_PKGS=("@react-native/eslint-config")
fi

if [[ "$TANSTACK" == "true" ]]; then
  QUERY_PKGS=("@tanstack/eslint-plugin-query")
fi

if [[ "$DRIZZLE" == "true" ]]; then
  DRIZZLE_PKGS=("eslint-plugin-drizzle")
fi

if [[ "$VITEST" == "true" ]]; then
  TEST_PKGS+=("@vitest/eslint-plugin")
fi

if [[ "$PLAYWRIGHT" == "true" ]]; then
  TEST_PKGS+=("eslint-plugin-playwright")
fi

if [[ "$TESTING_LIB" == "true" ]]; then
  TEST_PKGS+=("eslint-plugin-testing-library")
fi

if [[ "$NODE_BACKEND" == "true" ]]; then
  NODE_PKGS=("eslint-plugin-n")
fi

if [[ "$PRETTIER" == "true" ]]; then
  PRETTIER_PKGS=("eslint-config-prettier")
fi

# --- Build install command ---

ALL_PKGS=("${CORE_PKGS[@]}" "${REACT_PKGS[@]}" "${NATIVE_PKGS[@]}" "${QUERY_PKGS[@]}" "${DRIZZLE_PKGS[@]}" "${TEST_PKGS[@]}" "${NODE_PKGS[@]}" "${PRETTIER_PKGS[@]}")

case "$PKG_MANAGER" in
  pnpm)  CMD="pnpm add -D" ;;
  yarn)  CMD="yarn add -D" ;;
  bun)   CMD="bun add -D" ;;
  *)     CMD="npm install -D" ;;
esac

echo "# ================================================"
echo "# ESLint Dependencies Install Command"
echo "# Package manager: $PKG_MANAGER"
echo "# ================================================"
echo ""
echo "$CMD \\"

# Print with categories
echo "  # Core"
for pkg in "${CORE_PKGS[@]}"; do
  echo "  $pkg \\"
done

if [[ ${#REACT_PKGS[@]} -gt 0 ]]; then
  echo "  # React"
  for pkg in "${REACT_PKGS[@]}"; do
    echo "  $pkg \\"
  done
fi

if [[ ${#NATIVE_PKGS[@]} -gt 0 ]]; then
  echo "  # React Native"
  for pkg in "${NATIVE_PKGS[@]}"; do
    echo "  $pkg \\"
  done
fi

if [[ ${#QUERY_PKGS[@]} -gt 0 ]]; then
  echo "  # TanStack Query"
  for pkg in "${QUERY_PKGS[@]}"; do
    echo "  $pkg \\"
  done
fi

if [[ ${#DRIZZLE_PKGS[@]} -gt 0 ]]; then
  echo "  # Drizzle ORM"
  for pkg in "${DRIZZLE_PKGS[@]}"; do
    echo "  $pkg \\"
  done
fi

if [[ ${#TEST_PKGS[@]} -gt 0 ]]; then
  echo "  # Testing"
  for pkg in "${TEST_PKGS[@]}"; do
    echo "  $pkg \\"
  done
fi

if [[ ${#NODE_PKGS[@]} -gt 0 ]]; then
  echo "  # Node.js"
  for pkg in "${NODE_PKGS[@]}"; do
    echo "  $pkg \\"
  done
fi

if [[ ${#PRETTIER_PKGS[@]} -gt 0 ]]; then
  echo "  # Prettier"
  for pkg in "${PRETTIER_PKGS[@]}"; do
    echo "  $pkg \\"
  done
fi

# Remove trailing backslash from last line (cosmetic)
echo ""
echo "# Total packages: ${#ALL_PKGS[@]}"
