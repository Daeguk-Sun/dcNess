#!/usr/bin/env bash
# Install (or remove) the launchd LaunchAgent that runs the dcNess loop-diagnose
# sweep on a timer without a human session. dcNess self only — not a plugin
# deploy-path artifact. See docs/internal/self-improvement-loop.md.
set -euo pipefail

LABEL="com.dcness.loop-sweep"
INTERVAL="86400"   # default period: once per day (seconds). Override with --interval.
UNINSTALL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --interval)
      INTERVAL="${2:-}"
      shift 2
      ;;
    --uninstall)
      UNINSTALL=1
      shift
      ;;
    -h|--help)
      echo "usage: install-loop-sweep.sh [--interval SECONDS] [--uninstall]"
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_DEST="${AGENTS_DIR}/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

if [ "${UNINSTALL}" -eq 1 ]; then
  launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
  rm -f "${PLIST_DEST}"
  echo "uninstalled ${LABEL}"
  exit 0
fi

case "${INTERVAL}" in
  ''|*[!0-9]*)
    echo "interval must be a positive integer number of seconds" >&2
    exit 2
    ;;
esac
[ "${INTERVAL}" -ge 1 ] || { echo "interval must be >= 1" >&2; exit 2; }

PYTHON_BIN="$(command -v python3.11 || true)"
[ -n "${PYTHON_BIN}" ] || { echo "python3.11 not found on PATH" >&2; exit 1; }

TEMPLATE="${SCRIPT_DIR}/${LABEL}.plist.template"
[ -f "${TEMPLATE}" ] || { echo "template not found: ${TEMPLATE}" >&2; exit 1; }

mkdir -p "${AGENTS_DIR}" "${REPO_ROOT}/.metrics/loop-diagnose"

sed -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
    -e "s|__REPO_ROOT__|${REPO_ROOT}|g" \
    -e "s|__INTERVAL_SECONDS__|${INTERVAL}|g" \
    "${TEMPLATE}" > "${PLIST_DEST}"

launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "${DOMAIN}" "${PLIST_DEST}"

echo "installed ${LABEL} (interval=${INTERVAL}s) -> ${PLIST_DEST}"
echo "trigger a test run:  launchctl kickstart -k ${DOMAIN}/${LABEL}"
echo "check status:        launchctl print ${DOMAIN}/${LABEL} | grep -i state"
echo "digest:              ${REPO_ROOT}/.metrics/loop-diagnose/digest-latest.md"
echo "failure trace:       ${REPO_ROOT}/.metrics/loop-diagnose/sweep-log.jsonl (+ launchd.err.log)"
