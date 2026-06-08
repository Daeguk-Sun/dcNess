# GitHub Project Lifecycle

> **Status**: ACTIVE
> **Scope**: dcNess 표준 GitHub Project v2 축, repo label, lifecycle 상태 전이의 SSOT. 실행 메커니즘은 [`issue-lifecycle.md`](issue-lifecycle.md), git/PR trailer 룰은 [`git-spec.md`](git-spec.md), `/to-issue` 입력 필드 요약은 [`../../skills/to-issue/issue-fields.md`](../../skills/to-issue/issue-fields.md)를 함께 본다.

dcNess 활성 repo 는 GitHub Project v2 에 `Status`, `IssueType`, `Priority` 세 축을 둔다. `/init-dcness` 는 이 축과 repo label 6종을 점검하고, `--apply` 경로에서는 부족한 repo label 과 새 Project field 를 만들 수 있다. 기존 Project field 에 option 이 빠진 경우는 GitHub CLI 가 option 추가를 직접 지원하지 않으므로 명확한 복구 안내를 낸다.

## Status

| Value | Meaning | Usage example |
| --- | --- | --- |
| `Todo` | issue 가 등록됐지만 아직 설계나 구현 흐름이 시작되지 않은 상태. | `/to-issue` 가 승인된 새 issue 를 Project item 으로 추가한 직후 설정한다. |
| `In progress` | 대상 issue 를 두고 `/spec`, `/design`, `/impl`, `/ux` 같은 실제 작업 흐름이 시작된 상태. | `/impl #663` 처럼 특정 issue 구현을 시작하면 `start-work` 경로가 설정한다. |
| `Done` | default branch 로 merge 된 PR 이 `Closes`, `Fixes`, `Resolves` 로 완료한 issue. | PR merge 후처리가 완료 후보 issue 를 찾아 설정하거나 drift 를 보고한다. |

## IssueType

| Value | Repo label | Meaning | Usage example |
| --- | --- | --- | --- |
| `epic` | `epic` | 여러 feature 또는 story 를 묶는 큰 outcome. | PRD epic 또는 여러 story 의 parent issue. |
| `feature` | `feature` | 사용자 또는 운영자가 체감하는 capability. | 독립 기능 추가, workflow capability. |
| `story` | `story` | end-to-end 로 독립 구현과 검증이 가능한 vertical slice. | epic 아래의 story issue. |
| `task` | `task` | 사용자-facing 은 아니지만 완료 조건이 명확한 작업. | 인프라 보강, 도구 개선, 문서 sync. |
| `subTask` | `subTask` | parent issue 아래에서만 의미가 있는 child work item. | 큰 issue 를 세부 실행 단위로 나눈 경우. |
| `bug` | `bug` | 깨진 동작 또는 회귀를 복구해야 하는 issue. | 관측 가능한 실패와 복구 기대 동작이 있는 신고. |

repo label 6종은 `epic`, `feature`, `story`, `task`, `subTask`, `bug` 이며 IssueType 축과 같은 의미로 쓴다. issue list, Project board, 검색/필터가 같은 분류 체계를 보도록 issue 는 Project `IssueType` 과 같은 repo label 을 정확히 하나 가진다.

## Priority

| Value | Meaning | Usage example |
| --- | --- | --- |
| `blocker` | 의존 작업 또는 release 진행을 막는 issue. | merge, release, production recovery 를 차단하는 상태. |
| `critical` | 일반 major work 보다 먼저 다뤄야 하는 고위험 또는 시급 issue. | 보안, 데이터 손실, 매우 큰 운영 리스크. |
| `major` | 정상 우선순위의 중요 작업. | 일반 feature, 중요한 workflow 개선. |
| `minor` | 유용하지만 낮은 긴급도의 작업. | 작은 UX polish, 낮은 영향의 개선. |
| `trivial` | 영향이 제한적인 작은 정리. | 문구, 소규모 cleanup. |

## Lifecycle

이슈 등록 직후 Project `Status=Todo` 이다. 특정 issue 를 대상으로 설계나 구현 흐름을 실제 시작하면 `Status=In progress` 로 이동한다. default branch 에 merge 된 PR 이 `Closes #N`, `Fixes #N`, `Resolves #N` 또는 GitHub 의 실제 closing issue reference 로 issue 를 완료하면 `Status=Done` 으로 이동한다.

`Part of #N` 은 중간 연결일 뿐 완료 신호가 아니다. `Part of #N` 만 있는 PR 은 issue 를 `Done` 으로 옮기지 않는다.

## Drift Messages

status drift 는 어떤 issue 의 어떤 field 가 기대값과 실제값이 다른지 보여준다.

예:

```text
issue #663: status drift on Project field Status. expected=Done, actual=In progress.
```

IssueType / repo label drift 는 어떤 issue 에서 어떤 값이 어긋났는지 보여준다.

예:

```text
issue #663: Project IssueType=feature, repo label=bug. Set Project IssueType and exactly one matching repo label to the same value.
```

## Bootstrap Commands

Project 번호를 아는 경우:

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
