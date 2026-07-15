"""Shared persisted-run fixtures for reader and aggregate tests."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from harness import ledger


RunRow = Mapping[str, Any]


def _run_dir(root: Path, sid: str, rid: str) -> Path:
    path = root / ".claude" / "harness-state" / ".sessions" / sid / "runs" / rid
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_jsonl(path: Path, rows: Iterable[RunRow]) -> None:
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def make_ledger_run_dir(
    root: Path,
    sid: str,
    rid: str,
    events: Iterable[RunRow],
    prose_files: Mapping[str, str] | None = None,
) -> Path:
    """Write a canonical ledger fixture with valid prose receipts."""
    path = _run_dir(root, sid, rid)
    prose_by_name: dict[str, tuple[Path, str]] = {}
    for filename, content in (prose_files or {}).items():
        prose_path = path / filename
        prose_path.write_text(content, encoding="utf-8")
        prose_by_name[filename] = (prose_path, content)

    normalized_events: list[dict[str, Any]] = []
    implicit_steps = False
    for index, event in enumerate(events):
        record = dict(event)
        if "event" not in record and "agent" in record:
            implicit_steps = True
            record["event"] = "step_completed"
        prose_file = record.get("prose_file")
        if isinstance(prose_file, str) and prose_file in prose_by_name:
            prose_path, content = prose_by_name[prose_file]
            record["prose_file"] = str(prose_path)
            record.setdefault("sha256", ledger.sha256_text(content))
        elif isinstance(prose_file, str) and Path(prose_file).is_file():
            content = Path(prose_file).read_text(encoding="utf-8")
            record.setdefault("sha256", ledger.sha256_text(content))
        elif record.get("event") == "step_completed" and not prose_file:
            filename = f"fixture-{index}-{record.get('agent', 'step')}.md"
            content = str(record.get("prose_excerpt") or "fixture receipt\n")
            prose_path = path / filename
            prose_path.write_text(content, encoding="utf-8")
            record["prose_file"] = str(prose_path)
            record["sha256"] = ledger.sha256_text(content)
        normalized_events.append(record)
    if implicit_steps and not any(
        event.get("event") in {"run_started", "run_finished"}
        for event in normalized_events
    ):
        normalized_events.insert(0, {"event": "run_started", "ts": "1970-01-01T00:00:00Z"})
        normalized_events.append({"event": "run_finished", "ts": "2999-01-01T00:00:00Z"})
    _write_jsonl(path / "ledger.jsonl", normalized_events)
    return path
