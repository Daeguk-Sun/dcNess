"""Shared request and decision types for dcNess guards.

Policy modules decide *why* an operation is allowed or blocked.  Hook and CLI
adapters only translate this result to their existing exit/stdout contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal, Optional

from harness.agent_names import normalize_agent_type


@dataclass(frozen=True)
class GuardContext:
    guard: str
    category: str = ""
    session_id: str = ""
    run_id: str = ""
    agent: str = ""
    tool: str = ""

    def with_category(self, category: str) -> "GuardContext":
        return replace(self, category=category)


@dataclass(frozen=True)
class GuardDecision:
    context: GuardContext
    allowed: bool
    reason: str = ""
    evidence: tuple[str, ...] = ()

    @classmethod
    def allow(
        cls,
        context: GuardContext,
        reason: str = "",
        *,
        evidence: tuple[str, ...] = (),
    ) -> "GuardDecision":
        return cls(context=context, allowed=True, reason=reason, evidence=evidence)

    @classmethod
    def block(
        cls,
        context: GuardContext,
        reason: str,
        *,
        evidence: tuple[str, ...] = (),
    ) -> "GuardDecision":
        if not reason:
            raise ValueError("blocked guard decision requires a reason")
        return cls(context=context, allowed=False, reason=reason, evidence=evidence)

    @property
    def exit_code(self) -> int:
        return 0 if self.allowed else 1

    @property
    def legacy_reason(self) -> Optional[str]:
        return None if self.allowed else self.reason


@dataclass(frozen=True)
class HookRequest:
    context: GuardContext
    tool_input: dict[str, Any]
    tool_use_id: str = ""

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        guard: str,
        agent_source: Literal["acting", "requested"] = "acting",
    ) -> "HookRequest":
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        raw_tool_input = payload.get("tool_input", {})
        if not isinstance(raw_tool_input, dict):
            raise ValueError("tool_input must be an object")

        raw_agent = (
            raw_tool_input.get("subagent_type", "")
            if agent_source == "requested"
            else payload.get("agent_type", "")
        )
        agent = normalize_agent_type(str(raw_agent or "")) or ""
        session_id = str(
            payload.get("session_id")
            or payload.get("sessionId")
            or payload.get("sessionid")
            or ""
        )
        context = GuardContext(
            guard=guard,
            session_id=session_id,
            agent=agent,
            tool=str(payload.get("tool_name", "") or ""),
        )
        return cls(
            context=context,
            tool_input=dict(raw_tool_input),
            tool_use_id=str(payload.get("tool_use_id", "") or ""),
        )
