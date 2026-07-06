---
name: next-work
description: GitHub issue 상태와 label에서 이어하기, 긴급, 다음 작업 후보를 조회하는 read-only 유틸리티. 사용자가 "/next-work", "다음 작업", "뭐부터 하지", "진행 중 작업", "콜드스타트 시작점" 등을 말할 때 사용한다.
---

# Next Work — 다음 작업 read-only 조회

> GitHub open issue, Issue Brief Priority, repo label 을 읽어 cold-start 세션의 시작점을 확인한다. issue/label/Project 상태를 쓰거나 변경하지 않는다.

## 언제 사용

- 새 세션에서 다음 작업이나 시작점을 확인할 때
- 현재 `in-progress` 항목과 다음 후보를 빠르게 보고 싶을 때
- `docs/index.md` 의 정적 포인터만으로는 live 상태를 알 수 없을 때

## 절차

```bash
SCRIPT="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)/scripts/github_project_lifecycle.mjs"
node "$SCRIPT" next-work
```

사용자가 repo 를 명시한 경우에만 flag 를 그대로 전달한다.

```bash
node "$SCRIPT" next-work --repo OWNER/REPO
```

## 동작 계약

- read-only: `--apply` 를 쓰지 않고, issue/label/Project/PR 상태를 변경하지 않는다.
- Project 좌표나 bootstrap 없이 open issue 목록만으로 동작한다.
- 출력 계층은 L1 `in-progress` 이어하기 → L2 blocker/critical 긴급 → L3 story/feature/task/bug 후보 순서다.
- `subTask` 는 독립 후보에서 제외하고, body 의 `Part of #N` 부모가 L1 에 있을 때만 그 부모 아래에 중첩 표시한다.
- story 후보는 `epic-NN-<slug>` label 의 NN 오름차순, 같은 epic 안에서는 issue 번호 오름차순으로 표시한다.
- story 는 epic 단위로 로컬 설계 산출물(`docs/epics/epic-NN-<slug>/architecture.md` + `impl/NN-*.md`) 존재를 확인해 다음 액션을 구분한다. 설계 미완 epic 은 story 를 impl 후보로 내밀지 않고 `/design <epic-path>` 를 제시하고, 설계 완료 epic 만 story 를 impl 후보로 승격한다. 로컬에 해당 epic 산출물이 없으면(repo 밖 실행 / stale checkout) `/design` 을 단정하지 않고 판정을 보류한다.
- 로컬 산출물은 *현재 checkout* 의 repo 를 서술하므로, `--repo` 로 현재 로컬 checkout 과 다른 repo 를 지정하면 로컬 phase 판정을 쓰지 않고 전부 보류한다(엉뚱한 repo 의 설계 산출물로 `/design`/`/impl` 을 오판하지 않는다).
- Priority 는 Issue Brief 본문의 `Priority` 줄을 파싱한다. 없거나 invalid 면 `priority 미기재` 로 표시하고 그룹 뒤에 둔다.
- GitHub 조회가 실패하면 실패를 명시하고 로컬 대안 경로를 안내한다.

## 참조

- [`issue-lifecycle.md` Issue/label lifecycle](../docs/plugin/issue-lifecycle.md#issuelabel-status-lifecycle)
- [`positioning.md` Utility 공개 노출 범위](../docs/plugin/positioning.md#utility-공개-노출-범위)
