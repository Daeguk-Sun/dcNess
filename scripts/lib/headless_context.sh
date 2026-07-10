# Shared helpers for dcNess headless Bash wrappers.

dcness_resolve_headless_context() {
  local prefix="$1"
  local project_root="$2"
  local script_dir="$3"
  local context=""
  local rc=0

  DCNESS_HEADLESS_CONTEXT_DEGRADED=0
  DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC=""
  RESOLVED_SID=""
  RESOLVED_RID=""

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
' 2>&1
  )"
  rc=$?

  if [ "$rc" -eq 0 ]; then
    IFS="$(printf '\t')" read -r RESOLVED_SID RESOLVED_RID <<EOF
$context
EOF
    export DCNESS_SESSION_ID="$RESOLVED_SID"
    export DCNESS_RUN_ID="$RESOLVED_RID"
    RAW_LOG_DIR="$(
      PYTHONPATH="$script_dir/.." python3 - "$RESOLVED_SID" "$RESOLVED_RID" <<'PY'
import sys
from harness.session_state import run_dir

print(run_dir(sys.argv[1], sys.argv[2]) / "headless-logs")
PY
    )"
  else
    DCNESS_HEADLESS_CONTEXT_DEGRADED=1
    DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC="$context"
    unset DCNESS_SESSION_ID
    unset DCNESS_RUN_ID
    DCNESS_SESSION_ID=""
    DCNESS_RUN_ID=""
    RAW_LOG_DIR="$project_root/.dcness-work/headless-logs/unattributed"
    echo "[$prefix] WARN: sid/rid unresolved; continuing degraded/unattributed. fallback log dir: $RAW_LOG_DIR" >&2
    if [ -n "$DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC" ]; then
      printf '%s\n' "$DCNESS_HEADLESS_CONTEXT_DIAGNOSTIC" >&2
    fi
  fi

  export DCNESS_HEADLESS_CONTEXT_DEGRADED
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
