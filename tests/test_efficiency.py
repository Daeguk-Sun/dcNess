"""test_efficiency — Claude Code 세션 분석 스크립트 (jha0313 fork) 검증.

DCN-CHG-20260430-08: improve-token-efficiency skill 흡수. encode_repo_path 가
CC 인코딩 룰 (`/` + `.` 둘 다 → `-`) 정합 + price_for prefix 매칭 검증.

핵심 동작 (analyze_sessions / build_dashboard) 의 통합 smoke 만 — read-only 분석
도구라 catastrophic 룰 비대상.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent


class EncodeRepoPathTests(unittest.TestCase):
    """CC 인코딩 룰 — `/` + `.` 모두 `-` 로 변환."""

    def test_simple_path(self) -> None:
        from harness.efficiency.analyze_sessions import encode_repo_path
        self.assertEqual(
            encode_repo_path("/Users/foo/projects/bar"),
            "-Users-foo-projects-bar",
        )

    def test_dotted_username(self) -> None:
        """`/Users/dc.kim/...` 의 `.` 도 `-` 로 (CC 실 동작)."""
        from harness.efficiency.analyze_sessions import encode_repo_path
        result = encode_repo_path("/Users/dc.kim/project/dcNess")
        self.assertEqual(result, "-Users-dc-kim-project-dcNess")

    def test_dotted_dirname(self) -> None:
        from harness.efficiency.analyze_sessions import encode_repo_path
        self.assertEqual(
            encode_repo_path("/Users/x/.config/foo"),
            "-Users-x--config-foo",
        )


class PriceForTests(unittest.TestCase):
    """prefix 매칭 — dated suffix / variant tag 자동 흡수."""

    def test_exact_match(self) -> None:
        from harness.efficiency.analyze_sessions import price_for, PRICING
        self.assertEqual(price_for("claude-opus-4-6"), PRICING["claude-opus-4-6"])

    def test_dated_haiku_suffix(self) -> None:
        """`claude-haiku-4-5-20251001` → haiku 가격 (prefix 매칭)."""
        from harness.efficiency.analyze_sessions import price_for, PRICING
        self.assertEqual(
            price_for("claude-haiku-4-5-20251001"),
            PRICING["claude-haiku-4-5"],
        )

    def test_variant_tag_1m(self) -> None:
        """`claude-opus-4-7[1m]` → opus 가격 (변형 tag 무시)."""
        from harness.efficiency.analyze_sessions import price_for, PRICING
        self.assertEqual(
            price_for("claude-opus-4-7[1m]"),
            PRICING["claude-opus-4-7"],
        )

    def test_unknown_falls_back_default(self) -> None:
        from harness.efficiency.analyze_sessions import price_for, DEFAULT_PRICE
        # 새 모델 ID — DEFAULT_PRICE (Opus default) fallback
        self.assertEqual(price_for("claude-future-99-x-20300101"), DEFAULT_PRICE)


class WrapperSmokeTests(unittest.TestCase):
    """`scripts/dcness-efficiency` wrapper 가 정상 실행 + 빈 디렉토리 처리."""

    def test_no_subcommand_exits_1(self) -> None:
        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "dcness-efficiency")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("usage", result.stderr.lower())

    def test_analyze_empty_sessions_dir(self) -> None:
        """빈 sessions dir → analyze 가 graceful exit (FileNotFoundError 방지)."""
        with TemporaryDirectory() as td:
            sessions = Path(td) / "sessions"
            # 디렉토리만 만들고 jsonl 0개
            sessions.mkdir()
            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "dcness-efficiency"),
                    "analyze",
                    "--sessions-dir", str(sessions),
                    "--out", str(Path(td) / "out.json"),
                ],
                capture_output=True, text=True, timeout=10,
            )
            # 빈 sessions → analyze 가 명시 종료 (exit ≠ 0). 구현체 = exit 2.
            # 핵심 = silent crash X (FileNotFoundError 방지) + 명확한 에러 메시지.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no .jsonl files", result.stderr.lower())


class IntegrationSmokeTests(unittest.TestCase):
    """analyze + dashboard chain — 가짜 세션 jsonl 생성 후 실제 동작 검증."""

    def test_full_chain_with_fixture_session(self) -> None:
        with TemporaryDirectory() as td:
            sessions = Path(td) / "sessions"
            sessions.mkdir()
            # 가짜 세션 jsonl — 1 assistant message with usage
            fixture = sessions / "session-fixture.jsonl"
            record = {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-7",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_creation_input_tokens": 200,
                        "cache_read_input_tokens": 1000,
                    },
                },
            }
            fixture.write_text(json.dumps(record) + "\n", encoding="utf-8")

            json_out = Path(td) / "analysis.json"
            result = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "dcness-efficiency"),
                    "analyze",
                    "--sessions-dir", str(sessions),
                    "--out", str(json_out),
                ],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue(json_out.exists())

            data = json.loads(json_out.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(data.get("sessions", [])), 1)
            self.assertGreater(data.get("totals", {}).get("cost_usd", 0), 0)

            # dashboard 도 실행 가능한지
            html_out = Path(td) / "report.html"
            result2 = subprocess.run(
                [
                    str(REPO_ROOT / "scripts" / "dcness-efficiency"),
                    "dashboard",
                    "--input", str(json_out),
                    "--out", str(html_out),
                ],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result2.returncode, 0, msg=result2.stderr)
            self.assertTrue(html_out.exists())
            html_text = html_out.read_text(encoding="utf-8")
            self.assertIn("<html", html_text.lower())
            self.assertIn("chart", html_text.lower())


if __name__ == "__main__":
    unittest.main()
