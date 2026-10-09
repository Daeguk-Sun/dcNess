"""PR 생성·수정 명령 직전의 로컬 PR 본문·제목 검사.

git 에는 "PR 생성 직전" hook 이 없다. 그래서 PR 본문 오류는 CI 가 처음 발견했다.
이 모듈은 메인 Claude 가 실행하려는 명령에서 PR 본문과 제목을 꺼내 CI 와 같은
스크립트로 판정한다. CI workflow 를 설치하지 않은 프로젝트에서도 동작한다.

판정 진본:
    scripts/check_pr_body.mjs      — PR 본문 issue 트레일러
    scripts/check_git_naming.mjs   — PR 제목 형식

대상 명령:
    Bash  `gh pr create`, `gh pr edit` (본문·제목 인자가 있을 때)
    MCP   `mcp__github__create_pull_request`, `mcp__github__update_pull_request`

본문을 명령에서 확정할 수 없으면(`--fill`, 쉘 변수, stdin 등) 차단하고
`--body-file <파일>` 사용을 안내한다. 검사하지 못한 본문으로 PR 을 만들면
이 검사의 목적이 사라지기 때문이다. `--web` 과 `--help` 는 통과시킨다.

한계 (실수 방지용 검사이며 보안 경계가 아니다):
    `bash -c "gh pr create ..."`, `eval`, 다른 스크립트 안의 `gh` 호출은 보지 못한다.
    `scripts/pr-create.sh` 는 스크립트 안에서 같은 판정 스크립트를 직접 실행한다.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from harness.agent_boundary import (
    _GH_VALUE_FLAGS,
    _command_basename,
    _peel_wrappers,
    _strip_heredocs,
    extract_bash_paths,
)

__all__ = ["check_bash_command", "check_mcp_tool"]

FailOpen = Callable[[str, str], None]

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_NODE_TIMEOUT_SECONDS = 10

# `"$(cat <<'EOF' … EOF)"` — 본문 안 따옴표가 토큰 분해를 깨지 않도록 먼저 자리표시자로 바꾼다.
_BODY_HEREDOC_RE = re.compile(
    r"\$\(\s*cat\s*<<-?\s*(['\"]?)([A-Za-z_]\w*)\1[ \t]*\n"
    r"(?P<body>.*?)\n?^[ \t]*\2[ \t]*\n?\s*\)",
    re.DOTALL | re.MULTILINE,
)
_PLACEHOLDER_RE = re.compile(r"__DCNESS_PR_BODY_(\d+)__")
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# 따옴표 없는 heredoc 구분자(`<<EOF`)는 본문 안의 이 문자들을 쉘이 확장한다.
_HEREDOC_EXPANSION_RE = re.compile(r"[$`\\]")
_CHDIR_COMMANDS = frozenset({"cd", "pushd", "popd"})
# `$'…'` (ANSI-C 인용) 안에서 값이 고정된 이스케이프. 그 밖의 이스케이프는 확정 불가로 본다.
_ANSI_C_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "?": "?",
}
# gh 가 boolean 옵션의 `--flag=<값>` 에서 거짓으로 읽는 값.
_FALSE_VALUES = frozenset({"0", "f", "false"})

_BODY_FLAGS = {"-b": "body", "--body": "body", "-F": "body_file", "--body-file": "body_file"}
_TITLE_FLAGS = {"-t": "title", "--title": "title"}
_FILL_FLAGS = frozenset({"-f", "--fill", "--fill-first", "--fill-verbose"})
_PASS_FLAGS = frozenset({"-w", "--web", "-h", "--help"})
# 값을 받는 나머지 옵션 — 값 토큰을 옵션으로 오인하지 않도록 함께 건너뛴다.
_OTHER_VALUE_FLAGS = frozenset({
    "-a", "--assignee", "-B", "--base", "-H", "--head", "-l", "--label",
    "-m", "--milestone", "-p", "--project", "--recover", "-r", "--reviewer",
    "-T", "--template", "-R", "--repo",
    "--add-assignee", "--add-label", "--add-project", "--add-reviewer",
    "--remove-assignee", "--remove-label", "--remove-project", "--remove-reviewer",
})
_SHORT_VALUE_FLAGS = frozenset(
    flag[1] for flag in (*_BODY_FLAGS, *_TITLE_FLAGS, *_OTHER_VALUE_FLAGS)
    if len(flag) == 2
)

_MCP_PR_TOOLS = {
    "create_pull_request": True,   # 본문 필수
    "update_pull_request": False,  # 준 필드만 검사
}

_BODY_FILE_GUIDE = (
    "PR 본문을 파일에 먼저 쓰고, 다음 명령에서 "
    "`gh pr create --title \"<제목>\" --body-file <파일>` 을 실행하십시오.\n"
    "  본문에는 다음 중 하나가 있어야 합니다:\n"
    "    Closes #N                              (이 PR 이 issue 를 닫는다)\n"
    "    Part of #N                             (issue 의 중간 단계다)\n"
    "    Document-Exception-PR-Close: <사유>    (issue 가 없는 PR 이다)"
)


@dataclass(frozen=True)
class _Word:
    text: str
    dynamic: bool = False  # 쉘 확장($VAR, $(...), backtick)이 있어 값을 확정할 수 없다


def _consume_substitution(command: str, start: int) -> int:
    """`$(` 다음 위치에서 시작해 짝이 맞는 `)` 다음 위치를 돌려준다."""
    depth = 1
    quote = ""
    i = start
    while i < len(command) and depth:
        c = command[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = ""
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return i


def _lex(command: str) -> list[list[_Word]]:
    """명령을 segment 별 단어 목록으로 나눈다. 따옴표와 역슬래시 이스케이프를 해석한다."""
    segments: list[list[_Word]] = [[]]
    buf: list[str] = []
    dynamic = False
    in_word = False

    def end_word() -> None:
        nonlocal buf, dynamic, in_word
        if in_word:
            segments[-1].append(_Word("".join(buf), dynamic))
        buf, dynamic, in_word = [], False, False

    def expansion(i: int) -> int:
        nonlocal dynamic
        dynamic = True
        if command[i] == "`":
            end = command.find("`", i + 1)
            return len(command) if end < 0 else end + 1
        if command[i + 1:i + 2] == "(":
            return _consume_substitution(command, i + 2)
        return i + 1

    def ansi_c(i: int) -> int:
        """`$'` 다음 위치에서 닫는 `'` 다음 위치까지 읽는다."""
        nonlocal dynamic
        while i < n and command[i] != "'":
            if command[i] == "\\":
                decoded = _ANSI_C_ESCAPES.get(command[i + 1:i + 2])
                if decoded is None:
                    dynamic = True
                else:
                    buf.append(decoded)
                i += 2
            else:
                buf.append(command[i])
                i += 1
        return i + 1

    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c == "$" and command[i + 1:i + 2] == "'":
            in_word = True
            i = ansi_c(i + 2)
        elif c == "\\":
            if command[i + 1:i + 2] != "\n":
                buf.append(command[i + 1:i + 2])
                in_word = True
            i += 2
        elif c == "'":
            end = command.find("'", i + 1)
            end = n if end < 0 else end
            buf.append(command[i + 1:end])
            in_word = True
            i = end + 1
        elif c == '"':
            in_word = True
            i += 1
            while i < n and command[i] != '"':
                d = command[i]
                if d == "\\" and command[i + 1:i + 2] in ('"', "$", "`", "\\", "\n"):
                    if command[i + 1] != "\n":
                        buf.append(command[i + 1])
                    i += 2
                elif d in "$`":
                    i = expansion(i)
                else:
                    buf.append(d)
                    i += 1
            i += 1
        elif c in "$`":
            in_word = True
            i = expansion(i)
        elif c == "#" and not in_word:
            end = command.find("\n", i)
            i = n if end < 0 else end
        elif c in ";|&()\n":
            end_word()
            if segments[-1]:
                segments.append([])
            i += 1
        elif c.isspace():
            end_word()
            i += 1
        else:
            buf.append(c)
            in_word = True
            i += 1
    end_word()
    return [segment for segment in segments if segment]


def _command_words(words: list[_Word]) -> list[_Word]:
    """선행 `KEY=VAL` 과 명령 래퍼(`sudo`, `env` 등)를 벗긴 실제 명령 단어들."""
    texts = [word.text for word in words]
    start = 0
    while start < len(texts) and _ENV_ASSIGN_RE.match(texts[start]) and not words[start].dynamic:
        start += 1
    peeled = _peel_wrappers(texts[start:])
    return words[len(words) - len(peeled):]


def _gh_pr_args(words: list[_Word]) -> Optional[tuple[str, list[_Word]]]:
    """명령 단어들이 `gh pr create|edit` 이면 (verb, verb 뒤 단어들) 을 돌려준다."""
    if not words or _command_basename(words[0].text) != "gh":
        return None
    positionals: list[str] = []
    i = 1
    while i < len(words):
        text = words[i].text
        if text.startswith("-"):
            # `-R"$REPO"` 는 값이 붙은 한 단어다(쉘 확장 표시가 있다). `-R o/r` 만 다음 단어를 값으로 쓴다.
            i += 2 if text in _GH_VALUE_FLAGS and not words[i].dynamic else 1
            continue
        positionals.append(text)
        i += 1
        if len(positionals) == 2:
            break
    if positionals[:1] != ["pr"] or positionals[1:] not in (["create"], ["edit"]):
        return None
    return positionals[1], words[i:]


def _parse_flags(args: list[_Word]) -> dict[str, Any]:
    """`gh pr create|edit` 인자에서 본문·제목 출처와 통과·채움 옵션을 뽑는다."""
    found: dict[str, Any] = {}
    i = 0
    while i < len(args):
        word = args[i]
        text = word.text
        i += 1
        if text == "--" and not word.dynamic:
            break  # 옵션 종료 표시 — 뒤는 옵션이 아니다
        if not text.startswith("-") or text == "-":
            continue
        if text.startswith("--"):
            name, sep, inline = text.partition("=")
            values: list[tuple[str, Optional[_Word]]] = [
                (name, _Word(inline, word.dynamic) if sep else None)
            ]
        else:
            # 묶인 짧은 옵션(`-dw`)과 붙여 쓴 값(`-bTEXT`)을 푼다.
            values = []
            for pos, letter in enumerate(text[1:], start=1):
                rest = text[pos + 1:].removeprefix("=")
                if letter in _SHORT_VALUE_FLAGS:
                    values.append((f"-{letter}", _Word(rest, word.dynamic) if rest else None))
                    break
                values.append((f"-{letter}", None))
        for name, value in values:
            key = _BODY_FLAGS.get(name) or _TITLE_FLAGS.get(name)
            takes_value = key is not None or name in _OTHER_VALUE_FLAGS
            if takes_value and value is None and i < len(args):
                value = args[i]
                i += 1
            if key and value is not None:
                found[key] = value
                if key in ("body", "body_file"):
                    found["body_source"] = key
            elif value is not None and (
                value.dynamic or value.text.lower() in _FALSE_VALUES
            ):
                continue  # `--web=false` 처럼 꺼졌거나 값을 확정할 수 없는 boolean 옵션
            elif name in _FILL_FLAGS:
                found["fill"] = True
            elif name in _PASS_FLAGS:
                found["pass"] = True
    return found


def _checker_unavailable(on_fail_open: Optional[FailOpen]) -> bool:
    """판정 수단이 없으면 fail-open event 를 남기고 True — 호출자는 어떤 사유로도 차단하지 않는다."""
    if shutil.which("node"):
        return False
    if on_fail_open is not None:
        on_fail_open("pr_precheck_node_missing", "node 실행 파일 없음 — PR 사전 검사를 건너뜀")
    return True


def _run_checker(
    script: str,
    args: list[str],
    stdin: Optional[str],
    fail_marker: str,
    on_fail_open: Optional[FailOpen],
) -> Optional[str]:
    """판정 스크립트를 실행한다. 통과·판정 불가 = None, 위반 = 스크립트의 stderr.

    node 는 스크립트를 찾지 못하거나 읽지 못해도 exit 1 로 끝난다. 그래서 exit 1 이면서
    스크립트가 직접 쓴 위반 표시(`fail_marker`)가 있을 때만 위반으로 본다.
    """

    def fail_open(category: str, detail: str) -> None:
        if on_fail_open is not None:
            on_fail_open(category, detail)

    node = shutil.which("node")
    if not node:
        return None  # 진입 지점의 _checker_unavailable 이 이미 기록했다
    try:
        proc = subprocess.run(  # nosec B603
            [node, str(_SCRIPTS_DIR / script), *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=_NODE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        fail_open("pr_precheck_checker_error", f"{script}: {type(exc).__name__}: {exc}")
        return None
    if proc.returncode == 0:
        return None
    if proc.returncode == 1 and fail_marker in proc.stderr:
        return proc.stderr.strip()
    fail_open("pr_precheck_checker_error", f"{script} exited {proc.returncode} without a verdict")
    return None


def _check_body(body: str, on_fail_open: Optional[FailOpen]) -> Optional[str]:
    reason = _run_checker(
        "check_pr_body.mjs", ["--stdin"], body, "[pr-body] FAIL", on_fail_open
    )
    if reason is None:
        return None
    return f"PR 본문 검사 실패 — PR 을 만들거나 본문을 바꾸지 않았습니다.\n{reason}"


def _check_title(title: str, on_fail_open: Optional[FailOpen]) -> Optional[str]:
    reason = _run_checker(
        "check_git_naming.mjs", ["--title", title], None, "[git-naming] FAIL", on_fail_open
    )
    if reason is None:
        return None
    return f"PR 제목 검사 실패 — PR 을 만들거나 제목을 바꾸지 않았습니다.\n{reason}"


def _unknown_body(why: str) -> str:
    return f"PR 본문을 명령에서 확정할 수 없어 검사하지 못했습니다 ({why}).\n  {_BODY_FILE_GUIDE}"


def _read_body_file(
    raw: str, command: str, cwd: Path, cwd_changed: bool
) -> tuple[Optional[str], Optional[str]]:
    """(본문, 차단 사유). 둘 중 하나만 값이 있다."""
    if raw == "-":
        return None, _unknown_body("본문을 stdin 으로 넘김")
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute() and cwd_changed:
        return None, (
            f"PR 본문 파일 `{raw}` 이 상대경로인데 같은 명령이 작업 디렉터리를 바꿔 "
            "어느 파일인지 확정할 수 없습니다.\n"
            "  본문 파일을 절대경로로 지정하십시오."
        )
    if not path.is_absolute():
        path = cwd / path
    path = Path(os.path.normpath(path))

    def same(target: str) -> bool:
        other = Path(os.path.expanduser(target))
        if not other.is_absolute():
            other = cwd / other
        return Path(os.path.normpath(other)) == path

    if any(same(target) for target in extract_bash_paths(command)):
        return None, (
            f"PR 본문 파일 `{raw}` 을 같은 명령에서 쓰고 있어 검사할 내용이 아직 없습니다.\n"
            "  본문 파일을 쓰는 명령과 `gh pr create` 명령을 따로 실행하십시오."
        )
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError):
        return None, (
            f"PR 본문 파일 `{raw}` 을 읽을 수 없습니다.\n"
            "  파일을 먼저 만들고, 현재 디렉터리 기준 경로나 절대경로로 지정하십시오."
        )


def _check_gh_pr(
    verb: str,
    args: list[_Word],
    command: str,
    cwd: Path,
    cwd_changed: bool,
    on_fail_open: Optional[FailOpen],
) -> Optional[str]:
    flags = _parse_flags(args)
    if flags.get("pass"):
        return None
    source = flags.get("body_source")
    if source is None:
        if verb == "create":
            why = "commit 메시지로 본문을 채움" if flags.get("fill") else "본문 인자 없음"
            return _unknown_body(why)
    else:
        word: _Word = flags[source]
        if word.dynamic:
            return _unknown_body("본문 인자에 쉘 변수나 명령 치환이 있음")
        if source == "body_file":
            body, reason = _read_body_file(word.text, command, cwd, cwd_changed)
            if reason:
                return reason
        else:
            body = word.text
        reason = _check_body(body or "", on_fail_open)
        if reason:
            return reason
    title: Optional[_Word] = flags.get("title")
    if title is not None and not title.dynamic:
        return _check_title(title.text, on_fail_open)
    return None


def check_bash_command(
    command: str,
    *,
    cwd: Optional[Path] = None,
    on_fail_open: Optional[FailOpen] = None,
) -> Optional[str]:
    """Bash 명령 안의 `gh pr create|edit` 본문·제목 검사 — 차단 사유 / None=통과."""
    if not command or "gh" not in command or "pr" not in command:
        return None
    cwd = cwd if cwd is not None else Path.cwd()
    bodies: list[tuple[str, bool]] = []

    def stash(match: re.Match[str]) -> str:
        body = match.group("body")
        expands = not match.group(1) and bool(_HEREDOC_EXPANSION_RE.search(body))
        bodies.append((body, expands))
        return f"__DCNESS_PR_BODY_{len(bodies) - 1}__"

    stripped = _strip_heredocs(_BODY_HEREDOC_RE.sub(stash, command))

    def restore(word: _Word) -> _Word:
        used = [bodies[int(m.group(1))] for m in _PLACEHOLDER_RE.finditer(word.text)]
        text = _PLACEHOLDER_RE.sub(lambda m: bodies[int(m.group(1))][0], word.text)
        return _Word(text, word.dynamic or any(expands for _, expands in used))

    cwd_changed = False
    for segment in _lex(stripped):
        words = _command_words(segment)
        if words and words[0].text in _CHDIR_COMMANDS:
            cwd_changed = True
            continue
        target = _gh_pr_args(words)
        if target is None:
            continue
        if _checker_unavailable(on_fail_open):
            return None
        verb, args = target
        reason = _check_gh_pr(
            verb, [restore(word) for word in args], command, cwd, cwd_changed, on_fail_open
        )
        if reason:
            return reason
    return None


def check_mcp_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    on_fail_open: Optional[FailOpen] = None,
) -> Optional[str]:
    """GitHub MCP 의 PR 생성·수정 도구 본문·제목 검사 — 차단 사유 / None=통과."""
    prefix = "mcp__github__"
    if not tool_name.startswith(prefix):
        return None
    body_required = _MCP_PR_TOOLS.get(tool_name[len(prefix):])
    if body_required is None or _checker_unavailable(on_fail_open):
        return None
    body = tool_input.get("body")
    if body_required or body is not None:
        reason = _check_body(str(body or ""), on_fail_open)
        if reason:
            return reason
    title = tool_input.get("title")
    if isinstance(title, str) and title:
        return _check_title(title, on_fail_open)
    return None
