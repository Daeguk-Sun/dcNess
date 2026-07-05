"""Project activation whitelist helpers for :mod:`harness.session_state`."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

def _parent_state_module():
    module = sys.modules.get("harness.session_state")
    if module is not None and hasattr(module, "atomic_write"):
        return module
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "atomic_write"):
        return main
    import harness.session_state as module

    return module


_DEFAULT_WHITELIST_PATH = (
    Path.home() / ".claude" / "plugins" / "data" / "dcness-dcness" / "projects.json"
)

def whitelist_path() -> Path:
    """Plugin-scoped whitelist 경로.

    기본: `~/.claude/plugins/data/dcness-dcness/projects.json` (CC 공식 plugin-state
    컨벤션 — plugin install 시 자동 생성, plugin 제거 시 자동 정리).
    `DCNESS_WHITELIST_PATH` env 로 override (테스트 / 도그푸딩).
    """
    override = os.environ.get("DCNESS_WHITELIST_PATH")
    if override:
        return Path(override)
    return _DEFAULT_WHITELIST_PATH


def _load_whitelist() -> list:
    """projects.json 의 `projects` 배열 → resolved real path 리스트."""
    path = whitelist_path()
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("projects", [])
    if not isinstance(raw, list):
        return []
    out = []
    for p in raw:
        if not isinstance(p, str):
            continue
        try:
            out.append(str(Path(p).expanduser().resolve()))
        except (OSError, ValueError):
            continue
    return out


def _save_whitelist(paths: list) -> None:
    """projects.json atomic 작성. 중복 제거 + 정렬."""
    deduped = sorted(set(str(p) for p in paths))
    payload = json.dumps(
        {"version": 1, "projects": deduped},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    target = whitelist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    _parent_state_module().atomic_write(target, payload.encode("utf-8"))


def _resolve_project_root(cwd: Optional[Path] = None) -> Path:
    """cwd 의 main repo root (γ resolution).

    `_resolve_state_root_for_cwd` 가 `<main_root>/.claude/harness-state` 반환 →
    parent.parent = main_root. git 미사용 환경 폴백 시 cwd 자체 반환.
    """
    cwd_str = str((cwd or Path.cwd()).resolve())
    base = _parent_state_module()._resolve_state_root_for_cwd(cwd_str)
    return base.parent.parent


def is_project_active(cwd: Optional[Path] = None) -> bool:
    """현재 cwd (또는 인자) 가 dcNess whitelist 에 등록됐는지 판정.

    - 기본 disabled — whitelist 없거나 cwd 가 목록 밖이면 False
    - whitelist 경로의 서브디렉토리 (worktree 포함) 도 True (γ resolution 으로 main repo 추출)
    - `DCNESS_FORCE_ENABLE=1` env 로 임시 활성 (디버깅)
    """
    if os.environ.get("DCNESS_FORCE_ENABLE") == "1":
        return True
    try:
        project_root = _resolve_project_root(cwd).resolve()
    except OSError:
        return False
    project_root_str = str(project_root)
    for entry in _load_whitelist():
        if project_root_str == entry or project_root_str.startswith(entry + os.sep):
            return True
    return False


def enable_project(cwd: Optional[Path] = None) -> Path:
    """cwd 의 main repo root 를 whitelist 에 추가. 이미 있으면 noop."""
    project_root = _resolve_project_root(cwd).resolve()
    project_root_str = str(project_root)
    paths = _load_whitelist()
    if project_root_str not in paths:
        paths.append(project_root_str)
        _save_whitelist(paths)
    return project_root


def disable_project(cwd: Optional[Path] = None) -> Path:
    """cwd 의 main repo root 를 whitelist 에서 제거. 없으면 noop."""
    project_root = _resolve_project_root(cwd).resolve()
    project_root_str = str(project_root)
    paths = _load_whitelist()
    if project_root_str in paths:
        paths = [p for p in paths if p != project_root_str]
        _save_whitelist(paths)
    return project_root


def list_active_projects() -> list:
    """현재 whitelist 의 projects 배열 (resolved path 들)."""
    return _load_whitelist()
