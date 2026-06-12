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

command -v claude >/dev/null 2>&1 || { echo "[eval] claude CLI 가 필요하다"; exit 2; }

overall_fail=0

for case_dir in "$ROOT"/evals/cases/*/; do
  case_name="$(basename "$case_dir")"
  case_path="${case_dir%/}"

  for f in prompt.md expected.md; do
    [ -f "$case_path/$f" ] || { echo "[eval] $case_name: $f 없음 — skip"; overall_fail=1; continue 2; }
  done

  prompt="$(sed -e "s|{{REPO_ROOT}}|$ROOT|g" -e "s|{{CASE_DIR}}|$case_path|g" "$case_path/prompt.md")"
  expected="$(cat "$case_path/expected.md")"
  pass=0

  for ((i = 1; i <= RUNS; i++)); do
    if ! report="$(claude -p "$prompt" --model "$MODEL" --allowedTools "Read" "Glob" "Grep" 2>/dev/null)"; then
      echo "[eval] $case_name run $i: 검수 실행 실패"
      continue
    fi

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

    if printf '%s' "$grade" | grep -q "RESULT: PASS"; then
      pass=$((pass + 1))
      echo "[eval] $case_name run $i: 정답"
    else
      echo "[eval] $case_name run $i: 오답"
      printf '%s\n' "$grade" | grep -E "^(OK|MISS) " || true
    fi
  done

  echo "[eval] $case_name — 정답 $pass/$RUNS"
  [ "$pass" -gt 0 ] || overall_fail=1
done

if [ "$overall_fail" -ne 0 ]; then
  echo "[eval] FAIL — 정답 0회 케이스 존재. 방금 바꾼 지침이 보호를 깨먹었는지 확인할 것 (evals/README.md)."
  exit 1
fi
echo "[eval] PASS"
