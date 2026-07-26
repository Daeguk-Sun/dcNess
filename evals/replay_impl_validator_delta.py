#!/usr/bin/env python3
"""Run a two-round live replay for the impl-validator delta contract.

This is a manual, provider-backed performance check. It is not a CI gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "docs/plugin/agents/impl-validator/impl-validator-agent.md"


def _module_text(index: int) -> str:
    lines = [
        f"# module-{index:03d}/service.py",
        "",
        f"- owner: module_{index:03d}",
        "- public contract: unchanged",
        "- tests: unit and integration PASS",
        "- registration: unchanged",
    ]
    if index == 18:
        lines.extend(
            [
                "- changed code: `if messages_changed: persist(canonical_recipient)`",
                "- behavior: an unchanged existing row keeps its stored recipient.",
                "- contract: list and detail must show the same canonical recipient.",
            ]
        )
    elif index == 59:
        lines.extend(
            [
                "- changed code: `target = canonical or selected_message.address`",
                "- behavior: an outgoing MMS message address can be the account self-number.",
                "- contract: retransmit must never target the account self-number.",
            ]
        )
    elif index == 103:
        lines.extend(
            [
                "- changed code: `nexus://messages/thread/{id}`",
                "- router contract: a single-thread route requires `simple=true`.",
                "- tests: notification tap route has no assertion.",
            ]
        )
    else:
        lines.extend(
            [
                "- changed code: local naming/branch simplification only.",
                "- behavior: no entrypoint, state-owner, or dependency-edge change.",
                "- evidence: focused regression assertion covers the changed branch.",
            ]
        )
    for fact in range(1, 42):
        lines.append(
            f"- review fact {fact:02d}: module-{index:03d} keeps invariant "
            f"`owner_{index:03d}_state_{fact:02d}` unchanged with matching evidence."
        )
    lines.append("")
    return "\n".join(lines)


def _delta_modules() -> dict[str, str]:
    return {
        "module-018.md": """# module-018/service.py
- Always compare the stored recipient with the canonical recipient and persist on mismatch.
- Added an unchanged-message-row self-heal regression assertion.
""",
        "module-059.md": """# module-059/service.py
- Removed the selected-message fallback.
- Abort retransmit when the canonical thread recipient is unavailable.
- Added outgoing-MMS/self-number regression assertions.
""",
        "module-103.md": """# module-103/service.py
- Notification deep links now append `?simple=true`.
- Added a notification-tap single-thread routing assertion.
""",
        "module-104.md": """# module-104/retry_controller.py
- New code: `authorized = request.retry or policy.authorize(request.actor)`.
- A caller-controlled retry flag therefore bypasses the existing authorization policy.
""",
    }


def _run_claude(prompt: str, model: str, case_dir: Path) -> tuple[str, float]:
    started = time.monotonic()
    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--model",
            model,
            "--safe-mode",
            "--tools",
            "Read",
            "Glob",
            "--add-dir",
            str(ROOT),
            "--add-dir",
            str(case_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        raise RuntimeError(
            f"claude invocation failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip(), round(elapsed, 3)


def _judge(
    round_one: str, round_two: str, model: str, judge_cwd: Path
) -> tuple[bool, str]:
    prompt = f"""도구를 호출하지 말고 제공된 두 보고만 읽어 아래 품질 계약을 채점하라.

- 1라운드는 전체 candidate에서 세 결함(목록 canonical self-heal, retransmit self-number fallback,
  notification deep link simple=true 누락)을 모두 finding으로 잡아야 한다.
- 2라운드는 세 finding의 근본 해소를 확인하고 신규 authorization bypass를 finding으로 잡아야 한다.
- 2라운드는 delta 판정 범위, 이전 holistic 검토 이력 재사용 근거, 이전/현재 candidate와 receipt,
  전체 재독 승격 조건을 설명해야 한다.
- 자유 prose 형식은 채점하지 않는다.

[1라운드]
{round_one}

[2라운드]
{round_two}

모두 충족하면 마지막 줄에 RESULT: PASS, 아니면 RESULT: FAIL만 쓴다."""
    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--model",
            model,
            "--safe-mode",
            "--tools",
            "",
        ],
        cwd=judge_cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"judge invocation failed ({result.returncode}): {result.stderr.strip()}"
        )
    report = result.stdout.strip()
    return report.splitlines()[-1:] == ["RESULT: PASS"], report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--modules", type=int, default=110)
    parser.add_argument("--minimum-reduction-percent", type=float, default=15.0)
    parser.add_argument("--minimum-reduction-seconds", type=float, default=30.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if shutil.which("claude") is None:
        parser.error("claude CLI is required")
    if args.modules < 103:
        parser.error("--modules must be at least 103")

    case_dir = args.output_dir.resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    if any(case_dir.iterdir()):
        parser.error(f"--output-dir must be empty: {case_dir}")

    candidate_dir = case_dir / "candidate-round1"
    delta_dir = case_dir / "candidate-delta"
    receipt = case_dir / "round1-receipt.md"
    round_two_report = case_dir / "round2-report.md"
    judge_report = case_dir / "judge.md"
    metadata_path = case_dir / "metadata.json"
    candidate_dir.mkdir()
    for index in range(1, args.modules + 1):
        candidate_dir.joinpath(f"module-{index:03d}.md").write_text(
            _module_text(index), encoding="utf-8"
        )

    round_one_prompt = f"""너는 final merge candidate를 검증하는 impl-validator다.
먼저 `{VALIDATOR}`를 Read한다. base `1111111111111111111111111111111111111111`,
HEAD `2222222222222222222222222222222222222222`, tree
`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`인 첫 candidate의 변경 파일 {args.modules}개가
`{candidate_dir}`에 각각 있다. Glob으로 목록을 확정하고 모든 파일을 Read해 첫 라운드
전체 holistic 범위로 검토한다.
근거와 영향 범위를 자유 prose로 쓰고 마지막 단락에 PASS, FAIL, ESCALATE 중 하나를 명시한다."""
    round_one, round_one_seconds = _run_claude(
        round_one_prompt, args.model, case_dir
    )
    receipt.write_text(round_one + "\n", encoding="utf-8")
    receipt_sha = hashlib.sha256((round_one + "\n").encode()).hexdigest()
    delta_dir.mkdir()
    for name, text in _delta_modules().items():
        delta_dir.joinpath(name).write_text(text, encoding="utf-8")

    round_two_prompt = f"""너는 같은 close의 impl-validator 재리뷰를 수행한다.
먼저 `{VALIDATOR}`를 Read한다. 다음 입력으로 판정 범위를 스스로 정한다.

- retry round: 2
- 직전 receipt: `{receipt}`
- receipt sha256: `{receipt_sha}`
- 직전 candidate HEAD/tree/workspace root:
  2222222222222222222222222222222222222222 /
  aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa / {case_dir}
- 현재 candidate HEAD/tree/workspace root:
  3333333333333333333333333333333333333333 /
  bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb / {case_dir}
- 직전 candidate HEAD..현재 candidate HEAD의 변경 파일 4개: `{delta_dir}`
- 전체 첫 candidate는 필요하면 `{candidate_dir}`에서 읽을 수 있다.

근거와 영향 범위를 자유 prose로 쓰고 마지막 단락에 PASS, FAIL, ESCALATE 중 하나를 명시한다."""
    round_two, round_two_seconds = _run_claude(
        round_two_prompt, args.model, case_dir
    )
    round_two_report.write_text(round_two + "\n", encoding="utf-8")

    judge_cwd = case_dir / "judge-workspace"
    judge_cwd.mkdir()
    quality, judge = _judge(round_one, round_two, args.model, judge_cwd)
    judge_report.write_text(judge + "\n", encoding="utf-8")
    reduction = round(
        100 * (round_one_seconds - round_two_seconds) / round_one_seconds,
        1,
    )
    reduction_seconds = round(round_one_seconds - round_two_seconds, 3)
    result = {
        "schema_version": 1,
        "fixture": {
            "modules": args.modules,
            "first_candidate_files": len(list(candidate_dir.glob("*.md"))),
            "first_candidate_lines": sum(
                len(path.read_text(encoding="utf-8").splitlines())
                for path in candidate_dir.glob("*.md")
            ),
            "first_candidate_bytes": sum(
                path.stat().st_size for path in candidate_dir.glob("*.md")
            ),
            "delta_files": len(list(delta_dir.glob("*.md"))),
            "delta_bytes": sum(
                path.stat().st_size for path in delta_dir.glob("*.md")
            ),
        },
        "runtime": {"provider": "claude-cli", "model": args.model},
        "rounds": [
            {
                "round": 1,
                "review_scope": "full",
                "elapsed_seconds": round_one_seconds,
                "quality_contract_preserved": quality,
            },
            {
                "round": 2,
                "review_scope": "delta",
                "elapsed_seconds": round_two_seconds,
                "quality_contract_preserved": quality,
            },
        ],
        "reduction_seconds": reduction_seconds,
        "reduction_percent": reduction,
        "quality_contract_preserved": quality,
        "replay_command": (
            "python3.11 evals/replay_impl_validator_delta.py "
            "--model sonnet --modules 110 --minimum-reduction-percent 15 "
            "--minimum-reduction-seconds 30 "
            "--output-dir <empty-dir>"
        ),
        "limitations": [
            "Provider latency varies; this paired replay is evidence for the scoped "
            "contract, not a model-speed guarantee.",
            "The fixture preserves the observed 110-file and 5,500-line "
            "shape but uses synthetic module summaries rather than product source.",
            "A separate human verification remains required on one real story close.",
        ],
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    metadata_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return not (
        quality
        and reduction >= args.minimum_reduction_percent
        and reduction_seconds >= args.minimum_reduction_seconds
    )


if __name__ == "__main__":
    raise SystemExit(main())
