---
name: next-work
description: GitHub issue 상태와 label에서 이어하기, 긴급, 다음 작업 후보를 조회하는 read-only 유틸리티. 사용자가 "/next-work", "다음 작업", "뭐하지", "뭐부터 하지", "이제 뭐해야하지", "남은 일 알려줘", "남은 일 브리핑", "이어서", "진행 중 작업", "콜드스타트 시작점" 등 다음·남은 일을 물을 때 사용한다.
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
- 출력 계층은 L1 `in-progress` 이어하기 → L2 blocker/critical 긴급 → L3 story/feature/task/bug 후보 순서다. L2 긴급 승격은 story 를 제외한다 — story 는 priority 무관하게 소속 epic 설계 phase 로 판정하므로 항상 L3 로 흘려보낸다.
- 이 계층은 후보 나열이다. "뭐하지 / 남은 일" 자연어 질의의 소비 계약: warm 인계(이전 세션 `/handoff`)가 있으면 그것이 이 조회보다 우선한다. warm 이 없으면 이 계층의 최상위 1개(L1>L2>L3)를 다음 액션으로 단정하고(메뉴로 남기지 않는다 — `/design <epic-path>` · `/impl` · 특정 story 중 하나 + 근거), "남은 일 브리핑" 은 계층 전체로 답한다. 단, 최상위 후보에 위 phase 판정이 `판정 보류`(설계 산출물 로컬 확인 불가 / 대상 repo 불일치 등)로 나오면 `/design`·`/impl` 을 지어내지 말고 그 보류 사유를 그대로 전한다 — 확정 phase 일 때만 단정한다. 단정한 액션이 가리키는 컨텍스트(해당 epic stories / 설계 산출물 유무 / 리팩터 base 브랜치)만 focused preload 한다.
- `subTask` 는 독립 후보에서 제외하고, body 의 `Part of #N` 부모가 L1 에 있을 때만 그 부모 아래에 중첩 표시한다.
- story 후보는 `epic-NN-<slug>` label 의 NN 오름차순, 같은 epic 안에서는 issue 번호 오름차순으로 표시한다.
- story 는 epic 단위로 로컬 설계 산출물(`docs/epics/epic-NN-<slug>/architecture.md` + `impl/NN-*.md`) 존재를 확인해 다음 액션을 구분한다. 설계 미완 epic 은 story 를 impl 후보로 내밀지 않고 `/design <epic-path>` 를 제시하고, 설계 완료 epic 만 story 를 impl 후보로 승격한다. 로컬에 해당 epic 산출물이 없으면(repo 밖 실행 / stale checkout) `/design` 을 단정하지 않고 판정을 보류한다.
- 로컬 산출물은 *현재 git checkout* 의 repo 를 서술하므로, 대상 repo(issue 출처)가 현재 checkout 의 git remote 와 다르면(`--repo`/`GH_REPO` override 등) 로컬 phase 판정을 쓰지 않고 전부 보류한다(엉뚱한 repo 의 설계 산출물로 `/design`/`/impl` 을 오판하지 않는다). 로컬 repo 식별은 `gh` 가 아니라 git remote 에서 뽑아 override 에 영향받지 않는다.
- Priority 는 Issue Brief 본문의 `Priority` 줄을 파싱한다. 없거나 invalid 면 `priority 미기재` 로 표시하고 그룹 뒤에 둔다.
- GitHub 조회가 실패하면 실패를 명시하고 로컬 대안 경로를 안내한다.

## 참조

- [`issue-lifecycle.md` Issue/label lifecycle](../docs/plugin/issue-lifecycle.md#issuelabel-status-lifecycle)
- [`positioning.md` Utility 공개 노출 범위](../docs/plugin/positioning.md#utility-공개-노출-범위)
