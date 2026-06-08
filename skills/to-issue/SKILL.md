---
name: to-issue
description: 자연어 문제, 작업 후보, 계획 조각을 GitHub issue 로 만들기 위한 public entrypoint. 사용자가 "/to-issue", "이슈로 만들어줘", "티켓 만들어줘", "GitHub issue 등록", "issue 초안", "작업 후보를 issue 로 쪼개줘"처럼 issue draft/publish 를 원할 때 사용한다. 메인 Claude 가 직접 질문하고 dcNess 표준 Issue Brief 초안을 보여준 뒤 사용자 승인 후에만 GitHub issue 와 Project item 을 만든다.
---

# To Issue Skill

`/to-issue` 는 GitHub issue 작성/등록 흐름이다. 메인 Claude 가 사용자와 직접 대화하며 모호함을 해소하고, 표준 Issue Brief 초안을 만든 뒤, 사용자 승인 후에만 GitHub issue 를 생성한다.

## 범위

- 메인 Claude 전담 흐름이다. 서브에이전트, planner, validator 를 호출하지 않는다.
- 버그를 바로 고칠 요청은 `/impl`, GitHub issue 로 추적할 요청은 `/to-issue` 가 처리한다.
- `/to-issue` 는 이미 "issue 로 만들겠다"는 의도가 있는 문제/작업 후보를 durable 작업 계약으로 바꾸는 흐름이다.
- `/spec` 의 epic/story 일괄 생성 흐름은 제품 계획 산출물 전용이다. `/to-issue` 는 단발 issue 또는 승인된 vertical slice 묶음을 다룬다.
- `/to-issue` 는 권장 도우미다. `/to-issue` 외에 이미 승인된 대화나 다른 agent workflow 가 issue 를 만들 때도 `scripts/check_issue_body.mjs` pre-create validation 을 통과한 뒤 `gh issue create` 를 실행해야 한다.

## 원칙

- Issue Brief 는 agent 나 사람이 작업할 계약이다. 원래 대화와 코멘트는 context 이고, 작업 기준은 brief 다.
- 오래 살아도 유효해야 하므로 구현 파일 경로, line number, 현재 코드 구조에 의존하지 않는다.
- 무엇을 만들지와 어떤 동작이 되어야 하는지를 쓴다. 어떻게 구현할지는 `/impl` 또는 작업자가 판단한다.
- 코드 조각, 해결책 지시, layer-by-layer 작업 계획은 기본적으로 넣지 않는다. prototype 의 state machine, schema, type shape 가 prose 보다 결정을 정확히 담는 경우만 짧게 포함하고 prototype 출처를 명시한다.
- Acceptance criteria 는 각각 독립적으로 검증 가능해야 한다.
- 큰 계획을 여러 issue 로 나누는 경우 horizontal layer 가 아니라 end-to-end vertical slice 로 나눈다. 완료된 slice 는 독립적으로 demo 또는 검증 가능해야 한다.
- parent issue 가 있더라도 `/to-issue` 는 parent issue 를 닫거나 임의 수정하지 않는다.

## 기준 파일

- IssueType, Priority, repo label 매핑은 [`issue-fields.md`](issue-fields.md)를 SSOT 로 사용한다.
- Project lifecycle 전체 축과 status 전이는 [`../../docs/plugin/github-project.md`](../../docs/plugin/github-project.md)를 SSOT 로 사용한다.
- Issue Brief 본문 구조는 [`templates/issue-brief.md`](templates/issue-brief.md)를 템플릿으로 사용한다.
- Issue Brief 생성 직전 형식 검증은 [`../../scripts/check_issue_body.mjs`](../../scripts/check_issue_body.mjs)를 사용한다.
- `SKILL.md` 에 필드 선택지 목록이나 Issue Brief 본문 템플릿을 다시 쓰지 않는다. 선택지나 템플릿을 바꿔야 하면 기준 파일을 먼저 바꾼다.

## 입력 확인

이미 대화에 있는 정보를 우선 사용한다. 부족한 항목만 짧게 질문한다.

- 문제/작업 후보 요약
- 현재 동작 또는 배경
- 원하는 동작 또는 만들 결과
- 사용자가 보게 되는 command, API, 문서 surface, config shape, type/field 이름 같은 안정적인 계약
- 독립적으로 검증 가능한 acceptance criteria
- IssueType: [`issue-fields.md`](issue-fields.md)의 `IssueType` 값
- Priority: [`issue-fields.md`](issue-fields.md)의 `Priority` 값
- Blocked by: 없음 또는 blocking issue 링크
- Out of scope
- parent issue 여부
- Project target 과 필드 옵션. Project `Status`, Project `IssueType`, Project `Priority` 를 확인할 수 없으면 추측하지 않는다.

## 절차

### Step 1 — context 와 중복 확인

사용자가 issue 번호, PR 번호, URL, 파일 경로를 주면 본문과 댓글 또는 관련 문서를 읽는다. GitHub issue 를 만들기 전, read-only 조회로 중복 이슈 후보를 확인한다.

예:

```bash
gh issue list --state open --search "<핵심 키워드>" --json number,title,labels,url
```

중복 가능성이 있으면 새 issue 를 만들지 말고 사용자에게 기존 issue 를 이어갈지, 새 issue 로 분리할지 확인한다.

### Step 2 — 명확화

모호한 항목만 질문한다. 최소 확인 항목:

- granularity 가 너무 크거나 작지 않은가?
- dependency 관계가 맞는가?
- HITL/AFK 분류가 맞는가?
- Project `IssueType` 값이 맞는가?
- Project `Priority` 값이 맞는가?

여러 issue 로 나눠야 하면 numbered list 로 vertical slice 초안을 먼저 보여주고, 사용자가 breakdown 을 승인한 뒤 각 slice 의 Issue Brief 를 작성한다.

### Step 3 — Issue Brief 초안 작성

issue 생성 전 [`templates/issue-brief.md`](templates/issue-brief.md)를 읽고, [`issue-fields.md`](issue-fields.md)의 선택값으로 `{{IssueType}}`, `{{Priority}}` 를 채운 초안을 보여준다.

템플릿의 섹션 구조를 임의로 축약하지 않는다. 안정적인 계약을 모르면 추측하지 말고 비워두거나 명확화 질문으로 남긴다.

### Step 4 — 승인

초안 아래에 publish plan 을 함께 보여준다.

- title
- IssueType / Priority
- repo label: Project `IssueType`과 같은 repo label
- Project field update: `Status=Todo`, Project `IssueType`, Project `Priority`
- parent issue: 있으면 참조만 하고 닫거나 임의 수정하지 않는다

사용자가 명시적으로 승인하기 전에는 GitHub issue 를 만들지 않는다. 승인 전에는 GitHub issue 를 만들지 않는다. 승인을 거절하면 초안을 수정하고 다시 보여준다.

### Step 5 — 등록과 검증

등록 전 preflight 로 Issue Brief 본문, repo label, Project field/option 이 실제 존재하는지 확인한다. 없으면 issue 를 만들지 말고 빠진 setup 을 보고한다.

승인 후에만 생성한다.

```bash
node scripts/check_issue_body.mjs \
  --body-file <brief.md> \
  --labels "<IssueType>"

gh issue create --title "<title>" --body-file <brief.md> --label "<IssueType>"
```

validator 실패 시 `gh issue create` 를 실행하지 않는다. 실제 issue 생성 preflight 는 `--labels` 를 함께 넘겨 label 계약까지 검증하고, 본문 초안만 점검할 때만 `--body-only` 를 명시한다. 실패 메시지가 지적한 section, IssueType/Priority 값, repo label 매핑을 고친 뒤 다시 검증한다.

Project item 은 생성된 issue URL 로 추가한다. Project field 와 option id 는 `gh project field-list` 로 조회한 실제 값만 사용한다.

```bash
PROJECT_ID="$(gh project view <number> --owner <owner> --format json --jq .id)"
ITEM_ID="$(gh project item-add <number> --owner <owner> --url <issue-url> --format json --jq .id)"
gh project field-list <number> --owner <owner> --format json
gh project item-edit --project-id "$PROJECT_ID" --id "$ITEM_ID" --field-id <Status-field-id> --single-select-option-id <Todo-option-id>
gh project item-edit --project-id "$PROJECT_ID" --id "$ITEM_ID" --field-id <IssueType-field-id> --single-select-option-id <IssueType-option-id>
gh project item-edit --project-id "$PROJECT_ID" --id "$ITEM_ID" --field-id <Priority-field-id> --single-select-option-id <Priority-option-id>
```

성공 안내 전 검증한다.

```bash
gh issue view <number> --json number,title,labels,url
gh project item-list <number> --owner <owner> --format json
node scripts/github_project_lifecycle.mjs validate-issue \
  --repo <owner/repo> \
  --owner <owner> \
  --project <project-number> \
  --issue <number> \
  --expected-status Todo \
  --expected-issue-type "<IssueType>" \
  --expected-priority "<Priority>"
```

등록된 issue 는 Project 에 추가되고 `Status=Todo`, 선택한 `IssueType`, 선택한 `Priority` 를 가져야 한다. 등록된 issue 는 Project `IssueType`과 같은 repo label 을 가져야 한다. 저장 실패나 Project field 반영 실패 상황에서 성공 안내를 하지 않는다. 이미 issue 는 생성됐지만 Project 반영이 실패했다면 partial state 를 명확히 말하고 필요한 후속 조치만 제안한다.
