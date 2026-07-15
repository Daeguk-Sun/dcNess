from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from harness.story_runner import (
    build_state,
    mark_task,
    next_action,
    next_task,
    prepare_init_state,
)


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
            title="API slice",
        )
        self._write_task(
            "01-ui.md",
            story="1",
            task_index="1/2",
            title="UI slice",
        )
        self._write_task(
            "03-common.md",
            story="공통",
            task_index="",
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
                    "---",
                    "",
                    "# Task",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def test_plan_sorts_tasks_without_persisting_derived_story_or_run_state(self) -> None:
        state = build_state([str(self.impl_dir)], cwd=self.root, scope="epic")

        self.assertEqual(state["scope"], "epic")
        self.assertEqual(state["schema_version"], 2)
        self.assertEqual(
            [Path(task["path"]).name for task in state["tasks"]],
            ["01-ui.md", "02-api.md", "03-common.md"],
        )
        self.assertNotIn("stories", state)
        self.assertNotIn("status", state)
        self.assertNotIn("current_task", state)
        for task in state["tasks"]:
            self.assertNotIn("risk", task)
            self.assertNotIn("engine", task)
            self.assertNotIn("risk_reason", task)

    def test_plan_preserves_contiguous_story_blocks_in_path_order(self) -> None:
        common = self._write_task(
            "00-common.md",
            story="공통",
            task_index="",
            title="Shared setup",
        )
        story_two = self._write_task(
            "04-story-two.md",
            story="2",
            task_index="1/1",
            title="Story two",
        )

        state = build_state(
            [
                str(story_two),
                str(self.impl_dir / "02-api.md"),
                str(common),
                str(self.impl_dir / "01-ui.md"),
            ],
            cwd=self.root,
            scope="epic",
        )

        self.assertEqual(
            [Path(task["path"]).name for task in state["tasks"]],
            ["00-common.md", "01-ui.md", "02-api.md", "04-story-two.md"],
        )
        self.assertEqual(
            [task["story"] for task in state["tasks"]],
            ["공통", "1", "1", "2"],
        )

    def test_plan_applies_contiguity_rule_to_common_story(self) -> None:
        common_start = self._write_task(
            "00-common-start.md",
            story="공통",
            task_index="",
            title="Shared setup",
        )
        common_again = self._write_task(
            "02-common-again.md",
            story="공통",
            task_index="",
            title="Shared follow-up",
        )

        with self.assertRaisesRegex(ValueError, "story=공통") as raised:
            build_state(
                [
                    str(common_again),
                    str(self.impl_dir / "01-ui.md"),
                    str(common_start),
                ],
                cwd=self.root,
                scope="epic",
            )

        self.assertIn("00-common-start.md", str(raised.exception))
        self.assertIn("01-ui.md", str(raised.exception))
        self.assertIn("02-common-again.md", str(raised.exception))

    def test_script_plan_and_init_reject_non_contiguous_story_without_touching_state(
        self,
    ) -> None:
        crossing = self._write_task(
            "03-story-one-again.md",
            story="1",
            task_index="3/3",
            title="Story one again",
        )
        story_two = self._write_task(
            "02-story-two.md",
            story="2",
            task_index="1/1",
            title="Story two",
        )
        paths = [
            str(self.impl_dir / "01-ui.md"),
            str(story_two),
            str(crossing),
        ]
        env = {**os.environ, "PYTHONPATH": str(ROOT)}

        plan = subprocess.run(
            [str(SCRIPT), "plan", *paths, "--cwd", str(self.root)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(plan.returncode, 1)
        self.assertIn("non-contiguous story group", plan.stderr)
        self.assertIn("story=1", plan.stderr)
        for name in ("01-ui.md", "02-story-two.md", "03-story-one-again.md"):
            self.assertIn(name, plan.stderr)

        state_path = self.root / ".dcness-work" / "story-run.json"
        init_without_state = subprocess.run(
            [
                str(SCRIPT),
                "init",
                *paths,
                "--cwd",
                str(self.root),
                "--state",
                str(state_path),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(init_without_state.returncode, 1)
        self.assertFalse(state_path.exists())

        existing = build_state(
            [str(self.impl_dir / "01-ui.md")], cwd=self.root, scope="story"
        )
        existing["tasks"][0]["status"] = "completed"
        existing["tasks"][0]["commit"] = "abc123"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
        original = state_path.read_bytes()

        init_with_completed_state = subprocess.run(
            [
                str(SCRIPT),
                "init",
                *paths,
                "--cwd",
                str(self.root),
                "--state",
                str(state_path),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(init_with_completed_state.returncode, 1)
        self.assertIn("non-contiguous story group", init_with_completed_state.stderr)
        self.assertEqual(state_path.read_bytes(), original)
        self.assertEqual(
            list(state_path.parent.glob("story-run.completed-*.json")), []
        )

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
        action = next_action(state)
        self.assertEqual(action["action"], "done")
        self.assertEqual(action["final_story"]["story"], "1")
        self.assertEqual(action["final_story"]["task_ids"], [1, 2])
        self.assertEqual(action["final_story"]["commits"], ["abc123", "def456"])
        self.assertEqual(
            action["pr_base"], {"kind": "default-branch", "branch": "main"}
        )
        self.assertEqual(
            action["stack_tip"], {"kind": "story-branch", "story": "1"}
        )
        self.assertEqual(action["progress"], {"completed": 2, "total": 2})

    def test_next_stops_at_story_pr_boundary_before_later_story(self) -> None:
        state = build_state([str(self.impl_dir)], cwd=self.root, scope="epic")

        mark_task(state, "1", "completed", commit="abc123")
        self.assertEqual(next_task(state)["id"], 2)
        mark_task(state, "2", "completed", commit="def456")

        self.assertIsNone(next_task(state))
        action = next_action(state)
        self.assertEqual(action["action"], "story-pr")
        self.assertEqual(action["story"]["story"], "1")
        self.assertEqual(action["story"]["task_ids"], [1, 2])
        self.assertEqual(action["next_task"]["id"], 3)
        self.assertEqual(
            action["pr_base"], {"kind": "default-branch", "branch": "main"}
        )
        self.assertEqual(
            action["next_branch_base"],
            {"kind": "story-branch", "story": "1"},
        )

        # story PR 생성은 state 에 저장하지 않는다. 다음 story branch 를 직전
        # story branch tip 에서 만든 뒤 next_task 를 running 으로 mark 하면 전진한다.
        mark_task(state, "3", "running", provider="claude-headless")
        self.assertEqual(next_task(state)["id"], 3)
        self.assertEqual(next_action(state)["task"]["id"], 3)

    def test_done_exposes_final_story_base_and_stack_tip_for_epic(self) -> None:
        state = build_state([str(self.impl_dir)], cwd=self.root, scope="epic")

        mark_task(state, "1", "completed", commit="abc123")
        mark_task(state, "2", "completed", commit="def456")
        mark_task(state, "3", "completed", commit="ghi789")

        action = next_action(state)

        self.assertEqual(action["action"], "done")
        self.assertEqual(action["final_story"]["story"], "공통")
        self.assertEqual(
            action["pr_base"], {"kind": "story-branch", "story": "1"}
        )
        self.assertEqual(
            action["stack_tip"], {"kind": "story-branch", "story": "공통"}
        )

    def test_completed_requires_commit_and_failure_states_require_note(self) -> None:
        state = build_state([str(self.impl_dir / "01-ui.md")], cwd=self.root)

        with self.assertRaisesRegex(ValueError, "completed requires --commit"):
            mark_task(state, "1", "completed")
        with self.assertRaisesRegex(ValueError, "blocked requires --note"):
            mark_task(state, "1", "blocked")
        with self.assertRaisesRegex(ValueError, "error requires --note"):
            mark_task(state, "1", "error")

        mark_task(state, "1", "blocked", note="dependency unavailable")
        action = next_action(state)
        self.assertEqual(action["action"], "blocked")
        self.assertEqual(action["task"]["note"], "dependency unavailable")

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
        self.assertNotIn("status", ready)
        self.assertNotIn("stories", ready)
        self.assertTrue(all(task["status"] == "completed" for task in ready["tasks"]))

        action = subprocess.run(
            [str(SCRIPT), "next-action", "--state", str(state_path), "--json"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        action_payload = json.loads(action.stdout)
        self.assertEqual(action_payload["action"], "done")
        self.assertEqual(action_payload["final_story"]["story"], "1")

        removed = subprocess.run(
            [str(SCRIPT), "mark-story", "--state", str(state_path)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(removed.returncode, 2)
        self.assertIn("invalid choice", removed.stderr)

        reinit = subprocess.run(
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
        reinit_payload = json.loads(reinit.stdout)
        self.assertNotIn("status", reinit_payload)
        archives = list(state_path.parent.glob("story-run.completed-*.json"))
        self.assertEqual(len(archives), 1)
        archived = json.loads(archives[0].read_text(encoding="utf-8"))
        self.assertTrue(all(task["status"] == "completed" for task in archived["tasks"]))

    def test_script_init_refuses_active_state_without_force(self) -> None:
        state_path = self.root / ".dcness-work" / "story-run.json"
        env = {**os.environ, "PYTHONPATH": str(ROOT)}

        subprocess.run(
            [
                str(SCRIPT),
                "init",
                str(self.impl_dir / "01-ui.md"),
                "--cwd",
                str(self.root),
                "--state",
                str(state_path),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

        duplicate = subprocess.run(
            [
                str(SCRIPT),
                "init",
                str(self.impl_dir / "01-ui.md"),
                "--cwd",
                str(self.root),
                "--state",
                str(state_path),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(duplicate.returncode, 1)
        self.assertIn("state has incomplete task(s): #1=pending", duplicate.stderr)

        legacy = {"schema_version": 1, "tasks": []}
        state_path.write_text(json.dumps(legacy), encoding="utf-8")
        legacy_bytes = state_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "--force"):
            prepare_init_state(state_path, force=False)
        self.assertEqual(state_path.read_bytes(), legacy_bytes)
        self.assertIsNone(prepare_init_state(state_path, force=True))

if __name__ == "__main__":
    unittest.main()
