"""JOURNEY_CONVERGENCE write scope = chain 전체 task 의 `### 수정 허용` 합집합 (#1313)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.agent_boundary import check_write_allowed
from harness.session_state import impl_scope_paths_for_run
from harness.story_runner import build_state, save_state


def _task(path: Path, story: str, grants: list[str]) -> None:
    path.write_text(
        "---\n"
        f"story: {story}\n"
        "task_index: 1/1\n"
        "---\n\n"
        "## Scope\n\n### 수정 허용\n\n"
        + "".join(f"- `{grant}`\n" for grant in grants)
        + "\n### 수정 금지\n\n-\n",
        encoding="utf-8",
    )


class ConvergenceTaskScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name).resolve()
        impl = self.root / "docs" / "epics" / "epic-01-demo" / "impl"
        impl.mkdir(parents=True)
        self.first = impl / "01-login.md"
        self.last = impl / "02-home.md"
        _task(self.first, "1", ["src/login/", "scripts/acceptance/story-1.sh"])
        _task(self.last, "2", ["src/home/", "scripts/acceptance/story-2.sh"])
        self.state_path = self.root / ".dcness-work" / "custom-chain.json"
        state = build_state([str(impl)], cwd=self.root, scope="epic")
        save_state(self.state_path, state)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _scope(
        self, *, mode: str | None, design_doc: Path, chain_state: bool = True
    ) -> tuple[str, ...]:
        step = {"agent": "build-worker", "mode": mode}
        if chain_state:
            step["chain_state"] = str(self.state_path)
        slot = {"design_doc": str(design_doc), "current_step": step}
        with mock.patch("harness.session_state._slot_for_run", return_value=slot):
            return impl_scope_paths_for_run("sid", "run-1")

    def test_convergence_step_opens_every_chain_task_grant(self) -> None:
        scope = self._scope(mode="JOURNEY_CONVERGENCE", design_doc=self.last)

        self.assertEqual(
            set(scope),
            {
                "src/login/",
                "scripts/acceptance/story-1.sh",
                "src/home/",
                "scripts/acceptance/story-2.sh",
            },
        )

    def test_convergence_without_recorded_chain_state_keeps_own_grant(self) -> None:
        # 수동 begin-step 처럼 chain state 를 기록하지 않은 step 은 추측해서 넓히지 않는다.
        scope = self._scope(
            mode="JOURNEY_CONVERGENCE", design_doc=self.last, chain_state=False
        )

        self.assertEqual(set(scope), {"src/home/", "scripts/acceptance/story-2.sh"})

    def test_task_step_keeps_only_its_own_grant(self) -> None:
        scope = self._scope(mode=None, design_doc=self.last)

        self.assertEqual(set(scope), {"src/home/", "scripts/acceptance/story-2.sh"})

    def test_design_doc_outside_chain_state_keeps_only_its_own_grant(self) -> None:
        stray = self.root / "docs" / "epics" / "epic-02-other" / "impl" / "01-x.md"
        stray.parent.mkdir(parents=True)
        _task(stray, "9", ["src/other/"])

        scope = self._scope(mode="JOURNEY_CONVERGENCE", design_doc=stray)

        self.assertEqual(scope, ("src/other/",))

    def test_chain_task_from_other_impl_directory_is_not_merged(self) -> None:
        # headless 사후 검사는 story-run state 를 검사하지 않으므로, state 에 다른 Epic 문서를
        # 끼워 넣어도 같은 impl 디렉토리 밖의 설계 승인 경로는 열리지 않는다.
        other = self.root / "docs" / "epics" / "epic-02-other" / "impl" / "01-x.md"
        other.parent.mkdir(parents=True)
        _task(other, "9", ["build.gradle"])
        state = build_state(
            [str(self.first), str(self.last), str(other)], cwd=self.root, scope="epic"
        )
        save_state(self.state_path, state)

        scope = self._scope(mode="JOURNEY_CONVERGENCE", design_doc=self.last)

        self.assertNotIn("build.gradle", scope)
        self.assertIn("scripts/acceptance/story-1.sh", scope)

    def test_guard_allows_earlier_story_script_and_blocks_outside_path(self) -> None:
        scope = self._scope(mode="JOURNEY_CONVERGENCE", design_doc=self.last)

        self.assertIsNone(
            check_write_allowed(
                "build-worker",
                "scripts/acceptance/story-1.sh",
                cwd=self.root,
                task_scope_paths=scope,
            )
        )
        reason = check_write_allowed(
            "build-worker",
            "scripts/acceptance/representative.sh",
            cwd=self.root,
            task_scope_paths=scope,
        )
        self.assertIsNotNone(reason)
        self.assertIn("ALLOW_MATRIX 미매칭", reason)


if __name__ == "__main__":
    unittest.main()
