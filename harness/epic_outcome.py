#!/usr/bin/env python3
"""Summarize epic-close product verification in the user's product language.

`/impl-loop` 와 `/acceptance epic` 이 Epic 종료 직전에 읽는 요약을 만든다. 원시 지표
대신 대표 사용자 흐름의 실행 결과, 확인한 완료 기준, 막힌 이유, Epic 종료 가능 여부를
사람이 그대로 읽을 수 있는 문장으로 낸다.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from harness.product_journey import _ID_RE, _parse_ts, read_receipts


BLOCKING_REASONS: dict[str, str] = {
    "mock_only_boundary": "실제 제품이 아니라 모의 구현만 실행했다",
    "app_not_started": "앱이 기동되지 않았다",
    "health_failed": "실행 준비 확인이 실패해 흐름을 시작하지 못했다",
    "journey_not_executed": "대표 사용자 흐름을 실행하지 못했다",
    "journey_failed": "대표 사용자 흐름이 성공 조건을 만족하지 못했다",
    "assertion_not_evaluated": "성공 조건을 평가하지 않았다",
    "cleanup_failed": "실행 뒤 테스트 데이터 정리가 실패했다",
    "ui_evidence_missing": "핵심 단계의 화면 증거가 남지 않았다",
    "ux_integrity_chrome_overlap": "핵심 요소가 화면 밖이나 시스템 영역에 걸쳐 조작할 수 없다",
    "ux_integrity_occluded": "핵심 요소가 다른 화면 요소에 가려 조작할 수 없다",
    "ux_integrity_report_missing": "화면 배치 기록이 남지 않아 가림 여부를 판정할 수 없다",
    "ux_integrity_report_invalid": "화면 배치 기록을 읽을 수 없어 가림 여부를 판정할 수 없다",
    "ux_integrity_element_missing": "판정 대상 요소가 그 화면 기록에 없다",
}

NO_RUN_REASON = "대표 사용자 흐름을 실행한 기록이 아직 없다"


def _describe_reason(reason: str) -> str:
    return BLOCKING_REASONS.get(reason, f"확인이 실패했다 ({reason})")


def _sort_key(receipt: dict[str, Any]) -> tuple[datetime, str, str]:
    measured = _parse_ts(receipt.get("measured_at")) or datetime.min.replace(
        tzinfo=timezone.utc
    )
    finished = str(receipt.get("finished_at") or "")
    return (measured, finished, str(receipt.get("run_id") or ""))


def latest_runs_by_journey(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the most recent run of each journey so a fixed re-run supersedes."""
    latest: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        journey_id = str(receipt.get("journey_id"))
        current = latest.get(journey_id)
        if current is None or _sort_key(receipt) >= _sort_key(current):
            latest[journey_id] = receipt
    return [latest[key] for key in sorted(latest)]


def collect(
    project_root: Path | str, epic: str, *, cutoff: Optional[datetime] = None
) -> dict[str, Any]:
    """Collect one epic's representative-flow results, isolated from other epics."""
    if not isinstance(epic, str) or not _ID_RE.fullmatch(epic.strip()):
        raise ValueError("epic must match [a-z0-9][a-z0-9._-]{2,63}")
    epic = epic.strip()
    root = Path(project_root).expanduser().resolve()
    scoped = [
        receipt
        for receipt in read_receipts(root, cutoff=cutoff)
        if isinstance(receipt.get("epic_scope"), dict)
        and receipt["epic_scope"].get("epic") == epic
    ]
    runs = latest_runs_by_journey(scoped)

    flows: list[dict[str, Any]] = []
    for receipt in runs:
        scope = receipt["epic_scope"]
        passed = receipt["outcome"] == "PASS"
        flows.append(
            {
                "journey_id": receipt["journey_id"],
                "description": receipt["assertion"]["description"],
                "representative_story": scope["representative_story"],
                "selection_rationale": scope["selection_rationale"],
                "execution_environment": scope["execution_environment"],
                "code_revision": scope["code_revision"],
                "confirmed": passed,
                "target_ac": list(receipt["target_ac"]),
                "blocking_reasons": [
                    _describe_reason(reason)
                    for reason in receipt.get("failure_reasons", [])
                ],
                "measured_at": receipt["measured_at"],
                "evidence_path": receipt["receipt_path"],
            }
        )

    confirmed_ac = sum(
        int(receipt["product_ac"]["passed"]) for receipt in runs
    )
    total_ac = sum(int(receipt["product_ac"]["total"]) for receipt in runs)
    unresolved = [flow for flow in flows if not flow["confirmed"]]
    return {
        "epic": epic,
        "project_root": str(root),
        "flows": flows,
        "confirmed_criteria": confirmed_ac,
        "total_criteria": total_ac,
        "close_ready": bool(flows) and not unresolved,
        "close_blockers": (
            [NO_RUN_REASON]
            if not flows
            else sorted({reason for flow in unresolved for reason in flow["blocking_reasons"]})
        ),
    }


def render(summary: dict[str, Any]) -> str:
    """Render the summary as product-language prose, without internal metric shape."""
    lines = [f"Epic 결과 요약 — {summary['epic']}", ""]
    if not summary["flows"]:
        lines.append(f"대표 사용자 흐름: {NO_RUN_REASON}.")
    else:
        lines.append("대표 사용자 흐름")
        for flow in summary["flows"]:
            lines.append(f"- {flow['description']}")
            lines.append(
                f"  결과: {'확인됨' if flow['confirmed'] else '확인 실패'}"
            )
            lines.append(f"  대표로 고른 이유: {flow['selection_rationale']}")
            lines.append(f"  담당 story: {flow['representative_story']}")
            lines.append(f"  확인한 완료 기준: {', '.join(flow['target_ac'])}")
            lines.append(f"  실행 환경: {flow['execution_environment']}")
            lines.append(f"  구현 버전: {flow['code_revision']}")
            lines.append(f"  실행 시각: {flow['measured_at']}")
            lines.append(f"  실행 기록: {flow['evidence_path']}")
            for reason in flow["blocking_reasons"]:
                lines.append(f"  막힌 이유: {reason}")
        lines.append("")
        lines.append(
            "완료 기준 확인: "
            f"{summary['confirmed_criteria']} / {summary['total_criteria']}"
        )
    lines.append("")
    lines.append(f"Epic 종료 가능: {'예' if summary['close_ready'] else '아니오'}")
    if not summary["close_ready"]:
        for reason in summary["close_blockers"]:
            lines.append(f"- 막는 이유: {reason}")
        for flow in summary["flows"]:
            if flow["confirmed"]:
                continue
            lines.append(
                f"- 다시 확인할 곳: {flow['representative_story']} 의 "
                f"{', '.join(flow['target_ac'])}"
            )
    return "\n".join(lines)


def cli_epic_summary(project_root: str, epic: str) -> int:
    try:
        summary = collect(project_root, epic)
    except ValueError as exc:
        print(f"[product-journey] contract error: {exc}", file=sys.stderr)
        return 2
    print(render(summary))
    return 0 if summary["close_ready"] else 1
