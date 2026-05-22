"""eval_agentevals.py — AgentEvals 기반 dcNess 하네스 평가.

세 가지를 측정:
  1. Enum 추출 정확도 — 합성 prose (synthetic)
  2. Enum 추출 정확도 — 실제 run 데이터 (real)
  3. Trajectory 일치도 (loop 시퀀스 검증)

실행:
    # venv 준비 (최초 1회)
    python3 -m venv /tmp/dcness-eval-env
    /tmp/dcness-eval-env/bin/pip install agentevals

    # 실제 데이터 포함 실행 (자장 프로젝트)
    /tmp/dcness-eval-env/bin/python tests/eval_agentevals.py \\
        --real-data /Users/dc.kim/project/jajang/.claude/harness-state \\
        --html --open
"""
from __future__ import annotations

import json
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# repo root 를 sys.path 에 추가 (직접 실행 시)
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from agentevals.trajectory.match import create_trajectory_match_evaluator
    from agentevals.types import ChatCompletionMessage
except ImportError:
    print(
        "[ERROR] agentevals 가 설치되지 않았습니다.\n"
        "  python3 -m venv /tmp/dcness-eval-env\n"
        "  /tmp/dcness-eval-env/bin/pip install agentevals\n"
        "  /tmp/dcness-eval-env/bin/python tests/eval_agentevals.py"
    )
    sys.exit(1)

from harness.signal_io import MissingSignal, interpret_signal


# ── 1. Enum 추출 정확도 평가 ──────────────────────────────────────────────

# (agent, mode, allowed_enums, expected_enum, prose)
# prose 는 다양한 변형을 나타냄

@dataclass
class EnumCase:
    agent: str
    mode: Optional[str]
    allowed: list[str]
    expected: str
    prose: str
    label: str  # 변형 이름 (canonical / informal / deep_tail / misleading / ambiguous / false_positive)


_PADDING = (
    "이 섹션은 실제 작업 내용을 서술하는 긴 본문입니다. "
    "구체적인 구현 방법, 테스트 결과, 코드 리뷰 내용, "
    "인터페이스 설계, 의존성 분석 등이 여기에 포함됩니다. "
) * 25  # ~1 500자 padding


def _make_cases() -> list[EnumCase]:
    """agent × mode 별 합성 prose 케이스 생성."""
    specs = [
        # (agent, mode, allowed, happy_enum)
        ("module-architect",    None         ,      ["PASS", "SPEC_GAP_FOUND"],   "PASS"),
        ("system-architect",    None         ,    ["PASS", "SPEC_GAP_FOUND"], "PASS"),
        ("module-architect",    None         ,       ["PASS", "SPEC_GAP_FOUND"], "PASS"),
        ("module-architect",    None         ,         ["PASS", "ESCALATE"], "PASS"),
        ("module-architect",    None         ,        ["PASS"],                        "PASS"),
        ("engineer",      "IMPL",             ["IMPL_DONE", "SPEC_GAP_FOUND", "TESTS_FAIL"], "IMPL_DONE"),
        ("engineer",      "POLISH",           ["POLISH_DONE"],                        "POLISH_DONE"),
        ("test-engineer", None,               ["PASS", "SPEC_GAP_FOUND"],    "PASS"),
        ("code-validator",         None,         ["PASS", "FAIL", "ESCALATE"],          "PASS"),
        ("architecture-validator", None,         ["PASS", "FAIL", "ESCALATE"],          "PASS"),
        ("ux-architect",           None,         ["UX_FLOW_DONE", "UX_FLOW_ESCALATE"],  "UX_FLOW_DONE"),
        ("pr-reviewer",   None,               ["PASS", "FAIL"],          "PASS"),
        ("plan-reviewer", None,               ["PASS", "FAIL", "ESCALATE"], "PASS"),
    ]

    cases: list[EnumCase] = []
    for agent, mode, allowed, expected in specs:
        mode_label = mode or "DEFAULT"

        # 1. canonical — 마지막 단락 enum
        cases.append(EnumCase(
            agent=agent, mode=mode, allowed=allowed, expected=expected,
            label="canonical",
            prose=f"## 작업 결과 요약\n\n작업을 완료했습니다.\n\n## 결론\n\n{expected}\n",
        ))

        # 2. informal_korean — 구어체 문장 끝
        cases.append(EnumCase(
            agent=agent, mode=mode, allowed=allowed, expected=expected,
            label="informal_korean",
            prose=f"전반적인 검토 후 최종 판단: {expected}\n",
        ))

        # 3. deep_tail — 긴 본문 뒤 enum (tail scan 범위 검증)
        cases.append(EnumCase(
            agent=agent, mode=mode, allowed=allowed, expected=expected,
            label="deep_tail",
            prose=f"{_PADDING}\n\n## 최종 결론\n\n{expected}\n",
        ))

        # 4. misleading — 본문에 다른 enum 언급, 마지막에 정답
        if len(allowed) > 1:
            other = next(e for e in allowed if e != expected)
            cases.append(EnumCase(
                agent=agent, mode=mode, allowed=allowed, expected=expected,
                label="misleading",
                prose=(
                    f"초기 분석에서는 {other} 가능성도 검토했으나, "
                    f"최종 검증 결과 문제 없음.\n\n## 결론\n\n{expected}\n"
                ),
            ))

        # 5. ambiguous — enum 없음 → MissingSignal 예상
        cases.append(EnumCase(
            agent=agent, mode=mode, allowed=allowed, expected="__AMBIGUOUS__",
            label="ambiguous",
            prose="작업을 진행했으나 결론이 불명확합니다. 추가 검토가 필요합니다.\n",
        ))

        # 6. false_positive_trap — allowed enum 이 다른 단어 내 substring 으로 포함
        #    예: "PASS" 가 "COMPASS" 안에 있지만 단어경계로 걸리면 안 됨
        if expected == "PASS":
            cases.append(EnumCase(
                agent=agent, mode=mode, allowed=allowed, expected="__AMBIGUOUS__",
                label="false_positive_trap",
                prose="COMPASS 방향 기준으로 검토했습니다. 결과는 추후 공유 예정.\n",
            ))

    return cases


def run_enum_accuracy_eval() -> dict:
    """interpret_signal 정확도를 케이스별로 측정하고 리포트 반환."""
    cases = _make_cases()

    results: dict[str, dict] = {}  # (agent, mode, label) → result

    total = correct = ambiguous_ok = 0
    per_agent: dict[str, dict] = {}

    for c in cases:
        key = f"{c.agent}/{c.mode or 'DEFAULT'}/{c.label}"
        agent_key = f"{c.agent}/{c.mode or 'DEFAULT'}"
        if agent_key not in per_agent:
            per_agent[agent_key] = {"total": 0, "correct": 0, "errors": []}

        total += 1
        per_agent[agent_key]["total"] += 1

        try:
            got = interpret_signal(c.prose, c.allowed)
            if c.expected == "__AMBIGUOUS__":
                # MissingSignal 을 기대했는데 enum 이 나온 경우
                status = "UNEXPECTED_MATCH"
                ok = False
                per_agent[agent_key]["errors"].append(
                    f"  [{c.label}] expected AMBIGUOUS, got {got!r}"
                )
            elif got == c.expected:
                status = "OK"
                ok = True
                correct += 1
                per_agent[agent_key]["correct"] += 1
            else:
                status = "WRONG"
                ok = False
                per_agent[agent_key]["errors"].append(
                    f"  [{c.label}] expected {c.expected!r}, got {got!r}"
                )
        except MissingSignal as e:
            if c.expected == "__AMBIGUOUS__":
                status = "OK_AMBIGUOUS"
                ok = True
                correct += 1
                ambiguous_ok += 1
                per_agent[agent_key]["correct"] += 1
            else:
                status = f"UNEXPECTED_AMBIGUOUS({e.reason})"
                ok = False
                per_agent[agent_key]["errors"].append(
                    f"  [{c.label}] expected {c.expected!r}, got MissingSignal({e.reason})"
                )

        results[key] = {"status": status, "ok": ok}

    return {
        "total": total,
        "correct": correct,
        "ambiguous_ok": ambiguous_ok,
        "accuracy": correct / total if total else 0.0,
        "per_agent": per_agent,
        "case_results": results,
    }


# ── 2. Real Data Eval (실제 run 데이터) ──────────────────────────────────────

def _normalize_mode(mode: Optional[str]) -> str:
    """IMPL_RETRY_1 → IMPL 등 retry suffix 제거."""
    if mode is None:
        return "DEFAULT"
    return re.sub(r"_RETRY_\d+$", "", mode)


def _build_enum_catalog(harness_root: Path) -> dict[str, list[str]]:
    """모든 .steps.jsonl 에서 (agent/base_mode) → 관찰된 enum 목록 구축."""
    catalog: dict[str, set[str]] = {}
    for jsonl in harness_root.rglob(".steps.jsonl"):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = f"{rec['agent']}/{_normalize_mode(rec.get('mode'))}"
            enum = rec.get("enum", "")
            if enum:
                catalog.setdefault(key, set()).add(enum)
    return {k: sorted(v) for k, v in catalog.items()}


def run_real_data_eval(harness_root: Path) -> dict:
    """실제 .steps.jsonl + prose 파일로 interpret_signal 정확도 측정."""
    catalog = _build_enum_catalog(harness_root)

    per_agent: dict[str, dict] = {}
    skipped_no_prose = 0
    skipped_no_file = 0

    for jsonl in sorted(harness_root.rglob(".steps.jsonl")):
        run_id = jsonl.parent.name
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            prose_file = rec.get("prose_file")
            if not prose_file:
                skipped_no_prose += 1
                continue

            prose_path = Path(prose_file)
            if not prose_path.exists():
                skipped_no_file += 1
                continue

            agent = rec["agent"]
            mode = rec.get("mode")
            base_mode = _normalize_mode(mode)
            key = f"{agent}/{base_mode}"
            expected = rec.get("enum", "")
            if not expected:
                continue

            allowed = catalog.get(key, [expected])
            prose = prose_path.read_text(encoding="utf-8")

            ak = key
            if ak not in per_agent:
                per_agent[ak] = {"total": 0, "correct": 0, "ambiguous": 0, "errors": []}

            per_agent[ak]["total"] += 1

            try:
                got = interpret_signal(prose, allowed)
                ok = got == expected
                if ok:
                    per_agent[ak]["correct"] += 1
                else:
                    per_agent[ak]["errors"].append(
                        f"  run={run_id} expected={expected!r} got={got!r}"
                    )
            except MissingSignal as e:
                per_agent[ak]["ambiguous"] += 1
                per_agent[ak]["errors"].append(
                    f"  run={run_id} expected={expected!r} → AMBIGUOUS({e.reason})"
                )

    total   = sum(v["total"]   for v in per_agent.values())
    correct = sum(v["correct"] for v in per_agent.values())
    ambiguous = sum(v["ambiguous"] for v in per_agent.values())

    return {
        "total": total,
        "correct": correct,
        "ambiguous": ambiguous,
        "accuracy": correct / total if total else 0.0,
        "skipped_no_prose": skipped_no_prose,
        "skipped_no_file": skipped_no_file,
        "per_agent": per_agent,
    }


# ── 3. Trajectory 일치도 평가 ─────────────────────────────────────────────

def _step_to_message(agent: str, mode: Optional[str], enum: str, idx: int) -> ChatCompletionMessage:
    """dcNess step → AgentEvals OpenAI-style assistant message."""
    tool_name = f"{agent}__{mode or 'DEFAULT'}"
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": f"call_{idx}",
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps({"enum": enum}),
            },
        }],
    }


def _make_trajectory(steps: list[tuple[str, Optional[str], str]]) -> list[ChatCompletionMessage]:
    """[(agent, mode, enum), ...] → AgentEvals 메시지 리스트."""
    return [_step_to_message(a, m, e, i) for i, (a, m, e) in enumerate(steps)]


# 레퍼런스 시퀀스 정의 (루프별 happy-path)
_REFERENCE_TRAJECTORIES: dict[str, list[tuple[str, Optional[str], str]]] = {
    "impl_task_loop": [
        ("module-architect", None,    "PASS"),
        ("test-engineer",    None,    "PASS"),
        ("engineer",         "IMPL",  "IMPL_DONE"),
        ("code-validator",   None,    "PASS"),
        ("pr-reviewer",      None,    "PASS"),
    ],
    "feature_build_fragment": [
        ("system-architect",    None         ,   "PASS"),
        ("module-architect",    None         ,     "PASS"),
    ],
    "polish_loop": [
        ("engineer",      "POLISH",           "POLISH_DONE"),
        ("pr-reviewer",   None,               "PASS"),
    ],
}

# 실제 실행 시나리오 (reference 와 비교)
_ACTUAL_SCENARIOS: list[dict] = [
    # strict  = 순서 포함 완전 일치
    # superset = actual ⊇ reference  → 필수 단계가 모두 실행됐는가 (누락 탐지)
    # subset   = actual ⊆ reference  → 불필요한 단계가 없는가 (이탈 탐지)
    {
        "name": "impl_happy_path",
        "reference": "impl_task_loop",
        "actual": [
            ("module-architect", None,    "PASS"),
            ("test-engineer",    None,    "PASS"),
            ("engineer",         "IMPL",  "IMPL_DONE"),
            ("code-validator",   None,    "PASS"),
            ("pr-reviewer",      None,    "PASS"),
        ],
        "expect_strict":    True,   # 순서/내용 완전 일치
        "expect_superset":  True,   # 필수 단계 모두 있음
        "expect_subset":    True,   # 이탈 없음
    },
    {
        "name": "impl_missing_test_engineer",
        "reference": "impl_task_loop",
        "actual": [
            ("module-architect", None,    "PASS"),
            # test-engineer 누락
            ("engineer",         "IMPL",  "IMPL_DONE"),
            ("code-validator",   None,    "PASS"),
            ("pr-reviewer",      None,    "PASS"),
        ],
        "expect_strict":    False,  # 단계 누락
        "expect_superset":  False,  # test-engineer 없어서 필수 단계 미충족
        "expect_subset":    True,   # 실행된 단계는 모두 reference 안에 있음
    },
    {
        "name": "impl_with_spec_gap_retry",
        "reference": "impl_task_loop",
        "actual": [
            ("module-architect", None,    "PASS"),
            ("test-engineer",    None,    "PASS"),
            ("engineer",         "IMPL",  "SPEC_GAP_FOUND"),  # spec gap 발생
            ("module-architect", None,    "PASS"),  # reference 외 단계
            ("engineer",         "IMPL",  "IMPL_DONE"),
            ("code-validator",   None,    "PASS"),
            ("pr-reviewer",      None,    "PASS"),
        ],
        "expect_strict":    False,  # 추가 step 있어서 순서 불일치
        "expect_superset":  True,   # reference 필수 단계 모두 포함
        "expect_subset":    False,  # architect/SPEC_GAP 은 reference 외 단계
    },
    {
        "name": "polish_happy_path",
        "reference": "polish_loop",
        "actual": [
            ("engineer",      "POLISH",           "POLISH_DONE"),
            ("pr-reviewer",   None,               "PASS"),
        ],
        "expect_strict":    True,
        "expect_superset":  True,
        "expect_subset":    True,
    },
]


def run_trajectory_eval() -> dict:
    """AgentEvals trajectory match 를 이용해 루프 시퀀스 정확도 측정.

    3가지 모드:
      strict   — 순서 포함 완전 일치 (happy-path 확인)
      superset — actual ⊇ reference  → 필수 단계 누락 탐지
      subset   — actual ⊆ reference  → reference 외 이탈 단계 탐지
    """
    strict_eval = create_trajectory_match_evaluator(
        trajectory_match_mode="strict",
        tool_args_match_mode="exact",
    )
    superset_eval = create_trajectory_match_evaluator(
        trajectory_match_mode="superset",
        tool_args_match_mode="ignore",  # enum 값 무시, agent/mode 만 확인
    )
    subset_eval = create_trajectory_match_evaluator(
        trajectory_match_mode="subset",
        tool_args_match_mode="ignore",
    )

    results = []
    for scenario in _ACTUAL_SCENARIOS:
        ref_steps = _REFERENCE_TRAJECTORIES[scenario["reference"]]
        ref_traj = _make_trajectory(ref_steps)
        act_traj = _make_trajectory(scenario["actual"])

        strict_got  = bool(strict_eval(outputs=act_traj, reference_outputs=ref_traj).get("score", False))
        superset_got = bool(superset_eval(outputs=act_traj, reference_outputs=ref_traj).get("score", False))
        subset_got  = bool(subset_eval(outputs=act_traj, reference_outputs=ref_traj).get("score", False))

        results.append({
            "name":              scenario["name"],
            "reference":         scenario["reference"],
            "strict_got":        strict_got,
            "superset_got":      superset_got,
            "subset_got":        subset_got,
            "strict_expected":   scenario["expect_strict"],
            "superset_expected": scenario["expect_superset"],
            "subset_expected":   scenario["expect_subset"],
            "strict_ok":         strict_got  == scenario["expect_strict"],
            "superset_ok":       superset_got == scenario["expect_superset"],
            "subset_ok":         subset_got  == scenario["expect_subset"],
        })

    total = len(results)
    return {
        "total_scenarios": total,
        "strict_correct":   sum(1 for r in results if r["strict_ok"]),
        "superset_correct": sum(1 for r in results if r["superset_ok"]),
        "subset_correct":   sum(1 for r in results if r["subset_ok"]),
        "results": results,
    }


# ── 3. 리포트 출력 ────────────────────────────────────────────────────────

def _bar(ratio: float, width: int = 20) -> str:
    filled = int(ratio * width)
    return "█" * filled + "░" * (width - filled)


def build_html_report(enum_report: dict, traj_report: dict, real_report: Optional[dict] = None) -> str:
    """eval 결과를 HTML 리포트로 변환."""
    from datetime import datetime

    acc = enum_report["accuracy"]
    total_e = enum_report["total"]
    correct_e = enum_report["correct"]

    ts = traj_report["total_scenarios"]
    sc  = traj_report["strict_correct"]
    spc = traj_report["superset_correct"]
    sbc = traj_report["subset_correct"]

    real_pass  = (real_report["accuracy"] >= 0.90) if real_report else True
    enum_pass  = acc >= 0.90
    traj_pass  = sc == ts and spc == ts and sbc == ts
    overall    = "PASS" if (enum_pass and real_pass and traj_pass) else "FAIL"
    ov_color   = "#22c55e" if overall == "PASS" else "#ef4444"

    def pct(n, d):
        return f"{n/d*100:.1f}%" if d else "—"

    def badge(ok: bool, match: bool) -> str:
        if ok:
            color = "#22c55e" if match else "#6b7280"
            label = "✓ MATCH" if match else "✓ MISS"
        else:
            color = "#ef4444"
            label = "✗ MATCH" if match else "✗ MISS"
        return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{label}</span>'

    # per-agent rows
    agent_rows = ""
    for ak, v in sorted(enum_report["per_agent"].items()):
        n, c = v["total"], v["correct"]
        r = c / n if n else 0
        bar_w = int(r * 100)
        bar_color = "#22c55e" if r == 1.0 else ("#f59e0b" if r >= 0.7 else "#ef4444")
        errors_html = ""
        if v["errors"]:
            errors_html = "<ul style='margin:4px 0 0 16px;color:#ef4444;font-size:12px'>"
            for e in v["errors"]:
                errors_html += f"<li>{e.strip()}</li>"
            errors_html += "</ul>"
        agent_rows += f"""
        <tr>
          <td style="padding:6px 12px;font-family:monospace;font-size:13px">{ak}</td>
          <td style="padding:6px 12px;text-align:center">{c}/{n}</td>
          <td style="padding:6px 16px">
            <div style="background:#e5e7eb;border-radius:4px;height:14px;width:160px;overflow:hidden">
              <div style="background:{bar_color};height:100%;width:{bar_w}%"></div>
            </div>
          </td>
          <td style="padding:6px 12px;font-weight:600;color:{bar_color}">{pct(c,n)}</td>
          <td style="padding:6px 12px">{errors_html}</td>
        </tr>"""

    # trajectory rows
    traj_rows = ""
    for r in traj_report["results"]:
        traj_rows += f"""
        <tr>
          <td style="padding:6px 12px;font-family:monospace;font-size:13px">{r['name']}</td>
          <td style="padding:6px 12px;font-size:11px;color:#6b7280">{r['reference']}</td>
          <td style="padding:6px 12px">{badge(r['strict_ok'],  r['strict_got'])}</td>
          <td style="padding:6px 12px">{badge(r['superset_ok'], r['superset_got'])}</td>
          <td style="padding:6px 12px">{badge(r['subset_ok'],  r['subset_got'])}</td>
        </tr>"""

    # real data section HTML
    real_section_html = ""
    if real_report:
        ra  = real_report["accuracy"]
        rt  = real_report["total"]
        rc  = real_report["correct"]
        rab = real_report["ambiguous"]
        rbar_color = "#22c55e" if ra >= 0.9 else ("#f59e0b" if ra >= 0.7 else "#ef4444")
        real_agent_rows = ""
        for ak, v in sorted(real_report["per_agent"].items()):
            n, c, ab = v["total"], v["correct"], v["ambiguous"]
            r = c / n if n else 0
            bw = int(r * 100)
            bc = "#22c55e" if r == 1.0 else ("#f59e0b" if r >= 0.7 else "#ef4444")
            errs_html = ""
            if v["errors"]:
                errs_html = "<ul style='margin:4px 0 0 16px;color:#ef4444;font-size:11px'>"
                for e in v["errors"][:3]:
                    errs_html += f"<li>{e.strip()}</li>"
                if len(v["errors"]) > 3:
                    errs_html += f"<li>... 외 {len(v['errors'])-3}건</li>"
                errs_html += "</ul>"
            real_agent_rows += f"""
            <tr>
              <td style="padding:6px 12px;font-family:monospace;font-size:13px">{ak}</td>
              <td style="padding:6px 12px;text-align:center">{c}/{n}</td>
              <td style="padding:6px 12px;text-align:center;color:#6b7280">{ab}</td>
              <td style="padding:6px 16px">
                <div style="background:#e5e7eb;border-radius:4px;height:14px;width:160px;overflow:hidden">
                  <div style="background:{bc};height:100%;width:{bw}%"></div>
                </div>
              </td>
              <td style="padding:6px 12px;font-weight:600;color:{bc}">{pct(c,n)}</td>
              <td style="padding:6px 12px">{errs_html}</td>
            </tr>"""
        real_section_html = f"""
<div class="card">
  <div class="card-head"><h2>2. Enum 추출 정확도 — 실제 run 데이터 (자장 프로젝트)</h2></div>
  <div class="summary-grid">
    <div class="stat"><div class="num" style="color:{rbar_color}">{pct(rc,rt)}</div><div class="lbl">실제 데이터 정확도</div></div>
    <div class="stat"><div class="num">{rc}/{rt}</div><div class="lbl">평가된 step 수<br><span style="font-size:10px;color:#94a3b8">prose_file 있는 레코드</span></div></div>
    <div class="stat"><div class="num" style="color:{'#ef4444' if rab>0 else '#22c55e'}">{rab}</div><div class="lbl">Ambiguous<br><span style="font-size:10px;color:#94a3b8">(heuristic 탐지 실패)</span></div></div>
  </div>
  <table>
    <thead><tr><th>Agent / Mode</th><th>정확/전체</th><th>모호</th><th>정확도 바</th><th>정확도</th><th>오류</th></tr></thead>
    <tbody>{real_agent_rows}</tbody>
  </table>
  <div style="padding:12px 20px;font-size:12px;color:#94a3b8;border-top:1px solid #f1f5f9">
    skip: prose_file 없음 {real_report['skipped_no_prose']}건 / 파일 미존재 {real_report['skipped_no_file']}건
  </div>
</div>"""

    traj_section_num = "3" if real_report else "2"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>dcNess Harness Eval Report</title>
<style>
  body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f8fafc; margin:0; padding:32px; color:#1e293b }}
  h1   {{ font-size:22px; font-weight:700; margin-bottom:4px }}
  .sub {{ color:#64748b; font-size:13px; margin-bottom:32px }}
  .card {{ background:#fff; border-radius:12px; box-shadow:0 1px 4px rgba(0,0,0,.08); margin-bottom:28px; overflow:hidden }}
  .card-head {{ padding:16px 20px; border-bottom:1px solid #f1f5f9; display:flex; align-items:center; gap:12px }}
  .card-head h2 {{ font-size:15px; font-weight:600; margin:0 }}
  .summary-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; padding:20px }}
  .stat {{ background:#f8fafc; border-radius:8px; padding:16px 20px; text-align:center }}
  .stat .num {{ font-size:28px; font-weight:700 }}
  .stat .lbl {{ font-size:12px; color:#64748b; margin-top:4px }}
  table {{ width:100%; border-collapse:collapse }}
  thead tr {{ background:#f8fafc }}
  th {{ padding:8px 12px; text-align:left; font-size:12px; font-weight:600; color:#64748b; border-bottom:1px solid #e2e8f0 }}
  tbody tr:hover {{ background:#fafafa }}
  .overall {{ display:inline-block; font-size:22px; font-weight:800; color:{ov_color}; padding:8px 24px; border:3px solid {ov_color}; border-radius:8px }}
</style>
</head>
<body>
<h1>dcNess Harness Eval Report</h1>
<div class="sub">AgentEvals 기반 — {now}</div>

<div class="card">
  <div class="card-head">
    <h2>종합 판정</h2>
  </div>
  <div style="padding:20px">
    <div class="overall">{overall}</div>
    {"" if overall=="PASS" else f'<p style="color:#ef4444;margin-top:12px">{"Enum 정확도 미달 " if not enum_pass else ""}{"Trajectory 예측 불일치 존재" if not traj_pass else ""}</p>'}
  </div>
</div>

<div class="card">
  <div class="card-head"><h2>1. Enum 추출 정확도 — 합성 데이터 (interpret_signal heuristic)</h2></div>
  <div class="summary-grid">
    <div class="stat"><div class="num" style="color:#22c55e">{pct(correct_e,total_e)}</div><div class="lbl">전체 정확도</div></div>
    <div class="stat"><div class="num">{correct_e}/{total_e}</div><div class="lbl">케이스 (agent/mode × 변형)</div></div>
    <div class="stat"><div class="num">{enum_report['ambiguous_ok']}</div><div class="lbl">Ambiguous 올바르게 탐지</div></div>
  </div>
  <table>
    <thead><tr><th>Agent / Mode</th><th>정확/전체</th><th>정확도 바</th><th>정확도</th><th>오류</th></tr></thead>
    <tbody>{agent_rows}</tbody>
  </table>
</div>

{real_section_html}

<div class="card">
  <div class="card-head"><h2>{traj_section_num}. Trajectory 일치도 (루프 시퀀스 검증)</h2></div>
  <div class="summary-grid">
    <div class="stat"><div class="num" style="color:{'#22c55e' if sc==ts else '#ef4444'}">{sc}/{ts}</div><div class="lbl">strict 예측 정확</div></div>
    <div class="stat"><div class="num" style="color:{'#22c55e' if spc==ts else '#ef4444'}">{spc}/{ts}</div><div class="lbl">superset 예측 정확<br><span style="font-size:10px;color:#94a3b8">(필수 단계 누락 탐지)</span></div></div>
    <div class="stat"><div class="num" style="color:{'#22c55e' if sbc==ts else '#ef4444'}">{sbc}/{ts}</div><div class="lbl">subset 예측 정확<br><span style="font-size:10px;color:#94a3b8">(이탈 단계 탐지)</span></div></div>
  </div>
  <table>
    <thead><tr><th>시나리오</th><th>레퍼런스 루프</th><th>strict</th><th>superset</th><th>subset</th></tr></thead>
    <tbody>{traj_rows}</tbody>
  </table>
  <div style="padding:12px 20px;font-size:12px;color:#94a3b8;border-top:1px solid #f1f5f9">
    strict: 순서+내용 완전 일치 &nbsp;|&nbsp; superset: actual ⊇ reference (필수 단계 누락 탐지) &nbsp;|&nbsp; subset: actual ⊆ reference (이탈 단계 탐지)
  </div>
</div>
</body>
</html>"""


def print_report(enum_report: dict, traj_report: dict, real_report: Optional[dict] = None) -> None:
    print("\n" + "=" * 60)
    print("  dcNess Harness Eval — AgentEvals 기반")
    print("=" * 60)

    # ── Enum 추출 정확도 ──
    print("\n### 1. Enum 추출 정확도 (interpret_signal heuristic)\n")
    acc = enum_report["accuracy"]
    total = enum_report["total"]
    correct = enum_report["correct"]
    print(f"  전체: {correct}/{total}  {_bar(acc)}  {acc*100:.1f}%")
    print()

    # per-agent 테이블
    print(f"  {'Agent/Mode':<40} {'정확':<8} {'전체':<8} {'정확도'}")
    print(f"  {'-'*40} {'-'*8} {'-'*8} {'-'*8}")
    for ak, v in sorted(enum_report["per_agent"].items()):
        n, c = v["total"], v["correct"]
        r = c / n if n else 0
        mark = "✓" if r == 1.0 else ("△" if r >= 0.7 else "✗")
        print(f"  {ak:<40} {c:<8} {n:<8} {r*100:.0f}% {mark}")
        for err in v["errors"]:
            print(f"    {err}")

    # ── Real Data Enum 정확도 ──
    if real_report:
        print("\n\n### 2. Enum 추출 정확도 — 실제 run 데이터 (자장 프로젝트)\n")
        ra = real_report["accuracy"]
        rt = real_report["total"]
        rc = real_report["correct"]
        rab = real_report["ambiguous"]
        print(f"  전체: {rc}/{rt}  {_bar(ra)}  {ra*100:.1f}%")
        print(f"  Ambiguous (heuristic 탐지 실패): {rab}건")
        print(f"  prose_file 없어 skip: {real_report['skipped_no_prose']}건")
        print(f"  파일 존재하지 않아 skip: {real_report['skipped_no_file']}건")
        print()
        print(f"  {'Agent/Mode':<40} {'정확':<8} {'전체':<8} {'모호':<8} {'정확도'}")
        print(f"  {'-'*40} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        for ak, v in sorted(real_report["per_agent"].items()):
            n, c, ab = v["total"], v["correct"], v["ambiguous"]
            r = c / n if n else 0
            mark = "✓" if r == 1.0 else ("△" if r >= 0.7 else "✗")
            print(f"  {ak:<40} {c:<8} {n:<8} {ab:<8} {r*100:.0f}% {mark}")
            for err in v["errors"][:3]:  # 오류 최대 3건만 표시
                print(f"    {err}")

    # ── Trajectory 일치도 ──
    traj_section_num = "3" if real_report else "2"
    print(f"\n\n### {traj_section_num}. Trajectory 일치도 (루프 시퀀스 검증)\n")
    ts  = traj_report["total_scenarios"]
    sc  = traj_report["strict_correct"]
    spc = traj_report["superset_correct"]
    sbc = traj_report["subset_correct"]
    print(f"  strict   (순서+내용 완전 일치) 예측 정확: {sc}/{ts}")
    print(f"  superset (필수 단계 누락 탐지) 예측 정확: {spc}/{ts}")
    print(f"  subset   (이탈 단계 탐지)     예측 정확: {sbc}/{ts}")
    print()

    hdr = f"  {'시나리오':<32} {'strict':<9} {'superset':<11} {'subset':<9}"
    print(hdr)
    print(f"  {'-'*32} {'-'*9} {'-'*11} {'-'*9}")
    for r in traj_report["results"]:
        def _cell(got: bool, expected: bool, ok: bool) -> str:
            v = "MATCH" if got else "MISS"
            mark = "✓" if ok else "✗"
            return f"{mark}{v}"
        sc_cell  = _cell(r["strict_got"],   r["strict_expected"],   r["strict_ok"])
        spc_cell = _cell(r["superset_got"], r["superset_expected"],  r["superset_ok"])
        sbc_cell = _cell(r["subset_got"],   r["subset_expected"],    r["subset_ok"])
        print(f"  {r['name']:<32} {sc_cell:<9} {spc_cell:<11} {sbc_cell}")

    print("\n" + "=" * 60)

    # 종합 판정
    enum_pass  = acc >= 0.90
    real_pass  = (real_report["accuracy"] >= 0.90) if real_report else True
    traj_pass  = sc == ts and spc == ts and sbc == ts
    overall    = "PASS" if (enum_pass and real_pass and traj_pass) else "FAIL"
    print(f"\n  종합 판정: {overall}")
    if not enum_pass:
        print(f"    - Enum 정확도 (합성) {acc*100:.1f}% < 90%")
    if not real_pass:
        print(f"    - Enum 정확도 (실제) {real_report['accuracy']*100:.1f}% < 90%")
    if not traj_pass:
        print(f"    - Trajectory 예측 불일치 존재")
    print()


if __name__ == "__main__":
    import argparse, subprocess, os

    parser = argparse.ArgumentParser()
    parser.add_argument("--html", metavar="PATH", nargs="?", const="eval_report.html",
                        help="HTML 리포트 출력 경로 (기본: eval_report.html)")
    parser.add_argument("--open", action="store_true", help="생성 후 브라우저 자동 오픈")
    parser.add_argument("--real-data", metavar="HARNESS_ROOT",
                        help="실제 run 데이터 경로 (예: /path/to/project/.claude/harness-state)")
    args = parser.parse_args()

    print("Enum 추출 정확도 평가 중 (합성 데이터)...")
    enum_report = run_enum_accuracy_eval()

    real_report = None
    if args.real_data:
        harness_root = Path(args.real_data)
        if not harness_root.exists():
            print(f"[WARN] --real-data 경로 없음: {harness_root}")
        else:
            print(f"실제 run 데이터 평가 중 ({harness_root})...")
            real_report = run_real_data_eval(harness_root)

    print("Trajectory 일치도 평가 중...")
    traj_report = run_trajectory_eval()

    print_report(enum_report, traj_report, real_report)

    if args.html is not None:
        out = Path(args.html)
        out.write_text(
            build_html_report(enum_report, traj_report, real_report),
            encoding="utf-8",
        )
        print(f"HTML 리포트 저장: {out.resolve()}")
        if args.open:
            subprocess.run(["open", str(out.resolve())], check=False)
