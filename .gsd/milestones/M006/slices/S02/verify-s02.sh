#!/usr/bin/env bash
# verify-s02.sh — Verification script for S02 (Conversational Setup + Minimal UX)
# Checks system.md content contracts and index.ts go guard logic.

set -euo pipefail

FAIL=0
SYSTEM_MD="tui/src/resources/extensions/autoagent/prompts/system.md"
INDEX_TS="tui/src/resources/extensions/autoagent/index.ts"

check() {
  local desc="$1"
  local result="$2"
  if [ "$result" = "0" ]; then
    echo "PASS: $desc"
  else
    echo "FAIL: $desc"
    FAIL=1
  fi
}

check_not() {
  local desc="$1"
  local result="$2"
  if [ "$result" = "1" ]; then
    echo "PASS: $desc"
  else
    echo "FAIL: $desc"
    FAIL=1
  fi
}

# --- system.md checks ---

# prepare.py output contract (score: X.XXXX format)
grep -q 'score: X\.XXXX' "$SYSTEM_MD" && r=0 || r=1
check "system.md contains prepare.py output contract (score: X.XXXX)" "$r"

# prepare.py skeleton — def eval
grep -q 'def eval' "$SYSTEM_MD" && r=0 || r=1
check "system.md contains prepare.py skeleton (def eval)" "$r"

# prepare.py skeleton — test_cases
grep -q 'test_cases' "$SYSTEM_MD" && r=0 || r=1
check "system.md contains prepare.py skeleton (test_cases)" "$r"

# prepare.py skeleton — __main__
grep -q '__main__' "$SYSTEM_MD" && r=0 || r=1
check "system.md contains prepare.py skeleton (__main__)" "$r"

# pipeline.py contract — run(input_data, context)
grep -q 'run(input_data, context)' "$SYSTEM_MD" && r=0 || r=1
check "system.md contains pipeline.py contract (run(input_data, context))" "$r"

# pipeline.py contract — {"output": ...} return
grep -q '"output"' "$SYSTEM_MD" && r=0 || r=1
check "system.md contains pipeline.py contract (output key)" "$r"

# baseline validation — score range check (0.1 and 0.9)
(grep -q '0\.1' "$SYSTEM_MD" && grep -q '0\.9' "$SYSTEM_MD") && r=0 || r=1
check "system.md contains baseline validation (score range 0.1–0.9)" "$r"

# no "Copy program.md" step
grep -qi 'Copy program\.md\|Copy `program\.md`' "$SYSTEM_MD" && r=0 || r=1
check_not "system.md does NOT contain Copy program.md step" "$r"

# completion criteria
grep -qi 'setup is complete\|complete when\|completion criteria\|both conditions' "$SYSTEM_MD" && r=0 || r=1
check "system.md contains explicit completion criteria" "$r"

# --- index.ts checks ---

# go handler checks for pipeline.py existence
grep -A 5 'case "go"' "$INDEX_TS" | grep -q 'pipeline\.py' && r=0 || r=1
check "index.ts go handler checks for pipeline.py" "$r"

# go handler checks for prepare.py existence
grep -A 5 'case "go"' "$INDEX_TS" | grep -q 'prepare\.py' && r=0 || r=1
check "index.ts go handler checks for prepare.py" "$r"

# go handler has early return on missing files
grep -A 15 'case "go"' "$INDEX_TS" | grep -q 'Project not ready' && r=0 || r=1
check "index.ts go handler shows setup prompt when files missing" "$r"

echo ""
if [ "$FAIL" = "0" ]; then
  echo "All checks passed."
  exit 0
else
  echo "Some checks FAILED."
  exit 1
fi
