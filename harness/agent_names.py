"""agent_names.py — dcness sub-agent 이름 정규화 SSOT (issue #383 / #598).

CC hook payload / transcript 의 agent_type 는 plugin namespace prefix (`dcness:engineer`)
가 붙거나 옛 alias (`validator`) 일 수 있다. boundary (`agent_boundary`) / trace /
histogram / review 가 동일 canonical 이름으로 매칭하도록 본 모듈이 *단일* 정규화를
제공한다.

경량(stdlib only) — file-guard PreToolUse 핫패스에서 import 해도 안전. `run_review`
가 본 모듈을 재-export 해 backward compat 유지 (옛 `run_review._normalize_agent_type`
/ `run_review.LEGACY_AGENT_ALIASES` 참조 보존).
"""
from __future__ import annotations

from typing import Optional


# issue #383 — 옛 통합형 agent 이름 alias. 0.2.16 loop-procedure.md 의 bare
# `validator` 표현 학습으로 메인 Claude 가 `dcness:validator` 호출한 잔재
# (jajang 21건 trace 확인). backward compat + 옛 데이터 review 회복 위해 정식 이름 흡수.
LEGACY_AGENT_ALIASES: dict[str, str] = {
    "validator": "impl-validator",
}


def normalize_agent_type(agent_type: Optional[str]) -> Optional[str]:
    """`dcness:architect:system-design` → `architect`. None / 비-dcness → 원형 그대로.

    `dcness:` namespace prefix 제거 후 `LEGACY_AGENT_ALIASES` 적용. boundary /
    trace / histogram 매칭 전 호출해 namespaced(`dcness:impl-validator`) 가 ALLOW_MATRIX 미정의
    pass-through 로 새는 것을 차단 (issue #598).
    """
    if not agent_type:
        return None
    if agent_type.startswith("dcness:"):
        parts = agent_type.split(":")
        normalized = parts[1] if len(parts) > 1 else agent_type
    else:
        normalized = agent_type
    return LEGACY_AGENT_ALIASES.get(normalized, normalized)
