#!/usr/bin/env bash
# 행동 eval 러너 — 언제/어떻게/채점 원리는 evals/README.md 가 진본.
#
# 사용:
#   bash evals/run.sh                 # 전 케이스 1회씩
#   EVAL_RUNS=3 bash evals/run.sh     # 케이스당 3회 (릴리즈 전 권장)
#   EVAL_MODEL=opus bash evals/run.sh # 모델 변경 (기본 sonnet)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS="${EVAL_RUNS:-1}"
MODEL="${EVAL_MODEL:-sonnet}"
OUTPUT_DIR="${EVAL_OUTPUT_DIR:-$ROOT/.metrics/evals/run-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
RELEASE_CHECK="${EVAL_RELEASE_CHECK:-0}"
STRICT_CASES="${EVAL_STRICT_CASES:-shorts-real-spec headless-prose-quality}"

command -v claude >/dev/null 2>&1 || { echo "[eval] claude CLI 가 필요하다"; exit 2; }

overall_fail=0
mkdir -p "$OUTPUT_DIR"
echo "[eval] output: $OUTPUT_DIR"

is_strict_case() {
  local needle="$1"
  local item
  for item in $STRICT_CASES; do
    [ "$item" = "$needle" ] && return 0
  done
  return 1
}

for case_dir in "$ROOT"/evals/cases/*/; do
  case_name="$(basename "$case_dir")"
  case_path="${case_dir%/}"
  case_output="$OUTPUT_DIR/$case_name"
  mkdir -p "$case_output"

  for f in prompt.md expected.md; do
    [ -f "$case_path/$f" ] || { echo "[eval] $case_name: $f 없음 — skip"; overall_fail=1; continue 2; }
  done

  # 블라인드 보장 — fixture 만 sandbox 로 복사 (정답표/프롬프트 제외). sandbox 이름은
  # 케이스명을 포함하지 않는다 — 검수 agent 가 repo 의 정답표 경로를 역추적하지 못하게.
  sandbox="$(mktemp -d "${TMPDIR:-/tmp}/dcness-eval-XXXXXX")"
  for f in "$case_path"/*; do
    base="$(basename "$f")"
    case "$base" in prompt.md | expected.md) continue ;; esac
    cp -R "$f" "$sandbox/"
  done

  prompt="$(sed -e "s|{{REPO_ROOT}}|$ROOT|g" -e "s|{{CASE_DIR}}|$sandbox|g" "$case_path/prompt.md")"
  expected="$(cat "$case_path/expected.md")"
  pass=0

  for ((i = 1; i <= RUNS; i++)); do
    report_file="$case_output/run-$i-report.md"
    judge_file="$case_output/run-$i-judge.md"

    if ! report="$(claude -p "$prompt" --model "$MODEL" --allowedTools "Read" --add-dir "$sandbox" 2>/dev/null)"; then
      echo "[eval] $case_name run $i: 검수 실행 실패"
      continue
    fi
    printf '%s\n' "$report" > "$report_file"

    judge_prompt="너는 채점자다. 아래 [검수 보고]가 [정답표]의 각 기대를 충족하는지만 판정한다.
- MUST 기대: 그 취지의 결함이 보고 어딘가에서 지적되면 충족.
- MUST_NOT 기대: 보고가 그 취지의 결함을 지적하지 않으면 충족. 다른 이유의 결함 지적은 무관하다.
표현이 달라도 의미가 같으면 충족으로 본다. 기대 ID 마다 'OK <ID>' 또는 'MISS <ID>' 한 줄씩 쓰고, 마지막 줄에 전부 OK 면 'RESULT: PASS', 하나라도 MISS 면 'RESULT: FAIL' 만 쓴다.

[정답표]
$expected

[검수 보고]
$report"

    if ! grade="$(claude -p "$judge_prompt" --model "$MODEL" 2>/dev/null)"; then
      echo "[eval] $case_name run $i: 채점 실행 실패"
      continue
    fi
    printf '%s\n' "$grade" > "$judge_file"

    verdict="$(printf '%s\n' "$grade" | grep -E '^RESULT: (PASS|FAIL)$' | tail -1 || true)"
    if [ "$verdict" = "RESULT: PASS" ]; then
      pass=$((pass + 1))
      echo "[eval] $case_name run $i: 정답"
      PYTHONPATH="$ROOT:${PYTHONPATH:-}" python3 -m harness.guard_telemetry record-eval \
        --case "$case_name" \
        --passed \
        --run-index "$i" \
        --total-runs "$RUNS" \
        --report-file "$report_file" \
        --judge-file "$judge_file" \
        --model "$MODEL" \
        --base-dir "$OUTPUT_DIR" >/dev/null 2>&1 || true
    else
      echo "[eval] $case_name run $i: 오답"
      printf '%s\n' "$grade" | grep -E "^(OK|MISS) " || true
      PYTHONPATH="$ROOT:${PYTHONPATH:-}" python3 -m harness.guard_telemetry record-eval \
        --case "$case_name" \
        --failed \
        --run-index "$i" \
        --total-runs "$RUNS" \
        --report-file "$report_file" \
        --judge-file "$judge_file" \
        --model "$MODEL" \
        --base-dir "$OUTPUT_DIR" >/dev/null 2>&1 || true
    fi
  done

  rm -rf "$sandbox"
  echo "[eval] $case_name — 정답 $pass/$RUNS"
  [ "$pass" -gt 0 ] || overall_fail=1
  if [ "$RELEASE_CHECK" = "1" ] && is_strict_case "$case_name" && [ "$pass" -ne "$RUNS" ]; then
    echo "[eval] $case_name — 릴리즈 체크 실패: 핵심 실사고 케이스는 $RUNS/$RUNS 필요"
    overall_fail=1
  fi
done

if [ "$overall_fail" -ne 0 ]; then
  echo "[eval] FAIL — 정답 0회 케이스 존재. 방금 바꾼 지침이 보호를 깨먹었는지 확인할 것 (evals/README.md)."
  exit 1
fi
echo "[eval] PASS"
