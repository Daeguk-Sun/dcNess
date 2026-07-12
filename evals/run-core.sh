#!/usr/bin/env bash
# Versioned core incident subset runner. Full semantics: evals/README.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/evals/core-incident-subset.json"

subset_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["subset_version"])' "$MANIFEST")"
cases="$(python3 -c 'import json,sys; print(" ".join(item["case"] for item in json.load(open(sys.argv[1], encoding="utf-8"))["selected_cases"]))' "$MANIFEST")"

[ -n "$cases" ] || { echo "[eval core] selected_cases가 비어 있음" >&2; exit 2; }
for case_name in $cases; do
  [ -d "$ROOT/evals/cases/$case_name" ] || {
    echo "[eval core] manifest case 없음: $case_name" >&2
    exit 2
  }
done

echo "[eval core] subset=$subset_version cases=$cases"
EVAL_CASES="$cases" EVAL_STRICT_CASES="$cases" EVAL_RELEASE_CHECK=1 \
  bash "$ROOT/evals/run.sh"
