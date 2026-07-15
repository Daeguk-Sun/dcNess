"""agent_names.py — dcness sub-agent 이름 정규화 SSOT (issue #383 / #598).

CC hook payload / transcript 의 agent_type 에 붙는 plugin namespace prefix
(`dcness:build-worker`)를 제거한다. boundary (`agent_boundary`) / trace / histogram /
review 가 동일 canonical 이름으로 매칭하도록 본 모듈이 *단일* 정규화를 제공한다.

경량(stdlib only) — file-guard PreToolUse 핫패스에서 import 해도 안전.
"""
from __future__ import annotations

from typing import Optional


def normalize_agent_type(agent_type: Optional[str]) -> Optional[str]:
    """`dcness:module-architect` → `module-architect`. None / 비-dcness → 원형 그대로.

    `dcness:` namespace prefix를 제거한다. boundary / trace / histogram 매칭 전
    호출해 namespaced(`dcness:impl-validator`)가 ALLOW_MATRIX 미정의 pass-through로
    새는 것을 차단한다 (issue #598).
    """
    if not agent_type:
        return None
    if agent_type.startswith("dcness:"):
        parts = agent_type.split(":")
        normalized = parts[1] if len(parts) > 1 else agent_type
    else:
        normalized = agent_type
    return normalized
