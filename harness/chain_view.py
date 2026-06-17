"""chain_view — impl-loop chain 진행 뷰 자동 렌더 (#755).

진행 뷰 규칙 SSOT = `skills/impl-loop/SKILL.md` "진행 뷰 (task 리스트)" 절.
본 모듈은 그 규칙(엔진별 sub-step / 마감 acceptance / task 총수별 다시그리기
분기 / 완료-현재-예정 마킹)을 *코드로 옮길 뿐* 새 규칙을 만들지 않는다.

성격 — **도구이지 게이트 아님**:

- 입력은 task list(메인이 만든 chain task 메타) + current task index 뿐이다.
  run state 를 읽거나 쓰지 않는 **순수 변환**이라, 미사용해도 chain 진행을
  막지 않고 메인이 수동 rebuild 로 폴백할 수 있다 (AC: 폴백 보장).
- 출력은 (1) 사용자 가시용 ASCII 진행 뷰 `view`, (2) 메인이 Task 시스템에
  적용할 선언적 operation 시퀀스 `operations`, (3) 비용 분기 `strategy` 다.
  메인은 그 출력을 *적용만* 하고 들여쓰기·완료/현재/예정 마킹·sub-step 펼침
  규칙을 직접 계산하지 않는다.

진행 뷰 규칙(SSOT 인용):

- sub-step 수 = 엔진별 (SKILL line 435):
    build-worker 2 / build-worker-deep 3 / full-4 4 / advanced 5.
    story 마감 task +1 (`product-acceptance`),
    epic 마감 task +2 (`product-acceptance:STORY` / `product-acceptance:EPIC`).
- task 완료 → 다음 다시그리기 (SKILL 비용 분기): ≤10 full / 11~20 partial /
    >20 minimal. prev 헤더 완료(✓)는 **모든 tier 공통 불변식**(O(1), 생략 시
    in_progress 누적). 비용 분기가 제어하는 비싼 부분은 tail 재생성뿐이고,
    sub-step 펼침은 재생성 경로(full tier 또는 마감 task)에서만 가능하다
    (flat 리스트 nesting 제약).
- 완료 task 한 줄(✓) / 현재 task sub-step 펼침(▾, 재생성 tier 한정) /
    예정 task 대기 줄(○). `view ≡ operations` — 진행 뷰는 operation 적용
    결과와 항상 일치한다.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "ChainTask",
    "ENGINE_SUBSTEPS",
    "normalize_engine",
    "substeps_for",
    "redraw_strategy",
    "render_view",
    "transition_operations",
    "initial_operations",
    "parse_tasks",
    "build_chain_view",
]

# ── 엔진별 base sub-step (SKILL line 435 + impl-ui-design-loop 진본) ──
#
# impl-task-loop 엔진(build-worker/deep/full-4/advanced)은 SKILL line 435,
# impl-ui-design-loop(UI 감지 → designer + 사용자 PICK 선두)는 SKILL line 16-18
# `expected_steps` 가 진본. 모두 그대로 옮긴다(새 라벨 발명 X). 여기에 없는
# 변종은 task 입력의 `substeps` 명시 override 로 표현한다([`substeps_for`]).
ENGINE_SUBSTEPS: Dict[str, List[str]] = {
    "build-worker": ["build-worker", "pr-reviewer"],
    "build-worker-deep": ["module-architect", "build-worker", "pr-reviewer"],
    "full-4": ["test-engineer", "engineer:IMPL", "code-validator", "pr-reviewer"],
    "advanced": [
        "module-architect",
        "test-engineer",
        "engineer:IMPL",
        "code-validator",
        "pr-reviewer",
    ],
    # impl-ui-design-loop (풀 4-agent 한정, 선두 designer + 사용자 PICK) — 6 step.
    "ui": [
        "designer",
        "사용자 PICK",
        "test-engineer",
        "engineer:IMPL",
        "code-validator",
        "pr-reviewer",
    ],
    # UI + deep task 보강 (designer 앞 module-architect) — 7 step.
    "ui-advanced": [
        "module-architect",
        "designer",
        "사용자 PICK",
        "test-engineer",
        "engineer:IMPL",
        "code-validator",
        "pr-reviewer",
    ],
}

# frontmatter `engine` 값(#703: 2agent/4agent) + 흔한 별칭 → 정규 키.
_ENGINE_ALIASES: Dict[str, str] = {
    "build-worker": "build-worker",
    "2agent": "build-worker",
    "bw": "build-worker",
    "build-worker-deep": "build-worker-deep",
    "3agent": "build-worker-deep",
    "bw-deep": "build-worker-deep",
    "full-4": "full-4",
    "4agent": "full-4",
    "full": "full-4",
    "advanced": "advanced",
    "advanced-fallback": "advanced",
    "5agent": "advanced",
    "ui": "ui",
    "ui-design-loop": "ui",
    "impl-ui-design-loop": "ui",
    "ui-advanced": "ui-advanced",
    "ui-design-loop-advanced": "ui-advanced",
}

# 마감 task 의 추가 sub-step (SKILL line 435 + 마감 acceptance 절).
_CLOSE_ACCEPTANCE: Dict[str, List[str]] = {
    "story": ["product-acceptance"],
    "epic": ["product-acceptance:STORY", "product-acceptance:EPIC"],
}

# 진행 뷰 글리프 (SKILL lines 427-432).
_GLYPH_DONE = "✓"
_GLYPH_CURRENT = "▾"
_GLYPH_PENDING = "○"
_SUBSTEP_PREFIX = "   ㄴ "


def normalize_engine(engine: Any) -> str:
    """엔진 표기를 정규 키로. 미상/미지원 값은 ValueError."""
    if not isinstance(engine, str):
        raise ValueError(f"engine 은 문자열이어야 한다: {engine!r}")
    key = engine.strip().lower()
    if key in _ENGINE_ALIASES:
        return _ENGINE_ALIASES[key]
    raise ValueError(
        f"미지원 engine: {engine!r} (지원: {sorted(set(_ENGINE_ALIASES))})"
    )


@dataclass(frozen=True)
class ChainTask:
    """chain task 한 개의 진행 뷰 입력 (정규화 결과).

    name     — 모듈명 (진행 뷰 헤더 `task{n} · {name}`).
    engine   — 정규 엔진 키 (ENGINE_SUBSTEPS 키). substeps 명시 시 None 허용.
    closes   — 마감 단위. None(중간) / "story" / "epic".
    substeps — base sub-step 명시 override (tuple). 지정 시 engine preset 대신
               이 라벨들을 base 로 쓴다 — SKILL 진행 뷰 절이 enum 하지 않은
               변종(미래 flow 등)을 메인이 직접 라벨로 표현하는 escape hatch.
               마감 acceptance 는 override 여부와 무관하게 append.
    """

    name: str
    engine: Optional[str] = None
    closes: Optional[str] = None
    substeps: Optional[tuple] = None

    def __post_init__(self) -> None:  # 방어 — 직접 생성 시에도 불변식 보장
        if self.substeps is None:
            if self.engine not in ENGINE_SUBSTEPS:
                raise ValueError(f"미지원 engine 키: {self.engine!r}")
        else:
            if not self.substeps or not all(
                isinstance(s, str) and s.strip() for s in self.substeps
            ):
                raise ValueError("substeps override 는 비지 않은 문자열 목록이어야 한다")
            if self.engine is not None and self.engine not in ENGINE_SUBSTEPS:
                raise ValueError(f"미지원 engine 키: {self.engine!r}")
        if self.closes is not None and self.closes not in _CLOSE_ACCEPTANCE:
            raise ValueError(
                f"closes 는 None/story/epic 만: {self.closes!r}"
            )


def substeps_for(task: ChainTask) -> List[str]:
    """현재 task 의 sub-step 라벨 = (명시 substeps 또는 엔진 base) + 마감 acceptance."""
    if task.substeps is not None:
        steps = list(task.substeps)
    else:
        if task.engine is None:
            raise ValueError("engine or substeps is required")
        steps = list(ENGINE_SUBSTEPS[task.engine])
    if task.closes:
        steps.extend(_CLOSE_ACCEPTANCE[task.closes])
    return steps


def redraw_strategy(total: int) -> str:
    """task 총수별 다시그리기 분기 (SKILL lines 438-442).

    ≤10 → full / 11~20 → partial / >20 → minimal.
    """
    if total <= 10:
        return "full"
    if total <= 20:
        return "partial"
    return "minimal"


def _header_subject(index: int, task: ChainTask) -> str:
    """진행 뷰 헤더 텍스트 (1-based 표시)."""
    return f"task{index + 1} · {task.name}"


def _substep_subject(label: str) -> str:
    """진행 뷰 sub-step 텍스트 (들여쓰기 + ㄴ)."""
    return f"{_SUBSTEP_PREFIX}{label}"


def _expands_substeps(strategy: str, task: Optional[ChainTask]) -> bool:
    """현재 task 의 sub-step 을 펼치는가 (= 작업 적용 시 sub-step 이 보이는가).

    flat Task 리스트는 중간삽입이 안 돼 sub-step nesting 에 tail 재생성이
    필요하다(SKILL line 444). 따라서 sub-step 펼침은 재생성을 수행하는
    경로에서만 가능하다:

    - full(≤10): 매 경계 재생성 → 펼침.
    - 마감 task(story/epic close): chain 크기와 무관하게 펼침 — `product-acceptance`
      sub-step 가시성이 마감 게이트에 중요하므로 그 경계만 재생성한다(AC).
    - partial/minimal 의 비-마감 task: 재생성 skip → 미펼침(SKILL 비용 분기).
    """
    if task is None:
        return False
    return strategy == "full" or task.closes is not None


def render_view(
    tasks: Sequence[ChainTask], current: int, *, show_substeps: Optional[bool] = None
) -> str:
    """사용자 가시용 ASCII 진행 뷰 (완료 ✓ / 현재 ▾(+펼침) / 예정 ○).

    `view ≡ operations` 불변식 — 진행 뷰는 operation 적용 결과와 일치해야 한다.
    그래서 sub-step 펼침 여부(`show_substeps`)는 [`_expands_substeps`](#) 가 정하는
    operation 의 sub-step 생성 여부와 동일하게 맞춘다. 미지정 시 현재 task 의
    전략 기반 기본값을 쓴다.

    current == len(tasks) 면 전체 완료(터미널) — 모두 ✓ 한 줄.
    """
    if not tasks:
        raise ValueError("tasks 가 비어있다")
    if not (0 <= current <= len(tasks)):
        raise ValueError(
            f"current 범위 밖: {current} (0~{len(tasks)})"
        )
    if show_substeps is None:
        cur_task = tasks[current] if current < len(tasks) else None
        show_substeps = _expands_substeps(redraw_strategy(len(tasks)), cur_task)
    lines: List[str] = []
    for i, task in enumerate(tasks):
        if i < current:
            lines.append(f"{_GLYPH_DONE} {_header_subject(i, task)}")
        elif i == current:
            lines.append(f"{_GLYPH_CURRENT} {_header_subject(i, task)}")
            if show_substeps:
                for label in substeps_for(task):
                    lines.append(_substep_subject(label))
        else:
            lines.append(f"{_GLYPH_PENDING} {_header_subject(i, task)}")
    return "\n".join(lines)


def initial_operations(
    tasks: Sequence[ChainTask], current: int
) -> List[Dict[str, Any]]:
    """chain 진입 시 전체 task list 최초 생성 operation 시퀀스.

    current 이전 = completed, current = in_progress + sub-step, 이후 = pending.
    (보통 current=0 — 전부 pending + task0 만 in_progress.)
    """
    ops: List[Dict[str, Any]] = []
    for i, task in enumerate(tasks):
        if i < current:
            status = "completed"
        elif i == current:
            status = "in_progress"
        else:
            status = "pending"
        ops.append(
            {
                "op": "create_header",
                "index": i,
                "subject": _header_subject(i, task),
                "status": status,
            }
        )
        if i == current:
            for label in substeps_for(task):
                ops.append(
                    {
                        "op": "create_substep",
                        "index": i,
                        "subject": _substep_subject(label),
                        "label": label,
                    }
                )
    return ops


def transition_operations(
    tasks: Sequence[ChainTask], prev: int, current: int
) -> List[Dict[str, Any]]:
    """task `prev` 완료 → `current` 진입 시 다시그리기 operation 시퀀스.

    불변식 — prev 헤더는 **모든 전략에서 완료(✓) 마킹**한다. "완료 task = ✓
    한 줄"(SKILL line 425)은 비용 분기보다 상위 불변식이고, prev 완료는 O(1)
    이라 비용 절감 대상이 아니다. 이를 생략하면 경계마다 in_progress 가 누적돼
    진행 뷰가 깨진다. 비용 분기가 제어하는 비싼 부분은 **tail 재생성**뿐이다.

    sub-step nesting 은 flat 리스트라 tail 재생성을 해야만 부모 밑에 온다
    (SKILL line 444). 그래서 sub-step 펼침 = 재생성 경로 = [`_expands_substeps`]:

    - full(≤10) **또는 마감 task**: ① prev sub-step delete ② prev header complete
      ③ current~end header delete ④ current(in_progress)+sub-step+남은(pending) 재생성
    - partial/minimal 의 비-마감 task: ① prev sub-step delete ② prev header complete
      ③ current header in_progress (재생성 skip → sub-step 미펼침)

    current == len(tasks) (마지막 task 완료, 다음 없음) 면 prev 정리만 한다.
    """
    total = len(tasks)
    if not (0 <= prev < total):
        raise ValueError(f"prev 범위 밖: {prev} (0~{total - 1})")
    if not (0 <= current <= total):
        raise ValueError(f"current 범위 밖: {current} (0~{total})")
    # chain 은 경계마다 task 1개씩 전진 — prev 는 반드시 current 직전.
    # 비인접 jump 은 transition 으로 표현 불가(view ≡ operations 위반:
    # view 는 current 미만 전부 ✓ 인데 operations 는 prev 만 완료). 임의
    # current 로의 점프(resume 등)는 --initial(전체 재생성)을 쓴다.
    if current != prev + 1:
        raise ValueError(
            f"비인접 transition: prev={prev}, current={current} "
            f"(prev+1 != current). 임의 current 점프는 initial 모드를 쓸 것."
        )
    strategy = redraw_strategy(total)
    terminal = current >= total

    # ① prev sub-step delete ② prev header complete (모든 전략 공통 불변식).
    ops: List[Dict[str, Any]] = [
        {"op": "delete_substeps", "index": prev},
        {"op": "complete_header", "index": prev},
    ]

    if terminal:
        return ops

    cur_task = tasks[current]
    if not _expands_substeps(strategy, cur_task):
        # 재생성 skip — 다음 헤더만 in_progress (sub-step 미펼침).
        ops.append({"op": "set_in_progress", "index": current})
        return ops

    # 재생성 경로 — current~end 헤더 삭제 후 sub-step nesting 되게 다시 그린다.
    for k in range(current, total):
        ops.append({"op": "delete_header", "index": k})
    for k in range(current, total):
        task = tasks[k]
        status = "in_progress" if k == current else "pending"
        ops.append(
            {
                "op": "create_header",
                "index": k,
                "subject": _header_subject(k, task),
                "status": status,
            }
        )
        if k == current:
            for label in substeps_for(task):
                ops.append(
                    {
                        "op": "create_substep",
                        "index": k,
                        "subject": _substep_subject(label),
                        "label": label,
                    }
                )
    return ops


def build_chain_view(
    tasks: Sequence[ChainTask],
    current: int,
    *,
    prev: Optional[int] = None,
    initial: bool = False,
) -> Dict[str, Any]:
    """진행 뷰 payload 산출 (CLI / 호출자 공용 진입).

    operation_mode:
    - "initial"    — 전체 task list 최초 생성 (initial=True 이거나 current==0
                     이고 prev 미지정 → transition 불가).
    - "transition" — prev(기본 current-1) → current 경계 다시그리기.
    """
    total = len(tasks)
    if total == 0:
        raise ValueError("tasks 가 비어있다")
    if not (0 <= current <= total):
        raise ValueError(f"current 범위 밖: {current} (0~{total})")

    strategy = redraw_strategy(total)
    cur_task = tasks[current] if current < total else None

    effective_prev = prev if prev is not None else current - 1
    use_initial = initial or effective_prev < 0

    if use_initial:
        ops = initial_operations(tasks, current)
        mode = "initial"
        # initial 은 최초 1회 전체 생성 — 현재 task sub-step 을 항상 펼친다.
        expands = cur_task is not None
    else:
        ops = transition_operations(tasks, effective_prev, current)
        mode = "transition"
        expands = _expands_substeps(strategy, cur_task)

    # view ≡ operations 불변식 — 펼침 여부를 operation 의 sub-step 생성과 일치.
    view = render_view(tasks, current, show_substeps=expands)
    current_substeps = substeps_for(cur_task) if (expands and cur_task) else []

    return {
        "task_total": total,
        "current_index": current,
        "strategy": strategy,
        "operation_mode": mode,
        "substeps_expanded": expands,
        "view": view,
        "current_substeps": current_substeps,
        "operations": ops,
    }


# ── 입력 파싱 (JSON-ish) ────────────────────────────────────────


def parse_tasks(raw: Any) -> List[ChainTask]:
    """task list (dict 목록) → ChainTask 목록.

    각 항목 필수 키: name + (engine 또는 substeps 중 하나).
    선택: closes (None/story/epic), substeps (base 라벨 명시 override).
    """
    if not isinstance(raw, list):
        raise ValueError("tasks 는 리스트여야 한다")
    tasks: List[ChainTask] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"tasks[{i}] 는 객체여야 한다: {item!r}")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"tasks[{i}].name 누락/빈값")

        raw_substeps = item.get("substeps")
        substeps = None
        if raw_substeps not in ("", None, []):
            if not isinstance(raw_substeps, list) or not all(
                isinstance(s, str) and s.strip() for s in raw_substeps
            ):
                raise ValueError(
                    f"tasks[{i}].substeps 는 비지 않은 문자열 목록이어야 한다"
                )
            substeps = tuple(s.strip() for s in raw_substeps)

        raw_engine = item.get("engine")
        if raw_engine in ("", None):
            if substeps is None:
                raise ValueError(
                    f"tasks[{i}] 는 engine 또는 substeps 중 하나가 필요하다"
                )
            engine = None
        else:
            engine = normalize_engine(raw_engine)

        closes = item.get("closes")
        if closes in ("", None):
            closes = None
        elif closes not in _CLOSE_ACCEPTANCE:
            raise ValueError(
                f"tasks[{i}].closes 는 None/story/epic 만: {closes!r}"
            )
        tasks.append(
            ChainTask(
                name=name.strip(), engine=engine, closes=closes, substeps=substeps
            )
        )
    return tasks


def _load_input(source: str) -> Dict[str, Any]:
    """--tasks 입력 로드. '-' 면 stdin, 아니면 파일 경로."""
    if source == "-":
        text = sys.stdin.read()
    else:
        from pathlib import Path

        text = Path(source).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("입력 JSON 은 {tasks, current} 객체여야 한다")
    return data


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 진입 — `session_state.py` 의 `chain-view` 서브커맨드가 위임.

    독립 실행도 가능: `python -m harness.chain_view --tasks - --current 1`.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="chain-view",
        description="impl-loop chain 진행 뷰 자동 렌더 (#755) — 도구이지 게이트 아님",
    )
    parser.add_argument(
        "--tasks",
        required=True,
        help="task list JSON 경로 ('-' = stdin). {tasks:[{name,engine,closes?}], current?}",
    )
    parser.add_argument(
        "--current",
        type=int,
        default=None,
        help="현재(in_progress) task 0-based index. 미지정 시 입력 JSON 의 current.",
    )
    parser.add_argument(
        "--prev",
        type=int,
        default=None,
        help="직전 완료 task 0-based index (transition). 반드시 current-1(인접). "
        "미지정 시 current-1. 임의 current 점프는 --initial 을 쓸 것.",
    )
    parser.add_argument(
        "--initial",
        action="store_true",
        help="전체 task list 최초 생성/재생성 operation 산출 (임의 current 점프 포함).",
    )
    args = parser.parse_args(argv)

    try:
        data = _load_input(args.tasks)
        tasks = parse_tasks(data.get("tasks", []))
        current = args.current if args.current is not None else int(data.get("current", 0))
        payload = build_chain_view(
            tasks, current, prev=args.prev, initial=args.initial
        )
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"[chain-view] 입력 오류: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
