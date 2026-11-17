"""로컬 전용 하네스 파일을 linked worktree 에 연결한다.

하네스 파일을 커밋하지 않고 `.git/info/exclude` 등으로 로컬 전용으로 두는 프로젝트는
새 linked worktree 에 그 파일이 체크아웃되지 않는다. 그러면 worktree 세션에서 생성형
TDD guard hook 이 "파일 없음" 으로 실패하고 계약·경계 검사가 빠진다.

이 모듈은 main worktree 의 원본 파일을 worktree 의 같은 경로에 심볼릭 링크로 건다.
원본이 하나라 worktree 끼리 내용이 갈라지지 않는다. 프로젝트 설정
(`.dcness/worktree-files.json`)으로 링크·복사 대상을 추가할 수 있다.

연결 조건 (하나라도 어기면 건너뜀):
- 원본이 main worktree 에 있음
- 원본이 git 에 커밋되지 않음 (커밋된 파일은 checkout 이 이미 제공)
- worktree 의 같은 경로에 실제 파일이 없음 (있으면 보존)
- worktree 에서 그 경로가 git 무시 대상임 (아니면 미추적 파일로 나타나 커밋될 수 있음)

`.dcness-work/` 같은 branch 별 실행 상태는 대상이 아니다.

호출 지점: git post-checkout hook(`git worktree add`), PostToolUse EnterWorktree hook,
worktree 에서 시작한 세션의 SessionStart hook, `dcness-helper worktree-files sync`.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

CONFIG_REL = ".dcness/worktree-files.json"
DEFAULT_LINKS: tuple[str, ...] = (
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/settings.json",
    ".claude/hooks/dcness-tdd-guard.sh",
    ".codex/hooks.json",
    ".codex/hooks/dcness-tdd-guard.sh",
    ".dcness/tdd-hooks.json",
    ".dcness/boundary.json",
    "docs/index.md",
)


@dataclass
class SyncResult:
    worktree: Path
    linked_worktree: bool = False
    linked: list[str] = field(default_factory=list)
    copied: list[str] = field(default_factory=list)
    preserved: list[str] = field(default_factory=list)
    not_ignored: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=10,
    )


def _toplevel(path: Path) -> Optional[Path]:
    proc = _git(path, "rev-parse", "--show-toplevel")
    return Path(proc.stdout.strip()).resolve() if proc.returncode == 0 else None


def main_worktree(worktree: Path) -> Optional[Path]:
    """linked worktree 이면 main worktree 경로, 아니면 None."""
    git_dir = _git(worktree, "rev-parse", "--path-format=absolute", "--git-dir")
    common = _git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if git_dir.returncode != 0 or common.returncode != 0:
        return None
    git_path = Path(git_dir.stdout.strip()).resolve()
    common_path = Path(common.stdout.strip()).resolve()
    if git_path == common_path or common_path.name != ".git":
        return None
    return common_path.parent


def _entries(main: Path) -> list[tuple[str, str]]:
    entries = [(rel, "link") for rel in DEFAULT_LINKS]
    config_path = main / CONFIG_REL
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for mode in ("link", "copy"):
            values = data.get(mode) if isinstance(data, dict) else None
            for rel in values if isinstance(values, list) else []:
                if isinstance(rel, str) and rel and not Path(rel).is_absolute() and ".." not in Path(rel).parts:
                    entries.append((rel, mode))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for rel, mode in entries:
        if rel not in seen:
            seen.add(rel)
            unique.append((rel, mode))
    return unique


def _is_tracked(main: Path, rel: str) -> bool:
    return _git(main, "ls-files", "--error-unmatch", "--", rel).returncode == 0


def _is_ignored(worktree: Path, rel: str) -> bool:
    return _git(worktree, "check-ignore", "-q", "--no-index", "--", rel).returncode == 0


def _plan(worktree: Path, *, apply: bool) -> SyncResult:
    top = _toplevel(worktree) or worktree.resolve()
    result = SyncResult(worktree=top)
    main = main_worktree(top)
    if main is None:
        return result
    result.linked_worktree = True
    for rel, mode in _entries(main):
        src = main / rel
        if not src.is_file() or _is_tracked(main, rel):
            continue
        dst = top / rel
        if dst.is_symlink() and dst.resolve() == src.resolve():
            continue
        if dst.exists() or dst.is_symlink():
            if mode == "copy" and dst.is_file() and not dst.is_symlink():
                continue
            result.preserved.append(rel)
            continue
        if not _is_ignored(top, rel):
            result.not_ignored.append(rel)
            continue
        if not apply:
            result.missing.append(rel)
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if mode == "copy":
                shutil.copy2(src, dst)
                result.copied.append(rel)
            else:
                os.symlink(src, dst)
                result.linked.append(rel)
        except OSError as exc:
            result.errors.append(f"{rel}: {exc}")
    return result


def sync(worktree: Path) -> SyncResult:
    """linked worktree 에 빠진 로컬 전용 하네스 파일을 연결한다. main worktree 는 no-op."""
    return _plan(worktree, apply=True)


def inspect(worktree: Path) -> SyncResult:
    """sync 가 무엇을 할지 보고만 한다 (파일을 바꾸지 않음)."""
    return _plan(worktree, apply=False)


def local_only_files(main: Path) -> list[str]:
    """main worktree 에 있고 커밋되지 않은 연결 대상 파일 (linked worktree 에 체크아웃되지 않음)."""
    return [
        rel for rel, _ in _entries(main)
        if (main / rel).is_file() and not _is_tracked(main, rel)
    ]


def linked_from_main(worktree: Path, rel: str) -> bool:
    """worktree 의 rel 이 main worktree 의 커밋되지 않은 같은 파일로 연결돼 있는지."""
    main = main_worktree(worktree)
    if main is None:
        return False
    dst, src = worktree / rel, main / rel
    return dst.is_symlink() and src.is_file() and dst.resolve() == src.resolve() and not _is_tracked(main, rel)


def linked_worktrees(project: Path) -> list[Path]:
    proc = _git(project, "worktree", "list", "--porcelain")
    if proc.returncode != 0:
        return []
    paths = [
        Path(line.split(" ", 1)[1]).resolve()
        for line in proc.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    return [p for p in paths[1:] if p.is_dir()]


def sync_all(project: Path) -> list[SyncResult]:
    return [sync(path) for path in linked_worktrees(project)]


def _report(result: SyncResult) -> list[str]:
    lines = [f"[worktree-files] 링크: {rel}" for rel in result.linked]
    lines += [f"[worktree-files] 복사: {rel}" for rel in result.copied]
    lines += [
        f"[worktree-files] 건너뜀(커밋 제외 대상 아님 — 연결하면 미추적 파일이 됨): {rel}"
        for rel in result.not_ignored
    ]
    lines += [f"[worktree-files] 실패: {item}" for item in result.errors]
    return lines


def _worktree_from_hook_stdin() -> Optional[Path]:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    response = payload.get("tool_response")
    path = response.get("worktreePath") if isinstance(response, dict) else None
    path = path or payload.get("cwd")
    return Path(path) if isinstance(path, str) and path else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dcness-helper worktree-files")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sync = sub.add_parser("sync", help="linked worktree 에 로컬 전용 하네스 파일 연결")
    p_sync.add_argument("--worktree", default=None, help="대상 worktree (기본: 현재 디렉터리)")
    p_sync.add_argument("--all", action="store_true", help="이 저장소의 모든 linked worktree")
    p_sync.add_argument("--hook-stdin", action="store_true", help="Claude Code hook 입력에서 경로를 읽음")
    args = parser.parse_args(argv)

    if args.hook_stdin:
        target = _worktree_from_hook_stdin()
        if target is None:
            return 0
        results = [sync(target)]
    elif args.all:
        results = sync_all(Path(args.worktree or os.getcwd()))
    else:
        results = [sync(Path(args.worktree or os.getcwd()))]
    for result in results:
        for line in _report(result):
            print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
