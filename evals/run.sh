#!/usr/bin/env bash
# 행동 eval 러너 — 언제/어떻게/채점 원리는 evals/README.md 가 진본.
#
# 사용:
#   bash evals/run.sh                 # 전 케이스 1회씩 (셀 병렬 — 기본 EVAL_PARALLEL=4)
#   EVAL_RUNS=3 bash evals/run.sh     # 케이스당 3회 (릴리즈 전 권장)
#   EVAL_MODEL=opus bash evals/run.sh # 모델 변경 (기본 sonnet)
#   EVAL_CASES="case-a case-b" bash evals/run.sh # 선택 케이스만 실행
#   EVAL_PARALLEL=1 bash evals/run.sh # 직렬 실행 (병렬화 회귀 안전판 — 기본은 4 셀 병렬)
#
# (case, run_index) 셀은 서로 독립이므로 셀 단위로 병렬 실행한다. 셀 내부의 report→judge
# 순서만 유지하고, 케이스 간·run 간에는 순서 의존이 없다. macOS 기본 bash 3.2 는 `wait -n`
# 을 지원하지 않으므로 이식성을 위해 `xargs -P` 로 동시 셀 상한을 건다. 셀 워커는 자기
# 자신을 `__worker` 모드로 재호출한 프로세스이며, 결과는 shell 변수가 아니라 marker 파일로
# 집계한다 (서브셸이 부모 카운터를 못 갱신하는 문제 회피).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

byte_len() {
  LC_ALL=C printf '%s' "$1" | wc -c | tr -d ' '
}

# telemetry 기록 — case_name/i/RUNS/MODEL/OUTPUT_DIR 는 호출자(run_cell)의 local 을
# dynamic scope 로 참조한다. 병렬 append 는 harness.guard_telemetry 가 O_APPEND 라인
# 단위로 원자적이며, 빈 파일 첫 기록 시 telemetry_epoch 가 중복될 수 있으나 무해하다.
record_eval_result() {
  local passed_flag="$1"
  local failure_stage="$2"
  local report_path="$3"
  local judge_path="$4"
  local turns="$5"
  local report_len="$6"
  local judge_len="$7"
  local token_estimate="$8"
  local status_arg="--failed"
  if [ "$passed_flag" = "passed" ]; then
    status_arg="--passed"
  fi
  if [ -n "$failure_stage" ]; then
    PYTHONPATH="$ROOT:${PYTHONPATH:-}" python3 -m harness.guard_telemetry record-eval \
      --case "$case_name" \
      "$status_arg" \
      --run-index "$i" \
      --total-runs "$RUNS" \
      --report-file "$report_path" \
      --judge-file "$judge_path" \
      --model "$MODEL" \
      --llm-turns "$turns" \
      --report-chars "$report_len" \
      --judge-chars "$judge_len" \
      --estimated-output-tokens "$token_estimate" \
      --token-estimate-basis "utf8_bytes/4_lower_bound" \
      --failure-stage "$failure_stage" \
      --failure-detail "claude invocation failed" \
      --base-dir "$OUTPUT_DIR" >/dev/null 2>&1 || true
    return 0
  fi
  PYTHONPATH="$ROOT:${PYTHONPATH:-}" python3 -m harness.guard_telemetry record-eval \
    --case "$case_name" \
    "$status_arg" \
    --run-index "$i" \
    --total-runs "$RUNS" \
    --report-file "$report_path" \
    --judge-file "$judge_path" \
    --model "$MODEL" \
    --llm-turns "$turns" \
    --report-chars "$report_len" \
    --judge-chars "$judge_len" \
    --estimated-output-tokens "$token_estimate" \
    --token-estimate-basis "utf8_bytes/4_lower_bound" \
    --base-dir "$OUTPUT_DIR" >/dev/null 2>&1 || true
}

# 셀 워커 — 하나의 (case, run_index) 셀을 처리한다: 블라인드 검수(report) → 채점(judge)
# → verdict 파싱 → telemetry 기록 → PASS/FAIL marker. 진행 로그는 인터리빙 방지를 위해
# 자기 로그 파일에만 쓰고, 부모가 케이스 순서대로 다시 출력한다. 어떤 결과에서도 exit 0.
run_cell() {
  local spec="$1"
  local case_name run_index total_runs model output_dir instruction_root sandbox
  local prompt_file expected_file case_output marker_file log_file
  {
    IFS= read -r case_name
    IFS= read -r run_index
    IFS= read -r total_runs
    IFS= read -r model
    IFS= read -r output_dir
    IFS= read -r instruction_root
    IFS= read -r sandbox
    IFS= read -r prompt_file
    IFS= read -r expected_file
    IFS= read -r case_output
    IFS= read -r marker_file
    IFS= read -r log_file
  } < "$spec"

  # record_eval_result 가 참조하는 이름들을 셀 컨텍스트로 고정한다 (dynamic scope).
  local i="$run_index" RUNS="$total_runs" MODEL="$model" OUTPUT_DIR="$output_dir"
  local prompt expected report grade report_file judge_file
  prompt="$(cat "$prompt_file")"
  expected="$(cat "$expected_file")"
  report_file="$case_output/run-$run_index-report.md"
  judge_file="$case_output/run-$run_index-judge.md"
  : > "$log_file"

  # 하네스 무주입 격리 (#1073) — --safe-mode 가 CLAUDE.md·skills·hooks·MCP·user settings
  # customization 을 전부 끄고(OAuth 인증은 유지), --tools 가 도구 schema 를 제한한다.
  # 검수자는 격리된 instruction snapshot의 agent 지침을 Read 하고 일부 케이스는
  # {{CASE_DIR}} fixture 를 파일명 없이 열거(Glob)해야 하므로 --tools Read Glob +
  # --add-dir "$instruction_root"(지침) + --add-dir "$sandbox"(fixture)만 유지한다.
  # (--bare 는 OAuth/keychain 을 못 읽어 "Not logged in" 이라 쓰지 않는다.)
  if ! report="$(cd "$instruction_root" && claude -p "$prompt" --model "$MODEL" --safe-mode --tools Read Glob --add-dir "$instruction_root" --add-dir "$sandbox" 2>/dev/null)"; then
    echo "[eval] $case_name run $run_index: 검수 실행 실패" >> "$log_file"
    record_eval_result "failed" "report" "" "" 1 0 0 0
    printf 'FAIL\n' > "$marker_file"
    return 0
  fi
  printf '%s\n' "$report" > "$report_file"

  local judge_prompt
  judge_prompt="너는 채점자다. 아래 [검수 보고]가 [정답표]의 각 기대를 충족하는지만 판정한다.
- MUST 기대: 그 취지의 결함이 보고 어딘가에서 지적되면 충족.
- MUST_NOT 기대: 보고가 그 취지의 결함을 지적하지 않으면 충족. 다른 이유의 결함 지적은 무관하다.
- PASS / FAIL / ESCALATE 같은 최소 결론 enum 요구는 rigid schema 요구가 아니다. status JSON, marker, fixed table, fixed schema, exact template 같은 출력 구조 강제만 rigid schema 요구로 본다.
표현이 달라도 의미가 같으면 충족으로 본다. 기대 ID 마다 'OK <ID>' 또는 'MISS <ID>' 한 줄씩 쓰고, 마지막 줄에 전부 OK 면 'RESULT: PASS', 하나라도 MISS 면 'RESULT: FAIL' 만 쓴다.

[정답표]
$expected

[검수 보고]
$report"

  # 채점자는 정답표+보고가 프롬프트에 인라인 — repo 접근 0 필요. --safe-mode + --tools ""
  # 로 customization·도구를 전부 끈다. baseline 실측 43,455 → ~1,857.
  # (--allowedTools "" 는 permission 만 비우고 tool schema 는 남으므로 쓰지 않는다.)
  if ! grade="$(cd "$instruction_root" && claude -p "$judge_prompt" --model "$MODEL" --safe-mode --tools "" 2>/dev/null)"; then
    echo "[eval] $case_name run $run_index: 채점 실행 실패" >> "$log_file"
    local report_chars report_bytes estimated_output_tokens
    report_chars="${#report}"
    report_bytes="$(byte_len "$report")"
    estimated_output_tokens=$(((report_bytes + 3) / 4))
    record_eval_result "failed" "judge" "$report_file" "" 2 "$report_chars" 0 "$estimated_output_tokens"
    printf 'FAIL\n' > "$marker_file"
    return 0
  fi
  printf '%s\n' "$grade" > "$judge_file"

  local report_chars judge_chars report_bytes judge_bytes estimated_output_tokens llm_turns verdict
  report_chars="${#report}"
  judge_chars="${#grade}"
  report_bytes="$(byte_len "$report")"
  judge_bytes="$(byte_len "$grade")"
  estimated_output_tokens=$(((report_bytes + judge_bytes + 3) / 4))
  llm_turns=2

  verdict="$(printf '%s\n' "$grade" | grep -E '^RESULT: (PASS|FAIL)$' | tail -1 || true)"
  if [ "$verdict" = "RESULT: PASS" ]; then
    echo "[eval] $case_name run $run_index: 정답" >> "$log_file"
    record_eval_result "passed" "" "$report_file" "$judge_file" "$llm_turns" "$report_chars" "$judge_chars" "$estimated_output_tokens"
    printf 'PASS\n' > "$marker_file"
  else
    echo "[eval] $case_name run $run_index: 오답" >> "$log_file"
    printf '%s\n' "$grade" | grep -E "^(OK|MISS) " >> "$log_file" || true
    record_eval_result "failed" "" "$report_file" "$judge_file" "$llm_turns" "$report_chars" "$judge_chars" "$estimated_output_tokens"
    printf 'FAIL\n' > "$marker_file"
  fi
  return 0
}

# 셀 워커 재진입 — xargs 가 `bash run.sh __worker <spec>` 로 각 셀을 호출한다.
if [ "${1:-}" = "__worker" ]; then
  run_cell "$2"
  exit 0
fi

# =========================== main (부모 오케스트레이터) ===========================
RUNS="${EVAL_RUNS:-1}"
MODEL="${EVAL_MODEL:-sonnet}"
OUTPUT_DIR="${EVAL_OUTPUT_DIR:-$ROOT/.metrics/evals/run-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
RELEASE_CHECK="${EVAL_RELEASE_CHECK:-0}"
STRICT_CASES="${EVAL_STRICT_CASES:-shorts-real-spec headless-prose-quality}"
CASE_FILTER="${EVAL_CASES:-}"
PARALLEL="${EVAL_PARALLEL:-4}"
SELF="$ROOT/evals/run.sh"

command -v claude >/dev/null 2>&1 || { echo "[eval] claude CLI 가 필요하다"; exit 2; }

case "$PARALLEL" in
  '' | *[!0-9]*)
    echo "[eval] EVAL_PARALLEL 은 양의 정수여야 한다: '$PARALLEL'" >&2
    exit 2
    ;;
esac
if [ "$PARALLEL" -lt 1 ]; then
  echo "[eval] EVAL_PARALLEL 은 1 이상이어야 한다: '$PARALLEL'" >&2
  exit 2
fi

case_is_available() {
  local needle="$1"
  local available_dir
  for available_dir in "$ROOT"/evals/cases/*/; do
    [ "$(basename "$available_dir")" = "$needle" ] && return 0
  done
  return 1
}

if [ -n "$CASE_FILTER" ]; then
  selected_count=0
  for selected_case in $CASE_FILTER; do
    selected_count=$((selected_count + 1))
    case_is_available "$selected_case" || {
      echo "[eval] 선택 케이스 없음: $selected_case" >&2
      exit 2
    }
  done
  [ "$selected_count" -gt 0 ] || {
    echo "[eval] 선택 케이스가 비어 있음" >&2
    exit 2
  }
fi

is_strict_case() {
  local needle="$1"
  local item
  for item in $STRICT_CASES; do
    [ "$item" = "$needle" ] && return 0
  done
  return 1
}

is_selected_case() {
  local needle="$1"
  local item
  [ -z "$CASE_FILTER" ] && return 0
  for item in $CASE_FILTER; do
    [ "$item" = "$needle" ] && return 0
  done
  return 1
}

overall_fail=0
mkdir -p "$OUTPUT_DIR"
echo "[eval] output: $OUTPUT_DIR"

# Report agent에는 지침을 읽을 최소 snapshot만 노출한다. repo 전체를 --add-dir로 주면
# evals/golden/**의 사람 판정과 이유를 탐색할 수 있어 blind report가 오염된다.
instruction_root="$(mktemp -d "${TMPDIR:-/tmp}/dcness-eval-instructions-XXXXXX")"
# 셀 spec / marker / 로그 / sandbox 를 한 작업 디렉터리에 모아 trap 으로 일괄 정리한다.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcness-eval-work-XXXXXX")"
mkdir -p "$WORK/specs" "$WORK/markers" "$WORK/logs" "$WORK/sandboxes"
cleanup() {
  rm -rf -- "$WORK"
  rm -rf -- "$instruction_root"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cp -R "$ROOT/docs" "$ROOT/skills" "$ROOT/agents" "$instruction_root/"

# --- 준비 단계: 케이스별 sandbox·프롬프트 렌더링 후 (case, run) 셀 worklist 생성 ---
cases_ordered=()
cell_spec_list="$WORK/cell-spec-list"
: > "$cell_spec_list"

for case_dir in "$ROOT"/evals/cases/*/; do
  case_name="$(basename "$case_dir")"
  is_selected_case "$case_name" || continue
  case_path="${case_dir%/}"
  case_output="$OUTPUT_DIR/$case_name"
  mkdir -p "$case_output"

  missing=0
  for f in prompt.md expected.md; do
    [ -f "$case_path/$f" ] || {
      echo "[eval] $case_name: $f 없음 — skip"
      overall_fail=1
      missing=1
      break
    }
  done
  [ "$missing" -eq 0 ] || continue

  # 블라인드 보장 — fixture 만 sandbox 로 복사 (정답표/프롬프트 제외). sandbox 이름은
  # 케이스명을 포함하지 않는다 — 검수 agent 가 repo 의 정답표 경로를 역추적하지 못하게.
  # 케이스당 1회 생성해 그 케이스의 모든 run 이 공유 읽기(eval 중 read-only)한다.
  sandbox="$(mktemp -d "$WORK/sandboxes/sb.XXXXXX")"
  for f in "$case_path"/*; do
    base="$(basename "$f")"
    case "$base" in prompt.md | expected.md) continue ;; esac
    cp -R "$f" "$sandbox/"
  done

  prompt="$(sed -e "s|{{REPO_ROOT}}|$instruction_root|g" -e "s|{{CASE_DIR}}|$sandbox|g" "$case_path/prompt.md")"
  prompt_file="$WORK/specs/$case_name.prompt"
  expected_file="$WORK/specs/$case_name.expected"
  printf '%s' "$prompt" > "$prompt_file"
  cp "$case_path/expected.md" "$expected_file"
  cases_ordered+=("$case_name")

  for ((i = 1; i <= RUNS; i++)); do
    spec="$WORK/specs/${case_name}__run${i}.spec"
    marker="$WORK/markers/${case_name}__run${i}.marker"
    log_file="$WORK/logs/${case_name}__run${i}.log"
    {
      printf '%s\n' "$case_name"
      printf '%s\n' "$i"
      printf '%s\n' "$RUNS"
      printf '%s\n' "$MODEL"
      printf '%s\n' "$OUTPUT_DIR"
      printf '%s\n' "$instruction_root"
      printf '%s\n' "$sandbox"
      printf '%s\n' "$prompt_file"
      printf '%s\n' "$expected_file"
      printf '%s\n' "$case_output"
      printf '%s\n' "$marker"
      printf '%s\n' "$log_file"
    } > "$spec"
    printf '%s\n' "$spec" >> "$cell_spec_list"
  done
done

# --- 실행 단계: 셀을 EVAL_PARALLEL 상한으로 병렬 실행 (=1 이면 직렬 안전판) ---
if [ -s "$cell_spec_list" ]; then
  echo "[eval] 셀 실행 — 병렬도 $PARALLEL"
  set +e
  tr '\n' '\0' < "$cell_spec_list" | xargs -0 -P "$PARALLEL" -n1 bash "$SELF" __worker
  dispatch_rc=$?
  set -e
  if [ "$dispatch_rc" -ne 0 ]; then
    echo "[eval] 경고: 일부 셀 워커가 비정상 종료 (rc=$dispatch_rc) — marker 기준으로 집계" >&2
  fi
fi

# --- 집계 단계: 케이스별 pass/RUNS 를 marker 로 재현하고 로그를 순서대로 출력 ---
if [ "${#cases_ordered[@]}" -gt 0 ]; then
  for case_name in "${cases_ordered[@]}"; do
    pass=0
    for ((i = 1; i <= RUNS; i++)); do
      log_file="$WORK/logs/${case_name}__run${i}.log"
      [ -f "$log_file" ] && cat "$log_file"
      marker="$WORK/markers/${case_name}__run${i}.marker"
      if [ -f "$marker" ] && [ "$(cat "$marker")" = "PASS" ]; then
        pass=$((pass + 1))
      fi
    done
    echo "[eval] $case_name — 정답 $pass/$RUNS"
    [ "$pass" -gt 0 ] || overall_fail=1
    if [ "$RELEASE_CHECK" = "1" ] && is_strict_case "$case_name" && [ "$pass" -ne "$RUNS" ]; then
      echo "[eval] $case_name — 릴리즈 체크 실패: 핵심 실사고 케이스는 $RUNS/$RUNS 필요"
      overall_fail=1
    fi
  done
fi

if [ "$overall_fail" -ne 0 ]; then
  echo "[eval] FAIL — 정답 0회 케이스 존재. 방금 바꾼 지침이 보호를 깨먹었는지 확인할 것 (evals/README.md)."
  exit 1
fi
echo "[eval] PASS"
