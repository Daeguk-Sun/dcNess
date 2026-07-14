#!/usr/bin/env python3
"""Replay the frozen #1092 cleanup measurement implementation."""

from __future__ import annotations

import subprocess  # nosec B404 - argv-only internal git command
from pathlib import Path

_REVISION = "071146c8b1e3e2893e7c47578c55b8ada296886b"
_PATH = "scripts/policy_cleanup_baseline.py"
_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = subprocess.run(  # nosec B603, B607
    ["git", "show", f"{_REVISION}:{_PATH}"],
    cwd=_ROOT, check=True, capture_output=True, text=True,
).stdout
exec(compile(_SOURCE, f"{_REVISION}:{_PATH}", "exec"))  # nosec B102
