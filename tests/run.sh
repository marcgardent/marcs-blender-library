#!/usr/bin/env bash
# CI locale de Nodes as Text : les tests du langage, puis ceux dans Blender.
# S'arrête au premier échec et affiche son journal ; sinon une ligne par suite.
#
#   tests/run.sh
#   BLENDER=/chemin/vers/blender tests/run.sh

set -u
cd "$(dirname "$0")/.."

BLENDER="${BLENDER:-blender}"
LOGS="$(mktemp -d)"
trap 'rm -rf "$LOGS"' EXIT

passed=0

run() {
    local name="$1"
    shift
    local log="$LOGS/$name.log"
    if "$@" >"$log" 2>&1; then
        # La dernière ligne de chaque suite donne son compte ("156 passed", "8 passed, 0 failed")
        printf 'ok    %-12s %s\n' "$name" "$(grep -E 'passed' "$log" | tail -n 1)"
        passed=$((passed + 1))
    else
        printf 'ÉCHEC %s\n\n' "$name"
        cat "$log"
        exit 1
    fi
}

echo "$("$BLENDER" --version 2>/dev/null | head -n 1)"

run lang uv run --with pytest python -m pytest -q tests/bnodes/lang
for test in tests/bnodes/host/test_*.py; do
    run "$(basename "$test" .py)" \
        "$BLENDER" --background --factory-startup --python-exit-code 1 --python "$test"
done

echo "$passed suites passées"
