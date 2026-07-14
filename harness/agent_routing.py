"""Local provider routing for dcNess agent providers.

Provider routing is deliberately local state, not repository config. Existing
projects opt in via /init-dcness, which writes:

    ~/.claude/plugins/data/dcness-dcness/routing.json

Validation agents can be sent to Codex read-only. impl-validator defaults to
the implementation camp's opposite provider when no explicit local override
exists. The single implementation agent defaults to a headless chain: Codex
headless, Claude headless, then Claude main fallback.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "CONFIG_VERSION",
    "ROUTABLE_IMPLEMENTATION_AGENTS",
    "ROUTABLE_VALIDATION_AGENTS",
    "VALID_IMPLEMENTATION_PROVIDERS",
    "VALID_VALIDATION_PROVIDERS",
    "IMPLEMENTATION_PROVIDER_CHAINS",
    "routing_path",
    "load_routing",
    "save_routing",
    "resolve_provider",
    "implementation_provider_chain",
    "set_provider",
    "set_implementation_provider",
    "enable_role_split_routing",
    "enable_codex_validation",
    "disable_codex_validation",
    "enable_headless_implementation",
    "enable_claude_headless_implementation",
    "doctor",
    "format_status",
]

CONFIG_VERSION = 3
ROUTABLE_VALIDATION_AGENTS = (
    "impl-validator",
    "architecture-validator",
)
ROUTABLE_IMPLEMENTATION_AGENTS = (
    "build-worker",
)
VALID_VALIDATION_PROVIDERS = ("claude", "codex")
VALID_IMPLEMENTATION_PROVIDERS = (
    "claude",
    "claude-headless",
    "headless-chain",
)
IMPLEMENTATION_PROVIDER_CHAINS = {
    "headless-chain": ("codex-headless", "claude-headless", "claude-main"),
    "claude-headless": ("claude-headless", "claude-main"),
    "claude": ("claude-main",),
}
DEFAULT_VALIDATION_PROVIDER = "claude"
DEFAULT_IMPLEMENTATION_PROVIDER = "headless-chain"
SAFE_FALLBACK_PROVIDER = "claude"

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
        "implementation_routes": {},
        "updated_at": _now_iso(),
    }


def _codex_cli_available(codex_available: Optional[bool] = None) -> bool:
    if codex_available is not None:
        return codex_available
    return shutil.which("codex") is not None


def _implementation_camp(
    *,
    implementation_provider: Optional[str] = None,
    main_provider: str = "claude",
) -> str:
    """Return the model camp that is expected to implement the change."""
    if implementation_provider == "headless-chain":
        return "codex"
    if implementation_provider in {"claude", "claude-headless"}:
        return "claude"
    return "codex" if main_provider == "codex" else "claude"


def _default_validation_provider(
    agent: str,
    *,
    implementation_provider: Optional[str] = None,
    main_provider: str = "claude",
    codex_available: Optional[bool] = None,
) -> str:
    if agent != "impl-validator":
        return DEFAULT_VALIDATION_PROVIDER
    camp = _implementation_camp(
        implementation_provider=implementation_provider,
        main_provider=main_provider,
    )
    if camp == "codex":
        return "claude"
    return "codex" if _codex_cli_available(codex_available) else "claude"


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

    Missing config is not an error; validation agents resolve to Claude and
    implementation agents resolve to the default headless chain.
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
    implementation_routes = data.get("implementation_routes", {})
    if not isinstance(implementation_routes, dict):
        raise ValueError(
            f"routing config implementation_routes must be object: {target}"
        )
    cfg = _default_config()
    cfg.update(data)
    cfg["version"] = data.get("version")
    cfg["routes"] = routes
    cfg["implementation_routes"] = implementation_routes
    return cfg


def save_routing(config: Dict[str, Any], *, path: Optional[Path] = None) -> Path:
    target = Path(path) if path is not None else routing_path()
    routes = config.get("routes", {})
    if not isinstance(routes, dict):
        raise ValueError("routes must be dict")
    clean_routes: Dict[str, str] = {}
    for agent, provider in routes.items():
        if agent not in ROUTABLE_VALIDATION_AGENTS:
            raise ValueError(f"unsupported validation agent: {agent}")
        if provider not in VALID_VALIDATION_PROVIDERS:
            raise ValueError(f"unsupported provider for {agent}: {provider}")
        clean_routes[agent] = provider
    implementation_routes = config.get("implementation_routes", {})
    if not isinstance(implementation_routes, dict):
        raise ValueError("implementation_routes must be dict")
    clean_implementation_routes: Dict[str, str] = {}
    for agent, provider in implementation_routes.items():
        if agent not in ROUTABLE_IMPLEMENTATION_AGENTS:
            raise ValueError(f"unsupported implementation agent: {agent}")
        if provider not in VALID_IMPLEMENTATION_PROVIDERS:
            raise ValueError(
                f"unsupported implementation provider for {agent}: {provider}"
            )
        clean_implementation_routes[agent] = provider
    payload = {
        "version": CONFIG_VERSION,
        "routes": clean_routes,
        "implementation_routes": clean_implementation_routes,
        "updated_at": _now_iso(),
    }
    _atomic_write_json(target, payload)
    return target


def resolve_provider(
    agent: str,
    *,
    path: Optional[Path] = None,
    implementation_provider: Optional[str] = None,
    main_provider: str = "claude",
    codex_available: Optional[bool] = None,
) -> str:
    """Resolve provider for an agent.

    impl-validator defaults to the implementation camp's opposite provider when
    no explicit local override exists. If the opposite provider is Codex but the
    Codex CLI is unavailable, the default safely falls back to Claude.
    Other validation agents default to Claude. Implementation agents default to
    the 3-stage headless chain.
    Unknown agents always resolve to Claude.
    """
    if agent not in ROUTABLE_VALIDATION_AGENTS + ROUTABLE_IMPLEMENTATION_AGENTS:
        return SAFE_FALLBACK_PROVIDER
    cfg = load_routing(path=path)
    if cfg.get("version") != CONFIG_VERSION:
        return SAFE_FALLBACK_PROVIDER
    if agent in ROUTABLE_VALIDATION_AGENTS:
        routes = cfg.get("routes", {})
        provider = routes.get(agent)
        if provider is None:
            provider = _default_validation_provider(
                agent,
                implementation_provider=implementation_provider,
                main_provider=main_provider,
                codex_available=codex_available,
            )
        return (
            provider
            if provider in VALID_VALIDATION_PROVIDERS
            else SAFE_FALLBACK_PROVIDER
        )
    provider = cfg.get("implementation_routes", {}).get(
        agent, DEFAULT_IMPLEMENTATION_PROVIDER
    )
    return (
        provider
        if provider in VALID_IMPLEMENTATION_PROVIDERS
        else SAFE_FALLBACK_PROVIDER
    )


def implementation_provider_chain(provider: str) -> tuple[str, ...]:
    """Return execution stages for an implementation provider value."""
    if provider not in IMPLEMENTATION_PROVIDER_CHAINS:
        return IMPLEMENTATION_PROVIDER_CHAINS[SAFE_FALLBACK_PROVIDER]
    return IMPLEMENTATION_PROVIDER_CHAINS[provider]


def set_provider(agent: str, provider: str, *, path: Optional[Path] = None) -> Path:
    if agent not in ROUTABLE_VALIDATION_AGENTS:
        allowed = ", ".join(ROUTABLE_VALIDATION_AGENTS)
        raise ValueError(f"unsupported agent: {agent} (allowed: {allowed})")
    if provider not in VALID_VALIDATION_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider} (allowed: claude|codex)")
    cfg = load_routing(path=path)
    routes = dict(cfg.get("routes", {}))
    routes[agent] = provider
    cfg["routes"] = routes
    return save_routing(cfg, path=path)


def set_implementation_provider(
    agent: str, provider: str, *, path: Optional[Path] = None
) -> Path:
    if agent not in ROUTABLE_IMPLEMENTATION_AGENTS:
        allowed = ", ".join(ROUTABLE_IMPLEMENTATION_AGENTS)
        raise ValueError(f"unsupported implementation agent: {agent} (allowed: {allowed})")
    if provider not in VALID_IMPLEMENTATION_PROVIDERS:
        allowed_providers = "|".join(VALID_IMPLEMENTATION_PROVIDERS)
        raise ValueError(
            f"unsupported implementation provider: {provider} "
            f"(allowed: {allowed_providers})"
        )
    cfg = load_routing(path=path)
    routes = dict(cfg.get("implementation_routes", {}))
    routes[agent] = provider
    cfg["implementation_routes"] = routes
    return save_routing(cfg, path=path)


def enable_role_split_routing(*, path: Optional[Path] = None) -> Path:
    """Enable the recommended validation/worker routing preset."""
    cfg = load_routing(path=path)
    cfg["routes"] = {
        "impl-validator": "codex",
        "architecture-validator": "codex",
    }
    cfg["implementation_routes"] = {
        "build-worker": DEFAULT_IMPLEMENTATION_PROVIDER,
    }
    return save_routing(cfg, path=path)


def enable_codex_validation(*, path: Optional[Path] = None) -> Path:
    cfg = load_routing(path=path)
    routes = {agent: "codex" for agent in ROUTABLE_VALIDATION_AGENTS}
    cfg["routes"] = routes
    return save_routing(cfg, path=path)


def disable_codex_validation(*, path: Optional[Path] = None) -> Path:
    cfg = load_routing(path=path)
    routes = {agent: "claude" for agent in ROUTABLE_VALIDATION_AGENTS}
    cfg["routes"] = routes
    return save_routing(cfg, path=path)


def enable_headless_implementation(*, path: Optional[Path] = None) -> Path:
    cfg = load_routing(path=path)
    routes = {
        agent: DEFAULT_IMPLEMENTATION_PROVIDER
        for agent in ROUTABLE_IMPLEMENTATION_AGENTS
    }
    cfg["implementation_routes"] = routes
    return save_routing(cfg, path=path)


def enable_claude_headless_implementation(*, path: Optional[Path] = None) -> Path:
    cfg = load_routing(path=path)
    routes = {agent: "claude-headless" for agent in ROUTABLE_IMPLEMENTATION_AGENTS}
    cfg["implementation_routes"] = routes
    return save_routing(cfg, path=path)


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
            problems.append(f"unknown validation agent route: {agent}")
        if provider not in VALID_VALIDATION_PROVIDERS:
            problems.append(f"invalid provider for {agent}: {provider}")
    implementation_routes = cfg.get("implementation_routes", {})
    if not isinstance(implementation_routes, dict):
        problems.append("implementation_routes must be object")
        return problems
    for agent, provider in implementation_routes.items():
        if agent not in ROUTABLE_IMPLEMENTATION_AGENTS:
            problems.append(f"unknown implementation agent route: {agent}")
        if provider not in VALID_IMPLEMENTATION_PROVIDERS:
            problems.append(
                f"invalid implementation provider for {agent}: {provider}"
            )

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

    if cfg.get("version") != CONFIG_VERSION:
        cfg["routes"] = {
            agent: SAFE_FALLBACK_PROVIDER for agent in ROUTABLE_VALIDATION_AGENTS
        }
        cfg["implementation_routes"] = {
            agent: SAFE_FALLBACK_PROVIDER for agent in ROUTABLE_IMPLEMENTATION_AGENTS
        }

    lines = [
        f"[dcness routing] config: {target}",
        f"[dcness routing] status: {'OK' if not problems else 'INVALID'}",
    ]
    if not target.exists():
        lines.append(
            "[dcness routing] file: missing "
            "(default impl-validator cross-provider, implementation headless-chain)"
        )
    lines.append("[dcness routing] validation:")
    routes = cfg.get("routes", {})
    for agent in ROUTABLE_VALIDATION_AGENTS:
        provider = routes.get(agent)
        if provider is None:
            provider = _default_validation_provider(agent)
        if provider not in VALID_VALIDATION_PROVIDERS:
            provider = f"{provider} (invalid, resolves claude)"
        lines.append(f"  {agent}: {provider}")
    lines.append("[dcness routing] implementation:")
    for agent in ROUTABLE_IMPLEMENTATION_AGENTS:
        provider = cfg.get("implementation_routes", {}).get(
            agent, DEFAULT_IMPLEMENTATION_PROVIDER
        )
        if provider not in VALID_IMPLEMENTATION_PROVIDERS:
            provider = f"{provider} (invalid, resolves claude)"
        lines.append(f"  {agent}: {provider}")
    if problems:
        lines.append("[dcness routing] problems:")
        lines.extend(f"  - {problem}" for problem in problems)
    return "\n".join(lines)
