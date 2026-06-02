"""Local provider routing for dcNess validation agents.

Provider routing is deliberately local state, not repository config. Existing
projects opt in via /init-dcness, which writes:

    ~/.claude/plugins/data/dcness-dcness/routing.json

Only read-only validation agents are routable. All other agents stay on Claude.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "CONFIG_VERSION",
    "ROUTABLE_VALIDATION_AGENTS",
    "VALID_PROVIDERS",
    "routing_path",
    "load_routing",
    "save_routing",
    "resolve_provider",
    "set_provider",
    "enable_codex_validation",
    "disable_codex_validation",
    "doctor",
    "format_status",
]

CONFIG_VERSION = 1
ROUTABLE_VALIDATION_AGENTS = (
    "code-validator",
    "architecture-validator",
    "pr-reviewer",
)
VALID_PROVIDERS = ("claude", "codex")
DEFAULT_PROVIDER = "claude"

_DEFAULT_ROUTING_PATH = (
    Path.home() / ".claude" / "plugins" / "data" / "dcness-dcness" / "routing.json"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def routing_path() -> Path:
    """Return plugin-scoped local routing config path.

    `DCNESS_ROUTING_PATH` is a test/debug override. Normal plugin users should
    not set it.
    """
    override = os.environ.get("DCNESS_ROUTING_PATH")
    if override:
        return Path(override).expanduser()
    return _DEFAULT_ROUTING_PATH


def _default_config() -> Dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "routes": {},
        "updated_at": _now_iso(),
    }


def _atomic_write_json(target: Path, payload: Dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)


def load_routing(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """Load routing config.

    Missing config is not an error; it means all agents resolve to Claude.
    Invalid JSON raises ValueError so `routing doctor` can fail loudly.
    """
    target = Path(path) if path is not None else routing_path()
    if not target.exists():
        return _default_config()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"routing config parse failed: {target}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"routing config must be JSON object: {target}")
    routes = data.get("routes", {})
    if not isinstance(routes, dict):
        raise ValueError(f"routing config routes must be object: {target}")
    cfg = _default_config()
    cfg.update(data)
    cfg["routes"] = routes
    return cfg


def save_routing(config: Dict[str, Any], *, path: Optional[Path] = None) -> Path:
    target = Path(path) if path is not None else routing_path()
    routes = config.get("routes", {})
    if not isinstance(routes, dict):
        raise ValueError("routes must be dict")
    clean_routes: Dict[str, str] = {}
    for agent, provider in routes.items():
        if agent not in ROUTABLE_VALIDATION_AGENTS:
            raise ValueError(f"unsupported routable agent: {agent}")
        if provider not in VALID_PROVIDERS:
            raise ValueError(f"unsupported provider for {agent}: {provider}")
        clean_routes[agent] = provider
    payload = {
        "version": CONFIG_VERSION,
        "routes": clean_routes,
        "updated_at": _now_iso(),
    }
    _atomic_write_json(target, payload)
    return target


def resolve_provider(agent: str, *, path: Optional[Path] = None) -> str:
    """Resolve provider for an agent.

    Non-routable agents always resolve to Claude. This keeps routing opt-in
    limited to read-only validators and avoids accidental build-agent migration.
    """
    if agent not in ROUTABLE_VALIDATION_AGENTS:
        return DEFAULT_PROVIDER
    cfg = load_routing(path=path)
    provider = cfg.get("routes", {}).get(agent, DEFAULT_PROVIDER)
    return provider if provider in VALID_PROVIDERS else DEFAULT_PROVIDER


def set_provider(agent: str, provider: str, *, path: Optional[Path] = None) -> Path:
    if agent not in ROUTABLE_VALIDATION_AGENTS:
        allowed = ", ".join(ROUTABLE_VALIDATION_AGENTS)
        raise ValueError(f"unsupported agent: {agent} (allowed: {allowed})")
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider} (allowed: claude|codex)")
    cfg = load_routing(path=path)
    routes = dict(cfg.get("routes", {}))
    routes[agent] = provider
    cfg["routes"] = routes
    return save_routing(cfg, path=path)


def enable_codex_validation(*, path: Optional[Path] = None) -> Path:
    routes = {agent: "codex" for agent in ROUTABLE_VALIDATION_AGENTS}
    return save_routing({"routes": routes}, path=path)


def disable_codex_validation(*, path: Optional[Path] = None) -> Path:
    routes = {agent: "claude" for agent in ROUTABLE_VALIDATION_AGENTS}
    return save_routing({"routes": routes}, path=path)


def doctor(*, path: Optional[Path] = None) -> list[str]:
    """Return routing config problems. Empty list means healthy."""
    problems: list[str] = []
    target = Path(path) if path is not None else routing_path()
    try:
        cfg = load_routing(path=target)
    except ValueError as exc:
        return [str(exc)]

    version = cfg.get("version")
    if version != CONFIG_VERSION:
        problems.append(f"unsupported version: {version!r} (expected {CONFIG_VERSION})")

    routes = cfg.get("routes", {})
    if not isinstance(routes, dict):
        problems.append("routes must be object")
        return problems
    for agent, provider in routes.items():
        if agent not in ROUTABLE_VALIDATION_AGENTS:
            problems.append(f"unknown agent route: {agent}")
        if provider not in VALID_PROVIDERS:
            problems.append(f"invalid provider for {agent}: {provider}")

    return problems


def format_status(*, path: Optional[Path] = None) -> str:
    target = Path(path) if path is not None else routing_path()
    try:
        cfg = load_routing(path=target)
        problems = doctor(path=target)
    except ValueError as exc:
        return "\n".join(
            [
                f"[dcness routing] config: {target}",
                "[dcness routing] status: INVALID",
                f"[dcness routing] problem: {exc}",
            ]
        )

    lines = [
        f"[dcness routing] config: {target}",
        f"[dcness routing] status: {'OK' if not problems else 'INVALID'}",
    ]
    if not target.exists():
        lines.append("[dcness routing] file: missing (default all Claude)")
    for agent in ROUTABLE_VALIDATION_AGENTS:
        provider = cfg.get("routes", {}).get(agent, DEFAULT_PROVIDER)
        if provider not in VALID_PROVIDERS:
            provider = f"{provider} (invalid, resolves claude)"
        lines.append(f"  {agent}: {provider}")
    if problems:
        lines.append("[dcness routing] problems:")
        lines.extend(f"  - {problem}" for problem in problems)
    return "\n".join(lines)
