#!/usr/bin/env bash
# Test runner for the Olympus challenge.
#   ./test.sh base --output_path junit.xml  -> pre-existing tests only (must pass on the base commit)
#   ./test.sh new  --output_path junit.xml  -> hidden tests for the new behaviour (fail on base, pass on solution)
set -euo pipefail

MODE="new"
OUTPUT_PATH="junit.xml"

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        base|new) MODE="$1" ;;
        --output_path) OUTPUT_PATH="$2"; shift ;;
    esac
    shift
done

BASE_TESTS=(
    tests/test_url_for.py
    tests/test_url_building.py
    tests/test_requests.py
    tests/test_headers.py
)
NEW_TESTS=(
    tests/test_url_for_external_febf51.py
)

if [[ "$MODE" == "base" ]]; then
    TESTS=("${BASE_TESTS[@]}")
else
    TESTS=("${NEW_TESTS[@]}" "${BASE_TESTS[@]}")
fi

exec uv run pytest "${TESTS[@]}" -p no:cacheprovider --junitxml="$OUTPUT_PATH"