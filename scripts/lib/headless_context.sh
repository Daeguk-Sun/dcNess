# Shared helpers for dcNess headless Bash wrappers.

dcness_resolve_headless_context() {
  local prefix="$1"
  local project_root="$2"
  local script_dir="$3"
  local context=""
  local err_file=""
  local rc=0

  DCNESS_HEADLESS_CONTEXT_DEGRADED=0
  DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC=""
  RESOLVED_SID=""
  RESOLVED_RID=""
  CANONICAL_RUN_DIR=""

  err_file="$(mktemp "${TMPDIR:-/tmp}/dcness-headless-context.XXXXXX")"
  context="$(
    PYTHONPATH="$script_dir/.." python3 -c '
import sys
from harness.session_state import (
    auto_detect_run_id,
    auto_detect_session_id,
    diagnose_sid_rid_resolution,
)

sid = auto_detect_session_id()
rid = auto_detect_run_id()
if not sid or not rid:
    print(diagnose_sid_rid_resolution(mode="both"), file=sys.stderr)
    sys.exit(1)
print(f"{sid}\t{rid}")
' 2>"$err_file"
  )"
  rc=$?
  DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC="$(cat "$err_file" 2>/dev/null || true)"
  rm -f "$err_file"

  if [ "$rc" -eq 0 ]; then
    if [ -n "$DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC" ]; then
      printf '%s\n' "$DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC" >&2
    fi
    IFS="$(printf '\t')" read -r RESOLVED_SID RESOLVED_RID <<EOF
$context
EOF
    export DCNESS_SESSION_ID="$RESOLVED_SID"
    export DCNESS_RUN_ID="$RESOLVED_RID"
    CANONICAL_RUN_DIR="$(
      PYTHONPATH="$script_dir/.." python3 - "$RESOLVED_SID" "$RESOLVED_RID" <<'PY'
import sys
from harness.session_state import run_dir

print(run_dir(sys.argv[1], sys.argv[2]))
PY
    )"
    RAW_LOG_DIR="$CANONICAL_RUN_DIR/headless-logs"
  else
    DCNESS_HEADLESS_CONTEXT_DEGRADED=1
    unset DCNESS_SESSION_ID
    unset DCNESS_RUN_ID
    DCNESS_SESSION_ID=""
    DCNESS_RUN_ID=""
    CANONICAL_RUN_DIR=""
    RAW_LOG_DIR="$project_root/.dcness-work/headless-logs/unattributed"
    echo "[$prefix] WARN: sid/rid unresolved; continuing degraded/unattributed. fallback log dir: $RAW_LOG_DIR" >&2
    if [ -n "$DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC" ]; then
      printf '%s\n' "$DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC" >&2
    fi
  fi

  export DCNESS_HEADLESS_CONTEXT_DEGRADED
  export CANONICAL_RUN_DIR
  mkdir -p "$RAW_LOG_DIR"
}

dcness_write_headless_context_header() {
  local prefix="$1"
  local raw_log="$2"

  if [ "${DCNESS_HEADLESS_CONTEXT_DEGRADED:-0}" = "1" ]; then
    {
      echo "[$prefix] WARN: UNATTRIBUTED degraded execution."
      echo "[$prefix] sid/rid unresolved; provider launch continued without run attribution."
      echo "[$prefix] fallback raw log directory: $RAW_LOG_DIR"
      if [ -n "${DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC:-}" ]; then
        echo
        echo "----- SID/RID RESOLUTION DIAGNOSTIC -----"
        printf '%s\n' "$DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC"
      fi
      echo
    } >> "$raw_log"
  fi
}

dcness_append_final_prose_to_raw_log() {
  local label="$1"
  local prose_file="$2"
  local raw_log="$3"

  {
    echo
    echo "----- $label / FINAL PROSE -----"
    cat "$prose_file" 2>/dev/null || true
  } >> "$raw_log"
}

dcness_missing_build_phase_prose() {
  local phase=""

  [ -n "${CANONICAL_RUN_DIR:-}" ] || return 0
  for phase in build-test.md build-impl.md build-validate.md; do
    if [ ! -s "$CANONICAL_RUN_DIR/$phase" ]; then
      printf '%s\n' "$CANONICAL_RUN_DIR/$phase"
    fi
  done
}

dcness_build_outcome_requires_phase_prose() {
  local script_dir="$1"
  local prose_file="$2"
  local conclusion=""

  conclusion="$(
    PYTHONPATH="$script_dir/..${PYTHONPATH:+:$PYTHONPATH}" \
      python3 - "$prose_file" <<'PY'
import sys
from pathlib import Path

from harness.run_review import _extract_conclusion_enum

print(
    _extract_conclusion_enum(
        Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    )
)
PY
  )" || return 0

  # Canonical phase prose is a clean/PASS invariant. Routed non-PASS outcomes
  # such as a pre-implementation environment escalation must still reach the
  # main orchestrator as their original terminal receipt.
  case "$conclusion" in
    PASS|"") return 0 ;;
    *) return 1 ;;
  esac
}

dcness_record_end_step() {
  local prefix="$1"
  local provider="$2"
  local helper="$3"
  local agent="$4"
  local mode="$5"
  local prose_file="$6"
  local raw_log="$7"
  local rc=0

  if [ -n "$mode" ]; then
    "$helper" end-step "$agent" "$mode" --provider "$provider" --prose-file "$prose_file"
    rc=$?
  else
    "$helper" end-step "$agent" --provider "$provider" --prose-file "$prose_file"
    rc=$?
  fi

  if [ "$rc" -ne 0 ] && [ "${DCNESS_HEADLESS_CONTEXT_DEGRADED:-0}" = "1" ]; then
    echo "[$prefix] WARN: end-step recording skipped in degraded context (exit $rc); provider result is preserved. raw log: $raw_log" >&2
    {
      echo
      echo "[$prefix] WARN: end-step recording skipped in degraded context (exit $rc)."
      echo "[$prefix] Provider result was preserved; this run is UNATTRIBUTED."
    } >> "$raw_log"
    return 0
  fi

  return "$rc"
}
