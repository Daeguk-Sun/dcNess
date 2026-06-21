"""base-ref / PR 트레일러 추출·판정 로직 회귀 검증 (#424, #580 위임 반영).

base-ref·트레일러 *규칙* SSOT 는 git-spec.md (Git 절차 / PR 트레일러) 다 —
옛 loop-procedure.md 의 긴 추출·판정 bash 는 #580 (단일 목적 SSOT 재정의) 로
git-spec + 각 행동형 skill + pr-create.sh 로 위임·제거됐다.

본 테스트는 그 git-spec 규칙이 규정하는 추출·판정 로직 (Base Branch 마커
grep+sed / task_index i/total 트레일러 분기 / epic 단위 stories.md 경로 유도)
이 다양한 입력에 정상 동작하는지를 지키는 *회귀 가드* 다. (위임 구조 자체 —
loop-procedure 가 원칙만 남기고 규칙을 git-spec 에 위임했는지 — 는 아래
TestSSOTReferencePresent 가 검증.)
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


def extract_base_branch(stories_content: str) -> str:
    """loop-procedure.md 의 base-ref 분기 grep+sed 로직 wrapping."""
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
    """base-ref 분기 sh 추출 로직 검증."""

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
    """epic 단위 stories.md 경로 유도 (impl task 경로 조부모 + stories.md). 규칙 SSOT = git-spec / impl-loop SKILL."""
    cmd = f'printf %s "$(dirname "$(dirname "{task_file}")")/stories.md"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


# base-ref 분기 self-contained STORIES 유도 (충돌 가드 포함) — 입력은 env 로 주입(escaping 회피).
# F1-c/F1-d: EPIC_DIR/TASK_FILE 에서 직접 유도 + 둘 다 set 이고 불일치면 정지.
_SECTION_BASH = r'''
if [ -n "${EPIC_DIR:-}" ] && [ -n "${TASK_FILE:-}" ]; then
  S_EPIC="$EPIC_DIR/stories.md"
  S_TASK="$(dirname "$(dirname "$TASK_FILE")")/stories.md"
  if [ "$S_EPIC" != "$S_TASK" ]; then echo "conflict" >&2; exit 1; fi
  STORIES="$S_TASK"
elif [ -n "${EPIC_DIR:-}" ]; then STORIES="$EPIC_DIR/stories.md"
elif [ -n "${TASK_FILE:-}" ]; then STORIES="$(dirname "$(dirname "$TASK_FILE")")/stories.md"
else echo "missing-stories-input" >&2; exit 1; fi
if ! printf '%s\n' "$STORIES" | grep -Eq '(^|/)docs/epics/[^/]+/stories\.md$'; then
  echo "non-canonical-stories" >&2
  exit 1
fi
printf %s "$STORIES"
'''


def resolve_stories_section(epic_dir: str = "", task_file: str = ""):
    """(returncode, STORIES) 반환. 존재검사 폴백은 제외(파일 없는 테스트라 derivation/conflict 만 검증)."""
    env = {**os.environ, "EPIC_DIR": epic_dir, "TASK_FILE": task_file}
    r = subprocess.run(["bash", "-c", _SECTION_BASH], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout.strip()


# impl-task-loop commit 구조 PR 트레일러 분기 (gh epic-close 서브스텝 제외 — EPIC_OPEN_STORIES=0 폴백과 동일).
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
        task = "docs/epics/epic-07-foo/impl/03-bar.md"
        self.assertEqual(
            resolve_stories_path(task),
            "docs/epics/epic-07-foo/stories.md",
        )

    def test_not_root_docs_stories(self):
        # 회귀 차단: epic 단위 task 인데 root docs/stories.md 로 떨어지면 통합 브랜치 base 누락
        task = "docs/epics/epic-11-monkey/impl/01-theme.md"
        resolved = resolve_stories_path(task)
        self.assertNotEqual(resolved, "docs/stories.md")
        self.assertTrue(resolved.endswith("/epic-11-monkey/stories.md"), resolved)

    def test_section_self_contained_from_epic_dir(self):
        # design: EPIC_DIR 입력 → epic 단위 stories.md
        epic_dir = "docs/epics/epic-11-monkey"
        rc, path = resolve_stories_section(epic_dir=epic_dir)
        self.assertEqual((rc, path), (0, "docs/epics/epic-11-monkey/stories.md"))

    def test_section_self_contained_from_task_file(self):
        # impl-loop: TASK_FILE 입력 (EPIC_DIR 없음) → task 경로 조부모 stories.md
        task = "docs/epics/epic-07-foo/impl/03-bar.md"
        rc, path = resolve_stories_section(task_file=task)
        self.assertEqual((rc, path), (0, "docs/epics/epic-07-foo/stories.md"))

    def test_section_no_input_aborts(self):
        # 둘 다 부재 → root docs/stories.md fallback 없이 정지
        rc, path = resolve_stories_section()
        self.assertEqual(rc, 1)
        self.assertEqual(path, "")

    def test_section_docs_impl_path_aborts(self):
        # 비정식 위치(docs/impl/) task 는 root stories.md 로 흘러가지 않고 정지한다.
        task = "docs/impl/05-foo.md"
        rc, path = resolve_stories_section(task_file=task)
        self.assertEqual(rc, 1)
        self.assertEqual(path, "")

    def test_section_both_set_agree(self):
        # F1-d: EPIC_DIR 와 TASK_FILE 가 같은 epic → 정상 (한쪽 사용)
        epic_dir = "docs/epics/epic-07-foo"
        task = "docs/epics/epic-07-foo/impl/03-bar.md"
        rc, path = resolve_stories_section(epic_dir=epic_dir, task_file=task)
        self.assertEqual((rc, path), (0, "docs/epics/epic-07-foo/stories.md"))

    def test_section_both_set_mismatch_aborts(self):
        # F1-d: EPIC_DIR 와 TASK_FILE 가 다른 epic → stale env 의심, 정지 (조용히 택1 금지)
        epic_dir = "docs/epics/epic-07-foo"
        task = "docs/epics/epic-08-bar/impl/01-x.md"
        rc, _ = resolve_stories_section(epic_dir=epic_dir, task_file=task)
        self.assertEqual(rc, 1)


class TestSSOTReferencePresent(unittest.TestCase):
    """위임 구조 보존 검증 (#580 — loop-procedure 단일 목적 SSOT 재정의).

    base-ref·트레일러 규칙 SSOT 가 loop-procedure 의 긴 bash 에서 git-spec 으로
    이전됐다. 검증 3 축:
    (a) loop-procedure 는 base-ref 운전 원칙(heading) + git-spec 링크만 보유 —
        판정 bash(STORIES 유도 / task_index 트레일러) 는 제거.
    (b) impl-loop / design SKILL 이 base-ref 적용을 설명 (anchor 참조).
    (c) git-spec 이 Base Branch / sub-PR base / 트레일러 규칙 보유.
    """

    ROOT = Path(__file__).resolve().parent.parent

    def _read(self, rel: str) -> str:
        return (self.ROOT / rel).read_text(encoding="utf-8")

    def test_loop_procedure_keeps_principle_and_delegates(self):
        # (a) 원칙 heading(skill cross-ref anchor 대상) + Base Branch 마커 + git-spec 위임 링크 보존
        body = self._read("docs/plugin/loop-procedure.md")
        self.assertIn("### base-ref 분기 (통합 브랜치 모드, #424)", body)
        self.assertIn("**Base Branch:**", body)
        self.assertIn("git-spec.md#git-절차", body)
        # 그림자 판정 bash 는 제거됨 (git-spec / pr-create.sh 위임)
        self.assertNotIn("EPIC_OPEN_STORIES", body)
        self.assertNotIn("task_index", body)

    def test_impl_loop_references_section(self):
        # (b) impl + impl-loop 통합 — skills/impl-loop/SKILL.md 단일 진본
        body = self._read("skills/impl-loop/SKILL.md")
        self.assertIn("#base-ref-분기-통합-브랜치-모드-424", body)
        self.assertIn("Base ref 분기", body)

    def test_design_references_section(self):
        # (b)
        body = self._read("skills/design/SKILL.md")
        self.assertIn("#base-ref-분기-통합-브랜치-모드-424", body)
        self.assertIn("Base ref 분기", body)

    def test_git_spec_has_base_and_trailer_rules(self):
        # (c) base 분기 + 트레일러 규칙 SSOT = git-spec
        body = self._read("docs/plugin/git-spec.md")
        self.assertIn("**Base Branch:**", body)
        self.assertIn("## Git 절차", body)
        self.assertIn("## PR 트레일러", body)


if __name__ == "__main__":
    unittest.main()
