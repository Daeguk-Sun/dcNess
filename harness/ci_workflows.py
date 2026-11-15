"""/init-dcness 선택형 CI workflow 설치기.

workflow template 과 그 workflow 가 실행하는 검사 스크립트를 사용자 repo 에 함께
복사한다. 로컬 실행을 고른 검사(`--local`)는 workflow 대신 git pre-push hook 이
실행하는 스크립트를 복사한다. 설치된 workflow 는 외부 저장소 action 을 호출하지 않고 사용자 repo
체크아웃만으로 실행되며, 복사본은 설치 시점의 plugin 버전에 고정된다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from harness.tdd_hooks import resolve_platform

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = "templates/github-workflows"
WORKFLOW_DIR = ".github/workflows"
# 복사된 검사 스크립트는 plugin 안의 상대 경로 그대로 이 아래에 둔다.
INSTALL_ROOT = ".github/ci-checks"
EXECUTABLE_FILES = {"scripts/dcness-story-runner"}
LOCAL_TEMPLATE_DIR = "templates/local-checks"
# git pre-push hook 이 이 경로의 스크립트가 있으면 push 직전에 실행한다.
LOCAL_SCRIPT = ".dcness/lint-build-test.sh"

_DOC_SYNC_FILES = (
    "scripts/aggregate_index_map.mjs",
    "scripts/lib/epic_phase.mjs",
    "scripts/check_design_artifact_structure.mjs",
    "scripts/dcness-story-runner",
    "harness/story_runner.py",
    "harness/parallel_wave.py",
    "scripts/design/ux-flow.mjs",
    "scripts/design/build-journey-boards.mjs",
    "scripts/design/build-screen-states.mjs",
    "scripts/design/build-design-index.mjs",
    # ux-flow.mjs 가 프로젝트 엔진 사본과 비교하려고 런타임에 읽는 원본.
    "templates/design-variants/_lib/canvas.js",
    "templates/design-variants/_lib/only-variant.js",
    "templates/design-variants/_lib/report-size.js",
    "templates/design-variants/_lib/show-ids.js",
)
_HARNESS_FORMAT_REASON = (
    "중립 명명 설치에서 제외 — 하네스 산출물 형식(생성 구역 표식, 설정 변수 이름)을 "
    "직접 검사하므로 하네스 이름을 숨길 수 없다"
)


@dataclass(frozen=True)
class CheckSpec:
    template: str = ""
    support_files: tuple[str, ...] = ()
    neutral_ok: bool = True
    # platform -> template. 비어 있으면 단일 template 을 쓴다.
    platform_templates: dict[str, str] = field(default_factory=dict)
    # platform -> 로컬 실행 스크립트 template. 비어 있으면 로컬 실행을 지원하지 않는다.
    local_templates: dict[str, str] = field(default_factory=dict)

    def template_sources(self) -> list[str]:
        names = [self.template] if self.template else list(self.platform_templates.values())
        return [f"{TEMPLATE_DIR}/{name}" for name in names]


CHECKS: dict[str, CheckSpec] = {
    "git-naming-validation": CheckSpec(
        template="git-naming-validation.yml",
        support_files=("scripts/check_git_naming.mjs",),
    ),
    "pr-body-validation": CheckSpec(
        template="pr-body-validation.yml",
        support_files=("scripts/check_pr_body.mjs",),
    ),
    "doc-path-integrity": CheckSpec(
        template="doc-path-integrity.yml",
        support_files=("scripts/check_doc_path_integrity.mjs",),
    ),
    "doc-sync": CheckSpec(
        template="doc-sync.yml",
        support_files=_DOC_SYNC_FILES,
        neutral_ok=False,
    ),
    "github-project-lifecycle": CheckSpec(
        template="github-project-lifecycle.yml",
        support_files=(
            "scripts/github_project_lifecycle.mjs",
            "scripts/check_issue_body.mjs",
            "scripts/lib/epic_phase.mjs",
        ),
        neutral_ok=False,
    ),
    "lint-build-test": CheckSpec(
        platform_templates={"android": "lint-build-test/android.yml"},
        local_templates={"android": "lint-build-test/android.sh"},
    ),
}


@dataclass
class InstallResult:
    written: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _android_skip_reason(root: Path) -> Optional[str]:
    if not (root / "gradlew").is_file():
        return "android: gradlew 없음 — Gradle wrapper 를 커밋한 뒤 재실행"
    if not any((root / "app" / name).is_file() for name in ("build.gradle", "build.gradle.kts")):
        return (
            "android: app/build.gradle(.kts) 없음 — 기본 명령이 :app 모듈을 쓰므로 "
            "모듈 이름에 맞게 template 을 고쳐 직접 설치"
        )
    return None


def _lint_build_test_platform(root: Path, platform: Optional[str]) -> tuple[Optional[str], str]:
    spec = CHECKS["lint-build-test"]
    resolved = platform or resolve_platform(root)
    if not resolved:
        return None, (
            "플랫폼 미지정 — --platform 으로 지정하거나 TDD 계약"
            "(.dcness/tdd-hooks.json)을 먼저 생성"
        )
    template = spec.platform_templates.get(resolved)
    if template is None:
        supported = ", ".join(sorted(spec.platform_templates))
        return None, f"{resolved} 플랫폼 template 없음 (지원: {supported})"
    if resolved == "android":
        reason = _android_skip_reason(root)
        if reason:
            return None, reason
    return resolved, ""


def _copy(src: Path, dst: Path, *, executable: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    if executable:
        dst.chmod(0o755)


def _remove_if_unmodified(
    root: Path, rel: str, originals: Sequence[Path], result: InstallResult
) -> None:
    """dcNess 가 복사한 내용 그대로인 파일만 지운다. 사용자가 고친 파일은 남기고 알린다."""
    path = root / rel
    if not path.is_file():
        return
    content = path.read_bytes()
    if any(src.read_bytes() == content for src in originals):
        path.unlink()
        result.removed.append(rel)
    else:
        result.notes.append(f"{rel} 는 template 과 내용이 달라 남김 — 필요 없으면 직접 삭제")


def install(
    project_root: Path,
    checks: Sequence[str],
    *,
    neutral_naming: bool = False,
    platform: Optional[str] = None,
    local_checks: Sequence[str] = (),
    plugin_root: Path = PLUGIN_ROOT,
) -> InstallResult:
    unknown = [check for check in checks if check not in CHECKS]
    if unknown:
        raise ValueError(f"unknown check: {', '.join(unknown)} (지원: {', '.join(CHECKS)})")
    no_local = [check for check in local_checks if not CHECKS.get(check, CheckSpec()).local_templates]
    if no_local:
        raise ValueError(f"local 실행 미지원 check: {', '.join(no_local)}")

    root = project_root.resolve()
    result = InstallResult()
    for check in dict.fromkeys(checks):
        spec = CHECKS[check]
        if neutral_naming and not spec.neutral_ok:
            result.skipped.append((check, _HARNESS_FORMAT_REASON))
            continue
        template = spec.template
        target = f"{WORKFLOW_DIR}/{check}.yml"
        if spec.platform_templates:
            resolved, reason = _lint_build_test_platform(root, platform)
            if resolved is None:
                result.skipped.append((check, reason))
                continue
            workflow_sources = [plugin_root / src for src in spec.template_sources()]
            local_sources = [
                plugin_root / LOCAL_TEMPLATE_DIR / name for name in spec.local_templates.values()
            ]
            if check in local_checks:
                _copy(
                    plugin_root / LOCAL_TEMPLATE_DIR / spec.local_templates[resolved],
                    root / LOCAL_SCRIPT,
                    executable=True,
                )
                result.written.append(LOCAL_SCRIPT)
                _remove_if_unmodified(root, target, workflow_sources, result)
                continue
            _remove_if_unmodified(root, LOCAL_SCRIPT, local_sources, result)
            template = spec.platform_templates[resolved]
        _copy(plugin_root / TEMPLATE_DIR / template, root / target, executable=False)
        result.written.append(target)
        for rel in spec.support_files:
            target = f"{INSTALL_ROOT}/{rel}"
            _copy(plugin_root / rel, root / target, executable=rel in EXECUTABLE_FILES)
            if target not in result.written:
                result.written.append(target)
    return result


def _cmd_install(args: argparse.Namespace) -> int:
    checks = [item.strip() for item in args.checks.split(",") if item.strip()]
    local_checks = [item.strip() for item in args.local.split(",") if item.strip()]
    try:
        result = install(
            Path(args.project_root),
            checks,
            neutral_naming=args.neutral_naming,
            platform=args.platform,
            local_checks=local_checks,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    # 지운 파일도 stdout 에 내보내 workflow PR 이 삭제를 stage 하게 한다.
    for path in result.written + result.removed:
        print(path)
    for path in result.removed:
        print(f"removed {path}", file=sys.stderr)
    for check, reason in result.skipped:
        print(f"skip {check}: {reason}", file=sys.stderr)
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dcness-ci-workflows",
        description="copy CI workflow templates and their check scripts into a project",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_install = sub.add_parser("install", help="install selected CI workflows")
    p_install.add_argument("--project-root", required=True)
    p_install.add_argument("--checks", required=True, help="comma separated workflow names")
    p_install.add_argument("--neutral-naming", action="store_true")
    p_install.add_argument("--platform", default=None)
    p_install.add_argument(
        "--local",
        default="",
        help="comma separated checks to run from git pre-push hook instead of a workflow",
    )
    p_install.set_defaults(func=_cmd_install)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
