"""test_parallel_wave — 병렬 wave 계산 코어 단위 테스트 (#636).

정책 SSOT = docs/plugin/parallel-policy.md. 검증 축:

    parse_impl_task:
        - depends_on 3-state (미상 None / 명시적 [] () / 목록)
        - placeholder 잔존 → 미상
        - inline / block 리스트 둘 다
        - Scope 파싱: 정규화 경로 / 자유서술 ambiguous / 빈값 / 디렉토리

    compute_waves (AC: wave 후보 / scope 중첩 배제 / 미상 fallback / cap):
        - 독립 2개 disjoint → 같은 병렬 wave
        - Scope 중첩 → 같은 wave 배제(직렬)
        - depends_on 사슬 → 직렬 순서
        - depends_on 미상 → 직렬 fallback
        - 명시적 [] + disjoint → 병렬
        - max_parallel_workers=2 cap → 독립 3개 = wave(2)+직렬(1)
        - force_serial(parallel: serial) → 직렬
        - 디렉토리/파일 포함 충돌 → 직렬

    fan_in_check (AC: fan-in PASS / FALLBACK):
        - 깨끗한 wave → PASS
        - scope 이탈 → FALLBACK
        - cross-worker 파일 충돌 → FALLBACK
        - evidence 누락 → FALLBACK
"""
import tempfile
import unittest
from pathlib import Path

from harness.parallel_wave import (
    DEFAULT_MAX_PARALLEL_WORKERS,
    ImplTask,
    WorkerResult,
    compute_waves,
    fan_in_check,
    parse_impl_task,
    scopes_disjoint,
)


def _task(
    slug,
    depends_on,
    scope,
    *,
    scope_ambiguous=False,
    force_serial=False,
):
    """ImplTask 빌더 — depends_on/scope 를 직접 지정."""
    return ImplTask(
        slug=slug,
        path=f"{slug}.md",
        depends_on=depends_on,
        scope_paths=frozenset(scope),
        scope_ambiguous=scope_ambiguous,
        force_serial=force_serial,
    )


def _write_impl(dirpath, name, body):
    p = Path(dirpath) / name
    p.write_text(body, encoding="utf-8")
    return p


# ── parse_impl_task ─────────────────────────────────────────


class TestParseDependsOn(unittest.TestCase):
    def _parse(self, fm_depends, scope_block="- src/a.py\n"):
        body = (
            "---\n"
            f"{fm_depends}\n"
            "story: 1\n"
            "---\n\n"
            "## Scope\n\n### 수정 허용\n\n"
            f"{scope_block}\n"
            "### 수정 금지\n\n-\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write_impl(d, "01-foo.md", body)
            return parse_impl_task(p)

    def test_depends_on_absent_is_unknown(self):
        # depends_on 키 자체가 없음 → 미상(None)
        body = "---\nstory: 1\n---\n\n## Scope\n\n### 수정 허용\n\n- src/a.py\n"
        with tempfile.TemporaryDirectory() as d:
            p = _write_impl(d, "01-foo.md", body)
            t = parse_impl_task(p)
        self.assertIsNone(t.depends_on)
        self.assertTrue(t.serial_only)

    def test_depends_on_empty_with_comment_is_unknown(self):
        # 템플릿 기본형 — 값 없이 주석만 → 미상
        t = self._parse("depends_on:             # [<NN-slug>, ...] 선행 task")
        self.assertIsNone(t.depends_on)

    def test_depends_on_explicit_empty_is_independent(self):
        t = self._parse("depends_on: []")
        self.assertEqual(t.depends_on, ())
        self.assertFalse(t.serial_only)  # scope 정상이므로 병렬 후보

    def test_depends_on_inline_list(self):
        t = self._parse("depends_on: [01-foo, 02-bar]")
        self.assertEqual(t.depends_on, ("01-foo", "02-bar"))

    def test_depends_on_block_list(self):
        t = self._parse("depends_on:\n  - 01-foo\n  - 02-bar")
        self.assertEqual(t.depends_on, ("01-foo", "02-bar"))

    def test_depends_on_placeholder_unfilled_is_unknown(self):
        # [<NN-slug>] placeholder 가 값으로 남음 → 미상으로 강등
        t = self._parse("depends_on: [<NN-slug>]")
        self.assertIsNone(t.depends_on)

    def test_depends_on_explicit_empty_with_comment(self):
        t = self._parse("depends_on: []   # 선행 없음")
        self.assertEqual(t.depends_on, ())

    def test_depends_on_inline_list_with_comment(self):
        t = self._parse("depends_on: [01-a, 02-b]   # 선행 둘")
        self.assertEqual(t.depends_on, ("01-a", "02-b"))

    def test_depends_on_block_list_with_inline_comment(self):
        # codex P2 F1 회귀 가드 — block 원소의 inline 주석이 slug 에 새면 안 됨.
        t = self._parse("depends_on:\n  - 01-a  # produces X\n  - 02-b")
        self.assertEqual(t.depends_on, ("01-a", "02-b"))

    def test_depends_on_block_list_with_standalone_comment(self):
        # codex F6 회귀 가드 — 원소 사이 standalone 주석 라인에서 끊겨 뒤 원소 누락 금지.
        t = self._parse("depends_on:\n  - 01-a\n  # 02 는 forward dep\n  - 02-b")
        self.assertEqual(t.depends_on, ("01-a", "02-b"))


class TestParseScope(unittest.TestCase):
    def _parse_scope(self, scope_block):
        body = (
            "---\ndepends_on: []\n---\n\n"
            "## Scope\n\n### 수정 허용\n\n"
            f"{scope_block}\n"
            "### 수정 금지\n\n-\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write_impl(d, "01-foo.md", body)
            return parse_impl_task(p)

    def test_clean_paths(self):
        t = self._parse_scope("- src/a.py\n- harness/b.py\n")
        self.assertEqual(t.scope_paths, frozenset({"src/a.py", "harness/b.py"}))
        self.assertFalse(t.scope_ambiguous)

    def test_backtick_paths(self):
        t = self._parse_scope("- `src/a.py`\n")
        self.assertEqual(t.scope_paths, frozenset({"src/a.py"}))
        self.assertFalse(t.scope_ambiguous)

    def test_blockquote_note_ignored(self):
        t = self._parse_scope("> repo-relative 경로만 적는다\n\n- src/a.py\n")
        self.assertEqual(t.scope_paths, frozenset({"src/a.py"}))
        self.assertFalse(t.scope_ambiguous)

    def test_empty_placeholder_is_ambiguous(self):
        t = self._parse_scope("-\n")
        self.assertEqual(t.scope_paths, frozenset())
        self.assertTrue(t.scope_ambiguous)
        self.assertTrue(t.serial_only)

    def test_freeform_prose_is_ambiguous(self):
        # 다중 토큰 산문 bullet → 정규화 안 됨 → ambiguous
        t = self._parse_scope("- 사용자 입력 파서 전반\n")
        self.assertTrue(t.scope_ambiguous)
        self.assertTrue(t.serial_only)

    def test_mixed_path_and_prose_is_ambiguous(self):
        t = self._parse_scope("- src/a.py\n- 그리고 여러 곳\n")
        self.assertTrue(t.scope_ambiguous)
        self.assertTrue(t.serial_only)

    def test_nonbullet_prose_plus_path_is_ambiguous(self):
        # codex F7 — bullet 아닌 자유서술 산문 + 유효 path 가 섞이면 정규화 실패 → 미상.
        t = self._parse_scope("핵심 파서 전반을 수정한다\n\n- src/a.py\n")
        self.assertTrue(t.scope_ambiguous)
        self.assertTrue(t.serial_only)

    def test_scope_bullet_inline_comment_stripped(self):
        # 사전 감사 — depends_on 처럼 Scope bullet 의 inline 주석도 strip (일관성).
        t = self._parse_scope("- src/a.py  # 메인 핸들러\n- `src/b.py`  # 코멘트\n")
        self.assertEqual(t.scope_paths, frozenset({"src/a.py", "src/b.py"}))
        self.assertFalse(t.scope_ambiguous)

    def test_directory_scope(self):
        t = self._parse_scope("- src/feature/\n")
        self.assertEqual(t.scope_paths, frozenset({"src/feature/"}))
        self.assertFalse(t.scope_ambiguous)

    def test_dot_prefixed_paths_accepted(self):
        # codex F14 — leading dot 경로(dot-dir / 상대)가 ambiguous 로 오판되면 안 됨.
        t = self._parse_scope(
            "- .github/workflows/ci.yml\n- ./src/a.py\n"
        )
        self.assertEqual(
            t.scope_paths,
            frozenset({".github/workflows/ci.yml", "src/a.py"}),  # ./ 정규화
        )
        self.assertFalse(t.scope_ambiguous)

    def test_dot_placeholder_tokens_still_ambiguous(self):
        # bare . / .. / ... 는 경로가 아니므로 여전히 ambiguous
        for tok in (".", "..", "..."):
            t = self._parse_scope(f"- {tok}\n")
            self.assertTrue(t.scope_ambiguous, f"{tok} 는 ambiguous 여야")

    def test_hyphenated_paths_accepted(self):
        # codex P2 F3 회귀 가드 — 하이픈 포함 경로는 흔함(parallel-policy.md / package-lock.json).
        # ambiguous 로 오판하면 독립 task 가 직렬로 강등돼 병렬 후보 과소탐지.
        t = self._parse_scope(
            "- docs/plugin/parallel-policy.md\n- package-lock.json\n"
        )
        self.assertEqual(
            t.scope_paths,
            frozenset({"docs/plugin/parallel-policy.md", "package-lock.json"}),
        )
        self.assertFalse(t.scope_ambiguous)


class TestParseParallelMarker(unittest.TestCase):
    def test_parallel_serial_forces_serial(self):
        body = (
            "---\ndepends_on: []\nparallel: serial\n---\n\n"
            "## Scope\n\n### 수정 허용\n\n- src/a.py\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write_impl(d, "01-foo.md", body)
            t = parse_impl_task(p)
        self.assertTrue(t.force_serial)
        self.assertTrue(t.serial_only)


class TestHighRisk(unittest.TestCase):
    """codex F11 — 고위험 task 직렬 강제 (정책 §4)."""

    def _parse(self, fm_extra, scope):
        body = (
            f"---\ndepends_on: []\n{fm_extra}---\n\n"
            f"## Scope\n\n### 수정 허용\n\n{scope}\n"
        )
        with tempfile.TemporaryDirectory() as d:
            return parse_impl_task(_write_impl(d, "01-foo.md", body))

    def test_inherent_high_risk_scope_paths(self):
        # 경로 backstop — migrations/alembic/.env/secrets/credentials
        for scope in (
            "- migrations/0007_add.py",
            "- alembic/versions/x.py",
            "- config/.env",
            "- config/.env*",          # codex F15 — glob 변종
            "- config/.env.local",     # suffix 변종
            "- app/secrets/keys.json",
            "- src/credentials.py",
        ):
            t = self._parse("", scope)
            self.assertTrue(t.force_serial, f"{scope} 는 고위험이어야")

    def test_inherent_high_risk_no_false_positive(self):
        # codex F15 — `.environment`·`env_utils` 처럼 무관한 경로는 고위험 아님.
        for scope in ("- .environment/conf.py", "- src/env_utils.py"):
            t = self._parse("", scope)
            self.assertFalse(t.force_serial, f"{scope} 는 고위험 아님")

    def test_risk_frontmatter_marker(self):
        t = self._parse("risk: high-risk\n", "- src/x.py")
        self.assertTrue(t.force_serial)

    def test_risk_frontmatter_canonical_high_forces_serial(self):
        # #703 — 설계 산출물 frontmatter 의 canonical 값 `risk: high` 가 직렬 강등.
        t = self._parse("risk: high\n", "- src/x.py")
        self.assertTrue(t.force_serial)

    def test_risk_frontmatter_normal_low_not_serial(self):
        # #703 — normal/low 는 고위험 아님 → 병렬 후보 유지 (Scope disjoint 전제).
        for val in ("normal", "low"):
            t = self._parse(f"risk: {val}\n", "- src/x.py")
            self.assertFalse(t.force_serial, f"risk: {val} 는 고위험 아님")

    def test_ordinary_scope_not_high_risk(self):
        t = self._parse("", "- src/feature/widget.py")
        self.assertFalse(t.force_serial)

    def test_compute_waves_high_risk_slugs_forces_serial(self):
        # 메인 dry-preview 판정 전달 → 직렬
        tasks = [
            _task("01-a", (), {"a.py"}),
            _task("02-b", (), {"b.py"}),
        ]
        plan = compute_waves(tasks, high_risk_slugs={"02-b"})
        self.assertFalse(plan.has_parallel)
        # 02-b 가 고위험 → 01-a 도 짝 못 찾아 직렬, 순서 보존
        self.assertEqual(
            [s.tasks[0].slug for s in plan.steps], ["01-a", "02-b"]
        )

    def test_high_risk_slug_serial_reason(self):
        tasks = [_task("01-a", (), {"a.py"})]
        plan = compute_waves(tasks, high_risk_slugs={"01-a"})
        self.assertIn("고위험", plan.steps[0].reason)


# ── scopes_disjoint ─────────────────────────────────────────


class TestScopesDisjoint(unittest.TestCase):
    def test_disjoint_files(self):
        self.assertTrue(scopes_disjoint({"a.py"}, {"b.py"}))

    def test_same_file_overlap(self):
        self.assertFalse(scopes_disjoint({"a.py"}, {"a.py"}))

    def test_dir_contains_file_overlap(self):
        self.assertFalse(scopes_disjoint({"src/"}, {"src/a.py"}))

    def test_file_under_dir_overlap(self):
        self.assertFalse(scopes_disjoint({"src/sub/a.py"}, {"src/"}))

    def test_sibling_dirs_disjoint(self):
        self.assertTrue(scopes_disjoint({"src/a/"}, {"src/b/"}))

    def test_glob_overlap(self):
        self.assertFalse(scopes_disjoint({"src/*.py"}, {"src/a.py"}))

    def test_glob_segment_aware(self):
        # codex F4 — `*` 는 `/` 를 넘지 않는다. src/*.py 는 src/sub/a.py 와 disjoint.
        self.assertTrue(scopes_disjoint({"src/*.py"}, {"src/sub/a.py"}))
        self.assertTrue(scopes_disjoint({"src/*.py"}, {"lib/*.js"}))

    def test_glob_glob_same_dir_conservative_overlap(self):
        # glob-vs-glob 같은 디렉토리 → 보수적으로 충돌(직렬) 가정.
        self.assertFalse(scopes_disjoint({"src/*.py"}, {"src/a*"}))

    def test_glob_char_class(self):
        # 사전 감사 — _has_glob 이 `[` 를 glob 으로 인식하므로 _glob_to_regex 도 char
        # class 를 처리해야 함 (리터럴 취급 비일관 수정). segment-aware 유지.
        from harness.parallel_wave import _glob_match
        self.assertTrue(_glob_match("src/a.py", "src/[ab].py"))
        self.assertFalse(_glob_match("src/c.py", "src/[ab].py"))
        self.assertTrue(_glob_match("src/b.py", "src/[!a].py"))  # negation
        self.assertFalse(_glob_match("src/sub/a.py", "src/[ab].py"))  # / 안 넘음
        # 깨진 패턴은 리터럴 fallback (예외 안 남)
        self.assertTrue(_glob_match("src/[x.py", "src/[x.py"))

    def test_globstar_zero_and_deep_dirs(self):
        # codex F8 — src/**/*.py 는 중간 디렉토리 0개(src/a.py)도 매치해야 함.
        from harness.parallel_wave import _path_in_scope
        self.assertTrue(_path_in_scope("src/a.py", {"src/**/*.py"}))
        self.assertTrue(_path_in_scope("src/x/a.py", {"src/**/*.py"}))
        self.assertTrue(_path_in_scope("src/x/y/a.py", {"src/**/*.py"}))
        self.assertFalse(_path_in_scope("lib/a.py", {"src/**/*.py"}))
        # disjoint: src/**/*.py 는 src/a.py 와 겹침(둘 다 src 하위 .py)
        self.assertFalse(scopes_disjoint({"src/**/*.py"}, {"src/a.py"}))


# ── compute_waves ───────────────────────────────────────────


class TestComputeWaves(unittest.TestCase):
    def test_two_independent_disjoint_parallel(self):
        tasks = [
            _task("01-a", (), {"src/a.py"}),
            _task("02-b", (), {"src/b.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertTrue(plan.has_parallel)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].mode, "parallel")
        self.assertEqual(
            {t.slug for t in plan.steps[0].tasks}, {"01-a", "02-b"}
        )

    def test_scope_overlap_serialized(self):
        tasks = [
            _task("01-a", (), {"src/shared.py"}),
            _task("02-b", (), {"src/shared.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertFalse(plan.has_parallel)
        self.assertEqual([s.mode for s in plan.steps], ["serial", "serial"])

    def test_depends_on_chain_is_serial_order(self):
        tasks = [
            _task("01-a", (), {"src/a.py"}),
            _task("02-b", ("01-a",), {"src/b.py"}),
        ]
        plan = compute_waves(tasks)
        # 02-b 가 01-a 에 의존 → 같은 wave 불가 → 직렬 2단계
        self.assertFalse(plan.has_parallel)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].tasks[0].slug, "01-a")
        self.assertEqual(plan.steps[1].tasks[0].slug, "02-b")

    def test_unknown_depends_on_serial_fallback(self):
        tasks = [
            _task("01-a", None, {"src/a.py"}),  # 미상
            _task("02-b", (), {"src/b.py"}),
        ]
        plan = compute_waves(tasks)
        # 01-a 미상 → 직렬, 02-b 는 짝(01-a 직렬)이라 단독 → 직렬
        self.assertFalse(plan.has_parallel)
        self.assertEqual(plan.steps[0].mode, "serial")
        self.assertIn("미상", plan.steps[0].reason)

    def test_ambiguous_scope_serial_fallback(self):
        tasks = [
            _task("01-a", (), set(), scope_ambiguous=True),
            _task("02-b", (), {"src/b.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertFalse(plan.has_parallel)

    def test_max_parallel_cap_two(self):
        # 독립 3개 disjoint, cap=2 → wave(2) + serial(1)
        tasks = [
            _task("01-a", (), {"src/a.py"}),
            _task("02-b", (), {"src/b.py"}),
            _task("03-c", (), {"src/c.py"}),
        ]
        plan = compute_waves(tasks, max_parallel_workers=2)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].mode, "parallel")
        self.assertEqual(len(plan.steps[0].tasks), 2)
        self.assertEqual(plan.steps[1].mode, "serial")
        self.assertEqual(plan.steps[1].tasks[0].slug, "03-c")

    def test_higher_cap_three(self):
        tasks = [
            _task("01-a", (), {"src/a.py"}),
            _task("02-b", (), {"src/b.py"}),
            _task("03-c", (), {"src/c.py"}),
        ]
        plan = compute_waves(tasks, max_parallel_workers=3)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(len(plan.steps[0].tasks), 3)

    def test_force_serial_excluded_from_wave(self):
        tasks = [
            _task("01-a", (), {"src/a.py"}, force_serial=True),
            _task("02-b", (), {"src/b.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertFalse(plan.has_parallel)
        self.assertEqual(plan.steps[0].mode, "serial")

    def test_directory_overlap_serialized(self):
        tasks = [
            _task("01-a", (), {"src/feature/"}),
            _task("02-b", (), {"src/feature/x.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertFalse(plan.has_parallel)

    def test_mixed_wave_then_dependent_serial(self):
        # a,b 독립 병렬 → c 는 둘 다에 의존 → 다음 직렬
        tasks = [
            _task("01-a", (), {"src/a.py"}),
            _task("02-b", (), {"src/b.py"}),
            _task("03-c", ("01-a", "02-b"), {"src/c.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].mode, "parallel")
        self.assertEqual(plan.steps[1].mode, "serial")
        self.assertEqual(plan.steps[1].tasks[0].slug, "03-c")

    def test_external_dependency_not_blocking(self):
        # depends_on 이 batch 밖(이미 머지됨) → 차단 안 함
        tasks = [
            _task("02-a", ("00-merged",), {"src/a.py"}),
            _task("03-b", ("00-merged",), {"src/b.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertTrue(plan.has_parallel)

    def test_empty_task_list(self):
        plan = compute_waves([])
        self.assertEqual(plan.steps, ())
        self.assertFalse(plan.has_parallel)

    def test_default_cap_is_two(self):
        self.assertEqual(DEFAULT_MAX_PARALLEL_WORKERS, 2)

    def test_order_barrier_serial_task_between(self):
        # codex F10 — 사이의 serial task(02)를 건너뛰고 01,03 을 같은 wave 로 당기면
        # task_index 순서가 뒤집혀 issue close semantics 가 깨진다. 순서 보존 필수.
        tasks = [
            _task("01-a", (), {"a.py"}),
            _task("02-b", (), {"b.py"}, force_serial=True),
            _task("03-c", (), {"c.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertFalse(plan.has_parallel)  # [01,03] 병렬 금지
        self.assertEqual(
            [s.tasks[0].slug for s in plan.steps], ["01-a", "02-b", "03-c"]
        )

    def test_order_barrier_blocked_intervening_task(self):
        # codex F13 — 사이 task(02)가 *blocked*(미준비)면 frontier 에서 빠진다. 그래도
        # 01,03 을 같은 wave 로 당기면 안 됨(03 이 02 앞서 머지 → 순서 위반). 01 단독 후
        # 02 준비되면 진행.
        tasks = [
            _task("01-a", (), {"a.py"}),
            _task("02-b", ("01-a",), {"b.py"}),  # 01-a 에 의존 → 처음엔 blocked
            _task("03-c", (), {"c.py"}),
        ]
        plan = compute_waves(tasks)
        # 첫 step 에 03-c 가 01-a 와 함께 들어가면 안 됨
        first = {t.slug for t in plan.steps[0].tasks}
        self.assertNotIn("03-c", first)
        self.assertEqual(plan.steps[0].tasks[0].slug, "01-a")
        # 03-c 는 02-b 보다 먼저/같이 머지되면 안 됨 — 03-c 의 step 이 02-b step 이후거나 동일 wave 의 뒤
        order = [t.slug for s in plan.steps for t in s.tasks]
        self.assertLess(order.index("02-b"), order.index("03-c"))

    def test_order_barrier_scope_overlap_between(self):
        # 02 가 01 과 Scope 겹침 → 01 직렬 barrier, 그 다음 02‖03 (순서 보존).
        tasks = [
            _task("01-a", (), {"shared.py"}),
            _task("02-b", (), {"shared.py"}),
            _task("03-c", (), {"c.py"}),
        ]
        plan = compute_waves(tasks)
        self.assertEqual(plan.steps[0].mode, "serial")
        self.assertEqual(plan.steps[0].tasks[0].slug, "01-a")
        self.assertEqual(plan.steps[1].mode, "parallel")
        self.assertEqual(
            [t.slug for t in plan.steps[1].tasks], ["02-b", "03-c"]
        )

    def test_block_depends_on_comment_does_not_parallelize_dependent(self):
        # codex P2 F1 통합 — block depends_on 의 inline 주석이 slug 에 새면 의존이
        # 끊겨 의존 task 가 선행과 같은 wave 로 올라간다. parse→compute 로 방지 검증.
        with tempfile.TemporaryDirectory() as d:
            _write_impl(
                d,
                "01-a.md",
                "---\ndepends_on: []\n---\n\n## Scope\n\n### 수정 허용\n\n- src/a.py\n",
            )
            _write_impl(
                d,
                "02-b.md",
                "---\ndepends_on:\n  - 01-a  # produces shared contract\n---\n\n"
                "## Scope\n\n### 수정 허용\n\n- src/b.py\n",
            )
            a = parse_impl_task(Path(d) / "01-a.md")
            b = parse_impl_task(Path(d) / "02-b.md")
        self.assertEqual(b.depends_on, ("01-a",))
        plan = compute_waves([a, b])
        # 02-b 가 01-a 에 의존 → 절대 같은 wave 가 아니어야 함 (직렬 2단계).
        self.assertFalse(plan.has_parallel)
        self.assertEqual(plan.steps[0].tasks[0].slug, "01-a")
        self.assertEqual(plan.steps[1].tasks[0].slug, "02-b")


# ── fan_in_check ────────────────────────────────────────────


class TestFanInCheck(unittest.TestCase):
    def test_expected_slugs_required(self):
        results = [
            WorkerResult("01-a", frozenset({"src/a.py"}), frozenset({"src/a.py"})),
        ]
        with self.assertRaises(TypeError):
            fan_in_check(results)

    def test_clean_wave_passes(self):
        results = [
            WorkerResult("01-a", frozenset({"src/a.py"}), frozenset({"src/a.py"})),
            WorkerResult("02-b", frozenset({"src/b.py"}), frozenset({"src/b.py"})),
        ]
        r = fan_in_check(results, expected_slugs=("01-a", "02-b"))
        self.assertTrue(r.passed)
        self.assertEqual(r.verdict, "PASS")
        self.assertEqual(r.reasons, ())

    def test_scope_violation_fallback(self):
        results = [
            # a 가 선언 scope(src/a.py) 밖 src/other.py 를 건드림
            WorkerResult(
                "01-a",
                frozenset({"src/a.py", "src/other.py"}),
                frozenset({"src/a.py"}),
            ),
        ]
        r = fan_in_check(results, expected_slugs=("01-a",))
        self.assertFalse(r.passed)
        self.assertEqual(r.verdict, "FALLBACK")
        self.assertIn(("01-a", "src/other.py"), r.scope_violations)

    def test_cross_worker_conflict_fallback(self):
        results = [
            WorkerResult(
                "01-a", frozenset({"src/shared.py"}), frozenset({"src/shared.py"})
            ),
            WorkerResult(
                "02-b", frozenset({"src/shared.py"}), frozenset({"src/shared.py"})
            ),
        ]
        r = fan_in_check(results, expected_slugs=("01-a", "02-b"))
        self.assertFalse(r.passed)
        self.assertEqual(len(r.conflicts), 1)
        self.assertEqual(r.conflicts[0][0], "src/shared.py")
        self.assertEqual(r.conflicts[0][1], ("01-a", "02-b"))

    def test_missing_evidence_fallback(self):
        results = [
            WorkerResult(
                "01-a",
                frozenset({"src/a.py"}),
                frozenset({"src/a.py"}),
                evidence_present=False,
            ),
        ]
        r = fan_in_check(results, expected_slugs=("01-a",))
        self.assertFalse(r.passed)
        self.assertEqual(r.missing_evidence, ("01-a",))

    def test_empty_worker_results_fallback(self):
        # worker 결과 수집 자체가 실패했는데 빈 입력을 PASS 로 보면 안 됨.
        r = fan_in_check([], expected_slugs=())
        self.assertFalse(r.passed)
        self.assertEqual(r.verdict, "FALLBACK")
        self.assertIn("worker 결과 없음", r.reasons)

    def test_missing_expected_worker_result_fallback(self):
        # 2-worker wave 에서 한 worker 결과 record 가 통째로 누락된 경우도 evidence 누락.
        results = [
            WorkerResult("01-a", frozenset({"src/a.py"}), frozenset({"src/a.py"})),
        ]
        r = fan_in_check(results, expected_slugs=("01-a", "02-b"))
        self.assertFalse(r.passed)
        self.assertEqual(r.missing_evidence, ("02-b",))
        self.assertIn("evidence 누락 1건", r.reasons)

    def test_expected_worker_and_flagged_missing_deduped(self):
        # expected 에도 있고 evidence_present=False 인 경우 missing_evidence 중복 방지.
        results = [
            WorkerResult(
                "01-a",
                frozenset({"src/a.py"}),
                frozenset({"src/a.py"}),
                evidence_present=False,
            ),
        ]
        r = fan_in_check(results, expected_slugs=("01-a",))
        self.assertFalse(r.passed)
        self.assertEqual(r.missing_evidence, ("01-a",))

    def test_unexpected_worker_result_fallback(self):
        # wave 밖 worker 결과가 섞이면 identity 오류라 fan-in 을 통과하면 안 됨.
        results = [
            WorkerResult("01-a", frozenset({"src/a.py"}), frozenset({"src/a.py"})),
            WorkerResult("02-b", frozenset({"src/b.py"}), frozenset({"src/b.py"})),
            WorkerResult("99-z", frozenset({"src/z.py"}), frozenset({"src/z.py"})),
        ]
        r = fan_in_check(results, expected_slugs=("01-a", "02-b"))
        self.assertFalse(r.passed)
        self.assertEqual(r.unexpected_workers, ("99-z",))
        self.assertIn("예상 밖 worker 1건", r.reasons)

    def test_scope_dir_prefix_allowed(self):
        # 선언 scope 가 디렉토리면 그 아래 파일 변경은 준수
        results = [
            WorkerResult(
                "01-a", frozenset({"src/feature/x.py"}), frozenset({"src/feature/"})
            ),
        ]
        r = fan_in_check(results, expected_slugs=("01-a",))
        self.assertTrue(r.passed)

    def test_file_scope_no_descendant(self):
        # codex F12 — 확장자 없는 파일 scope(scripts/tool)를 디렉토리로 오인해
        # scripts/tool/x.py 를 통과시키면 안 됨. 디렉토리는 끝에 / 를 적어야 함.
        violator = WorkerResult(
            "01-a", frozenset({"scripts/tool/x.py"}), frozenset({"scripts/tool"})
        )
        self.assertFalse(
            fan_in_check([violator], expected_slugs=("01-a",)).passed
        )
        exact = WorkerResult(
            "02-b", frozenset({"scripts/tool"}), frozenset({"scripts/tool"})
        )
        self.assertTrue(fan_in_check([exact], expected_slugs=("02-b",)).passed)
        # 명시적 디렉토리 scope(끝 /)는 하위 허용
        dir_ok = WorkerResult(
            "03-c", frozenset({"scripts/tool/x.py"}), frozenset({"scripts/tool/"})
        )
        self.assertTrue(fan_in_check([dir_ok], expected_slugs=("03-c",)).passed)

    def test_glob_scope_segment_aware_violation(self):
        # codex F4 — glob scope `src/*.py` 선언했는데 src/sub/a.py 를 건드리면
        # fnmatch 였다면 통과했을 것. segment-aware 라 scope 이탈로 잡아야 함.
        violator = WorkerResult(
            "01-a", frozenset({"src/sub/a.py"}), frozenset({"src/*.py"})
        )
        self.assertFalse(
            fan_in_check([violator], expected_slugs=("01-a",)).passed
        )
        # 같은 glob scope 의 직접 자식은 준수
        ok = WorkerResult(
            "02-b", frozenset({"src/a.py"}), frozenset({"src/*.py"})
        )
        self.assertTrue(fan_in_check([ok], expected_slugs=("02-b",)).passed)


class TestWavePlanFromPaths(unittest.TestCase):
    """경로 인자 전개 — 디렉토리 / 절대 glob / 상대 glob (codex F5)."""

    def _make_two(self, d):
        _write_impl(
            d, "01-a.md",
            "---\ndepends_on: []\n---\n\n## Scope\n\n### 수정 허용\n\n- src/a.py\n",
        )
        _write_impl(
            d, "02-b.md",
            "---\ndepends_on: []\n---\n\n## Scope\n\n### 수정 허용\n\n- src/b.py\n",
        )

    def test_directory_arg(self):
        from harness.parallel_wave import wave_plan_from_paths
        with tempfile.TemporaryDirectory() as d:
            self._make_two(d)
            plan = wave_plan_from_paths([d])
            self.assertTrue(plan.has_parallel)

    def test_absolute_glob_does_not_crash(self):
        # codex F5 — 절대경로 glob 은 Path('.').glob 에서 NotImplementedError 였음.
        from harness.parallel_wave import wave_plan_from_paths
        with tempfile.TemporaryDirectory() as d:
            self._make_two(d)
            plan = wave_plan_from_paths([str(Path(d) / "*.md")])
            self.assertEqual(len(plan.steps), 1)
            self.assertEqual(plan.steps[0].mode, "parallel")

    def test_explicit_file_list(self):
        from harness.parallel_wave import wave_plan_from_paths
        with tempfile.TemporaryDirectory() as d:
            self._make_two(d)
            plan = wave_plan_from_paths(
                [str(Path(d) / "01-a.md"), str(Path(d) / "02-b.md")]
            )
            self.assertTrue(plan.has_parallel)


# ── 직렬 강등 사유 진단 (#693) ───────────────────────────────


class TestSerialCause(unittest.TestCase):
    """#693 — 직렬 강등 사유의 기계 판독 분류 (형식 미정규화 vs 의도/의존)."""

    def test_scope_unnormalized_cause(self):
        t = _task("01-a", (), set(), scope_ambiguous=True)
        self.assertEqual(t.serial_cause, "scope_unnormalized")

    def test_empty_scope_is_scope_unnormalized(self):
        t = _task("01-a", (), set())  # 경로 없음
        self.assertEqual(t.serial_cause, "scope_unnormalized")

    def test_unknown_deps_cause(self):
        t = _task("01-a", None, {"src/a.py"})  # depends_on 미상
        self.assertEqual(t.serial_cause, "unknown_deps")

    def test_forced_cause(self):
        t = _task("01-a", (), {"src/a.py"}, force_serial=True)
        self.assertEqual(t.serial_cause, "forced")

    def test_parallel_capable_has_no_cause(self):
        t = _task("01-a", (), {"src/a.py"})
        self.assertIsNone(t.serial_cause)

    def test_cause_precedence_forced_over_scope(self):
        # 의도적 직렬이 우선 — 형식 잡음 안 냄.
        t = _task("01-a", (), set(), scope_ambiguous=True, force_serial=True)
        self.assertEqual(t.serial_cause, "forced")

    def test_cause_precedence_unknown_deps_over_scope(self):
        t = _task("01-a", None, set(), scope_ambiguous=True)
        self.assertEqual(t.serial_cause, "unknown_deps")

    def test_serial_cause_and_reason_consistent(self):
        # serial_cause(코드)와 serial_reason(문장)은 같은 조건에서 동시에 None/non-None.
        for t in (
            _task("a", (), {"x.py"}),                      # 병렬 가능
            _task("b", None, {"x.py"}),                    # 미상
            _task("c", (), set(), scope_ambiguous=True),   # 형식
            _task("d", (), {"x.py"}, force_serial=True),   # forced
        ):
            self.assertEqual(
                t.serial_cause is None, t.serial_reason is None, msg=t.slug
            )


class TestWaveStepCause(unittest.TestCase):
    """#693 — WaveStep 에 기계 판독 cause 부여 + to_dict 노출."""

    def _step_for(self, plan, slug):
        return next(s for s in plan.steps if any(t.slug == slug for t in s.tasks))

    def test_parallel_step_cause(self):
        plan = compute_waves([
            _task("01-a", (), {"a.py"}),
            _task("02-b", (), {"b.py"}),
        ])
        self.assertEqual(plan.steps[0].mode, "parallel")
        self.assertEqual(plan.steps[0].cause, "parallel")
        self.assertEqual(plan.steps[0].to_dict()["cause"], "parallel")

    def test_scope_unnormalized_step_cause(self):
        plan = compute_waves([
            _task("01-a", (), set(), scope_ambiguous=True),
            _task("02-b", (), {"b.py"}),
        ])
        a = self._step_for(plan, "01-a")
        self.assertEqual(a.mode, "serial")
        self.assertEqual(a.cause, "scope_unnormalized")

    def test_unknown_deps_step_cause(self):
        plan = compute_waves([
            _task("01-a", None, {"a.py"}),
            _task("02-b", (), {"b.py"}),
        ])
        self.assertEqual(self._step_for(plan, "01-a").cause, "unknown_deps")

    def test_forced_step_cause(self):
        plan = compute_waves([
            _task("01-a", (), {"a.py"}, force_serial=True),
            _task("02-b", (), {"b.py"}),
        ])
        self.assertEqual(self._step_for(plan, "01-a").cause, "forced")

    def test_high_risk_step_cause(self):
        plan = compute_waves(
            [_task("01-a", (), {"a.py"})], high_risk_slugs={"01-a"}
        )
        self.assertEqual(plan.steps[0].cause, "high_risk")

    def test_dependency_chain_cause_not_format(self):
        # 의존 사슬 — 형식 멀쩡, 짝 없어 직렬. format 사유 아님.
        plan = compute_waves([
            _task("01-a", (), {"a.py"}),
            _task("02-b", ("01-a",), {"b.py"}),
        ])
        self.assertFalse(plan.has_parallel)
        for s in plan.steps:
            self.assertNotEqual(s.cause, "scope_unnormalized")
            self.assertEqual(s.cause, "no_disjoint_pair")


class TestWavePlanSerialDiagnostics(unittest.TestCase):
    """#693 — wave-plan 집계 (소비측 dry preview 안내 입력)."""

    def test_all_format_unnormalized(self):
        # youTubeGenerator 실증 축약 — 전부 라벨/산문 형식 → 전부 형식 직렬.
        plan = compute_waves([
            _task("01-a", (), set(), scope_ambiguous=True),
            _task("02-b", (), set(), scope_ambiguous=True),
            _task("03-c", (), set(), scope_ambiguous=True),
        ])
        d = plan.to_dict()
        self.assertFalse(d["has_parallel"])
        self.assertEqual(
            sorted(d["format_unnormalized_slugs"]), ["01-a", "02-b", "03-c"]
        )
        self.assertTrue(
            all(x["cause"] == "scope_unnormalized" for x in d["serial_demotions"])
        )

    def test_dependency_serial_not_flagged_as_format(self):
        plan = compute_waves([
            _task("01-a", (), {"a.py"}),
            _task("02-b", ("01-a",), {"b.py"}),
        ])
        d = plan.to_dict()
        self.assertEqual(d["format_unnormalized_slugs"], [])
        causes = {x["cause"] for x in d["serial_demotions"]}
        self.assertNotIn("scope_unnormalized", causes)

    def test_parallel_step_excluded_from_demotions(self):
        plan = compute_waves([
            _task("01-a", (), {"a.py"}),
            _task("02-b", (), {"b.py"}),
        ])
        d = plan.to_dict()
        self.assertTrue(d["has_parallel"])
        self.assertEqual(d["serial_demotions"], [])
        self.assertEqual(d["format_unnormalized_slugs"], [])

    def test_demotion_entry_shape(self):
        plan = compute_waves([_task("01-a", (), set(), scope_ambiguous=True)])
        entry = plan.to_dict()["serial_demotions"][0]
        self.assertEqual(entry["slug"], "01-a")
        self.assertEqual(entry["cause"], "scope_unnormalized")
        self.assertIn("미정규화", entry["reason"])

    def test_mixed_format_and_dependency(self):
        # 형식 직렬(03) + 의존 직렬(01,02) 혼재 — 형식만 집계.
        plan = compute_waves([
            _task("01-a", (), {"a.py"}),
            _task("02-b", ("01-a",), {"b.py"}),
            _task("03-c", (), set(), scope_ambiguous=True),
        ])
        d = plan.to_dict()
        self.assertEqual(d["format_unnormalized_slugs"], ["03-c"])

    def test_format_normalized_paths_enable_parallel(self):
        # AC1 회귀 — 규격(순수 경로) 형식이면 의존 독립 task 가 병렬 후보로 잡힌다.
        plan = compute_waves([
            _task("01-a", (), {"src/a.py"}),
            _task("02-b", (), {"src/b.py"}),
        ])
        d = plan.to_dict()
        self.assertTrue(d["has_parallel"])
        self.assertEqual(d["format_unnormalized_slugs"], [])


if __name__ == "__main__":
    unittest.main()
