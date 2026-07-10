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


@dataclass(frozen=True)
class ImplTask:
    path: str
    slug: str
    story: str
    task_index: str
    title: str

    def to_state(self, task_id: int) -> dict[str, Any]:
        return {
            "id": task_id,
            "path": self.path,
            "slug": self.slug,
            "title": self.title,
            "story": self.story,
            "task_index": self.task_index,
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
    )


def _validate_story_contiguity(tasks: Sequence[ImplTask]) -> None:
    story_indexes: dict[str, list[int]] = {}
    for index, task in enumerate(tasks):
        story_indexes.setdefault(task.story, []).append(index)

    violations: list[str] = []
    for story, indexes in story_indexes.items():
        if all(right == left + 1 for left, right in zip(indexes, indexes[1:])):
            continue
        crossing = " -> ".join(
            f"{task.path} (story={task.story})"
            for task in tasks[indexes[0] : indexes[-1] + 1]
        )
        violations.append(f"story={story}: {crossing}")

    if violations:
        details = "; ".join(violations)
        raise ValueError(
            "non-contiguous story group(s) after path sorting: "
            f"{details}; rename or relocate task paths so each story forms one "
            "contiguous block; the runner will not reorder tasks automatically"
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
    impl_tasks = [
        task_from_path(path, cwd=root)
        for path in discover_tasks(inputs, cwd=root)
    ]
    _validate_story_contiguity(impl_tasks)
    tasks = [task.to_state(idx) for idx, task in enumerate(impl_tasks, start=1)]
    story_ids = sorted({str(task["story"]) for task in tasks})
    resolved_scope = "story" if scope == "auto" and len(story_ids) == 1 else scope
    if resolved_scope == "auto":
        resolved_scope = "epic"
    if resolved_scope == "story" and len(story_ids) > 1:
        raise ValueError("scope=story requires tasks from exactly one story")
    return {
        "schema_version": 2,
        "kind": "dcness-story-run",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "scope": resolved_scope,
        "project_root": str(root),
        "tasks": tasks,
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
    tasks = existing.get("tasks")
    if isinstance(tasks, list) and tasks and all(
        task.get("status") == "completed" for task in tasks
    ):
        # Normalize schema-v1 states that were stranded at ready_for_review.
        # PR metadata never participates in the task-state lifetime.
        save_state(path, existing)
        return archive_completed_state(path)
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(
            f"state has no task records: {path}; inspect it or use --force"
        )
    incomplete = ", ".join(
        f"#{task.get('id', '?')}={task.get('status', 'unknown')}"
        for task in tasks
        if task.get("status") != "completed"
    )
    raise ValueError(
        f"state has incomplete task(s): {incomplete}; resume it or use --force"
    )


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["schema_version"] = 2
    for derived_key in ("status", "current_task", "stories"):
        state.pop(derived_key, None)
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


def _tasks_for_story(state: dict[str, Any], story: str) -> list[dict[str, Any]]:
    return [
        task
        for task in state.get("tasks", [])
        if str(task.get("story")) == story
    ]


def _story_summary(state: dict[str, Any], story: str) -> dict[str, Any]:
    tasks = _tasks_for_story(state, story)
    return {
        "story": story,
        "task_ids": [task.get("id") for task in tasks],
        "commits": [task.get("commit") for task in tasks],
    }


def _progress(state: dict[str, Any]) -> dict[str, int]:
    tasks = state.get("tasks", [])
    return {
        "completed": sum(task.get("status") == "completed" for task in tasks),
        "total": len(tasks),
    }


def _story_boundary_before(
    state: dict[str, Any],
    pending_index: int,
) -> str | None:
    tasks = state.get("tasks", [])
    if pending_index <= 0:
        return None
    previous_story = str(tasks[pending_index - 1].get("story"))
    next_story = str(tasks[pending_index].get("story"))
    if previous_story == next_story:
        return None
    story_tasks = _tasks_for_story(state, previous_story)
    if story_tasks and all(task.get("status") == "completed" for task in story_tasks):
        return previous_story
    return None


def next_task(state: dict[str, Any]) -> dict[str, Any] | None:
    action = next_action(state)
    if action.get("action") == "task":
        return action.get("task")
    return None


def next_action(state: dict[str, Any]) -> dict[str, Any]:
    tasks = state.get("tasks", [])

    for task in tasks:
        if task.get("status") in {"blocked", "error"}:
            return {"action": task["status"], "task": task, "progress": _progress(state)}

    for task in state.get("tasks", []):
        if task.get("status") == "running":
            return {"action": "task", "task": task, "progress": _progress(state)}

    for index, task in enumerate(tasks):
        if task.get("status") == "pending":
            boundary_story = _story_boundary_before(state, index)
            if boundary_story is not None:
                return {
                    "action": "story-pr",
                    "story": _story_summary(state, boundary_story),
                    "next_task": task,
                    "progress": _progress(state),
                }
            return {"action": "task", "task": task, "progress": _progress(state)}

    if tasks and all(task.get("status") == "completed" for task in tasks):
        final_story = str(tasks[-1].get("story"))
        return {
            "action": "done",
            "final_story": _story_summary(state, final_story),
            "progress": _progress(state),
        }

    return {"action": "error", "note": "invalid or empty task state", "progress": _progress(state)}


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
    if status == "completed" and not (commit or task.get("commit")):
        raise ValueError("mark completed requires --commit")
    if status in {"error", "blocked"} and not (note and note.strip()):
        raise ValueError(f"mark {status} requires --note")
    task["status"] = status
    if status == "running":
        task["attempts"] = int(task.get("attempts") or 0) + 1
    if commit is not None:
        task["commit"] = commit
    if provider is not None:
        task["provider"] = provider
    if note is not None:
        task["note"] = note
    state["updated_at"] = _now_iso()
    return task


def _print(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload is None:
        print("next: none")
    elif isinstance(payload, dict) and payload.get("tasks"):
        story_count = len({str(task.get("story")) for task in payload["tasks"]})
        print(
            f"{payload['scope']} story-run: "
            f"{len(payload['tasks'])} task(s), {story_count} story(s)"
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
            state = build_state(args.paths, cwd=cwd, scope=args.scope)
            prepare_init_state(state_path, force=args.force)
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
    except ValueError as exc:
        parser.exit(1, f"story-runner: {exc}\n")
        return 1
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
