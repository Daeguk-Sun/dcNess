"""/init-dcness 선택형 CI workflow 설치기.

workflow template 과 그 workflow 가 실행하는 검사 스크립트를 사용자 repo 에 함께
복사한다. 설치된 workflow 는 외부 저장소 action 을 호출하지 않고 사용자 repo
체크아웃만으로 실행되며, 복사본은 설치 시점의 plugin 버전에 고정된다.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from harness.tdd_hooks import COPIED_CI_CHECKS_REL

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = "templates/github-workflows"
WORKFLOW_DIR = ".github/workflows"
# 복사된 검사 스크립트는 plugin 안의 상대 경로 그대로 이 아래에 둔다.
INSTALL_ROOT = COPIED_CI_CHECKS_REL.as_posix()
EXECUTABLE_FILES = {"scripts/dcness-story-runner"}

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
    template: str
    support_files: tuple[str, ...] = ()
    neutral_ok: bool = True

    def template_sources(self) -> list[str]:
        return [f"{TEMPLATE_DIR}/{self.template}"]


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
}


@dataclass
class InstallResult:
    written: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def _copy(src: Path, dst: Path, *, executable: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    if executable:
        dst.chmod(0o755)


def install(
    project_root: Path,
    checks: Sequence[str],
    *,
    neutral_naming: bool = False,
    plugin_root: Path = PLUGIN_ROOT,
) -> InstallResult:
    unknown = [check for check in checks if check not in CHECKS]
    if unknown:
        raise ValueError(f"unknown check: {', '.join(unknown)} (지원: {', '.join(CHECKS)})")

    root = project_root.resolve()
    result = InstallResult()
    for check in dict.fromkeys(checks):
        spec = CHECKS[check]
        if neutral_naming and not spec.neutral_ok:
            result.skipped.append((check, _HARNESS_FORMAT_REASON))
            continue
        target = f"{WORKFLOW_DIR}/{check}.yml"
        _copy(plugin_root / TEMPLATE_DIR / spec.template, root / target, executable=False)
        result.written.append(target)
        for rel in spec.support_files:
            target = f"{INSTALL_ROOT}/{rel}"
            _copy(plugin_root / rel, root / target, executable=rel in EXECUTABLE_FILES)
            if target not in result.written:
                result.written.append(target)
    return result


def _cmd_install(args: argparse.Namespace) -> int:
    checks = [item.strip() for item in args.checks.split(",") if item.strip()]
    try:
        result = install(
            Path(args.project_root),
            checks,
            neutral_naming=args.neutral_naming,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for path in result.written:
        print(path)
    for check, reason in result.skipped:
        print(f"skip {check}: {reason}", file=sys.stderr)
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
    p_install.set_defaults(func=_cmd_install)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
