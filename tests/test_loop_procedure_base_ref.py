"""docs/plugin/loop-procedure.md §1.1.1 의 base-ref 추출 sh 명령 검증 (#424).

§1.1.1 의 sh 블록:

    BASE_BRANCH=$(grep -m1 -E '^\\*\\*Base Branch:\\*\\*' docs/stories.md 2>/dev/null \\
      | sed -E 's/.*Base Branch:\\*\\*[[:space:]]+//')

이 추출 로직이 다양한 stories.md 입력에 대해 정상 동작하는지 검증.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


def extract_base_branch(stories_content: str) -> str:
    """loop-procedure.md §1.1.1 의 grep+sed 로직 wrapping."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(stories_content)
        path = f.name
    try:
        cmd = (
            f"grep -m1 -E '^\\*\\*Base Branch:\\*\\*' {path} 2>/dev/null | "
            f"sed -E 's/.*Base Branch:\\*\\*[[:space:]]+//'"
        )
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
        )
        return result.stdout.strip()
    finally:
        Path(path).unlink()


class TestBaseBranchExtraction(unittest.TestCase):
    """§1.1.1 sh 추출 로직 검증."""

    def test_integration_branch_extracted(self):
        content = (
            "**GitHub Epic Issue:** [#19]\n"
            "**Base Branch:** feature/local-dsp\n"
            "\n# stories\n"
        )
        self.assertEqual(extract_base_branch(content), "feature/local-dsp")

    def test_no_marker_returns_empty(self):
        content = "# stories\n\nno marker here\n"
        self.assertEqual(extract_base_branch(content), "")

    def test_main_value(self):
        """Base Branch 가 main 으로 명시되면 'main' 추출."""
        content = "**Base Branch:** main\n"
        self.assertEqual(extract_base_branch(content), "main")

    def test_marker_with_extra_whitespace(self):
        """`**Base Branch:**` 와 값 사이 다중 공백/탭 허용."""
        content = "**Base Branch:**    feature/foo-bar\n"
        self.assertEqual(extract_base_branch(content), "feature/foo-bar")

    def test_first_match_only(self):
        """여러 줄 매치 시 첫 줄만 추출 (-m1)."""
        content = (
            "**Base Branch:** feature/first\n"
            "**Base Branch:** feature/second\n"
        )
        self.assertEqual(extract_base_branch(content), "feature/first")

    def test_marker_not_at_line_start_ignored(self):
        """`^` anchor — 줄 시작에 없으면 매치 X."""
        content = "prefix **Base Branch:** feature/foo\n"
        self.assertEqual(extract_base_branch(content), "")

    def test_marker_with_slash_in_value(self):
        """feature/<slug> 안 `/` 문자 유지."""
        content = "**Base Branch:** feature/epic-19/integration\n"
        self.assertEqual(
            extract_base_branch(content), "feature/epic-19/integration"
        )


def resolve_stories_path(task_file: str) -> str:
    """§3.4 의 epic 단위 stories.md 경로 유도 (impl task 경로 조부모 + stories.md)."""
    cmd = f'printf %s "$(dirname "$(dirname "{task_file}")")/stories.md"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


# §1.1.1 self-contained STORIES 유도 (충돌 가드 포함) — 입력은 env 로 주입(escaping 회피).
# F1-c/F1-d: EPIC_DIR/TASK_FILE 에서 직접 유도 + 둘 다 set 이고 불일치면 정지.
_SECTION_BASH = r'''
if [ -n "${EPIC_DIR:-}" ] && [ -n "${TASK_FILE:-}" ]; then
  S_EPIC="$EPIC_DIR/stories.md"
  S_TASK="$(dirname "$(dirname "$TASK_FILE")")/stories.md"
  if [ "$S_EPIC" != "$S_TASK" ]; then echo "conflict" >&2; exit 1; fi
  STORIES="$S_TASK"
elif [ -n "${EPIC_DIR:-}" ]; then STORIES="$EPIC_DIR/stories.md"
elif [ -n "${TASK_FILE:-}" ]; then STORIES="$(dirname "$(dirname "$TASK_FILE")")/stories.md"
else STORIES="docs/stories.md"; fi
printf %s "$STORIES"
'''


def resolve_stories_section(epic_dir: str = "", task_file: str = ""):
    """(returncode, STORIES) 반환. 존재검사 폴백은 제외(파일 없는 테스트라 derivation/conflict 만 검증)."""
    env = {**os.environ, "EPIC_DIR": epic_dir, "TASK_FILE": task_file}
    r = subprocess.run(["bash", "-c", _SECTION_BASH], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout.strip()


# §3.4 PR 트레일러 분기 (gh epic-close 서브스텝 제외 — EPIC_OPEN_STORIES=0 폴백과 동일).
# F2-b/F2-d: 공통 task 는 story:공통 으로 키잉, 정식 story 는 i/total, 숫자 story+malformed index 는 정지.
_TRAILER_BASH = r'''
if [ "$STORY_NUM" = "공통" ]; then
  EPIC_ISSUE="${EPIC_ISSUE:-$(grep -m1 -E '^\*\*GitHub Epic Issue:\*\*' "$STORIES" 2>/dev/null | grep -oE '#[0-9]+' | head -1 | tr -d '#')}"
  if [ -z "$EPIC_ISSUE" ]; then echo "no-epic" >&2; exit 1; fi
  PR_BODY="Part of #${EPIC_ISSUE}"
elif printf '%s' "$TASK_INDEX" | grep -qE '^[0-9]+/[0-9]+$'; then
  I="${TASK_INDEX%/*}"; TOTAL="${TASK_INDEX#*/}"
  if [ "$I" = "$TOTAL" ]; then PR_BODY="Closes #${STORY_ISSUE}"; else PR_BODY="Part of #${STORY_ISSUE}"; fi
else
  echo "malformed" >&2; exit 1
fi
printf %s "$PR_BODY"
'''


def decide_trailer(story_num="", task_index="", story_issue="100",
                   epic_issue="", stories_content=""):
    """(returncode, PR_BODY) 반환. stories_content 로 epic 마커 파싱 테스트."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(stories_content)
        stories_path = f.name
    try:
        env = {
            **os.environ,
            "STORY_NUM": story_num, "TASK_INDEX": task_index,
            "STORY_ISSUE": story_issue, "EPIC_ISSUE": epic_issue,
            "STORIES": stories_path,
        }
        r = subprocess.run(["bash", "-c", _TRAILER_BASH],
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stdout.strip()
    finally:
        Path(stories_path).unlink()


class TestTrailerDecision(unittest.TestCase):
    """F2-b/F2-d: PR 트레일러 분기 — 공통/정식/malformed 정확 분류."""

    EPIC_MARKER = "**GitHub Epic Issue:** [#42](https://x/issues/42)\n"

    def test_common_task_part_of_epic(self):
        rc, body = decide_trailer(story_num="공통", task_index="—",
                                  stories_content=self.EPIC_MARKER)
        self.assertEqual(rc, 0)
        self.assertEqual(body, "Part of #42")

    def test_common_task_no_epic_marker_aborts(self):
        rc, _ = decide_trailer(story_num="공통", task_index="—",
                               stories_content="no marker here\n")
        self.assertEqual(rc, 1)  # 빈 "Part of #" 방지

    def test_story_last_task_closes(self):
        rc, body = decide_trailer(story_num="2", task_index="3/3", story_issue="100")
        self.assertEqual((rc, body), (0, "Closes #100"))

    def test_story_mid_task_part_of(self):
        rc, body = decide_trailer(story_num="2", task_index="1/3", story_issue="100")
        self.assertEqual((rc, body), (0, "Part of #100"))

    def test_numeric_story_missing_index_aborts(self):
        # F2-d: 정식 story 인데 task_index 누락 → 공통 오분류 금지, 정지
        rc, _ = decide_trailer(story_num="2", task_index="")
        self.assertEqual(rc, 1)

    def test_numeric_story_malformed_index_aborts(self):
        rc, _ = decide_trailer(story_num="2", task_index="foo")
        self.assertEqual(rc, 1)


class TestStoriesPathResolution(unittest.TestCase):
    """F1-b/F1-c: base 분기용 stories.md 는 root 가 아니라 epic 단위 (입력에서 직접 유도) 여야 함."""

    def test_epic_level_stories_from_task_path(self):
        task = "docs/milestones/v0.2/epics/epic-07-foo/impl/03-bar.md"
        self.assertEqual(
            resolve_stories_path(task),
            "docs/milestones/v0.2/epics/epic-07-foo/stories.md",
        )

    def test_not_root_docs_stories(self):
        # 회귀 차단: epic 단위 task 인데 root docs/stories.md 로 떨어지면 통합 브랜치 base 누락
        task = "docs/milestones/v01/epics/epic-11-monkey/impl/01-theme.md"
        resolved = resolve_stories_path(task)
        self.assertNotEqual(resolved, "docs/stories.md")
        self.assertTrue(resolved.endswith("/epic-11-monkey/stories.md"), resolved)

    def test_section_self_contained_from_epic_dir(self):
        # architect-loop: EPIC_DIR 입력 → epic 단위 stories.md
        epic_dir = "docs/milestones/v01/epics/epic-11-monkey"
        rc, path = resolve_stories_section(epic_dir=epic_dir)
        self.assertEqual((rc, path), (0, "docs/milestones/v01/epics/epic-11-monkey/stories.md"))

    def test_section_self_contained_from_task_file(self):
        # impl-loop: TASK_FILE 입력 (EPIC_DIR 없음) → task 경로 조부모 stories.md
        task = "docs/milestones/v0.2/epics/epic-07-foo/impl/03-bar.md"
        rc, path = resolve_stories_section(task_file=task)
        self.assertEqual((rc, path), (0, "docs/milestones/v0.2/epics/epic-07-foo/stories.md"))

    def test_section_fallback_when_no_input(self):
        # 둘 다 부재 → root docs/stories.md legacy 폴백
        self.assertEqual(resolve_stories_section(), (0, "docs/stories.md"))

    def test_section_docs_impl_fallback_path(self):
        # 비정식 위치(docs/impl/) task — 조부모 = docs → root stories.md (안전 폴백, 통합 브랜치 비대상)
        task = "docs/impl/05-foo.md"
        self.assertEqual(resolve_stories_section(task_file=task), (0, "docs/stories.md"))

    def test_section_both_set_agree(self):
        # F1-d: EPIC_DIR 와 TASK_FILE 가 같은 epic → 정상 (한쪽 사용)
        epic_dir = "docs/milestones/v01/epics/epic-07-foo"
        task = "docs/milestones/v01/epics/epic-07-foo/impl/03-bar.md"
        rc, path = resolve_stories_section(epic_dir=epic_dir, task_file=task)
        self.assertEqual((rc, path), (0, "docs/milestones/v01/epics/epic-07-foo/stories.md"))

    def test_section_both_set_mismatch_aborts(self):
        # F1-d: EPIC_DIR 와 TASK_FILE 가 다른 epic → stale env 의심, 정지 (조용히 택1 금지)
        epic_dir = "docs/milestones/v01/epics/epic-07-foo"
        task = "docs/milestones/v01/epics/epic-08-bar/impl/01-x.md"
        rc, _ = resolve_stories_section(epic_dir=epic_dir, task_file=task)
        self.assertEqual(rc, 1)


class TestSSOTReferencePresent(unittest.TestCase):
    """SSOT (loop-procedure.md §1.1.1) 참조가 skill 본문에 박혀있는지 검증."""

    ROOT = Path(__file__).resolve().parent.parent

    def _read(self, rel: str) -> str:
        return (self.ROOT / rel).read_text(encoding="utf-8")

    def test_loop_procedure_section_present(self):
        body = self._read("docs/plugin/loop-procedure.md")
        self.assertIn("### base-ref 분기 (통합 브랜치 모드, #424)", body)
        self.assertIn("**Base Branch:**", body)
        self.assertIn("git worktree add -b", body)
        self.assertIn("EnterWorktree(path=", body)

    def test_impl_loop_references_section(self):
        # impl + impl-loop 통합 — skills/impl-loop/SKILL.md 단일 진본
        body = self._read("skills/impl-loop/SKILL.md")
        self.assertIn("#base-ref-분기-통합-브랜치-모드-424", body)
        self.assertIn("Base ref 분기", body)

    def test_architect_loop_references_section(self):
        body = self._read("skills/architect-loop/SKILL.md")
        self.assertIn("#base-ref-분기-통합-브랜치-모드-424", body)
        self.assertIn("Base ref 분기", body)


if __name__ == "__main__":
    unittest.main()
