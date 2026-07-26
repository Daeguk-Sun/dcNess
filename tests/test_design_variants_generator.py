"""Project-agnostic design-variants generator contract tests (#1207)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "design"
TEMPLATE = ROOT / "templates" / "design-variants"


def _screen(
    screen_id: str,
    variants: list[tuple[str, str]],
    *,
    representative: str | None = None,
) -> str:
    blocks = []
    for variant, axes in variants:
        marker = (
            ' data-journey-representative="true"'
            if variant == representative
            else ""
        )
        blocks.append(
            f'<section data-variant="{variant}" '
            f'data-variant-values="{axes}"{marker} '
            f'data-node-id="{screen_id}.{variant}">{variant}</section>'
        )
    blocks_html = "\n".join(blocks)
    return textwrap.dedent(
        f"""\
        <!doctype html>
        <html lang="ko">
        <head><meta charset="utf-8"><title>{screen_id}</title></head>
        <body>
          {blocks_html}
          <script defer src="../_lib/only-variant.js"></script>
          <script defer src="../_lib/report-size.js"></script>
          <script defer src="../_lib/show-ids.js"></script>
        </body>
        </html>
        """
    )


def _ux_flow(*, include_journeys: bool = True, ambiguous: bool = False) -> str:
    duplicate = "  Home --> Review: 보조 경로\n" if ambiguous else ""
    journey_contract = ""
    if include_journeys:
        journey_contract = textwrap.dedent(
            """\
            ```json dcness-journey-contract
            {
              "unit": "user-goal",
              "journeyHeadingPattern": "^Goal (?<id>[a-z0-9-]+)$",
              "nameSource": {
                "kind": "table",
                "path": "ux-flow.md",
                "section": "여정 카탈로그",
                "idColumn": "여정 ID",
                "nameColumn": "이름"
              }
            }
            ```

            ### 여정 카탈로그

            | 여정 ID | 이름 |
            |---|---|
            | review-notice | 알림 확인 |
            | missing-screen | 설정 진입 |

            ### 여정 경로

            #### Goal review-notice

            - Home --> Review
            - Review --> Detail

            #### Goal missing-screen

            - Home --> Settings
            - Settings --> Detail
            """
        )
    return textwrap.dedent(
        f"""\
        # UX flow

        ## 화면 인벤토리

        | 화면 ID | 화면명 | 역할 | 확정 목업 경로 |
        |---|---|---|---|
        | S01 | 홈 | 알림 목록 | `docs/design-variants/screens/home.html` |
        | S02 | 검토 | 알림 검토 | `docs/design-variants/screens/review.html` |
        | S03 | 상세 | 알림 상세 | `docs/design-variants/screens/detail.html` |
        | S04 | 설정 | 사용자 설정 | `docs/design-variants/screens/settings.html` |

        ## 화면 흐름

        ```mermaid
        stateDiagram-v2
          state "홈 (S01)" as Home
          state "검토 (S02)" as Review
          state "상세 (S03)" as Detail
          state "설정 (S04)" as Settings
          Home --> Review: 알림 선택
        {duplicate}  Review --> Detail: 검토 완료
          Home --> Settings: 설정 열기
          Settings --> Detail: 설정 완료
        ```

        {journey_contract}
        """
    )


def _second_ux_flow() -> str:
    return textwrap.dedent(
        """\
        # Second UX flow

        ## 화면 인벤토리

        | 화면 ID | 화면명 | 역할 | 확정 목업 경로 |
        |---|---|---|---|
        | S01 | 홈 | 알림 목록 | `docs/design-variants/screens/home.html` |
        | S02 | 검토 | 알림 검토 | `docs/design-variants/screens/review.html` |
        | S03 | 상세 | 알림 상세 | `docs/design-variants/screens/detail.html` |

        ## 화면 흐름

        ```mermaid
        stateDiagram-v2
          state "홈 (S01)" as Home
          state "검토 (S02)" as Review
          state "상세 (S03)" as Detail
          Home --> Review: 두 번째 진입
          Review --> Detail: 두 번째 완료
        ```

        ```json dcness-journey-contract
        {
          "unit": "user-goal",
          "journeyHeadingPattern": "^Goal (?<id>[a-z0-9-]+)$",
          "nameSource": {
            "kind": "table",
            "path": "ux-flow.md",
            "section": "여정 카탈로그",
            "idColumn": "여정 ID",
            "nameColumn": "이름"
          }
        }
        ```

        ### 여정 카탈로그

        | 여정 ID | 이름 |
        |---|---|
        | second-goal | 두 번째 목표 |

        ### 여정 경로

        #### Goal second-goal

        - Home --> Review
        - Review --> Detail
        """
    )


class DesignVariantsGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.design = self.project / "docs" / "design-variants"
        shutil.copytree(TEMPLATE, self.design)
        (self.project / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")
        (self.project / "docs" / "index.md").write_text(
            "# Documentation\n", encoding="utf-8"
        )
        epic = self.project / "docs" / "epics" / "epic-ui"
        epic.mkdir(parents=True)
        self.ux_flow = epic / "ux-flow.md"
        self.ux_flow.write_text(_ux_flow(), encoding="utf-8")
        screens = self.design / "screens"
        screens.mkdir()
        (screens / "home.html").write_text(
            _screen(
                "home",
                [
                    ("mobile-loading", "breakpoint=mobile;state=loading"),
                    ("desktop-loading", "breakpoint=desktop;state=loading"),
                    ("mobile-ready", "breakpoint=mobile;state=ready"),
                    ("desktop-ready", "breakpoint=desktop;state=ready"),
                ],
                representative="mobile-ready",
            ),
            encoding="utf-8",
        )
        for screen_id in ("review", "detail"):
            (screens / f"{screen_id}.html").write_text(
                _screen(screen_id, [("default", "state=default")]),
                encoding="utf-8",
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                "node",
                str(SCRIPTS / name),
                "--project-root",
                str(self.project),
                "--ux-flow",
                str(self.ux_flow.relative_to(self.project)),
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(f"{name} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
        return result

    def _run_no_flow(
        self, name: str, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                "node",
                str(SCRIPTS / name),
                "--project-root",
                str(self.project),
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                f"{name} failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result

    def _generate_all(self) -> None:
        self._run("build-journey-boards.mjs")
        self._run("build-screen-states.mjs")
        self._run("build-design-index.mjs")

    def test_generic_journey_contract_generates_boards_without_story_convention(self) -> None:
        self._generate_all()

        board = self.design / "boards" / "journey-review-notice.html"
        self.assertTrue(board.is_file())
        text = board.read_text(encoding="utf-8")
        self.assertIn("알림 확인", text)
        self.assertIn("home", text)
        self.assertIn("review", text)
        self.assertIn("detail", text)
        self.assertIn("screens/home.html#only=mobile-ready", text)
        self.assertNotIn("Story", text)
        for hand_value in ("data-pos=", "data-bend=", "data-gap-", "data-w=", "data-h="):
            self.assertNotIn(hand_value, text)
        self.assertFalse((self.design / "boards" / "journey-missing-screen.html").exists())

        readme = (self.design / "README.md").read_text(encoding="utf-8")
        self.assertIn("알림 확인", readme)
        self.assertIn("home → review → detail", readme)
        self.assertIn("설정 진입", readme)
        self.assertIn("확정본 없는 화면", readme)
        self.assertIn("진본과 파생 규칙", readme)
        self.assertIn("drafts/", readme)

    def test_heading_name_source_uses_declared_pattern(self) -> None:
        flow = _ux_flow().replace(
            '''"kind": "table",
                "path": "ux-flow.md",
                "section": "여정 카탈로그",
                "idColumn": "여정 ID",
                "nameColumn": "이름"''',
            '''"kind": "heading",
                "path": "ux-flow.md",
                "headingPattern": "^Journey (?<id>[a-z0-9-]+): (?<name>.+)$"''',
        ).replace(
            """### 여정 카탈로그

            | 여정 ID | 이름 |
            |---|---|
            | review-notice | 알림 확인 |
            | missing-screen | 설정 진입 |""",
            """### 여정 카탈로그

            #### Journey review-notice: 알림 확인

            #### Journey missing-screen: 설정 진입""",
        )
        self.ux_flow.write_text(flow, encoding="utf-8")

        self._generate_all()

        self.assertTrue(
            (self.design / "boards" / "journey-review-notice.html").is_file()
        )
        self.assertIn(
            "알림 확인",
            (self.design / "README.md").read_text(encoding="utf-8"),
        )

    def test_journey_node_order_follows_last_occurrence(self) -> None:
        flow = _ux_flow().replace(
            "Review --> Detail: 검토 완료",
            "Review --> Home: 다시 보기\n          Home --> Detail: 바로 완료",
            1,
        ).replace(
            "- Review --> Detail",
            "- Review --> Home\n- Home --> Detail",
        )
        self.ux_flow.write_text(flow, encoding="utf-8")

        self._run("build-journey-boards.mjs")

        board = (
            self.design / "boards" / "journey-review-notice.html"
        ).read_text(encoding="utf-8")
        self.assertLess(
            board.index('data-node-id="review"'),
            board.index('data-node-id="home"'),
        )
        self.assertLess(
            board.index('data-node-id="home"'),
            board.index('data-node-id="detail"'),
        )

    def test_screen_states_uses_row_and_column_axes_without_copying_screens(self) -> None:
        self._run("build-screen-states.mjs")

        board = (self.design / "boards" / "screen-states.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-column-axis="breakpoint"', board)
        self.assertIn('data-row-axis="state"', board)
        self.assertIn('data-screen-src="../screens/home.html"', board)
        self.assertIn('data-variant-id="mobile-loading"', board)
        self.assertIn("#only=mobile-loading", board)
        self.assertIn("#only=desktop-ready", board)
        self.assertEqual(len(list((self.design / "screens").glob("*.html"))), 3)
        self.assertNotIn("data-pos=", board)
        self.assertNotIn("data-w=", board)
        self.assertNotIn("data-h=", board)

    def test_multiple_epics_generate_and_check_one_project_wide_board_set(self) -> None:
        second = self.project / "docs" / "epics" / "epic-two" / "ux-flow.md"
        second.parent.mkdir(parents=True)
        second.write_text(_second_ux_flow(), encoding="utf-8")
        self.assertFalse((self.design / "README.md").exists())

        for generator in (
            "build-journey-boards.mjs",
            "build-screen-states.mjs",
            "build-design-index.mjs",
        ):
            self._run_no_flow(generator)
        for generator in (
            "build-journey-boards.mjs",
            "build-screen-states.mjs",
            "build-design-index.mjs",
        ):
            self._run_no_flow(generator, "--check")

        first_board = self.design / "boards" / "journey-review-notice.html"
        second_board = self.design / "boards" / "journey-second-goal.html"
        self.assertTrue(first_board.is_file())
        self.assertTrue(second_board.is_file())
        readme = (self.design / "README.md").read_text(encoding="utf-8")
        self.assertIn("epic-ui/ux-flow.md", readme)
        self.assertIn("epic-two/ux-flow.md", readme)
        self.assertIn("알림 확인", readme)
        self.assertIn("두 번째 목표", readme)

        self._run("build-journey-boards.mjs")
        self.assertTrue(first_board.is_file())
        self.assertTrue(second_board.is_file())

    def test_shared_screen_metadata_conflict_lists_each_flow_and_value(self) -> None:
        second = self.project / "docs" / "epics" / "epic-two" / "ux-flow.md"
        second.parent.mkdir(parents=True)
        second.write_text(
            _second_ux_flow()
            .replace(
                "| S01 | 홈 | 알림 목록 |",
                "| S13 | 화면3 | 다른 역할 |",
            )
            .replace('state "홈 (S01)" as Home', 'state "화면3 (S13)" as Home'),
            encoding="utf-8",
        )

        for generator in (
            "build-journey-boards.mjs",
            "build-screen-states.mjs",
            "build-design-index.mjs",
        ):
            with self.subTest(generator=generator):
                result = self._run_no_flow(generator, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("화면 메타데이터가 충돌합니다: home", result.stderr)
                self.assertIn("docs/epics/epic-ui/ux-flow.md", result.stderr)
                self.assertIn("S01 | 홈 | 알림 목록", result.stderr)
                self.assertIn("docs/epics/epic-two/ux-flow.md", result.stderr)
                self.assertIn("S13 | 화면3 | 다른 역할", result.stderr)

    def test_duplicate_journey_ids_are_scoped_and_scope_collision_fails(self) -> None:
        second_flow = _second_ux_flow().replace("second-goal", "review-notice")
        second = self.project / "docs" / "epics" / "epic-two" / "ux-flow.md"
        second.parent.mkdir(parents=True)
        second.write_text(second_flow, encoding="utf-8")

        self._run_no_flow("build-journey-boards.mjs")
        self._run_no_flow("build-screen-states.mjs")
        self._run_no_flow("build-design-index.mjs")

        boards = self.design / "boards"
        self.assertTrue(
            (boards / "journey-epic-ui-review-notice.html").is_file()
        )
        self.assertTrue(
            (boards / "journey-epic-two-review-notice.html").is_file()
        )
        self.assertFalse((boards / "journey-review-notice.html").exists())
        readme = (self.design / "README.md").read_text(encoding="utf-8")
        self.assertIn("journey-epic-ui-review-notice.html", readme)
        self.assertIn("journey-epic-two-review-notice.html", readme)

        colliding = self.project / "docs" / "epics" / "epic.two" / "ux-flow.md"
        colliding.parent.mkdir(parents=True)
        colliding.write_text(second_flow, encoding="utf-8")
        result = self._run_no_flow("build-journey-boards.mjs", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("여러 ux-flow의 여정 보드 파일명이 충돌합니다", result.stderr)

    def test_multi_variant_screen_requires_one_explicit_journey_representative(
        self,
    ) -> None:
        home = self.design / "screens" / "home.html"
        original = home.read_text(encoding="utf-8")
        home.write_text(
            original.replace(' data-journey-representative="true"', ""),
            encoding="utf-8",
        )

        missing = self._run("build-journey-boards.mjs", check=False)

        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("data-journey-representative", missing.stderr)

        home.write_text(
            original.replace(
                'data-variant="desktop-ready"',
                (
                    'data-variant="desktop-ready" '
                    'data-journey-representative="true"'
                ),
            ),
            encoding="utf-8",
        )
        duplicate = self._run("build-journey-boards.mjs", check=False)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("data-journey-representative", duplicate.stderr)
        self.assertIn("중복", duplicate.stderr)

    def test_labels_keep_project_text_and_canvas_measures_rendered_width(self) -> None:
        self.ux_flow.write_text(
            _ux_flow().replace("알림 선택", "AC-12 (중요) 알림 선택"),
            encoding="utf-8",
        )

        self._run("build-journey-boards.mjs")

        board = (
            self.design / "boards" / "journey-review-notice.html"
        ).read_text(encoding="utf-8")
        self.assertIn('data-label="AC-12 (중요) 알림 선택"', board)
        engine = (TEMPLATE / "_lib" / "canvas.js").read_text(encoding="utf-8")
        self.assertIn("labelTextWidth(spec.label)", engine)
        self.assertNotIn("spec.label.length * 7.5", engine)

    def test_screen_variant_inventory_is_runtime_reported_for_stale_board_recovery(
        self,
    ) -> None:
        self._run("build-screen-states.mjs")
        board_path = self.design / "boards" / "screen-states.html"
        board_before = board_path.read_text(encoding="utf-8")
        home = self.design / "screens" / "home.html"
        home.write_text(
            home.read_text(encoding="utf-8").replace(
                "</body>",
                (
                    '<section data-variant="tablet-ready" '
                    'data-variant-values="breakpoint=tablet;state=ready">'
                    "tablet</section></body>"
                ),
            ),
            encoding="utf-8",
        )

        self.assertEqual(board_path.read_text(encoding="utf-8"), board_before)
        report = (
            TEMPLATE / "_lib" / "report-size.js"
        ).read_text(encoding="utf-8")
        engine = (TEMPLATE / "_lib" / "canvas.js").read_text(encoding="utf-8")
        self.assertIn("variants: variants()", report)
        self.assertIn("dcness-request-frame-size", report)
        self.assertIn("syncVariantFrames(node, data.variants)", engine)
        self.assertIn("node.dataset.screenSrc", engine)
        self.assertIn("seedFrameSize(node, iframe)", engine)
        self.assertIn("measureSameOriginFrame(frame)", engine)
        self.assertIn("frame-size-warning", engine)
        self.assertNotIn("frame.clientWidth || 1", engine)
        self.assertNotIn(
            "querySelectorAll(':scope > .variant-grid, :scope > .variant-facet')",
            engine,
        )
        self.assertIn("new MutationObserver(records =>", engine)

    def test_check_detects_source_drift_and_stale_journey_board(self) -> None:
        self._generate_all()
        self.ux_flow.write_text(
            self.ux_flow.read_text(encoding="utf-8").replace(
                "- Review --> Detail", "- Review --> Detail (검토 완료)"
            ),
            encoding="utf-8",
        )

        stale = self._run("build-journey-boards.mjs", "--check", check=False)
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("DRIFT", stale.stderr)

        self._run("build-journey-boards.mjs")
        self._run("build-journey-boards.mjs", "--check")
        extra = self.design / "boards" / "journey-obsolete.html"
        extra.write_text("stale", encoding="utf-8")
        stale_board = self._run("build-journey-boards.mjs", "--check", check=False)
        self.assertNotEqual(stale_board.returncode, 0)
        self.assertIn("journey-obsolete.html", stale_board.stderr)

    def test_no_journey_declaration_removes_journey_boards_and_cards(self) -> None:
        self._generate_all()
        self.ux_flow.write_text(_ux_flow(include_journeys=False), encoding="utf-8")

        self._generate_all()

        self.assertEqual(list((self.design / "boards").glob("journey-*.html")), [])
        index = (self.design / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('class="journey-card"', index)
        readme = (self.design / "README.md").read_text(encoding="utf-8")
        self.assertIn("선언된 여정 없음", readme)

    def test_ambiguous_journey_step_lists_candidates_and_fails(self) -> None:
        self.ux_flow.write_text(_ux_flow(ambiguous=True), encoding="utf-8")

        result = self._run("build-journey-boards.mjs", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("후보", result.stderr)
        self.assertIn("알림 선택", result.stderr)
        self.assertIn("보조 경로", result.stderr)

    def test_missing_variant_marker_and_promoted_draft_metadata_fail_check(self) -> None:
        bad = self.design / "screens" / "bad.html"
        bad.write_text(
            (
                '<html><body>'
                '<section data-variant="default" data-variant-values="state=default">'
                "ok</section>"
                '<section data-variant-values="state=error" data-node-id="bad.root">'
                "draft 2</section>"
                "</body></html>"
            ),
            encoding="utf-8",
        )
        (self.design / "drafts" / "bad-draft1.html").write_text(
            _screen("bad", [("default", "state=default")]),
            encoding="utf-8",
        )

        result = self._run("build-screen-states.mjs", "--check", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data-variant가 없습니다", result.stderr)
        self.assertIn("draft", result.stderr)

    def test_empty_variant_id_and_missing_screen_helpers_fail_check(self) -> None:
        bad = self.design / "screens" / "helperless.html"
        bad.write_text(
            (
                '<html><body><section data-variant="" '
                'data-variant-values="state=default">bad</section></body></html>'
            ),
            encoding="utf-8",
        )

        result = self._run("build-screen-states.mjs", "--check", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("비어 있을 수 없습니다", result.stderr)
        for helper in ("only-variant.js", "report-size.js", "show-ids.js"):
            self.assertIn(helper, result.stderr)

    def test_malformed_or_duplicate_variant_axis_fails_check(self) -> None:
        bad = self.design / "screens" / "bad-axis.html"
        bad.write_text(
            _screen("bad-axis", [("default", "state=;state=ready")]),
            encoding="utf-8",
        )

        result = self._run("build-screen-states.mjs", "--check", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("잘못된 data-variant-values", result.stderr)
        bad.write_text(
            _screen("bad-axis", [("default", "state=ready;state=loading")]),
            encoding="utf-8",
        )
        duplicate = self._run("build-screen-states.mjs", "--check", check=False)
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("축이 중복됩니다", duplicate.stderr)

    def test_promotion_check_preserves_other_screen_drafts(self) -> None:
        unrelated = self.design / "drafts" / "settings-draft1.html"
        unrelated.write_text(
            _screen("settings", [("default", "state=default")]),
            encoding="utf-8",
        )

        self._run("build-screen-states.mjs")

        self.assertTrue(unrelated.is_file())

    def test_engine_drift_warns_without_overwriting_project_copy(self) -> None:
        self._run("build-screen-states.mjs")
        engine = self.design / "_lib" / "canvas.js"
        original = engine.read_text(encoding="utf-8")
        engine.write_text(original + "\n// local edit\n", encoding="utf-8")

        result = self._run("build-screen-states.mjs", "--check", check=False)

        self.assertEqual(result.returncode, 0)
        self.assertIn("ENGINE WARNING", result.stderr)
        self.assertEqual(engine.read_text(encoding="utf-8"), original + "\n// local edit\n")

    def test_generated_outputs_include_regeneration_sources_and_hashes(self) -> None:
        self._generate_all()
        outputs = [
            self.design / "boards" / "journey-review-notice.html",
            self.design / "boards" / "screen-states.html",
            self.design / "README.md",
            self.design / "index.html",
        ]
        for output in outputs:
            with self.subTest(output=output.name):
                text = output.read_text(encoding="utf-8")
                self.assertIn("재생성", text)
                self.assertIn("ux-flow.md", text)
                self.assertRegex(text, r"[a-f0-9]{12}")

    def test_index_generator_owns_one_project_pointer_per_entry_document(self) -> None:
        self._generate_all()
        self._run("build-design-index.mjs")

        claude = (self.project / "CLAUDE.md").read_text(encoding="utf-8")
        docs_index = (self.project / "docs" / "index.md").read_text(encoding="utf-8")
        self.assertEqual(claude.count("dcness-design-variants-entry"), 1)
        self.assertEqual(docs_index.count("dcness-design-variants-entry"), 1)
        self.assertIn("(docs/design-variants/README.md)", claude)
        self.assertIn("(design-variants/README.md)", docs_index)

        (self.project / "CLAUDE.md").write_text(
            claude + "\n",
            encoding="utf-8",
        )
        self._run("build-design-index.mjs", "--check")

        (self.project / "CLAUDE.md").write_text(
            claude + "- duplicate <!-- dcness-design-variants-entry -->\n",
            encoding="utf-8",
        )
        self._run("build-design-index.mjs")
        self.assertEqual(
            (self.project / "CLAUDE.md")
            .read_text(encoding="utf-8")
            .count("dcness-design-variants-entry"),
            1,
        )

        (self.project / "docs" / "index.md").write_text(
            docs_index.replace("design-variants/README.md", "stale.md"),
            encoding="utf-8",
        )
        drift = self._run("build-design-index.mjs", "--check", check=False)
        self.assertNotEqual(drift.returncode, 0)
        self.assertIn("DRIFT", drift.stderr)

    def test_release_artifact_packages_plugin_owned_generators(self) -> None:
        manifest = json.loads(
            (ROOT / "scripts" / "release_artifact.json").read_text(encoding="utf-8")
        )
        self.assertIn("scripts/design", manifest["include_paths"])
        doc_sync = (
            ROOT / ".github" / "actions" / "doc-sync" / "action.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('screens/*.html', doc_sync)
        for generator in (
            "build-journey-boards.mjs",
            "build-screen-states.mjs",
            "build-design-index.mjs",
        ):
            self.assertIn(generator, doc_sync)

        workflow = (
            ROOT / ".github" / "workflows" / "python-tests.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("tests/design_variants_browser_smoke.mjs", workflow)
        self.assertEqual(workflow.count("'templates/design-variants/**'"), 2)


if __name__ == "__main__":
    unittest.main()
