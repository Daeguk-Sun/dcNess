# GitHub Project Lifecycle

> **Status**: ACTIVE
> **Scope**: dcNess 표준 issue/label lifecycle, 선택적 GitHub Project v2 축, repo label, 상태 전이의 SSOT. 실행 메커니즘은 [`issue-lifecycle.md`](issue-lifecycle.md), git/PR trailer 룰은 [`git-spec.md`](git-spec.md), `/to-issue` 입력 필드 요약은 [`../../skills/to-issue/issue-fields.md`](../../skills/to-issue/issue-fields.md)를 함께 본다.

dcNess 활성 repo 의 기계 SSOT 는 GitHub issue 자체다. `IssueType` 은 repo label 6종 중 정확히 1개, `Priority` 는 Issue Brief 본문 줄, `Status` 는 issue open/closed 상태와 `in-progress` label 로 판정한다. GitHub Project v2 의 `Status`, `IssueType`, `Priority` 세 축은 원하는 프로젝트가 쓰는 사람용 파생 뷰이며, dcNess 는 좌표가 설정된 repo 에서만 best-effort 로 보드 상태를 미러한다. Project 좌표 부재는 정상 skip 이고, Project item 부재·권한 실패·field/option 불일치·API 실패는 warning 으로 보고하되 issue/label lifecycle 의 성패를 바꾸지 않는다. `/init-dcness` bootstrap 은 선택 시 Project 축과 lifecycle repo label 7종(`IssueType` 6종 + `in-progress`)을 점검하고, `--apply` 경로에서는 부족한 repo label 과 새 Project field 를 만들 수 있다. 기존 Project field 에 option 이 빠진 경우는 GitHub CLI 가 option 추가를 직접 지원하지 않으므로 명확한 복구 안내를 낸다.

## Status

| Value | Meaning | Usage example |
| --- | --- | --- |
| `Todo` | open issue 이며 `in-progress` label 이 없는 상태. | 새 issue 생성 직후 기본 상태. |
| `In progress` | open issue 이며 `in-progress` label 이 있는 상태. | `/impl #663` 처럼 특정 issue 구현을 시작하면 `start-work` 경로가 label 을 붙인다. |
| `Done` | closed issue. 별도 `done` label 은 만들지 않는다. | default branch 로 merge 된 PR 이 `Closes`, `Fixes`, `Resolves` 로 issue 를 close 하면 완료 상태가 된다. |

## IssueType

| Value | Repo label | Meaning | Usage example |
| --- | --- | --- | --- |
| `epic` | `epic` | 여러 feature 또는 story 를 묶는 큰 outcome. | PRD epic 또는 여러 story 의 parent issue. |
| `feature` | `feature` | 사용자 또는 운영자가 체감하는 capability. | 독립 기능 추가, workflow capability. |
| `story` | `story` | end-to-end 로 독립 구현과 검증이 가능한 vertical slice. | epic 아래의 story issue. |
| `task` | `task` | 사용자-facing 은 아니지만 완료 조건이 명확한 작업. | 인프라 보강, 도구 개선, 문서 sync. |
| `subTask` | `subTask` | parent issue 아래에서만 의미가 있는 child work item. | 큰 issue 를 세부 실행 단위로 나눈 경우. |
| `bug` | `bug` | 깨진 동작 또는 회귀를 복구해야 하는 issue. | 관측 가능한 실패와 복구 기대 동작이 있는 신고. |

IssueType repo label 6종은 `epic`, `feature`, `story`, `task`, `subTask`, `bug` 이며 issue 는 이 중 정확히 하나를 가진다. 작업 중에는 `in-progress` label 이 추가될 수 있으므로 기계 계약 label 은 평상시 1개, 작업 중 최대 2개다. Project `IssueType` 은 이 label 의 선택적 미러다.

## Priority

| Value | Meaning | Usage example |
| --- | --- | --- |
| `blocker` | 의존 작업 또는 release 진행을 막는 issue. | merge, release, production recovery 를 차단하는 상태. |
| `critical` | 일반 major work 보다 먼저 다뤄야 하는 고위험 또는 시급 issue. | 보안, 데이터 손실, 매우 큰 운영 리스크. |
| `major` | 정상 우선순위의 중요 작업. | 일반 feature, 중요한 workflow 개선. |
| `minor` | 유용하지만 낮은 긴급도의 작업. | 작은 UX polish, 낮은 영향의 개선. |
| `trivial` | 영향이 제한적인 작은 정리. | 문구, 소규모 cleanup. |

Priority 처리는 경로별로 다르다. 단발 `/to-issue` 는 Priority 를 맥락에서 추론해 명시한다 (기본값 없음 — [`../../skills/to-issue/issue-fields.md`](../../skills/to-issue/issue-fields.md) 의 Priority 추론 가이드). epic/story 일괄 생성은 전부 `major` 고정이다. Priority label 은 만들지 않는다. `/next-work` 는 Issue Brief 본문 `Priority` 줄을 파싱해 blocker/critical 만 L2 긴급 후보로 승격하고, 값이 없거나 invalid 면 `priority 미기재` 로 그룹 뒤에 둔다. `register-issue` 의 `--priority` 생략 시 `major` fallback 은 일괄 경로와 선택적 Project backfill 을 위한 동작이며, 단발 등록은 추론값을 항상 명시해 그 fallback 에 의존하지 않는다.

## Lifecycle

이슈 등록 직후 상태는 `open` + `in-progress` label 없음, 즉 `Todo` 다. 특정 issue 를 대상으로 설계나 구현 흐름을 실제 시작하면 `start-work` 가 `in-progress` label 을 붙인다. default branch 에 merge 된 PR 이 `Closes #N`, `Fixes #N`, `Resolves #N` 또는 GitHub 의 실제 closing issue reference 로 issue 를 완료하면 GitHub native close 가 `Done` 진본이 되고, 후처리 경로는 `in-progress` label 만 제거한다.

`Part of #N` 은 중간 연결일 뿐 완료 신호가 아니다. `Part of #N` 만 있는 PR 은 issue 를 close 하지 않고 `in-progress` label 제거 대상으로도 보지 않는다.

등록 명령, 선택적 보드 좌표 해석, 멱등 backfill, PR merge 후처리 같은 실행 메커니즘은 [`issue-lifecycle.md#issuelabel-status-lifecycle`](issue-lifecycle.md#issuelabel-status-lifecycle) 가 소유한다. 본 문서는 issue/label 계약과 선택적 Project 축, drift 메시지의 의미만 정의한다.

## Drift Messages

label drift 는 어떤 issue 의 lifecycle label 이 계약과 다른지 보여준다.

예:

```text
issue #663: closed issue retains in-progress label; remove in-progress.
```

IssueType / repo label drift 는 어떤 issue 에서 어떤 label 계약이 어긋났는지 보여준다. Project 좌표가 있는 경우 보드를 best-effort 로 읽어 Project field drift 도 warning 으로 보고할 수 있다. 이 warning 은 사람이 보드를 미러로 정리할 때 쓰는 정보이며, drift 실패 판정은 IssueType label 유일성, `in-progress` label 유일성, closed issue 의 `in-progress` 잔존 같은 issue/label 규칙만 본다.

예:

```text
issue #663: Project IssueType=feature, repo label=bug. Set Project IssueType and exactly one matching repo label to the same value.
```

## Bootstrap Commands

Project 번호를 아는 경우 선택적 Project 축과 lifecycle label 7종을 함께 점검한다.

```bash
node scripts/github_project_lifecycle.mjs bootstrap --repo OWNER/REPO --owner OWNER --project PROJECT_NUMBER
node scripts/github_project_lifecycle.mjs bootstrap --repo OWNER/REPO --owner OWNER --project PROJECT_NUMBER --apply
```

Project 가 없는 경우:

```bash
gh project create --owner OWNER --title "dcNess" --format json
gh project link PROJECT_NUMBER --owner OWNER --repo REPO
node scripts/github_project_lifecycle.mjs bootstrap --repo OWNER/REPO --owner OWNER --project PROJECT_NUMBER --apply
```
