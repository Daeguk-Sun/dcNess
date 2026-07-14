"""tests/test_benchmark_aggregate.py — #766 fleet(cross-run) 집계기 단위 테스트.

run_review.py (run 1개) 위의 fleet 레이어. fixture 는 정식 ledger.jsonl
(sha256 receipt 자동) 로 만들어 production reader 와 동형으로 검증한다.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from harness.benchmark_aggregate import (  # noqa: E402
    aggregate_runs,
    aggregate_sessions,
    render_markdown,
    main,
)
from tests.run_fixtures import (  # noqa: E402
    make_ledger_run_dir as _make_run_dir_ledger,
    make_legacy_run_dir as _make_run_dir_steps,
)


def _step(agent: str, prose_name: str, *, enum: str = "PROSE_LOGGED",
          mode: Optional[str] = None, ts: str = "2026-06-01T00:01:00Z") -> dict:
    return {
        "event": "step_completed", "agent": agent, "mode": mode,
        "enum": enum, "prose_file": prose_name, "prose_excerpt": "", "ts": ts,
    }


def _run_events(entry_point: str, steps: list, *, finished: bool = True,
                extra: Optional[list] = None) -> list:
    evs = [{"event": "run_started", "entry_point": entry_point,
            "ts": "2026-06-01T00:00:00Z"}]
    evs.extend(steps)
    evs.extend(extra or [])
    if finished:
        evs.append({"event": "run_finished", "ts": "2026-06-01T00:09:00Z"})
    return evs


class TestAggregateBasic(unittest.TestCase):
    def test_run_count_and_entry_point(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r1 = _make_run_dir_ledger(
                tmp, "s1", "run-aaa11111",
                _run_events("impl", [_step("impl-validator", "pr.md")]),
                {"pr.md": "리뷰 결과\n중대 결함\nFAIL\n"},
            )
            r2 = _make_run_dir_ledger(
                tmp, "s1", "run-bbb22222",
                _run_events("design", [_step("impl-validator", "pr.md")]),
                {"pr.md": "리뷰 결과\n문제 없음\nPASS\n"},
            )
            rep = aggregate_runs([r1, r2])
            self.assertEqual(rep.run_count, 2)
            self.assertEqual(rep.by_entry_point, {"impl": 1, "design": 1})

    def test_agent_conclusion_distribution_and_fail_ratio(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            runs = []
            # 3 impl-validator FAIL + 1 PASS → fail ratio = 0.75
            for i, verdict in enumerate(["FAIL", "FAIL", "FAIL", "PASS"]):
                runs.append(_make_run_dir_ledger(
                    tmp, "s1", f"run-c{i:07d}",
                    _run_events("impl", [_step("impl-validator", "pr.md")]),
                    {"pr.md": f"리뷰\n결론\n{verdict}\n"},
                ))
            rep = aggregate_runs(runs)
            self.assertEqual(rep.agent_conclusions["impl-validator"]["FAIL"], 3)
            self.assertEqual(rep.agent_conclusions["impl-validator"]["PASS"], 1)
            self.assertAlmostEqual(rep.pr_reviewer_fail_ratio, 0.75)

    def test_legacy_steps_jsonl_enum_fallback(self):
        # prose 부재 legacy row — conclusion_enum 없어도 stored enum 으로 폴백 집계.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_steps(tmp, "s1", "run-leg00001", [
                {"agent": "impl-validator", "mode": None, "enum": "FAIL",
                 "ts": "2026-06-01T00:01:00Z"},
            ])
            rep = aggregate_runs([r])
            self.assertEqual(rep.agent_conclusions["impl-validator"]["FAIL"], 1)
            self.assertAlmostEqual(rep.pr_reviewer_fail_ratio, 1.0)

    def test_legacy_changes_requested_counts_as_fail(self):
        # 옛 impl-validator CHANGES_REQUESTED 도 FAIL 버킷 + 분모에 포함 → ratio 1.0.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_steps(tmp, "s1", "run-cr000001", [
                {"agent": "impl-validator", "mode": None,
                 "enum": "CHANGES_REQUESTED", "ts": "2026-06-01T00:01:00Z"},
            ])
            rep = aggregate_runs([r])
            self.assertAlmostEqual(rep.pr_reviewer_fail_ratio, 1.0)

    def test_stored_verdict_wins_over_misparsed_prose(self):
        # legacy stored enum(CHANGES_REQUESTED)이 prose 오파싱(LGTM 후보)을 이긴다 —
        # 거부된 리뷰가 LGTM 으로 둔갑하는 회귀 방지.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-pv000001",
                _run_events("impl", [
                    _step("impl-validator", "pr.md", enum="CHANGES_REQUESTED"),
                ]),
                {"pr.md": "MUST FIX: 보강 필요\nLGTM 후보 X\n"},
            )
            rep = aggregate_runs([r])
            dist = rep.agent_conclusions["impl-validator"]
            self.assertEqual(dist.get("LGTM", 0), 0)
            self.assertEqual(dist.get("CHANGES_REQUESTED"), 1)
            self.assertAlmostEqual(rep.pr_reviewer_fail_ratio, 1.0)

    def test_prose_logged_sentinel_not_counted_as_verdict(self):
        # PROSE_LOGGED sentinel 은 verdict 로 세지 않는다 (prose 결론도 없을 때).
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_steps(tmp, "s1", "run-snt00001", [
                {"agent": "module-architect", "mode": None,
                 "enum": "PROSE_LOGGED", "ts": "2026-06-01T00:01:00Z"},
            ])
            rep = aggregate_runs([r])
            self.assertEqual(rep.agent_conclusions.get("module-architect", {}), {})

    def test_fail_ratio_none_when_no_pr_reviewer(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-d0000001",
                _run_events("impl", [_step("engineer", "e.md")]),
                {"e.md": "구현 완료\nIMPL_DONE\n"},
            )
            rep = aggregate_runs([r])
            self.assertIsNone(rep.pr_reviewer_fail_ratio)


class TestEscalateAndBlocked(unittest.TestCase):
    def test_escalate_count(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-e0000001",
                _run_events("design", [
                    _step("architecture-validator", "av.md", mode="REVIEW"),
                ]),
                {"av.md": "설계 검토\n외부 검증 불가\nESCALATE\n"},
            )
            rep = aggregate_runs([r])
            self.assertEqual(rep.escalate_count, 1)

    def test_specialized_escalate_variant_counted(self):
        # IMPLEMENTATION_ESCALATE / UX_FLOW_ESCALATE 등 변종도 escalate 로 집계.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-e1000001",
                _run_events("impl", [
                    _step("engineer", "e.md", mode="POLISH"),
                ]),
                {"e.md": "구현 보강 중단\n외부 의존 미해결\nIMPLEMENTATION_ESCALATE\n"},
            )
            rep = aggregate_runs([r])
            self.assertEqual(rep.escalate_count, 1)
            self.assertIn("IMPLEMENTATION_ESCALATE",
                          rep.agent_conclusions["engineer"])

    def test_blocked_event_count(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-f0000001",
                _run_events("impl", [_step("engineer", "e.md")],
                            extra=[{"event": "blocked", "ts": "2026-06-01T00:05:00Z"}]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            rep = aggregate_runs([r])
            self.assertEqual(rep.blocked_event_count, 1)


class TestSuccessMeasurable(unittest.TestCase):
    def test_not_measurable_without_pr_created(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-g0000001",
                _run_events("impl", [_step("engineer", "e.md")]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            rep = aggregate_runs([r])
            self.assertFalse(rep.success_measurable)
            self.assertIsNone(rep.pr_merge_success_ratio)
            self.assertEqual(rep.pr_created_count, 0)
            self.assertEqual(rep.pr_merged_count, 0)

    def test_not_measurable_from_orphan_pr_merged_only(self):
        # legacy/manual pr_merged 만 있으면 denominator(pr_created)가 없어 성공률을
        # 합성하지 않는다. merged event count 는 노출하되 ratio 는 None.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-h0000001",
                _run_events("impl", [_step("engineer", "e.md")],
                            extra=[{"event": "pr_merged", "ts": "2026-06-01T00:08:00Z"}]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            rep = aggregate_runs([r])
            self.assertFalse(rep.success_measurable)
            self.assertIsNone(rep.pr_merge_success_ratio)
            self.assertEqual(rep.pr_created_count, 0)
            self.assertEqual(rep.pr_merged_count, 1)
            self.assertEqual(rep.pr_merge_orphan_count, 1)

    def test_pr_merge_success_ratio_from_created_and_merged_events(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r1 = _make_run_dir_ledger(
                tmp, "s1", "run-h1000001",
                _run_events("impl", [_step("engineer", "e.md")],
                            extra=[
                                {"event": "pr_created", "pr_number": 10,
                                 "url": "https://github.com/o/r/pull/10",
                                 "ts": "2026-06-01T00:04:00Z"},
                                {"event": "pr_merged", "pr_number": 10,
                                 "url": "https://github.com/o/r/pull/10",
                                 "ts": "2026-06-01T00:08:00Z"},
                            ]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            r2 = _make_run_dir_ledger(
                tmp, "s1", "run-h2000002",
                _run_events("impl", [_step("engineer", "e.md")],
                            extra=[
                                {"event": "pr_created", "pr_number": 11,
                                 "url": "https://github.com/o/r/pull/11",
                                 "ts": "2026-06-01T00:04:00Z"},
                            ]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            rep = aggregate_runs([r1, r2])
            self.assertTrue(rep.success_measurable)
            self.assertEqual(rep.pr_created_count, 2)
            self.assertEqual(rep.pr_merged_count, 1)
            self.assertEqual(rep.pr_merge_success_count, 1)
            self.assertEqual(rep.pr_merge_orphan_count, 0)
            self.assertAlmostEqual(rep.pr_merge_success_ratio, 0.5)

    def test_pr_number_keys_do_not_collide_across_projects(self):
        # URL 없는 manual events 도 repo path 를 key 에 포함해 project A #1 과
        # project B #1 을 서로 다른 PR 로 센다.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            repo_a = tmp / "repo-a"
            repo_b = tmp / "repo-b"
            r1 = _make_run_dir_ledger(
                repo_a, "s1", "run-ha000001",
                _run_events("impl", [_step("engineer", "e.md")],
                            extra=[
                                {"event": "pr_created", "pr_number": 1,
                                 "ts": "2026-06-01T00:04:00Z"},
                                {"event": "pr_merged", "pr_number": 1,
                                 "ts": "2026-06-01T00:08:00Z"},
                            ]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            r2 = _make_run_dir_ledger(
                repo_b, "s1", "run-hb000002",
                _run_events("impl", [_step("engineer", "e.md")],
                            extra=[
                                {"event": "pr_created", "pr_number": 1,
                                 "ts": "2026-06-01T00:04:00Z"},
                            ]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            rep = aggregate_runs([r1, r2])
            self.assertEqual(rep.pr_created_count, 2)
            self.assertEqual(rep.pr_merge_success_count, 1)
            self.assertAlmostEqual(rep.pr_merge_success_ratio, 0.5)


class TestWasteTop(unittest.TestCase):
    def test_waste_top_aggregates_retry_same_fail(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            # 연속 동일 agent + enum=FAIL(ADVANCE 제외) + 동일 prose → RETRY_SAME_FAIL
            same = "동일 실패 반복\nFAIL\n"
            runs = []
            for i in range(2):
                runs.append(_make_run_dir_ledger(
                    tmp, "s1", f"run-w{i:07d}",
                    _run_events("impl", [
                        _step("impl-validator", "v.md", enum="FAIL",
                              ts="2026-06-01T00:01:00Z"),
                        _step("impl-validator", "v.md", enum="FAIL",
                              ts="2026-06-01T00:02:00Z"),
                    ]),
                    {"v.md": same},
                ))
            rep = aggregate_runs(runs)
            patterns = dict(rep.waste_top)
            self.assertIn("RETRY_SAME_FAIL", patterns)
            self.assertEqual(patterns["RETRY_SAME_FAIL"], 2)

    def test_waste_top_is_sorted_list(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-x0000001",
                _run_events("impl", [_step("engineer", "e.md")]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            rep = aggregate_runs([r])
            self.assertIsInstance(rep.waste_top, list)

    def test_full_waste_counts_are_not_truncated_by_display_top_limit(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            retry = _make_run_dir_ledger(
                tmp,
                "s1",
                "run-wfull001",
                _run_events(
                    "impl",
                    [
                        _step("impl-validator", "v.md", enum="FAIL"),
                        _step(
                            "impl-validator",
                            "v.md",
                            enum="FAIL",
                            ts="2026-06-01T00:02:00Z",
                        ),
                    ],
                ),
                {"v.md": "동일 실패 반복\nFAIL\n"},
            )
            missing = _make_run_dir_ledger(
                tmp,
                "s1",
                "run-wfull002",
                _run_events("impl", [_step("engineer", "e.md")]),
                {"e.md": "결론 enum이 없는 보고\n"},
            )

            report = aggregate_runs([retry, missing], top=1)

            self.assertEqual(len(report.waste_top), 1)
            self.assertIn("RETRY_SAME_FAIL", report.waste_counts)
            self.assertIn("MISSING_CONCLUSION_ENUM", report.waste_counts)


class TestImprovementCandidates(unittest.TestCase):
    def _run_with_retry_waste(self, tmp: Path, rid: str) -> Path:
        same = "동일 실패 반복\nFAIL\n"
        return _make_run_dir_ledger(
            tmp, "s1", rid,
            _run_events("impl", [
                _step("impl-validator", "v.md", enum="FAIL",
                      ts="2026-06-01T00:01:00Z"),
                _step("impl-validator", "v.md", enum="FAIL",
                      ts="2026-06-01T00:02:00Z"),
            ]),
            {"v.md": same},
        )

    def test_default_threshold_surfaces_recurrent_waste_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            runs = [
                self._run_with_retry_waste(tmp, f"run-rc{i:06d}")
                for i in range(3)
            ]

            rep = aggregate_runs(runs)

            self.assertEqual(rep.recurrence_threshold, 3)
            self.assertEqual(len(rep.improvement_candidates), 1)
            candidate = rep.improvement_candidates[0]
            self.assertEqual(candidate.pattern, "RETRY_SAME_FAIL")
            self.assertEqual(candidate.count, 3)
            self.assertEqual(candidate.threshold, 3)
            self.assertIn("기존 룰 제거", candidate.suggestion)

            md = render_markdown(rep)
            self.assertIn("## 재발 기반 개선 후보", md)
            self.assertIn("RETRY_SAME_FAIL", md)
            self.assertIn("기존 룰 제거", md)

    def test_recurrence_threshold_is_adjustable(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            runs = [
                self._run_with_retry_waste(tmp, f"run-th{i:06d}")
                for i in range(2)
            ]

            default_rep = aggregate_runs(runs)
            lowered_rep = aggregate_runs(runs, recurrence_threshold=2)

            self.assertEqual(default_rep.improvement_candidates, [])
            self.assertEqual(len(lowered_rep.improvement_candidates), 1)
            self.assertEqual(lowered_rep.improvement_candidates[0].threshold, 2)

    def test_good_text_is_not_counted_as_recurrence_signal(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            runs = [
                _make_run_dir_ledger(
                    tmp, "s1", f"run-good{i:04d}",
                    _run_events("impl", [_step("engineer", "e.md")]),
                    {"e.md": "좋았던 점 GOOD\nIMPL_DONE\n"},
                )
                for i in range(3)
            ]

            rep = aggregate_runs(runs)

            self.assertEqual(rep.waste_top, [])
            self.assertEqual(rep.improvement_candidates, [])


class TestEntryPointFilter(unittest.TestCase):
    def test_aggregate_sessions_filters_entry_point(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_run_dir_ledger(
                tmp, "s1", "run-i0000001",
                _run_events("impl", [_step("engineer", "e.md")]),
                {"e.md": "구현\nIMPL_DONE\n"},
            )
            _make_run_dir_ledger(
                tmp, "s1", "run-j0000002",
                _run_events("design", [_step("module-architect", "m.md")]),
                {"m.md": "설계\nPASS\n"},
            )
            sessions_root = tmp / ".claude" / "harness-state" / ".sessions"
            rep_all = aggregate_sessions(sessions_root)
            self.assertEqual(rep_all.run_count, 2)
            rep_impl = aggregate_sessions(sessions_root, entry_point="impl")
            self.assertEqual(rep_impl.run_count, 1)
            self.assertEqual(rep_impl.by_entry_point, {"impl": 1})


class TestRenderAndCli(unittest.TestCase):
    def test_render_markdown_contains_key_sections(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-k0000001",
                _run_events("impl", [_step("impl-validator", "pr.md")]),
                {"pr.md": "리뷰\nFAIL\n"},
            )
            md = render_markdown(aggregate_runs([r]))
            self.assertIn("impl-validator", md)
            self.assertIn("1", md)  # run count
            # 성공률 미측정 정직 표기 — 합성 placeholder 금지.
            self.assertRegex(md, r"(측정 불가|미측정|이벤트)")
            self.assertIn("review rejection", md)

    def test_render_markdown_contains_measured_pr_success(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            r = _make_run_dir_ledger(
                tmp, "s1", "run-k1000001",
                _run_events("impl", [_step("impl-validator", "pr.md")],
                            extra=[
                                {"event": "pr_created", "pr_number": 7,
                                 "url": "https://github.com/o/r/pull/7",
                                 "ts": "2026-06-01T00:04:00Z"},
                                {"event": "pr_merged", "pr_number": 7,
                                 "url": "https://github.com/o/r/pull/7",
                                 "ts": "2026-06-01T00:08:00Z"},
                            ]),
                {"pr.md": "리뷰\nPASS\n"},
            )
            md = render_markdown(aggregate_runs([r]))
            self.assertIn("PR 머지 성공률: **100.0%**", md)
            self.assertIn("1/1", md)

    def test_main_runs_on_sessions_root(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_run_dir_ledger(
                tmp, "s1", "run-l0000001",
                _run_events("impl", [_step("impl-validator", "pr.md")]),
                {"pr.md": "리뷰\nFAIL\n"},
            )
            sessions_root = tmp / ".claude" / "harness-state" / ".sessions"
            rc = main([str(sessions_root)])
            self.assertEqual(rc, 0)

    def test_repo_override_accepted(self):
        # --repo override 가 받아들여지고 정상 종료 (cost/invocation 보정 escape hatch).
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_run_dir_ledger(
                tmp, "s1", "run-r0000001",
                _run_events("impl", [_step("impl-validator", "pr.md")]),
                {"pr.md": "리뷰\nPASS\n"},
            )
            sessions_root = tmp / ".claude" / "harness-state" / ".sessions"
            rc = main([str(sessions_root), "--repo", str(tmp)])
            self.assertEqual(rc, 0)
            # 함수 레벨 override 도 동작
            rep = aggregate_sessions(sessions_root, repo_override=tmp)
            self.assertEqual(rep.run_count, 1)

    def test_main_json_output(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _make_run_dir_ledger(
                tmp, "s1", "run-m0000001",
                _run_events("impl", [_step("impl-validator", "pr.md")]),
                {"pr.md": "리뷰\nPASS\n"},
            )
            sessions_root = tmp / ".claude" / "harness-state" / ".sessions"
            rc = main([str(sessions_root), "--json"])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
