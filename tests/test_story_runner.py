from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness.story_runner import build_state, mark_story, mark_task, next_task


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dcness-story-runner"


class StoryRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        self.impl_dir = self.root / "docs" / "epics" / "epic-01-demo" / "impl"
        self.impl_dir.mkdir(parents=True)
        self._write_task(
            "02-api.md",
            story="1",
            task_index="2/2",
            engine="4agent",
            risk="high",
            title="API slice",
        )
        self._write_task(
            "01-ui.md",
            story="1",
            task_index="1/2",
            engine="2agent",
            risk="normal",
            title="UI slice",
        )
        self._write_task(
            "03-common.md",
            story="공통",
            task_index="",
            engine="2agent",
            risk="normal",
            title="Common",
        )

    def tearDown(self) -> None:
        self._td.cleanup()

    def _write_task(
        self,
        name: str,
        *,
        story: str,
        task_index: str,
        engine: str,
        risk: str,
        title: str,
    ) -> Path:
        path = self.impl_dir / name
        path.write_text(
            "\n".join(
                [
                    "---",
                    f"title: {title}",
                    f"story: {story}",
                    f"task_index: {task_index}",
                    f"risk: {risk}",
                    f"engine: {engine}",
                    "risk_reason: fixture",
                    "---",
                    "",
                    "# Task",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_plan_sorts_tasks_and_groups_story_pr_boundaries(self) -> None:
        state = build_state([str(self.impl_dir)], cwd=self.root, scope="epic")

        self.assertEqual(state["scope"], "epic")
        self.assertEqual(
            [Path(task["path"]).name for task in state["tasks"]],
            ["01-ui.md", "02-api.md", "03-common.md"],
        )
        self.assertEqual([story["story"] for story in state["stories"]], ["1", "공통"])
        self.assertEqual(state["stories"][0]["task_ids"], [1, 2])
        self.assertEqual(state["stories"][1]["task_ids"], [3])

    def test_mark_resume_transitions(self) -> None:
        state = build_state([str(self.impl_dir / "01-ui.md"), str(self.impl_dir / "02-api.md")], cwd=self.root)

        first = next_task(state)
        self.assertEqual(first["id"], 1)
        mark_task(state, "1", "running", provider="codex-headless")
        self.assertEqual(next_task(state)["id"], 1)
        mark_task(state, "1", "completed", commit="abc123")
        self.assertEqual(next_task(state)["id"], 2)
        mark_task(state, "2", "completed", commit="def456")

        self.assertIsNone(next_task(state))
        self.assertEqual(state["status"], "ready_for_pr")
        self.assertEqual(state["stories"][0]["status"], "ready_for_pr")

        mark_story(state, "1", "completed", pr="https://github.test/pr/1")
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["stories"][0]["status"], "completed")
        self.assertEqual(state["stories"][0]["pr"], "https://github.test/pr/1")

    def test_script_init_next_mark_round_trip(self) -> None:
        state_path = self.root / ".dcness-work" / "story-run.json"
        env = {**os.environ, "PYTHONPATH": str(ROOT)}

        init = subprocess.run(
            [
                str(SCRIPT),
                "init",
                str(self.impl_dir / "01-ui.md"),
                str(self.impl_dir / "02-api.md"),
                "--cwd",
                str(self.root),
                "--state",
                str(state_path),
                "--json",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(init.stdout)
        self.assertEqual(payload["scope"], "story")
        self.assertTrue(state_path.exists())

        nxt = subprocess.run(
            [str(SCRIPT), "next", "--state", str(state_path), "--json"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(nxt.stdout)["id"], 1)

        subprocess.run(
            [
                str(SCRIPT),
                "mark",
                "--state",
                str(state_path),
                "--task",
                "1",
                "--status",
                "completed",
                "--commit",
                "abc123",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["tasks"][0]["commit"], "abc123")
        self.assertEqual(saved["tasks"][1]["status"], "pending")

        subprocess.run(
            [
                str(SCRIPT),
                "mark",
                "--state",
                str(state_path),
                "--task",
                "2",
                "--status",
                "completed",
                "--commit",
                "def456",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        ready = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(ready["status"], "ready_for_pr")
        self.assertEqual(ready["stories"][0]["status"], "ready_for_pr")

        subprocess.run(
            [
                str(SCRIPT),
                "mark-story",
                "--state",
                str(state_path),
                "--story",
                "1",
                "--status",
                "completed",
                "--pr",
                "https://github.test/pr/1",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        done = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(done["status"], "completed")
        self.assertEqual(done["stories"][0]["pr"], "https://github.test/pr/1")


if __name__ == "__main__":
    unittest.main()
