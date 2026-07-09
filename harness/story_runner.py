"""Deterministic story/epic runner state for `/impl-loop`.

This module deliberately stops at planning and durable state transitions. The
actual provider execution remains owned by the existing implementation-chain
wrappers and the main driver.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


VALID_SCOPES = {"auto", "story", "epic"}
VALID_STATUSES = {"pending", "running", "completed", "error", "blocked"}
VALID_STORY_STATUSES = {"pending", "running", "ready_for_pr", "completed", "error", "blocked"}
VALID_STORY_MARK_STATUSES = {"completed", "error", "blocked"}
STOP_STORY_STATUSES = {"ready_for_pr", "error", "blocked"}


@dataclass(frozen=True)
class ImplTask:
    path: str
    slug: str
    story: str
    task_index: str
    risk: str
    engine: str
    risk_reason: str
    title: str

    def to_state(self, task_id: int) -> dict[str, Any]:
        return {
            "id": task_id,
            "path": self.path,
            "slug": self.slug,
            "title": self.title,
            "story": self.story,
            "task_index": self.task_index,
            "risk": self.risk,
            "engine": self.engine,
            "risk_reason": self.risk_reason,
            "status": "pending",
            "attempts": 0,
            "commit": None,
            "provider": None,
            "note": None,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    frontmatter: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            frontmatter[key] = value
    return frontmatter


def _sort_key(path: Path) -> tuple[Any, ...]:
    key: list[Any] = []
    for part in path.parts:
        prefix = part.split("-", 1)[0]
        if prefix.isdigit():
            key.append((0, int(prefix), part))
        else:
            key.append((1, part))
    return tuple(key)


def _relative_to_root(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root)
    except ValueError:
        return resolved


def _iter_path_matches(raw: str, *, cwd: Path) -> Iterable[Path]:
    candidate = Path(raw)
    path = candidate if candidate.is_absolute() else cwd / candidate
    if path.is_file():
        yield path
        return
    if path.is_dir():
        for child in path.rglob("*.md"):
            if child.parent.name == "impl" or "impl" in child.parts:
                yield child
        return
    for match in cwd.glob(raw):
        if match.is_file() and match.suffix == ".md":
            yield match
        elif match.is_dir():
            yield from _iter_path_matches(str(match), cwd=cwd)


def discover_tasks(inputs: Sequence[str], *, cwd: Path | None = None) -> list[Path]:
    root = (cwd or Path.cwd()).resolve()
    found: dict[str, Path] = {}
    for raw in inputs:
        for path in _iter_path_matches(raw, cwd=root):
            resolved = path.resolve()
            if resolved.suffix != ".md":
                continue
            found[str(resolved)] = resolved
    if not found:
        raise ValueError("no impl task files matched")
    return sorted(found.values(), key=lambda p: _sort_key(_relative_to_root(p, root)))


def task_from_path(path: Path, *, cwd: Path | None = None) -> ImplTask:
    root = (cwd or Path.cwd()).resolve()
    rel = _relative_to_root(path, root).as_posix()
    fm = parse_frontmatter(path)
    slug = path.stem
    title = fm.get("title") or slug.split("-", 1)[-1]
    return ImplTask(
        path=rel,
        slug=slug,
        title=title,
        story=fm.get("story") or "unknown",
        task_index=fm.get("task_index") or "",
        risk=fm.get("risk") or "",
        engine=fm.get("engine") or "",
        risk_reason=fm.get("risk_reason") or "",
    )


def build_state(
    inputs: Sequence[str],
    *,
    cwd: Path | None = None,
    scope: str = "auto",
) -> dict[str, Any]:
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid scope: {scope}")
    root = (cwd or Path.cwd()).resolve()
    tasks = [
        task_from_path(path, cwd=root).to_state(idx)
        for idx, path in enumerate(discover_tasks(inputs, cwd=root), start=1)
    ]
    story_ids = sorted({str(task["story"]) for task in tasks})
    resolved_scope = "story" if scope == "auto" and len(story_ids) == 1 else scope
    if resolved_scope == "auto":
        resolved_scope = "epic"
    if resolved_scope == "story" and len(story_ids) > 1:
        raise ValueError("scope=story requires tasks from exactly one story")
    stories = [
        {
            "story": story,
            "status": "pending",
            "task_ids": [task["id"] for task in tasks if str(task["story"]) == story],
            "pr": None,
        }
        for story in story_ids
    ]
    return {
        "schema_version": 1,
        "kind": "dcness-story-run",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "scope": resolved_scope,
        "status": "pending",
        "project_root": str(root),
        "current_task": None,
        "tasks": tasks,
        "stories": stories,
    }


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def archive_completed_state(path: Path) -> Path:
    stamp = _now_compact()
    for index in range(1, 1000):
        suffix = "" if index == 1 else f"-{index}"
        archive = path.with_name(f"{path.stem}.completed-{stamp}{suffix}{path.suffix}")
        if not archive.exists():
            os.replace(path, archive)
            return archive
    raise ValueError(f"could not allocate archive path for completed state: {path}")


def prepare_init_state(path: Path, *, force: bool) -> Path | None:
    if not path.exists() or force:
        return None
    try:
        existing = load_state(path)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"state exists but is not valid JSON: {path}; use --force to replace it"
        ) from exc
    except OSError as exc:
        raise ValueError(
            f"state exists but cannot be read: {path}; use --force to replace it"
        ) from exc
    if existing.get("status") == "completed":
        return archive_completed_state(path)
    status = existing.get("status") or "unknown"
    raise ValueError(
        f"state exists with status={status}: {path}; resume it or use --force"
    )


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now_iso()
    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def find_task(state: dict[str, Any], ref: str) -> dict[str, Any]:
    for task in state.get("tasks", []):
        if str(task.get("id")) == str(ref) or task.get("path") == ref or task.get("slug") == ref:
            return task
    raise ValueError(f"task not found: {ref}")


def find_story(state: dict[str, Any], ref: str) -> dict[str, Any]:
    for story in state.get("stories", []):
        if str(story.get("story")) == str(ref):
            return story
    raise ValueError(f"story not found: {ref}")


def _tasks_for_story(state: dict[str, Any], story: dict[str, Any]) -> list[dict[str, Any]]:
    task_by_id = {task.get("id"): task for task in state.get("tasks", [])}
    return [
        task_by_id[task_id]
        for task_id in story.get("task_ids", [])
        if task_id in task_by_id
    ]


def _first_story_with_status(
    state: dict[str, Any],
    statuses: set[str],
) -> dict[str, Any] | None:
    for story in state.get("stories", []):
        if story.get("status") in statuses:
            return story
    return None


def next_task(state: dict[str, Any]) -> dict[str, Any] | None:
    for task in state.get("tasks", []):
        if task.get("status") == "running":
            return task
    if _first_story_with_status(state, STOP_STORY_STATUSES) is not None:
        return None
    for task in state.get("tasks", []):
        if task.get("status") == "pending":
            return task
    return None


def next_action(state: dict[str, Any]) -> dict[str, Any]:
    state_status = state.get("status")
    for task in state.get("tasks", []):
        if task.get("status") == "running":
            return {"action": "task", "state_status": state_status, "task": task}

    for story in state.get("stories", []):
        status = story.get("status")
        if status == "ready_for_pr":
            return {"action": "story-pr", "state_status": state_status, "story": story}
        if status in {"blocked", "error"}:
            return {"action": status, "state_status": state_status, "story": story}

    for task in state.get("tasks", []):
        if task.get("status") == "pending":
            return {"action": "task", "state_status": state_status, "task": task}

    return {"action": "done", "state_status": state_status}


def _refresh_story_statuses(state: dict[str, Any]) -> None:
    task_by_id = {task.get("id"): task for task in state.get("tasks", [])}
    for story in state.get("stories", []):
        story_tasks = [
            task_by_id[task_id]
            for task_id in story.get("task_ids", [])
            if task_id in task_by_id
        ]
        if not story_tasks:
            continue
        statuses = {task.get("status") for task in story_tasks}
        if story.get("status") in {"completed", "blocked", "error"} and all(
            status == "completed" for status in statuses
        ):
            continue
        if "blocked" in statuses:
            story["status"] = "blocked"
        elif "error" in statuses:
            story["status"] = "error"
        elif all(status == "completed" for status in statuses):
            if story.get("status") != "completed":
                story["status"] = "ready_for_pr"
        elif "running" in statuses or "completed" in statuses:
            story["status"] = "running"
        else:
            story["status"] = "pending"

    story_statuses = {story.get("status") for story in state.get("stories", [])}
    if "blocked" in story_statuses:
        state["status"] = "blocked"
    elif "error" in story_statuses:
        state["status"] = "error"
    elif story_statuses and all(status == "completed" for status in story_statuses):
        state["status"] = "completed"
    elif "ready_for_pr" in story_statuses:
        state["status"] = "ready_for_pr"
    elif "running" in story_statuses:
        state["status"] = "running"
    else:
        state["status"] = "pending"


def mark_task(
    state: dict[str, Any],
    ref: str,
    status: str,
    *,
    commit: str | None = None,
    provider: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid task status: {status}")
    task = find_task(state, ref)
    task["status"] = status
    if status == "running":
        task["attempts"] = int(task.get("attempts") or 0) + 1
        state["current_task"] = task["id"]
        state["status"] = "running"
    elif status in {"completed", "error", "blocked"}:
        if state.get("current_task") == task.get("id"):
            state["current_task"] = None
        if status in {"error", "blocked"}:
            state["status"] = status
    if commit is not None:
        task["commit"] = commit
    if provider is not None:
        task["provider"] = provider
    if note is not None:
        task["note"] = note
    _refresh_story_statuses(state)
    state["updated_at"] = _now_iso()
    return task


def mark_story(
    state: dict[str, Any],
    ref: str,
    status: str,
    *,
    pr: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if status not in VALID_STORY_MARK_STATUSES:
        raise ValueError(f"invalid story status: {status}")
    story = find_story(state, ref)
    story_tasks = _tasks_for_story(state, story)
    if not story_tasks:
        raise ValueError(f"story has no tasks: {ref}")
    if not all(task.get("status") == "completed" for task in story_tasks):
        raise ValueError("mark-story requires all story tasks completed")
    if status == "completed" and not pr:
        raise ValueError("mark-story completed requires --pr")
    story["status"] = status
    if pr is not None:
        story["pr"] = pr
    if note is not None:
        story["note"] = note
    _refresh_story_statuses(state)
    state["updated_at"] = _now_iso()
    return story


def _print(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload is None:
        print("next: none")
    elif isinstance(payload, dict) and payload.get("tasks"):
        print(
            f"{payload['scope']} story-run: "
            f"{len(payload['tasks'])} task(s), {len(payload['stories'])} story PR(s)"
        )
        for task in payload["tasks"]:
            print(
                f"- #{task['id']} {task['path']} "
                f"story={task['story']} status={task['status']}"
            )
    else:
        print(json.dumps(payload, ensure_ascii=False))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="dcNess story/epic runner state helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("paths", nargs="+")
    p_plan.add_argument("--cwd", default="")
    p_plan.add_argument("--scope", choices=sorted(VALID_SCOPES), default="auto")
    p_plan.add_argument("--json", action="store_true")

    p_init = sub.add_parser("init")
    p_init.add_argument("paths", nargs="+")
    p_init.add_argument("--state", required=True)
    p_init.add_argument("--cwd", default="")
    p_init.add_argument("--scope", choices=sorted(VALID_SCOPES), default="auto")
    p_init.add_argument("--force", action="store_true")
    p_init.add_argument("--json", action="store_true")

    p_next = sub.add_parser("next")
    p_next.add_argument("--state", required=True)
    p_next.add_argument("--json", action="store_true")

    p_next_action = sub.add_parser("next-action")
    p_next_action.add_argument("--state", required=True)
    p_next_action.add_argument("--json", action="store_true")

    p_mark = sub.add_parser("mark")
    p_mark.add_argument("--state", required=True)
    p_mark.add_argument("--task", required=True)
    p_mark.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    p_mark.add_argument("--commit", default=None)
    p_mark.add_argument("--provider", default=None)
    p_mark.add_argument("--note", default=None)
    p_mark.add_argument("--json", action="store_true")

    p_mark_story = sub.add_parser("mark-story")
    p_mark_story.add_argument("--state", required=True)
    p_mark_story.add_argument("--story", required=True)
    p_mark_story.add_argument("--status", required=True, choices=sorted(VALID_STORY_MARK_STATUSES))
    p_mark_story.add_argument("--pr", default=None)
    p_mark_story.add_argument("--note", default=None)
    p_mark_story.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cwd = Path(args.cwd).resolve() if getattr(args, "cwd", "") else Path.cwd()
    try:
        if args.cmd == "plan":
            state = build_state(args.paths, cwd=cwd, scope=args.scope)
            _print(state, as_json=args.json)
            return 0
        if args.cmd == "init":
            state_path = Path(args.state)
            prepare_init_state(state_path, force=args.force)
            state = build_state(args.paths, cwd=cwd, scope=args.scope)
            save_state(state_path, state)
            _print(state, as_json=args.json)
            return 0
        if args.cmd == "next":
            state = load_state(Path(args.state))
            _print(next_task(state), as_json=args.json)
            return 0
        if args.cmd == "next-action":
            state = load_state(Path(args.state))
            _print(next_action(state), as_json=args.json)
            return 0
        if args.cmd == "mark":
            state_path = Path(args.state)
            state = load_state(state_path)
            task = mark_task(
                state,
                args.task,
                args.status,
                commit=args.commit,
                provider=args.provider,
                note=args.note,
            )
            save_state(state_path, state)
            _print(task, as_json=args.json)
            return 0
        if args.cmd == "mark-story":
            state_path = Path(args.state)
            state = load_state(state_path)
            story = mark_story(
                state,
                args.story,
                args.status,
                pr=args.pr,
                note=args.note,
            )
            save_state(state_path, state)
            _print(story, as_json=args.json)
            return 0
    except ValueError as exc:
        parser.exit(1, f"story-runner: {exc}\n")
        return 1
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
