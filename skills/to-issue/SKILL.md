---
name: to-issue
description: 자연어 문제, 작업 후보, 계획 조각을 GitHub issue 로 바로 등록하기 위한 공개 진입점. 사용자가 "/to-issue", "이슈 등록해줘", "이슈 만들어줘", "이거 이슈로 남겨줘", "티켓 만들어줘", "GitHub issue 등록", "후속 이슈 등록", "issue 초안", "작업 후보를 issue 로 쪼개줘"처럼 issue 등록을 원하거나, 작업 흐름 중 후속 이슈를 남길 때 사용한다. GitHub issue 생성·등록은 직접 만들지 말고 이 스킬을 기본 경로로 사용한다. 메인 Claude 가 대화 맥락으로 IssueType/Priority 를 추론하고 라벨을 붙여, 초안 승인 대기 없이 바로 GitHub issue 를 등록한 뒤 선택적으로 Project backfill 을 수행한다. 사용자는 등록된 issue 를 GitHub web 에서 확인하고 수정을 요청한다.
---

# To Issue Skill

`/to-issue` 는 GitHub issue 등록 흐름이다. 메인 Claude 가 대화 맥락으로 모호함을 해소하고 표준 Issue Brief 를 구성한 뒤, IssueType/Priority 를 추론하고 라벨을 붙여 초안 승인 대기 없이 바로 GitHub issue 를 등록한다. 사용자는 등록된 issue 를 GitHub web 에서 확인하고 수정 요청으로 교정한다.

## 범위

- 메인 Claude 전담 흐름이다. 서브에이전트, planner, validator 를 호출하지 않는다.
- 버그를 바로 고칠 요청은 `/impl`, GitHub issue 로 추적할 요청은 `/to-issue` 가 처리한다.
- `/to-issue` 는 이미 "issue 로 만들겠다"는 의도가 있는 문제/작업 후보를 durable 작업 계약으로 바꾸는 흐름이다.
- `/spec` 의 epic/story 일괄 생성 흐름은 제품 계획 산출물 전용이다. `/to-issue` 는 단발 issue 또는 승인된 vertical slice 묶음을 다룬다.
- GitHub issue 생성·등록은 `/to-issue` 를 기본 경로로 사용하고 직접 만들지 않는다 (작업 흐름 중 자발적으로 남기는 후속 이슈 포함). `/to-issue` 외 대화나 다른 agent workflow 가 issue 를 만들 때도 `scripts/check_issue_body.mjs` pre-create validation 을 통과하고 IssueType 라벨을 붙인 뒤 `gh issue create` 를 실행해야 한다.

## 원칙

- Issue Brief 는 agent 나 사람이 작업할 계약이다. 원래 대화와 코멘트는 context 이고, 작업 기준은 brief 다.
- 이슈를 등록한 세션이 아닌 다른 세션이 처리·구현하는 것이 기본이다. 그래서 등록 세션이 이미 아는 배경·제약·의도는 대화에만 두고 생략하지 말고 Issue Brief(특히 Context)에 옮겨, 이슈 하나만 읽어도 자족적으로 착수할 수 있게 한다. 옮기는 대상은 목표와 판단 근거이지 구현 방법이 아니다.
- 오래 살아도 유효해야 하므로 구현 파일 경로, line number, 현재 코드 구조에 의존하지 않는다.
- 무엇을 만들지와 어떤 동작이 되어야 하는지를 쓴다. 어떻게 구현할지는 `/impl` 또는 작업자가 판단한다.
- 코드 조각, 해결책 지시, layer-by-layer 작업 계획은 기본적으로 넣지 않는다. prototype 의 state machine, schema, type shape 가 prose 보다 결정을 정확히 담는 경우만 짧게 포함하고 prototype 출처를 명시한다.
- Acceptance criteria 는 각각 독립적으로 검증 가능해야 한다.
- 큰 계획을 여러 issue 로 나누는 경우 horizontal layer 가 아니라 end-to-end vertical slice 로 나눈다. 완료된 slice 는 독립적으로 demo 또는 검증 가능해야 한다.
- parent issue 가 있더라도 `/to-issue` 는 parent issue 를 닫거나 임의 수정하지 않는다.
- UI 성격 issue 는 기준 canvas / 목업 / flow 문서를 본문에 명시한다. 후속 `/impl` 이 이슈만 보고 UI 기준 확보 분기를 통과할 수 있어야 한다.

## 기준 파일

- IssueType, Priority, repo label 매핑은 [`issue-fields.md`](issue-fields.md)를 SSOT 로 사용한다.
- Issue/label lifecycle 전체 축과 optional Project backfill 은 [`../../docs/plugin/github-project.md`](../../docs/plugin/github-project.md)를 SSOT 로 사용한다.
- Issue Brief 본문 구조는 [`templates/issue-brief.md`](templates/issue-brief.md)를 템플릿으로 사용한다.
- Issue Brief 생성 직전 형식 검증은 [`../../scripts/check_issue_body.mjs`](../../scripts/check_issue_body.mjs)를 사용한다.
- 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`../../docs/plugin/terms.md`](../../docs/plugin/terms.md)를 확인한다.
- `SKILL.md` 에 필드 선택지 목록이나 Issue Brief 본문 템플릿을 다시 쓰지 않는다. 선택지나 템플릿을 바꿔야 하면 기준 파일을 먼저 바꾼다.

## 입력 확인

이미 대화에 있는 정보를 우선 사용한다. 부족한 항목만 짧게 질문한다.

- 문제/작업 후보 요약
- 현재 동작 또는 배경
- 원하는 동작 또는 만들 결과
- 사용자가 보게 되는 command, API, 문서 공개 노출 범위, config shape, type/field 이름 같은 안정적인 계약
- UI 성격이면 기준 canvas / 목업 / flow 문서 또는 사용자 제공 이미지·스케치 링크. 시각 구조 불변이면 `목업 없이` 사유
- 독립적으로 검증 가능한 acceptance criteria
- IssueType: [`issue-fields.md`](issue-fields.md)의 `IssueType` 값
- Priority: [`issue-fields.md`](issue-fields.md)의 `Priority` 값. 단발 등록은 기본값 없이 맥락에서 추론한다 ([`issue-fields.md`](issue-fields.md)의 Priority 추론 가이드).
- Blocked by: 없음 또는 blocking issue 링크
- Out of scope
- parent issue 여부
- 선택적 Project target 과 field option. Project 는 사람용 파생 뷰이므로 확인할 수 없으면 추측하지 않고 issue/label 등록만 진행한다.

## 절차

### Step 1 — context 와 중복 확인

사용자가 issue 번호, PR 번호, URL, 파일 경로를 주면 본문과 댓글 또는 관련 문서를 읽는다. GitHub issue 를 만들기 전, read-only 조회로 중복 이슈 후보를 확인한다.

예:

```bash
gh issue list --state open --search "<핵심 키워드>" --json number,title,labels,url
```

제목이 거의 동일한 open issue 가 있으면 등록하지 말고, 기존 issue 를 이어갈지 새 issue 로 분리할지 먼저 확인한다. 명백한 중복이 아니면 확인 없이 바로 등록으로 진행한다.

### Step 2 — 명확화

모호한 항목만 질문한다. 최소 확인 항목:

- granularity 가 너무 크거나 작지 않은가?
- dependency 관계가 맞는가?
- HITL/AFK 분류가 맞는가?
- IssueType label 값이 맞는가?
- Priority 는 맥락에서 추론한다 — 매번 되묻지 않는다. 추론 신호가 상충하거나 사용자가 특정 우선순위를 의도한 정황이 있을 때만 확인한다.
- UI 성격 issue 인데 기준 canvas / 목업 / flow 문서, 사용자 제공 이미지·스케치 링크, 또는 `목업 없이` 사유가 없는가? 없으면 등록 전 한 번만 확인한다.

여러 issue 로 나눠야 하면 end-to-end vertical slice 로 나눠 각 slice 를 바로 등록하고, 분할 기준은 등록 안내에 함께 밝힌다.

### Step 3 — 본문 구성과 바로 등록

[`templates/issue-brief.md`](templates/issue-brief.md)를 읽고, [`issue-fields.md`](issue-fields.md)의 선택값으로 `{{IssueType}}`, `{{Priority}}` 를 채운다. `{{Priority}}` 는 [`issue-fields.md`](issue-fields.md)의 Priority 추론 가이드로 맥락에서 추론해 채우고, default `major` 로 조용히 수렴시키지 않는다. 템플릿의 섹션 구조를 임의로 축약하지 않는다. 안정적인 계약을 모르면 추측하지 말고 비워두거나 명확화 질문으로 남긴다.

UI 성격 issue 는 `Key interfaces / Contracts` 에 `UI 기준:` 항목을 둔다. 값은 `docs/design-variants/<screen-id>.html`, `docs/design-variants/canvas.html`, `docs/epics/.../ux-flow.md`, 사용자 제공 이미지·스케치 링크, 또는 `목업 없이(시각 구조 불변 사유=<reason>)` 중 하나다. "나중에 정함" 으로 등록하지 않는다.

초안을 미리 보여주거나 승인을 기다리지 않는다. 추론한 IssueType/Priority 와 그에 대응하는 repo label 을 그대로 적용해 바로 등록한다. 사용자는 등록된 issue 를 GitHub web 에서 확인하고 수정 요청으로 교정한다.

등록 전 preflight 로 Issue Brief 본문과 repo label 이 실제 계약에 맞는지 확인한다. Project field/option 은 선택적 backfill 대상이다. 보드(Project)나 field/option 이 없거나 불완전하면 등록을 멈추지 말고, 사용자가 원할 때만 `node scripts/github_project_lifecycle.mjs bootstrap --apply` (보드 자체가 없으면 `gh project create` + `gh project link` 를 먼저) 로 셋업하고, 좌표를 `gh variable set DCNESS_PROJECT_NUMBER --body <number>` / `gh variable set DCNESS_PROJECT_OWNER --body <owner>` 로 저장한 뒤 Project 등록을 backfill 한다. 거부하면 보드 없이 issue 만 등록한다. 어떤 경우에도 Project 상태는 등록 자체를 막지 않는다.

```bash
node scripts/check_issue_body.mjs \
  --body-file <brief.md> \
  --labels "<IssueType>"

gh issue create --title "<title>" --body-file <brief.md> --label "<IssueType>"
```

validator 실패 시 `gh issue create` 를 실행하지 않는다. 실제 issue 생성 preflight 는 `--labels` 를 함께 넘겨 label 계약까지 검증하고, 본문 초안만 점검할 때만 `--body-only` 를 명시한다. 실패 메시지가 지적한 section, IssueType/Priority 값, repo label 매핑을 고친 뒤 다시 검증한다.

보드 좌표가 있으면(또는 위에서 셋업했으면) 생성된 issue 를 Project 보드에 선택 등록한다. `register-issue` 가 item 추가(없으면 add, 멱등) + `Status=Todo` + 선택한 `IssueType` + 추론·확정한 `Priority` 설정 + drift 사후검증을 한 번에 처리한다. Project field 와 option id 는 스크립트가 `gh project field-list` 로 조회한 실제 값만 사용한다. `--priority` 에는 추론·확정한 Priority 를 항상 명시한다 — 생략하면 `register-issue` 가 스크립트 기본값(major)으로 fallback 하므로, 단발 등록에서는 생략하지 않는다 (epic/story 일괄 생성만 그 fallback 에 의존한다).

```bash
node scripts/github_project_lifecycle.mjs register-issue \
  --repo <owner/repo> \
  --owner <owner> \
  --project <project-number> \
  --issue <number> \
  --issue-type "<IssueType>" \
  --priority "<Priority>" \
  --apply
```

### Step 4 — 등록 후 통보와 검증

등록 직후 issue 링크를 사용자에게 통보하고, GitHub web 에서 확인해 수정할 것이 있으면 말해달라고 안내한다. 통보에는 등록된 issue 의 확정 상태를 함께 밝힌다.

- title
- IssueType / Priority (Priority 는 추론값과 추론 근거를 함께 표기)
- repo label: IssueType 과 같은 repo label
- lifecycle state: open issue + `in-progress` label 없음 (`Todo`)
- optional Project backfill: Project 좌표가 있으면 `Status=Todo`, Project `IssueType`, Project `Priority`
- parent issue: 있으면 참조만 하고 닫거나 임의 수정하지 않는다

성공 안내 전 등록 상태를 다시 검증한다.

```bash
gh issue view <number> --json number,title,labels,url
node scripts/github_project_lifecycle.mjs validate-issue \
  --repo <owner/repo> \
  --issue <number>
```

Project backfill 을 수행한 경우에만 Project 기대값도 함께 검증한다.

```bash
node scripts/github_project_lifecycle.mjs validate-issue \
  --repo <owner/repo> \
  --owner <owner> \
  --project <project-number> \
  --issue <number> \
  --expected-status Todo \
  --expected-issue-type "<IssueType>" \
  --expected-priority "<Priority>"
```

등록된 issue 는 선택한 IssueType repo label 을 정확히 하나 가져야 하며, Priority 는 Issue Brief 본문에 남아야 한다. Project backfill 을 수행한 경우에만 Project `Status=Todo`, 선택한 `IssueType`, 선택한 `Priority` 반영까지 확인한다. 저장 실패나 Project field 반영 실패 상황에서 Project까지 성공했다고 안내하지 않는다. 보드 미연결로 등록을 건너뛰었거나, issue 는 생성됐지만 Project 반영이 실패했다면 partial state 를 명확히 말하고 필요한 후속 조치만 제안한다.
