"""test_chain_view — impl-loop chain 진행 뷰 자동 렌더 코어 단위 테스트 (#755).

진행 뷰 규칙 SSOT = skills/impl-loop/SKILL.md "진행 뷰 (task 리스트)" 절.
본 테스트는 그 규칙(엔진별 sub-step / 마감 acceptance / task 총수 분기 /
완료-현재-예정 마킹)이 코드에 동일하게 옮겨졌는지 검증한다 (새 규칙 도입 X).

검증 축:

    substeps_for (AC: 현재 sub-step 펼침 — 엔진별):
        - build-worker(2) / build-worker-deep(3) / full-4(4) / advanced(5)
        - 엔진 별칭 정규화 (2agent/4agent 등)
        - 마감 acceptance: story +1 / epic +2 / None +0

    redraw_strategy (AC: task 총수별 분기):
        - <=10 full / 11~20 partial / >20 minimal (경계 10/11/20/21)

    render_view (AC: 완료 한 줄 / 현재 펼침 / 예정 대기):
        - 완료 task 글리프(✓) 한 줄
        - 현재 task 글리프(▾) + sub-step 펼침
        - 예정 task 글리프(○) 대기 줄

    transition_operations (AC: 다시 그리기 분기 — 비용):
        - full = 4 단계 (sub-step del → header complete → tail del → 재생성)
        - partial = 3 단계 (재생성 skip — 다음 헤더만 in_progress)
        - minimal = 2 단계 (sub-step del + 다음 헤더 in_progress)

    build_chain_view / parse_tasks (AC: helper 산출 + 폴백):
        - JSON-ish 입력 파싱 → payload
        - 순수 변환(run state mutation 없음 — 도구이지 게이트 아님)
"""
import unittest

from harness.chain_view import (
    ChainTask,
    MAIN_OWNED_SUBSTEPS,
    build_chain_view,
    initial_operations,
    normalize_engine,
    parse_tasks,
    redraw_strategy,
    render_view,
    substeps_for,
    transition_operations,
)


def _task(name, engine="build-worker", closes=None):
    return ChainTask(name=name, engine=normalize_engine(engine), closes=closes)


class TestSubsteps(unittest.TestCase):
    """엔진별 sub-step 펼침 + 마감 acceptance (SKILL line 435)."""

    def test_build_worker_two_substeps(self):
        self.assertEqual(
            substeps_for(_task("m", "build-worker")),
            ["build-worker", "pr-reviewer"],
        )

    def test_build_worker_deep_three_substeps(self):
        self.assertEqual(
            substeps_for(_task("m", "build-worker-deep")),
            ["module-architect", "build-worker", "pr-reviewer"],
        )

    def test_full_four_substeps(self):
        self.assertEqual(
            substeps_for(_task("m", "full-4")),
            ["test-engineer", "engineer:IMPL", "code-validator", "pr-reviewer"],
        )

    def test_advanced_five_substeps(self):
        self.assertEqual(
            substeps_for(_task("m", "advanced")),
            [
                "module-architect",
                "test-engineer",
                "engineer:IMPL",
                "code-validator",
                "pr-reviewer",
            ],
        )

    def test_engine_aliases(self):
        self.assertEqual(normalize_engine("2agent"), "build-worker")
        self.assertEqual(normalize_engine("4agent"), "full-4")
        self.assertEqual(normalize_engine("3agent"), "build-worker-deep")
        self.assertEqual(normalize_engine("advanced-fallback"), "advanced")
        self.assertEqual(normalize_engine("impl-ui-design-loop"), "ui")
        self.assertEqual(normalize_engine("ui-build-worker"), "ui-build-worker")
        self.assertEqual(normalize_engine("ui-3agent"), "ui-build-worker-deep")
        self.assertEqual(normalize_engine("ui-advanced"), "ui-advanced")
        # case-insensitive + whitespace
        self.assertEqual(normalize_engine("  Build-Worker "), "build-worker")

    def test_ui_loop_substeps(self):
        # impl-ui-design-loop — canvas-design 선두 + full-4.
        # 사용자 PICK 은 draft 생성 시 canvas-design 내부 조건부 절차다.
        self.assertEqual(
            substeps_for(_task("m", "ui")),
            [
                "canvas-design",
                "test-engineer",
                "engineer:IMPL",
                "code-validator",
                "pr-reviewer",
            ],
        )

    def test_ui_build_worker_substeps(self):
        # UI 기준 확보는 engine 무관 — build-worker 앞에도 같은 canvas-design 절차가 붙는다.
        self.assertEqual(
            substeps_for(_task("m", "ui-build-worker")),
            [
                "canvas-design",
                "build-worker",
                "pr-reviewer",
            ],
        )

    def test_ui_build_worker_deep_substeps(self):
        self.assertEqual(
            substeps_for(_task("m", "ui-build-worker-deep")),
            [
                "module-architect",
                "canvas-design",
                "build-worker",
                "pr-reviewer",
            ],
        )

    def test_ui_advanced_substeps(self):
        # UI + deep 보강 — canvas-design 앞 module-architect.
        self.assertEqual(
            substeps_for(_task("m", "ui-advanced")),
            [
                "module-architect",
                "canvas-design",
                "test-engineer",
                "engineer:IMPL",
                "code-validator",
                "pr-reviewer",
            ],
        )

    def test_canvas_design_is_main_owned_progress_checkpoint(self):
        self.assertIn("canvas-design", MAIN_OWNED_SUBSTEPS)
        self.assertNotIn("designer", MAIN_OWNED_SUBSTEPS)

    def test_explicit_substeps_override(self):
        # engine preset 이 enum 하지 않은 변종을 명시 라벨로 표현 (escape hatch).
        t = ChainTask(name="m", substeps=("designer", "사용자 PICK", "engineer:IMPL"))
        self.assertEqual(
            substeps_for(t), ["designer", "사용자 PICK", "engineer:IMPL"]
        )

    def test_explicit_substeps_with_closing_appends_acceptance(self):
        t = ChainTask(
            name="m", substeps=("designer", "engineer:IMPL"), closes="story"
        )
        self.assertEqual(
            substeps_for(t),
            ["designer", "engineer:IMPL", "product-acceptance"],
        )

    def test_empty_substeps_override_rejected(self):
        with self.assertRaises(ValueError):
            ChainTask(name="m", substeps=())

    def test_unknown_engine_rejected(self):
        with self.assertRaises(ValueError):
            normalize_engine("nonsense-engine")

    def test_story_closing_appends_one_acceptance(self):
        steps = substeps_for(_task("m", "build-worker", closes="story"))
        self.assertEqual(
            steps, ["build-worker", "pr-reviewer", "product-acceptance"]
        )

    def test_epic_closing_appends_two_acceptance(self):
        steps = substeps_for(_task("m", "full-4", closes="epic"))
        self.assertEqual(
            steps,
            [
                "test-engineer",
                "engineer:IMPL",
                "code-validator",
                "pr-reviewer",
                "product-acceptance:STORY",
                "product-acceptance:EPIC",
            ],
        )

    def test_no_close_no_acceptance(self):
        steps = substeps_for(_task("m", "build-worker", closes=None))
        self.assertNotIn("product-acceptance", steps)


class TestRedrawStrategy(unittest.TestCase):
    """task 총수별 다시그리기 분기 (SKILL lines 438-442)."""

    def test_small_full(self):
        self.assertEqual(redraw_strategy(1), "full")
        self.assertEqual(redraw_strategy(10), "full")

    def test_medium_partial(self):
        self.assertEqual(redraw_strategy(11), "partial")
        self.assertEqual(redraw_strategy(20), "partial")

    def test_large_minimal(self):
        self.assertEqual(redraw_strategy(21), "minimal")
        self.assertEqual(redraw_strategy(50), "minimal")


class TestRenderView(unittest.TestCase):
    """완료 한 줄 / 현재 펼침 / 예정 대기 (SKILL lines 425-433)."""

    def setUp(self):
        self.tasks = [
            _task("alpha", "build-worker"),
            _task("beta", "full-4"),
            _task("gamma", "build-worker"),
        ]

    def test_completed_one_line(self):
        view = render_view(self.tasks, current=1)
        lines = view.splitlines()
        self.assertEqual(lines[0], "✓ task1 · alpha")
        # 완료 task 는 sub-step 펼치지 않는다
        self.assertNotIn("test-engineer", lines[0])

    def test_current_expanded(self):
        view = render_view(self.tasks, current=1)
        self.assertIn("▾ task2 · beta", view)
        self.assertIn("   ㄴ test-engineer", view)
        self.assertIn("   ㄴ pr-reviewer", view)

    def test_pending_waiting_line(self):
        view = render_view(self.tasks, current=1)
        lines = view.splitlines()
        self.assertIn("○ task3 · gamma", lines)
        # 예정 task 는 sub-step 펼치지 않는다
        self.assertEqual(sum(1 for ln in lines if "gamma" in ln), 1)

    def test_terminal_all_completed(self):
        view = render_view(self.tasks, current=3)
        self.assertEqual(
            view.splitlines(),
            ["✓ task1 · alpha", "✓ task2 · beta", "✓ task3 · gamma"],
        )

    def test_current_substeps_include_acceptance(self):
        tasks = [
            _task("alpha", "build-worker"),
            _task("omega", "build-worker", closes="epic"),
        ]
        view = render_view(tasks, current=1)
        self.assertIn("   ㄴ product-acceptance:STORY", view)
        self.assertIn("   ㄴ product-acceptance:EPIC", view)


class TestTransitionOperations(unittest.TestCase):
    """다시 그리기 단계 분기 (SKILL line 444)."""

    def _tasks(self, n):
        return [_task(f"m{i}", "build-worker") for i in range(n)]

    def test_full_four_steps(self):
        tasks = self._tasks(3)  # total 3 → full
        ops = transition_operations(tasks, prev=0, current=1)
        kinds = [o["op"] for o in ops]
        # ① delete_substeps(prev) ② complete_header(prev)
        self.assertEqual(kinds[0], "delete_substeps")
        self.assertEqual(ops[0]["index"], 0)
        self.assertEqual(kinds[1], "complete_header")
        self.assertEqual(ops[1]["index"], 0)
        # ③ tail headers deleted (current..end)
        self.assertIn("delete_header", kinds)
        deleted = [o["index"] for o in ops if o["op"] == "delete_header"]
        self.assertEqual(sorted(deleted), [1, 2])
        # ④ recreate: current header in_progress + its substeps + remaining pending
        creates = [o for o in ops if o["op"] == "create_header"]
        self.assertEqual(creates[0]["index"], 1)
        self.assertEqual(creates[0]["status"], "in_progress")
        self.assertTrue(
            any(o["op"] == "create_substep" and o["index"] == 1 for o in ops)
        )
        # 남은 헤더(task3)는 pending 으로 재생성
        self.assertTrue(
            any(c["index"] == 2 and c["status"] == "pending" for c in creates)
        )

    def test_partial_three_steps_no_regenerate(self):
        tasks = self._tasks(15)  # total 15 → partial
        ops = transition_operations(tasks, prev=0, current=1)
        kinds = [o["op"] for o in ops]
        self.assertEqual(
            kinds, ["delete_substeps", "complete_header", "set_in_progress"]
        )
        # 재생성 skip → delete_header / create_header 없음
        self.assertNotIn("delete_header", kinds)
        self.assertNotIn("create_header", kinds)
        self.assertEqual(ops[2]["index"], 1)

    def test_minimal_completes_prev_no_accumulation(self):
        # 최소 갱신도 prev 를 완료(✓) 마킹한다 — 생략 시 경계마다 in_progress 누적.
        tasks = self._tasks(25)  # total 25 → minimal
        ops = transition_operations(tasks, prev=0, current=1)
        kinds = [o["op"] for o in ops]
        self.assertEqual(
            kinds, ["delete_substeps", "complete_header", "set_in_progress"]
        )
        self.assertEqual(ops[1]["op"], "complete_header")
        self.assertEqual(ops[1]["index"], 0)
        # 비-마감 minimal 은 sub-step 미펼침.
        self.assertFalse(any(o["op"] == "create_substep" for o in ops))

    def test_no_accumulation_across_boundaries(self):
        # 연속 경계 — 매번 직전 task 가 완료 마킹되는지 (누적 in_progress 차단).
        tasks = self._tasks(30)  # minimal
        for i in range(1, 30):
            ops = transition_operations(tasks, prev=i - 1, current=i)
            self.assertTrue(
                any(
                    o["op"] == "complete_header" and o["index"] == i - 1
                    for o in ops
                ),
                f"경계 {i - 1}→{i} 에서 prev 완료 마킹 누락",
            )

    def test_closing_task_expands_substeps_even_in_large_chain(self):
        # 마감 task 는 chain 크기와 무관하게 sub-step(product-acceptance 포함) 펼침.
        tasks = [_task(f"m{i}", "build-worker") for i in range(24)]
        tasks.append(
            _task("final", "build-worker", closes="epic")
        )  # total 25 → minimal
        ops = transition_operations(tasks, prev=23, current=24)
        labels = [o["label"] for o in ops if o["op"] == "create_substep"]
        self.assertIn("product-acceptance:STORY", labels)
        self.assertIn("product-acceptance:EPIC", labels)
        # 마감 경계는 재생성 경로 → create_header 존재.
        self.assertTrue(any(o["op"] == "create_header" for o in ops))

    def test_non_adjacent_transition_rejected(self):
        # 비인접 prev/current 는 view ≡ operations 위반 → 거부 (임의 점프는 initial).
        tasks = self._tasks(5)
        with self.assertRaises(ValueError):
            transition_operations(tasks, prev=0, current=2)
        with self.assertRaises(ValueError):
            transition_operations(tasks, prev=0, current=5)  # terminal 점프
        with self.assertRaises(ValueError):
            transition_operations(tasks, prev=2, current=2)  # 동일

    def test_terminal_transition_completes_last(self):
        tasks = self._tasks(3)
        ops = transition_operations(tasks, prev=2, current=3)
        kinds = [o["op"] for o in ops]
        # 마지막 task 완료 — 다음 헤더 없음
        self.assertIn("delete_substeps", kinds)
        self.assertIn("complete_header", kinds)
        self.assertFalse(any(o["op"] == "set_in_progress" for o in ops))
        self.assertFalse(any(o["op"] == "create_header" for o in ops))

    def test_full_marks_closing_acceptance_substeps(self):
        tasks = [
            _task("a", "build-worker"),
            _task("z", "build-worker", closes="story"),
        ]
        ops = transition_operations(tasks, prev=0, current=1)
        substep_labels = [
            o["label"] for o in ops if o["op"] == "create_substep"
        ]
        self.assertIn("product-acceptance", substep_labels)


class TestInitialOperations(unittest.TestCase):
    """chain 진입 시 전체 task list 최초 생성."""

    def test_initial_creates_all_headers(self):
        tasks = [_task(f"m{i}", "build-worker") for i in range(3)]
        ops = initial_operations(tasks, current=0)
        creates = [o for o in ops if o["op"] == "create_header"]
        self.assertEqual([c["index"] for c in creates], [0, 1, 2])
        self.assertEqual(creates[0]["status"], "in_progress")
        self.assertEqual(creates[1]["status"], "pending")
        # current(0) 만 substep 펼침
        sub_idx = {o["index"] for o in ops if o["op"] == "create_substep"}
        self.assertEqual(sub_idx, {0})

    def test_initial_with_nonzero_current_marks_prior_completed(self):
        tasks = [_task(f"m{i}", "build-worker") for i in range(3)]
        ops = initial_operations(tasks, current=1)
        creates = {o["index"]: o["status"] for o in ops if o["op"] == "create_header"}
        self.assertEqual(creates[0], "completed")
        self.assertEqual(creates[1], "in_progress")
        self.assertEqual(creates[2], "pending")


class TestBuildChainViewAndParse(unittest.TestCase):
    """helper 산출 payload + JSON 입력 파싱 + 순수성(폴백 보장)."""

    SAMPLE = {
        "tasks": [
            {"name": "alpha", "engine": "2agent"},
            {"name": "beta", "engine": "4agent"},
            {"name": "gamma", "engine": "build-worker", "closes": "story"},
        ],
        "current": 1,
    }

    def test_parse_tasks(self):
        tasks = parse_tasks(self.SAMPLE["tasks"])
        self.assertEqual([t.name for t in tasks], ["alpha", "beta", "gamma"])
        self.assertEqual(tasks[0].engine, "build-worker")
        self.assertEqual(tasks[1].engine, "full-4")
        self.assertEqual(tasks[2].closes, "story")

    def test_build_transition_payload(self):
        tasks = parse_tasks(self.SAMPLE["tasks"])
        payload = build_chain_view(tasks, current=1)
        self.assertEqual(payload["task_total"], 3)
        self.assertEqual(payload["current_index"], 1)
        self.assertEqual(payload["strategy"], "full")
        self.assertEqual(payload["operation_mode"], "transition")
        self.assertIn("▾ task2 · beta", payload["view"])
        self.assertEqual(
            payload["current_substeps"],
            ["test-engineer", "engineer:IMPL", "code-validator", "pr-reviewer"],
        )
        self.assertTrue(payload["operations"])

    def test_build_initial_payload(self):
        tasks = parse_tasks(self.SAMPLE["tasks"])
        payload = build_chain_view(tasks, current=0, initial=True)
        self.assertEqual(payload["operation_mode"], "initial")
        self.assertTrue(
            any(o["op"] == "create_header" for o in payload["operations"])
        )

    def test_current_zero_defaults_to_initial(self):
        tasks = parse_tasks(self.SAMPLE["tasks"])
        payload = build_chain_view(tasks, current=0)
        # current=0 은 transition prev 가 없으므로 initial 로 폴백
        self.assertEqual(payload["operation_mode"], "initial")

    def test_explicit_prev_override(self):
        tasks = parse_tasks(self.SAMPLE["tasks"])
        payload = build_chain_view(tasks, current=2, prev=1)
        self.assertEqual(payload["operation_mode"], "transition")
        # prev=1 완료 마킹
        self.assertTrue(
            any(
                o["op"] == "complete_header" and o["index"] == 1
                for o in payload["operations"]
            )
        )

    def test_out_of_range_current_rejected(self):
        tasks = parse_tasks(self.SAMPLE["tasks"])
        with self.assertRaises(ValueError):
            build_chain_view(tasks, current=99)

    def test_non_adjacent_prev_rejected_in_payload(self):
        tasks = parse_tasks(self.SAMPLE["tasks"])
        with self.assertRaises(ValueError):
            build_chain_view(tasks, current=2, prev=0)

    def test_initial_handles_arbitrary_current_jump(self):
        # 임의 current 점프는 initial 로 — 이전 전부 completed + 전체 재생성.
        tasks = parse_tasks(self.SAMPLE["tasks"])
        payload = build_chain_view(tasks, current=2, initial=True)
        self.assertEqual(payload["operation_mode"], "initial")
        creates = {
            o["index"]: o["status"]
            for o in payload["operations"]
            if o["op"] == "create_header"
        }
        self.assertEqual(creates[0], "completed")
        self.assertEqual(creates[1], "completed")
        self.assertEqual(creates[2], "in_progress")

    def test_empty_tasks_rejected(self):
        with self.assertRaises(ValueError):
            build_chain_view([], current=0)

    def test_parse_rejects_missing_name(self):
        with self.assertRaises(ValueError):
            parse_tasks([{"engine": "2agent"}])

    def test_parse_rejects_bad_closes(self):
        with self.assertRaises(ValueError):
            parse_tasks([{"name": "x", "engine": "2agent", "closes": "release"}])

    def test_parse_ui_engine(self):
        tasks = parse_tasks([{"name": "screen", "engine": "impl-ui-design-loop"}])
        self.assertEqual(tasks[0].engine, "ui")
        self.assertIn("canvas-design", substeps_for(tasks[0]))
        self.assertNotIn("사용자 PICK", substeps_for(tasks[0]))

    def test_parse_substeps_override_without_engine(self):
        tasks = parse_tasks(
            [{"name": "screen", "substeps": ["designer", "engineer:IMPL"]}]
        )
        self.assertIsNone(tasks[0].engine)
        self.assertEqual(substeps_for(tasks[0]), ["designer", "engineer:IMPL"])

    def test_parse_rejects_neither_engine_nor_substeps(self):
        with self.assertRaises(ValueError):
            parse_tasks([{"name": "x"}])

    def test_parse_rejects_bad_substeps(self):
        with self.assertRaises(ValueError):
            parse_tasks([{"name": "x", "substeps": ["ok", ""]}])

    def test_ui_task_renders_substeps_in_full_tier(self):
        tasks = parse_tasks(
            [
                {"name": "a", "engine": "2agent"},
                {"name": "screen", "engine": "ui"},
            ]
        )
        payload = build_chain_view(tasks, current=1, prev=0)
        self.assertIn("   ㄴ canvas-design", payload["view"])
        self.assertNotIn("   ㄴ 사용자 PICK", payload["view"])
        self.assertIn("canvas-design", payload["current_substeps"])


class TestViewOperationsConsistency(unittest.TestCase):
    """view ≡ operations 불변식 — 진행 뷰는 operation 적용 결과와 일치해야 한다.

    codex 리뷰 finding 근본원인: 비용 분기 tier 에서 view 와 operations 가
    서로 다른 end-state 를 가리키면 메인이 어느 쪽도 신뢰 못 한다.
    """

    def _tasks(self, n, closing_last=False):
        ts = [_task(f"m{i}", "build-worker") for i in range(n)]
        if closing_last and ts:
            ts[-1] = _task(ts[-1].name, "build-worker", closes="story")
        return ts

    def test_substeps_in_view_iff_created_by_operations(self):
        # 모든 tier × (마감/비마감) 조합에서 view 의 sub-step 노출 ⟺ operation 의
        # create_substep 존재.
        for total in (5, 15, 25):  # full / partial / minimal
            for closing in (False, True):
                tasks = self._tasks(total, closing_last=closing)
                # 마감 task 를 current 로 두려면 마지막 경계를 본다.
                current = total - 1
                payload = build_chain_view(tasks, current=current, prev=current - 1)
                has_substep_op = any(
                    o["op"] == "create_substep" for o in payload["operations"]
                )
                view_has_substep = "   ㄴ " in payload["view"]
                self.assertEqual(
                    has_substep_op,
                    view_has_substep,
                    f"total={total} closing={closing}: view↔ops sub-step 불일치",
                )
                self.assertEqual(
                    has_substep_op,
                    bool(payload["current_substeps"]),
                    f"total={total} closing={closing}: current_substeps↔ops 불일치",
                )
                self.assertEqual(payload["substeps_expanded"], has_substep_op)

    def test_prev_completed_in_view_and_ops_all_tiers(self):
        # 어느 tier 든 prev 는 view 에서 ✓, operations 에서 complete_header.
        for total in (5, 15, 25):
            tasks = self._tasks(total)
            payload = build_chain_view(tasks, current=1, prev=0)
            self.assertIn("✓ task1 · m0", payload["view"])
            self.assertTrue(
                any(
                    o["op"] == "complete_header" and o["index"] == 0
                    for o in payload["operations"]
                ),
                f"total={total}: prev complete_header 누락",
            )

    def test_partial_minimal_nonclosing_hide_substeps(self):
        # 비-마감 partial/minimal 은 view 에 sub-step 줄이 없다 (재생성 skip).
        for total in (15, 25):
            tasks = self._tasks(total)
            payload = build_chain_view(tasks, current=1, prev=0)
            self.assertFalse(payload["substeps_expanded"])
            self.assertNotIn("   ㄴ ", payload["view"])
            self.assertEqual(payload["current_substeps"], [])


if __name__ == "__main__":
    unittest.main()
