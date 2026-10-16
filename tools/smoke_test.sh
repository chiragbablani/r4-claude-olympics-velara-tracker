#!/usr/bin/env bash
# Run solve.py against a pack folder, time it, confirm stdout parses as a
# single JSON object, and run the contract validator.
#
# Usage: tools/smoke_test.sh <pack_dir>
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: tools/smoke_test.sh <pack_dir>" >&2
    exit 2
fi

PACK_DIR="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [[ "$PACK_DIR" != /* ]]; then
    PACK_DIR="$(cd "$PACK_DIR" && pwd)"
fi

OUT_FILE="$(mktemp -t velara_smoke_out)"
ERR_FILE="$(mktemp -t velara_smoke_err)"
trap 'rm -f "$OUT_FILE" "$ERR_FILE"' EXIT

echo "pack dir: $PACK_DIR" >&2
echo "running: python3 solve.py $PACK_DIR" >&2

START_TIME=$(date +%s)
set +e
(cd "$REPO_ROOT" && python3 solve.py "$PACK_DIR" >"$OUT_FILE" 2>"$ERR_FILE")
SOLVE_EXIT=$?
set -e
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "elapsed: ${ELAPSED}s" >&2
echo "solve.py exit code: $SOLVE_EXIT" >&2

echo "---- stderr from solve.py ----" >&2
cat "$ERR_FILE" >&2
echo "-------------------------------" >&2

if [[ $ELAPSED -gt 300 ]]; then
    echo "FAIL: runtime ${ELAPSED}s exceeds 300s limit" >&2
    exit 1
fi

echo "---- validating stdout against contract ----" >&2
python3 "$SCRIPT_DIR/validate_output.py" "$OUT_FILE"
VALIDATE_EXIT=$?

if [[ $VALIDATE_EXIT -ne 0 ]]; then
    echo "FAIL: output did not pass contract validation" >&2
    exit 1
fi

echo "PASS: smoke test completed in ${ELAPSED}s" >&2
exit 0
