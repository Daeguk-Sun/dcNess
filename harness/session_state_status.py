"""Status diagnostics for the dcNess helper CLI."""
from __future__ import annotations

import json
import os
import subprocess  # nosec B404
from pathlib import Path
from typing import Any, Dict, Optional

from harness.session_state_activation import _resolve_project_root, is_project_active
from harness.session_state_fail_open import collect_fail_open_summary, _format_fail_open_summary

_READ_PERM = "Read(~/.claude/plugins/cache/dcness/**)"
_GIT_HOOK_SHIMS = ("commit-msg", "post-checkout", "pre-push", "pre-commit")
_SHIM_MARKERS = ("plugins/cache/dcness", "CLAUDE_PLUGIN_ROOT")
_CI_WORKFLOWS = (
    "git-naming-validation.yml",
    "pr-body-validation.yml",
    "doc-path-integrity.yml",
    "doc-sync.yml",
    "github-project-lifecycle.yml",
)
_CODEX_VALIDATOR_SKILLS = (
    "dcness-code-validator",
    "dcness-architecture-validator",
    "dcness-pr-reviewer",
)

def _is_self_repo(project_root: Path) -> bool:
    """dcNess plugin 본체 repo 판정 — `.claude-plugin/plugin.json` name == dcness.

    외부 활성 프로젝트엔 이 파일이 없다. self repo 는 init-dcness 미적용이라
    외부 활성 규칙(whitelist/Read권한/hook/CI)을 검사 대상에서 제외한다 (#520 AC 5).
    """
    pj = project_root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("name") == "dcness"


def _plugin_root() -> Path:
    """설치된 plugin root.

    CLAUDE_PLUGIN_ROOT env 우선 — 단 그 경로의 manifest 가 *dcness* 일 때만 신뢰한다.
    다른 plugin/agent runtime 이 env 를 set 한 경우 그 plugin 의 version 을 dcNess
    version 으로 오보하지 않도록, env 가 비었거나 dcness 가 아니면 본 파일 기준
    (harness 의 부모) 으로 폴백.
    """
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        cand = Path(env)
        if _is_self_repo(cand):
            return cand
    return Path(__file__).resolve().parent.parent


def _installed_plugin_version(plugin_root: Path) -> Optional[str]:
    """설치된 plugin 의 manifest version. 읽기 실패 시 None."""
    pj = plugin_root / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    v = data.get("version")
    return v if isinstance(v, str) else None


def _settings_path() -> Path:
    """CC 사용자 settings.json 경로."""
    return Path.home() / ".claude" / "settings.json"


def _check_read_permission(settings_path: Path) -> bool:
    """SessionStart 가 plugin SSOT 문서를 inject 하려면 필요한 Read allow 존재 여부."""
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    perms = data.get("permissions")
    allow = perms.get("allow") if isinstance(perms, dict) else None
    return isinstance(allow, list) and _READ_PERM in allow


def _resolve_git_hooks_dir(project_root: Path) -> Path:
    """git 이 실제로 실행하는 hooks 디렉토리.

    `core.hooksPath` (Husky 등) 가 설정되면 git 은 `.git/hooks` 를 무시한다. 진단이
    "git 이 정말 이 hook 을 실행하는가" 를 보려면 git 이 보는 경로를 따라야 한다.
    git 호출 실패 시 `.git/hooks` 폴백.
    """
    try:
        proc = subprocess.run(  # nosec B603, B607
            [
                "git", "-C", str(project_root),
                "rev-parse", "--path-format=absolute", "--git-path", "hooks",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            text=True,
        )
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out:
                return Path(out)
    except (OSError, subprocess.SubprocessError):
        pass
    return project_root / ".git" / "hooks"


def _check_git_hooks(hooks_dir: Path) -> Dict[str, str]:
    """각 git hook 의 상태.

    git 이 그 hook 을 실제로 실행할 조건까지 본다:
    'ok' (thin shim + 실행권한) / 'missing' / 'foreign' (dcness shim 아님)
    / 'not-exec' (dcness shim 이지만 실행권한 없어 git 이 무시 — POSIX).
    """
    result: Dict[str, str] = {}
    for name in _GIT_HOOK_SHIMS:
        p = hooks_dir / name
        if not p.exists():
            result[name] = "missing"
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            result[name] = "foreign"
            continue
        if not any(m in content for m in _SHIM_MARKERS):
            result[name] = "foreign"
            continue
        if not os.access(p, os.X_OK):
            result[name] = "not-exec"
            continue
        result[name] = "ok"
    return result


def _check_ci_workflows(project_root: Path) -> Dict[str, bool]:
    """선택형 CI workflow yml 존재 여부 (선택이라 부재해도 FAIL 아님)."""
    wf_dir = project_root / ".github" / "workflows"
    return {name: (wf_dir / name).exists() for name in _CI_WORKFLOWS}


def _check_codex_validator_skills(plugin_root: Path, codex_home: Path) -> Dict[str, str]:
    """Codex validator skill 배포 상태.

    'ok' / 'missing' / 'stale' / 'missing-source'. target 이 plugin source 와
    byte-for-byte 같아야 core activation 이 실제 배포 완료라고 볼 수 있다.
    """
    result: Dict[str, str] = {}
    for name in _CODEX_VALIDATOR_SKILLS:
        source = plugin_root / "codex" / "skills" / name / "SKILL.md"
        target = codex_home / "skills" / name / "SKILL.md"
        try:
            source_content = source.read_text(encoding="utf-8")
        except OSError:
            result[name] = "missing-source"
            continue
        try:
            target_content = target.read_text(encoding="utf-8")
        except OSError:
            result[name] = "missing"
            continue
        result[name] = "ok" if target_content == source_content else "stale"
    return result


def _check_gh_auth() -> bool:
    """gh CLI 인증 여부 (read-only). gh 미설치/미인증 시 False."""
    try:
        proc = subprocess.run(  # nosec B603, B607
            ["gh", "auth", "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def collect_status_diagnostics(
    cwd: Optional[Path] = None,
    *,
    settings_path: Optional[Path] = None,
    plugin_root: Optional[Path] = None,
    codex_home: Optional[Path] = None,
    check_gh: bool = True,
    check_routing: bool = True,
) -> Dict[str, Any]:
    """현재 프로젝트 설치 상태를 검사해 진단 결과를 모은다 (read-only, deterministic).

    반환: {project_root, self_repo, checks: [{key,label,status,detail,fix}], summary}.
    status ∈ {PASS, FAIL, WARN, INFO, NA}. 외부 의존(gh / routing)은 toggle 로 분리해
    단위 테스트에서 부수효과를 끈다.
    """
    project_root = _resolve_project_root(cwd).resolve()
    self_repo = _is_self_repo(project_root)
    settings_path = settings_path or _settings_path()
    plugin_root = plugin_root or _plugin_root()
    codex_home = codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))

    checks: list = []

    def add(key: str, label: str, status: str, detail: str, fix: Optional[str] = None) -> None:
        checks.append(
            {"key": key, "label": label, "status": status, "detail": detail, "fix": fix}
        )

    # 정보 항목 (self / 외부 공통)
    add("project_root", "cwd project root", "INFO", str(project_root))
    version = _installed_plugin_version(plugin_root)
    add("plugin_version", "installed plugin version", "INFO", version or "unknown")

    if self_repo:
        na_detail = "self repo — init-dcness 미적용 (CLAUDE.md + git-spec 만 적용)"
        for key, label in (
            ("whitelist", "whitelist 활성"),
            ("read_perm", "Read 권한 (~/.claude/settings.json)"),
            ("git_hooks", "git hook shim 3종"),
            ("claude_context", "CLAUDE.md context"),
            ("codex_skills", "Codex validator skills"),
            ("generated_tdd_hooks", "Generated TDD hooks"),
            ("ci_workflows", "선택형 CI workflow"),
        ):
            add(key, label, "NA", na_detail)
    else:
        # whitelist 활성
        active = is_project_active(cwd)
        add(
            "whitelist",
            "whitelist 활성",
            "PASS" if active else "FAIL",
            "활성" if active else "비활성 (이 프로젝트가 whitelist 에 없음)",
            None if active else 'dcness-helper enable',
        )
        # Read 권한
        has_perm = _check_read_permission(settings_path)
        add(
            "read_perm",
            "Read 권한 (~/.claude/settings.json)",
            "PASS" if has_perm else "FAIL",
            f"{_READ_PERM} {'존재' if has_perm else '없음'}",
            None if has_perm else f"init-dcness Step 3 으로 {_READ_PERM} 추가",
        )
        # git hook shim 3종 (git 이 실제 실행하는 경로 + 실행권한까지 검사)
        hooks_dir = _resolve_git_hooks_dir(project_root)
        hooks = _check_git_hooks(hooks_dir)
        all_ok = all(v == "ok" for v in hooks.values())
        custom_path = hooks_dir.resolve() != (project_root / ".git" / "hooks").resolve()
        hook_detail = ", ".join(f"{k}={v}" for k, v in hooks.items())
        if custom_path:
            hook_detail += f" (core.hooksPath={hooks_dir})"
        if all_ok:
            hook_fix = None
        elif custom_path:
            # init-dcness Step 4 는 .git/hooks 로 복사 → core.hooksPath 환경에선 무효.
            hook_fix = (
                f"core.hooksPath={hooks_dir} 설정됨 — Step 4(.git/hooks 복사)로는 해결 안 됨. "
                f"shim 을 {hooks_dir} 로 설치(chmod +x)하거나 core.hooksPath 를 해제하세요."
            )
        else:
            hook_fix = "init-dcness Step 4 로 thin shim 재설치 (chmod +x 포함)"
        add(
            "git_hooks",
            "git hook shim 3종",
            "PASS" if all_ok else "FAIL",
            hook_detail,
            hook_fix,
        )
        # Codex validator skills (core — source 와 target 일치까지 검사)
        codex_skills = _check_codex_validator_skills(plugin_root, codex_home)
        codex_all_ok = all(v == "ok" for v in codex_skills.values())
        add(
            "codex_skills",
            "Codex validator skills",
            "PASS" if codex_all_ok else "FAIL",
            ", ".join(f"{k}={v}" for k, v in codex_skills.items()),
            None
            if codex_all_ok
            else "/init-dcness Core Step 5 로 $CODEX_HOME/skills 의 Codex validator skills 재배포",
        )
        try:
            from harness.context_docs import audit_claude_md_file

            claude_audit = audit_claude_md_file(project_root)
            if not claude_audit.exists:
                add(
                    "claude_context",
                    "CLAUDE.md context",
                    "WARN",
                    "CLAUDE.md 없음",
                    "init-dcness Core Step 6 로 공식 구조 기반 CLAUDE.md seed 생성",
                )
            elif not claude_audit.has_cold_start_anchor:
                add(
                    "claude_context",
                    "CLAUDE.md context",
                    "WARN",
                    f"dcNess Cold Start 앵커 없음; score={claude_audit.total_score}/100",
                    "init-dcness Core Step 6 로 기존 파일에 앵커만 append",
                )
            elif claude_audit.missing_sections:
                missing = ", ".join(claude_audit.missing_sections)
                add(
                    "claude_context",
                    "CLAUDE.md context",
                    "INFO",
                    f"권장 섹션 누락: {missing}; "
                    f"score={claude_audit.total_score}/100 ({claude_audit.grade})",
                )
            elif claude_audit.total_score < 90:
                add(
                    "claude_context",
                    "CLAUDE.md context",
                    "INFO",
                    f"score={claude_audit.total_score}/100 ({claude_audit.grade}); 개선 후보 있음",
                )
            else:
                add(
                    "claude_context",
                    "CLAUDE.md context",
                    "PASS",
                    f"score={claude_audit.total_score}/100 ({claude_audit.grade})",
                )
        except Exception as exc:
            add(
                "claude_context",
                "CLAUDE.md context",
                "WARN",
                f"진단 실패: {exc}",
                "init-dcness Core Step 6 재실행 또는 dcness 업데이트 확인",
            )
        # 선택형 CI workflow (선택 — INFO)
        ci = _check_ci_workflows(project_root)
        installed = [k for k, present in ci.items() if present]
        add(
            "ci_workflows",
            "선택형 CI workflow",
            "INFO",
            f"설치됨: {', '.join(installed)}" if installed else "없음 (선택 사항)",
        )
        try:
            from harness.tdd_hooks import inspect_installation

            generated_tdd = inspect_installation(project_root)
            platform = generated_tdd.get("platform")
            if not platform:
                add(
                    "generated_tdd_hooks",
                    "Generated TDD hooks",
                    "INFO",
                    "빈 프로젝트 또는 미지원 플랫폼 — 생성 skip",
                )
            elif (
                generated_tdd.get("cc_registered")
                and generated_tdd.get("codex_registered")
                and generated_tdd.get("generated_files_commit_required")
            ):
                uncommitted = generated_tdd.get("uncommitted_generated_files") or []
                detail = ", ".join(str(item) for item in uncommitted[:5])
                add(
                    "generated_tdd_hooks",
                    "Generated TDD hooks",
                    "WARN",
                    (
                        f"platform={platform}, CC+Codex 등록됨, linked worktree 에서 "
                        f"커밋 필요한 생성 파일: {detail}"
                    ),
                    "generated TDD hook 파일을 bootstrap commit 에 포함",
                )
            elif generated_tdd.get("cc_registered") and generated_tdd.get("codex_registered"):
                suffix = ""
                if not generated_tdd.get("generated_files_committed"):
                    suffix = ", in-place disk 실존으로 통과 (linked worktree/headless 재사용 전 commit 필요)"
                add(
                    "generated_tdd_hooks",
                    "Generated TDD hooks",
                    "PASS",
                    f"platform={platform}, CC+Codex 로컬 등록됨{suffix} (Codex trust 승인은 별도 확인)",
                )
            elif generated_tdd.get("cc_registered") or generated_tdd.get("codex_registered"):
                add(
                    "generated_tdd_hooks",
                    "Generated TDD hooks",
                    "WARN",
                    (
                        f"platform={platform}, partial "
                        f"cc={generated_tdd.get('cc_registered')} "
                        f"codex={generated_tdd.get('codex_registered')}"
                    ),
                    "scripts/dcness-tdd-hooks ensure --targets cc,codex 재실행",
                )
            else:
                add(
                    "generated_tdd_hooks",
                    "Generated TDD hooks",
                    "WARN",
                    f"platform={platform}, 프로젝트 로컬 TDD hook 미생성",
                    "init-dcness 의 generated TDD hook 단계 실행",
                )
        except Exception as exc:
            add(
                "generated_tdd_hooks",
                "Generated TDD hooks",
                "WARN",
                f"진단 실패: {exc}",
                "dcness 업데이트 또는 scripts/dcness-tdd-hooks status 확인",
            )

    # Provider routing (self / 외부 공통 — INFO)
    if check_routing:
        try:
            from harness import agent_routing

            routing_detail = agent_routing.format_status().strip().replace("\n", " | ")
        except Exception:
            routing_detail = "조회 실패"
        add("routing", "Provider routing", "INFO", routing_detail)

    # gh CLI 인증 (self / 외부 공통 — WARN)
    if check_gh:
        gh_ok = _check_gh_auth()
        add(
            "gh_auth",
            "GitHub CLI 인증",
            "PASS" if gh_ok else "WARN",
            "인증됨" if gh_ok else "미인증/미설치 — PR·issue 자동화 제한",
            None if gh_ok else "gh auth login",
        )

    fail_open = collect_fail_open_summary(cwd=project_root)
    fail_open_total = int(fail_open.get("total") or 0)
    add(
        "hook_fail_open",
        "hook fail-open 진단",
        "WARN" if fail_open_total else "PASS",
        _format_fail_open_summary(fail_open),
        (
            "반복되면 hook stderr 로그와 fail-open reason category 를 확인하고 "
            "dcness 업데이트 또는 이슈 제보"
            if fail_open_total else None
        ),
    )

    status_labels = ("PASS", "WARN", "FAIL")
    summary = {status: 0 for status in status_labels}
    for c in checks:
        if c["status"] in summary:
            summary[c["status"]] += 1

    return {
        "project_root": str(project_root),
        "self_repo": self_repo,
        "checks": checks,
        "summary": summary,
    }


def format_status_report(diag: Dict[str, Any]) -> str:
    """진단 결과를 사람이 읽는 PASS/WARN/FAIL prose 로 포맷한다."""
    lines: list = []
    if diag["self_repo"]:
        lines.append("[dcness] === self repo (dcNess plugin 본체) 진단 ===")
        lines.append(
            "[dcness] init-dcness 미적용 — CLAUDE.md + docs/plugin/git-spec.md 만 적용"
        )
        lines.append("[dcness] 외부 활성 항목은 self repo 에 해당 없음 (N/A)")
    else:
        lines.append("[dcness] === 외부 활성 프로젝트 진단 ===")

    for c in diag["checks"]:
        line = f"  [{c['status']}] {c['label']}: {c['detail']}"
        lines.append(line)
        if c["status"] in ("FAIL", "WARN") and c["fix"]:
            lines.append(f"        → 해결: {c['fix']}")

    s = diag["summary"]
    lines.append(
        f"[dcness] 요약: {s['PASS']} PASS / {s['WARN']} WARN / {s['FAIL']} FAIL"
    )
    if s["FAIL"]:
        lines.append("[dcness] FAIL 항목을 위 해결 명령으로 처리한 뒤 status 를 재실행하세요.")
    elif s["WARN"]:
        lines.append("[dcness] WARN 항목은 선택 — 필요 시 해결 명령을 실행하세요.")
    elif not diag["self_repo"]:
        lines.append("[dcness] 모든 필수 항목 PASS — 활성화 정상.")
    return "\n".join(lines)


def _cli_status(args: Any) -> int:
    """whitelist + 현재 cwd 활성 상태를 진단표로 출력 (#520)."""
    diag = collect_status_diagnostics()
    print(format_status_report(diag))
    return 0
