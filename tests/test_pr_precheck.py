"""PR 생성·수정 명령 직전의 로컬 PR 본문·제목 검사 (harness/pr_precheck.py).

판정 진본은 scripts/check_pr_body.mjs 와 scripts/check_git_naming.mjs 다.
이 모듈은 명령에서 본문·제목을 꺼내 그 스크립트에 넘기는 부분만 검증한다.

node 미설치 환경에서는 판정 테스트를 skip 한다.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from harness import hooks, pr_precheck
from harness.hooks import handle_pretooluse_file_op, handle_session_start


ROOT = Path(__file__).resolve().parents[1]
BODY_SCRIPT = ROOT / "scripts" / "check_pr_body.mjs"
PR_CREATE = ROOT / "scripts" / "pr-create.sh"
NODE = shutil.which("node")

GOOD_TITLE = "[feature] 로컬 검사 추가"
NO_TRAILER = "## 변경 내용\n트레일러 없음\n"
PASSING_BODIES = (
    "## 작업내용\n수정\n\nCloses #12\n",
    "## 작업내용\n중간 단계\n\nPart of #12\n",
    "## 작업내용\n이슈 없는 변경\n\nDocument-Exception-PR-Close: 이슈 없음\n",
)
PARITY_SAMPLES = PASSING_BODIES + (
    NO_TRAILER,
    "## 관련 이슈\n- 없음\n",
    "fixes #7",
    "resolved #7 은 본문 중간에 있다",
    "Closes 12",
    "Document-Exception-PR-Close:\n",
    "Document-Exception-PR-Close: 통합 브랜치 story sub-PR — main 머지 시 일괄 close\n",
    "본문에 \"따옴표\" 와 'EOF' 가 있다\n\nPart of #3\n",
)


def _check(command: str, cwd: Path) -> str | None:
    return pr_precheck.check_bash_command(command, cwd=cwd)


def _heredoc_command(body: str, title: str = GOOD_TITLE) -> str:
    return (
        f"gh pr create --title \"{title}\" --body \"$(cat <<'EOF'\n"
        f"{body}\nEOF\n)\""
    )


@unittest.skipUnless(NODE, "node not installed — 판정 진본이 node 스크립트")
class BashCommandVerdictTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self.cwd = Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def _body_file(self, body: str, name: str = "body.md") -> Path:
        path = self.cwd / name
        path.write_text(body, encoding="utf-8")
        return path

    def test_missing_trailer_blocks_and_prints_allowed_formats(self) -> None:
        path = self._body_file(NO_TRAILER)
        commands = (
            f"gh pr create --title \"{GOOD_TITLE}\" --body-file {path}",
            f"gh pr create --title \"{GOOD_TITLE}\" --body \"변경 내용만 있다\"",
            _heredoc_command(NO_TRAILER),
        )
        for command in commands:
            with self.subTest(command=command):
                reason = _check(command, self.cwd)
                self.assertIsNotNone(reason)
                assert reason is not None
                self.assertIn("Closes #N", reason)
                self.assertIn("Part of #N", reason)
                self.assertIn("Document-Exception-PR-Close: <사유>", reason)

    def test_each_allowed_trailer_passes_in_every_body_form(self) -> None:
        for index, body in enumerate(PASSING_BODIES):
            path = self._body_file(body, f"body-{index}.md")
            one_line = body.strip().splitlines()[-1]
            commands = (
                f"gh pr create --title \"{GOOD_TITLE}\" --body-file {path}",
                f"gh pr create -t \"{GOOD_TITLE}\" -F body-{index}.md",
                f"gh pr create --title \"{GOOD_TITLE}\" --body \"{one_line}\"",
                f"gh pr create --title \"{GOOD_TITLE}\" --body='{one_line}'",
                _heredoc_command(body),
                f"git push -u origin work && gh -R o/r pr create -t \"{GOOD_TITLE}\" -b \"{one_line}\"",
            )
            for command in commands:
                with self.subTest(command=command):
                    self.assertIsNone(_check(command, self.cwd))

    def test_heredoc_body_with_quotes_is_read_in_full(self) -> None:
        body = "본문에 \"큰따옴표\" 와 '작은따옴표' 와 $(명령) 이 있다\n\nPart of #3"
        self.assertIsNone(_check(_heredoc_command(body), self.cwd))

    def test_escaped_quotes_do_not_truncate_inline_body(self) -> None:
        command = (
            f"gh pr create --title \"{GOOD_TITLE}\" "
            "--body \"그는 \\\"완료\\\" 라고 했다; 다음 줄\n\nCloses #5\""
        )
        self.assertIsNone(_check(command, self.cwd))

    def test_unknown_body_source_blocks_with_body_file_guidance(self) -> None:
        commands = (
            "gh pr create --fill",
            "gh pr create --fill-first",
            f"gh pr create --title \"{GOOD_TITLE}\"",
            f"gh pr create --title \"{GOOD_TITLE}\" --body \"$BODY\"",
            f"gh pr create --title \"{GOOD_TITLE}\" --body \"$(cat body.md)\"",
            f"gh pr create --title \"{GOOD_TITLE}\" --body-file -",
            f"gh pr create --title \"{GOOD_TITLE}\" --body-file \"$TMP/body.md\"",
            f"gh pr create --title \"{GOOD_TITLE}\" --template t.md",
        )
        for command in commands:
            with self.subTest(command=command):
                reason = _check(command, self.cwd)
                self.assertIsNotNone(reason)
                assert reason is not None
                self.assertIn("--body-file", reason)

    def test_body_file_missing_or_written_by_same_command_blocks(self) -> None:
        missing = f"gh pr create --title \"{GOOD_TITLE}\" --body-file nope.md"
        self.assertIn("nope.md", _check(missing, self.cwd) or "")

        stale = self._body_file(PASSING_BODIES[0], "stale.md")
        same_command = (
            f"cat > {stale} <<'EOF'\n{NO_TRAILER}EOF\n"
            f"gh pr create --title \"{GOOD_TITLE}\" --body-file {stale}"
        )
        reason = _check(same_command, self.cwd)
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("같은 명령", reason)

    def test_relative_body_file_after_directory_change_blocks(self) -> None:
        self._body_file(PASSING_BODIES[0], "body.md")
        sub = self.cwd / "sub"
        sub.mkdir()
        absolute = self._body_file(PASSING_BODIES[0], "abs.md")
        title = f"--title \"{GOOD_TITLE}\""
        for command in (
            f"cd sub && gh pr create {title} --body-file body.md",
            f"(cd sub; gh pr create {title} -F body.md)",
            f"pushd sub\ngh pr create {title} --body-file ./body.md",
        ):
            with self.subTest(command=command):
                reason = _check(command, self.cwd)
                self.assertIsNotNone(reason)
                assert reason is not None
                self.assertIn("절대경로", reason)
        self.assertIsNone(
            _check(f"cd sub && gh pr create {title} --body-file {absolute}", self.cwd)
        )
        self.assertIsNone(
            _check(f"gh pr create {title} --body-file body.md && cd sub", self.cwd)
        )

    def test_unquoted_heredoc_with_shell_expansion_is_unknown(self) -> None:
        title = f"--title \"{GOOD_TITLE}\""
        for body in ("완료 `Closes #123`", "$TRAILER", "Closes \\#5"):
            command = f"gh pr create {title} --body \"$(cat <<EOF\n{body}\nEOF\n)\""
            with self.subTest(body=body):
                reason = _check(command, self.cwd)
                self.assertIsNotNone(reason)
                assert reason is not None
                self.assertIn("--body-file", reason)
        plain = f"gh pr create {title} --body \"$(cat <<EOF\n변경\n\nCloses #5\nEOF\n)\""
        self.assertIsNone(_check(plain, self.cwd))

    def test_only_what_the_shell_and_gh_read_as_options_counts(self) -> None:
        title = f"--title \"{GOOD_TITLE}\""
        blocked = (
            f"gh pr create {title} --body missing # --help",
            f"gh pr create {title} --body missing # --body \"Closes #1\"",
            f"gh pr create {title} --body missing --web=false",
            f"gh pr create {title} --body missing --help=false",
            f"gh pr create {title} --body missing --web=\"$FLAG\"",
            f"gh pr create {title} --body missing -- --web",
            f"gh pr create {title} --body missing --label --help",
        )
        for command in blocked:
            with self.subTest(command=command):
                self.assertIsNotNone(_check(command, self.cwd))
        passing = (
            f"gh pr create {title} --body \"Closes #1\" # --body missing",
            f"gh pr create {title} --body \"Closes #1\"  # --fill 은 쓰지 않는다\nls",
            f"gh pr create {title} --body \"이슈#없음 Closes #1\"",
            f"gh pr create {title} --body missing --web=true",
            f"gh pr create {title} --body \"Closes #1\" --fill=false",
        )
        for command in passing:
            with self.subTest(command=command):
                self.assertIsNone(_check(command, self.cwd))

    def test_dynamic_repo_option_does_not_hide_the_pr_command(self) -> None:
        for repo in ('-R"$REPO"', '-R "$REPO"', '--repo="$REPO"', "--repo $REPO"):
            with self.subTest(repo=repo):
                bad = f"gh {repo} pr create --title \"{GOOD_TITLE}\" --body missing"
                good = f"gh {repo} pr create --title \"{GOOD_TITLE}\" --body \"Closes #1\""
                self.assertIsNotNone(_check(bad, self.cwd))
                self.assertIsNone(_check(good, self.cwd))

    def test_ansi_c_quoted_body_is_read_as_static_text(self) -> None:
        title = f"--title \"{GOOD_TITLE}\""
        self.assertIsNone(
            _check(f"gh pr create {title} --body $'요약\\n\\nCloses #12'", self.cwd)
        )
        self.assertIsNotNone(
            _check(f"gh pr create {title} --body $'요약\\n\\n트레일러 없음'", self.cwd)
        )
        unknown = _check(f"gh pr create {title} --body $'Closes \\x2312'", self.cwd)
        self.assertIn("--body-file", unknown or "")

    def test_commands_outside_scope_pass(self) -> None:
        commands = (
            "gh pr create --web",
            "gh pr create --help",
            "gh pr view 12",
            "gh pr list --state open",
            "gh pr merge 12 --merge",
            "gh issue create --title x --body y",
            "echo \"gh pr create --fill\"",
            "git commit -m \"gh pr create --fill 설명\"",
            "gh pr edit 12 --add-label bug",
            "ls",
            "",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(_check(command, self.cwd))

    def test_title_format_is_checked_when_literal(self) -> None:
        bad = "gh pr create --title \"로컬 검사 추가\" --body \"Closes #1\""
        reason = _check(bad, self.cwd)
        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("[feature]", reason)

        dynamic = "gh pr create --title \"$TITLE\" --body \"Closes #1\""
        self.assertIsNone(_check(dynamic, self.cwd))

    def test_pr_edit_checks_only_given_body_and_title(self) -> None:
        self.assertIsNotNone(_check("gh pr edit 12 --body \"본문만\"", self.cwd))
        self.assertIsNotNone(_check("gh pr edit --title \"형식 없음\"", self.cwd))
        self.assertIsNotNone(_check("gh pr edit 12 --body \"$BODY\"", self.cwd))
        self.assertIsNone(_check("gh pr edit 12 --body \"Part of #2\"", self.cwd))
        self.assertIsNone(
            _check(f"gh pr edit 12 --title \"{GOOD_TITLE}\"", self.cwd)
        )

    def test_local_verdict_equals_ci_script_verdict(self) -> None:
        for index, body in enumerate(PARITY_SAMPLES):
            with self.subTest(body=body):
                proc = subprocess.run(
                    [NODE, str(BODY_SCRIPT), "--stdin"],
                    input=body,
                    capture_output=True,
                    text=True,
                )
                script_pass = proc.returncode == 0
                path = self._body_file(body, f"sample-{index}.md")
                by_file = _check(
                    f"gh pr create --title \"{GOOD_TITLE}\" --body-file {path}",
                    self.cwd,
                )
                by_heredoc = _check(_heredoc_command(body), self.cwd)
                by_mcp = pr_precheck.check_mcp_tool(
                    "mcp__github__create_pull_request",
                    {"title": GOOD_TITLE, "body": body},
                )
                self.assertEqual(by_file is None, script_pass)
                self.assertEqual(by_heredoc is None, script_pass)
                self.assertEqual(by_mcp is None, script_pass)


@unittest.skipUnless(NODE, "node not installed — 판정 진본이 node 스크립트")
class McpToolVerdictTests(unittest.TestCase):
    def test_create_requires_trailer_and_title_format(self) -> None:
        tool = "mcp__github__create_pull_request"
        self.assertIsNone(
            pr_precheck.check_mcp_tool(tool, {"title": GOOD_TITLE, "body": "Closes #1"})
        )
        self.assertIsNotNone(
            pr_precheck.check_mcp_tool(tool, {"title": GOOD_TITLE, "body": NO_TRAILER})
        )
        self.assertIsNotNone(pr_precheck.check_mcp_tool(tool, {"title": GOOD_TITLE}))
        self.assertIsNotNone(
            pr_precheck.check_mcp_tool(tool, {"title": "형식 없음", "body": "Closes #1"})
        )

    def test_update_checks_only_given_fields_and_reads_pass(self) -> None:
        update = "mcp__github__update_pull_request"
        self.assertIsNone(pr_precheck.check_mcp_tool(update, {"state": "closed"}))
        self.assertIsNotNone(pr_precheck.check_mcp_tool(update, {"body": NO_TRAILER}))
        self.assertIsNone(
            pr_precheck.check_mcp_tool("mcp__github__get_pull_request", {"body": "x"})
        )
        self.assertIsNone(
            pr_precheck.check_mcp_tool("mcp__github__create_issue", {"body": "x"})
        )


class FailOpenTests(unittest.TestCase):
    def test_missing_node_allows_and_reports(self) -> None:
        seen: list[tuple[str, str]] = []
        record = lambda category, detail: seen.append((category, detail))  # noqa: E731
        commands = (
            "gh pr create --title x --body y",
            "gh pr create --fill",
            "gh pr create --title x --body \"$BODY\"",
            "gh pr create --title x --body-file nope.md",
            "cd sub && gh pr create --title x --body-file body.md",
        )
        with patch.object(pr_precheck.shutil, "which", return_value=None):
            for command in commands:
                with self.subTest(command=command):
                    seen.clear()
                    self.assertIsNone(
                        pr_precheck.check_bash_command(
                            command, cwd=Path.cwd(), on_fail_open=record
                        )
                    )
                    self.assertEqual(
                        [category for category, _ in seen], ["pr_precheck_node_missing"]
                    )
            seen.clear()
            self.assertIsNone(
                pr_precheck.check_mcp_tool(
                    "mcp__github__create_pull_request", {"title": "x"}, on_fail_open=record
                )
            )
            self.assertEqual([category for category, _ in seen], ["pr_precheck_node_missing"])
            seen.clear()
            self.assertIsNone(
                pr_precheck.check_bash_command("gh pr view 1", cwd=Path.cwd(), on_fail_open=record)
            )
            self.assertEqual(seen, [])

    @unittest.skipUnless(NODE, "node not installed")
    def test_checker_that_cannot_run_allows_and_reports(self) -> None:
        seen: list[tuple[str, str]] = []
        with TemporaryDirectory() as td, patch.object(pr_precheck, "_SCRIPTS_DIR", Path(td)):
            reason = pr_precheck.check_bash_command(
                "gh pr create --title x --body y",
                cwd=Path(td),
                on_fail_open=lambda category, detail: seen.append((category, detail)),
            )
        self.assertIsNone(reason)
        self.assertEqual({category for category, _ in seen}, {"pr_precheck_checker_error"})

    def test_init_dcness_workflow_pr_command_is_checkable(self) -> None:
        text = (ROOT / "commands" / "init-dcness.md").read_text(encoding="utf-8")
        commands = [line.strip() for line in text.splitlines() if "gh pr create --" in line]
        self.assertEqual(len(commands), 1)
        self.assertNotIn("$", commands[0])
        self.assertIn("--body-file /tmp/dcness-init-pr-body.md", commands[0])
        self.assertIn("Document-Exception-PR-Close: dcness init workflow bootstrap", text)


@unittest.skipUnless(NODE, "node not installed — 판정 진본이 node 스크립트")
class MainHookAdapterTests(unittest.TestCase):
    def _run(self, payload_tool: dict, *, opt_out: bool = False, infra: bool = False) -> int:
        with TemporaryDirectory() as td:
            base = Path(td)
            handle_session_start({"session_id": "sid-main"}, 12345, base_dir=base)
            payload = {"session_id": "sid-main", **payload_tool}
            with patch("harness.agent_boundary.is_infra_project", return_value=infra), \
                    patch("harness.agent_boundary.is_opt_out", return_value=opt_out), \
                    patch.object(hooks, "_record_guard_hit_safe") as hit:
                rc = handle_pretooluse_file_op(payload, 12345, base_dir=base)
            self._hits = hit.call_args_list
            return rc

    def test_main_bash_pr_create_is_blocked_then_recorded(self) -> None:
        bad = {
            "tool_name": "Bash",
            "tool_input": {"command": f"gh pr create --title \"{GOOD_TITLE}\" --body x"},
        }
        self.assertEqual(self._run(bad), 1)
        self.assertEqual(self._hits[0].args[:2], ("file-guard", "pr_precheck"))

        good = {
            "tool_name": "Bash",
            "tool_input": {
                "command": f"gh pr create --title \"{GOOD_TITLE}\" --body \"Closes #1\""
            },
        }
        self.assertEqual(self._run(good), 0)

    def test_main_mcp_pr_create_is_blocked(self) -> None:
        bad = {
            "tool_name": "mcp__github__create_pull_request",
            "tool_input": {"title": GOOD_TITLE, "body": NO_TRAILER},
        }
        self.assertEqual(self._run(bad), 1)

    def test_opt_out_marker_and_infra_project_skip_the_check(self) -> None:
        bad = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr create --fill"},
        }
        self.assertEqual(self._run(bad, opt_out=True), 0)
        self.assertEqual(self._run(bad, infra=True), 0)

    def test_main_non_pr_tools_still_pass(self) -> None:
        self.assertEqual(
            self._run({"tool_name": "Bash", "tool_input": {"command": "git push"}}), 0
        )
        self.assertEqual(
            self._run({"tool_name": "Edit", "tool_input": {"file_path": "src/a.ts"}}), 0
        )


@unittest.skipUnless(NODE, "node not installed — 판정 진본이 node 스크립트")
class PrCreateScriptTests(unittest.TestCase):
    def _run(self, title: str, body: str) -> subprocess.CompletedProcess[str]:
        with TemporaryDirectory() as td:
            tmp = Path(td)
            body_file = tmp / "body.md"
            body_file.write_text(body, encoding="utf-8")
            msg_file = tmp / "msg.txt"
            msg_file.write_text(f"{title}\n", encoding="utf-8")
            return subprocess.run(
                [
                    "bash", str(PR_CREATE),
                    "--branch", "feature/local_check",
                    "--base", "main",
                    "--title", title,
                    "--body-file", str(body_file),
                    "--commit-msg-file", str(msg_file),
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
            )

    def test_bad_body_stops_before_any_git_step(self) -> None:
        proc = self._run(GOOD_TITLE, NO_TRAILER)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Document-Exception-PR-Close", proc.stderr)
        self.assertNotIn("git add", proc.stderr)

    def test_bad_title_stops_before_any_git_step(self) -> None:
        proc = self._run("형식 없음", PASSING_BODIES[0])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("[git-naming] FAIL", proc.stderr)

    def test_good_body_and_title_reach_the_git_steps(self) -> None:
        proc = self._run(GOOD_TITLE, PASSING_BODIES[0])
        self.assertNotIn("[pr-body] FAIL", proc.stderr)
        self.assertNotIn("[git-naming] FAIL", proc.stderr)


if __name__ == "__main__":
    unittest.main()
