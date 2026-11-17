"""로컬 lint-build-test 우회 차단.

비공개 저장소에서 `/init-dcness` 가 workflow 대신 `.dcness/lint-build-test.sh` 를
설치하면 git pre-push hook 이 push 직전에 lint·build·test 를 실행한다. git hook 은
`--no-verify`, hook 경로 변경, hook 파일 삭제로 건너뛸 수 있으므로, 그 스크립트가
있는 프로젝트에서는 file-guard 가 Claude 의 해당 명령을 실행 전에 막는다.

사람이 터미널에서 직접 실행하는 명령은 대상이 아니다. 명령 문자열 정적 검사라
`eval`, command substitution, 환경변수(`GIT_CONFIG_*`)로 만든 우회는 보지 못한다.
"""
from __future__ import annotations

import subprocess  # nosec B404
from pathlib import Path
from typing import Any, Optional

from harness.agent_boundary import (
    _GIT_VALUE_FLAGS,
    _command_basename,
    _nested_shell_payload,
    _peel_wrappers,
    _segment_tokens,
    _split_segments_quote_aware,
    _strip_heredocs,
    extract_bash_paths,
)
from harness.ci_workflows import LOCAL_SCRIPT

_FILE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
_HOOKS_PATH_KEY = "core.hookspath"
_CONFIG_READ_FLAGS = frozenset({"--get", "--get-all", "--get-regexp", "--list", "-l"})
_NO_VERIFY = "--no-verify"
# git 은 모호하지 않은 long option 약어를 받는다. `--no-ve` 까지는 `--no-verbose` 와 겹친다.
_NO_VERIFY_MIN = len("--no-veri")
_RECURSION_LIMIT = 3
_HINT = "로컬 lint-build-test 는 push 직전 검사를 대신하므로 건너뛸 수 없다. 실패 원인을 고친 뒤 push 한다."


def _project_root(cwd: Path) -> Optional[Path]:
    # 모든 도구 호출마다 실행되므로 git 프로세스 없이 `.git`(linked worktree 는 파일)을 찾는다.
    for candidate in (cwd.resolve(), *cwd.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _hooks_dirs(cwd: Path, root: Path) -> list[Path]:
    dirs = [(root / ".git" / "hooks").resolve()]
    proc = subprocess.run(  # nosec B603 B607
        ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-path", "hooks"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        dirs.append(Path(proc.stdout.strip()).resolve())
    return dirs


def _in_hooks_dir(path: str, cwd: Path, hooks_dirs: list[Path]) -> bool:
    target = Path(path).expanduser()
    target = (target if target.is_absolute() else cwd / target).resolve()
    return any(target == d or d in target.parents for d in hooks_dirs)


def _git_reason(toks: list[str]) -> Optional[str]:
    args = toks[1:]
    i = 0
    while i < len(args) and args[i].startswith("-"):
        flag, _, inline = args[i].partition("=")
        value = inline
        if flag in _GIT_VALUE_FLAGS and not inline and i + 1 < len(args):
            value = args[i + 1]
            i += 1
        if flag in ("-c", "--config-env") and value.lower().startswith(_HOOKS_PATH_KEY):
            return "git hook 경로 변경(core.hooksPath) 차단"
        i += 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub == "push" and any(
        len(a) >= _NO_VERIFY_MIN and _NO_VERIFY.startswith(a) for a in rest
    ):
        return "git push --no-verify 차단"
    if sub == "config" and any(a.lower() == _HOOKS_PATH_KEY for a in rest):
        if not any(a in _CONFIG_READ_FLAGS for a in rest):
            return "git hook 경로 설정(core.hooksPath) 변경 차단"
    return None


def _bash_reason(command: str, depth: int = 0) -> Optional[str]:
    if depth > _RECURSION_LIMIT:
        return None
    for segment in _split_segments_quote_aware(_strip_heredocs(command)):
        toks = _peel_wrappers(_segment_tokens(segment))
        if not toks:
            continue
        nested = _nested_shell_payload(toks)
        if nested:
            reason = _bash_reason(nested[1], depth + 1)
            if reason:
                return reason
            continue
        if _command_basename(toks[0]) == "git":
            reason = _git_reason(toks)
            if reason:
                return reason
    return None


def check_tool(tool_name: str, tool_input: dict[str, Any], *, cwd: Path) -> Optional[str]:
    """로컬 검사 우회 명령이면 차단 사유, 아니면 None."""
    if tool_name != "Bash" and tool_name not in _FILE_TOOLS:
        return None
    root = _project_root(cwd)
    if root is None or not (root / LOCAL_SCRIPT).is_file():
        return None
    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        reason = _bash_reason(command)
        if reason is None:
            hooks_dirs = _hooks_dirs(cwd, root)
            if any(_in_hooks_dir(p, cwd, hooks_dirs) for p in extract_bash_paths(command)):
                reason = "git hook 파일 수정·삭제 차단"
    else:
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        hooks_dirs = _hooks_dirs(cwd, root)
        reason = "git hook 파일 수정·삭제 차단" if path and _in_hooks_dir(path, cwd, hooks_dirs) else None
    return f"{reason} — {_HINT}" if reason else None
