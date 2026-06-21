# Issue Lifecycle

> **Status**: ACTIVE
> **Scope**: GitHub 이슈 lifecycle 운영·메커니즘 SSOT. 등록 양식·트레일러 키워드·완료 *룰* 은 [`git-spec.md`](git-spec.md) 의 이슈 등록 양식·PR 트레일러·이슈 완료 규칙 참조 — 본 문서는 *어떻게 실행하느냐* (gh API 호출 / 멱등성 / pre-flight gate) 만 다룬다.

## 이슈 계층

```
epic issue ─┬─ story issue ── (task: PR 기반, 이슈 없음)
            └─ story issue ── (task: PR 기반, 이슈 없음)
```

- **epic** = 1 개 `docs/epics/epic-NN-<slug>/stories.md` 영역 (epic 단위 stories.md 1 개 = 1 epic)
- **story** = epic 단위 stories.md 안의 Story N 단위
- **task** = `docs/epics/epic-NN-*/impl/NN-*.md` 단위. PR 1 개 = task 1 개. GitHub 이슈 X — PR 자체가 추적 단위

`epic-NN` 은 프로젝트 전역 번호다. milestone 은 path segment 가 아니라 stories frontmatter `milestone: vNN` 로 남긴다.

> 양식 (레이블 / 마일스톤 / 제목 / 본문 / stories.md 기록 형식) 은 [`git-spec.md`](git-spec.md#이슈-등록-양식) SSOT.

## Sub-issue 연결 (epic ↔ story, gh API 메커니즘)

자동화 = [`scripts/create_epic_story_issues.sh`](../../scripts/create_epic_story_issues.sh) — stories.md parse + epic/story 이슈 생성 + sub-issue API 연결 한 명령으로 처리. 별도 호출 (구 ISSUE_SYNC) X.

수동 호출 시 (script 미사용):

```bash
# story_id = mcp__github__create_issue 응답의 .id 필드 (database id, NOT .number)
gh api -X POST repos/{owner}/{repo}/issues/{epic_number}/sub_issues \
  -F sub_issue_id={story_id}
# 주의: -f (string) 아닌 -F (typed) — -f 시 422 Invalid property
```

멱등성: 재호출 전 `gh api repos/{owner}/{repo}/issues/{epic_number} --jq '.sub_issues_summary.total'` 로 연결 상태 조회. 누락 story 만 추가 (이미 연결된 story 재추가 시 422).

task 는 GitHub 이슈 X — [`git-spec.md`](git-spec.md#pr-트레일러-part-of-closes) PR 트레일러로만 추적.

## Issue pre-create validation

에이전트 workflow 가 `gh issue create` 를 실행하기 전에는 Issue Brief 본문과 repo label 매핑을 로컬에서 먼저 검증한다. 이 검증은 사람의 GitHub UI issue 생성을 막는 hard gate 가 아니다. 목적은 dcNess/Codex/Claude workflow 가 issue 생성 전에 같은 문서 형식과 IssueType/Priority/label 계약을 따르도록 하는 것이다.

```bash
node scripts/check_issue_body.mjs \
  --body-file <brief.md> \
  --labels "<IssueType>"

gh issue create --title "<title>" --body-file <brief.md> --label "<IssueType>"
```

`scripts/check_issue_body.mjs` 가 실패하면 `gh issue create` 를 실행하지 않는다. 실제 issue 생성 preflight 는 `--labels` 를 함께 넘겨 label 계약까지 검증하고, 본문 초안만 점검할 때만 `--body-only` 를 명시한다. `/to-issue` 는 권장 도우미이며, `/to-issue` 외 이미 승인된 대화나 agent workflow 가 issue 를 생성하는 경우에도 같은 pre-create validation 을 통과해야 한다.

## GitHub Project Status lifecycle

Project 축 정의의 SSOT 는 [`github-project.md`](github-project.md) 이다. 본 절은 issue 등록, `/spec`, `/design`, `/impl`, `/ux`, PR merge 후처리가 그 축을 어떻게 갱신하는지만 다룬다.

### 이슈 등록 — Status=Todo

issue 등록 직후 Project item 으로 추가하고 `Status=Todo` + `IssueType` + `Priority` 를 설정한다. 단발 등록 (`/to-issue`) 과 epic/story 일괄 생성 ([`scripts/create_epic_story_issues.sh`](../../scripts/create_epic_story_issues.sh)) 이 같은 경로 `register-issue` 를 쓴다. epic → `IssueType=epic`, story → `IssueType=story`, 둘 다 `Priority=major` (일괄 기본).

```bash
node scripts/github_project_lifecycle.mjs register-issue \
  --repo OWNER/REPO --owner OWNER --project PROJECT_NUMBER \
  --issue ISSUE_NUMBER --issue-type epic|story [--priority major] --apply
```

`register-issue` 는 item 이 없으면 추가하고 (멱등), Status/IssueType/Priority 를 설정한 뒤 drift 를 사후검증한다.

보드 (Project) 나 field/option 이 없거나 불완전해도 **issue 생성은 막지 않는다.** 메인은 사용자에게 보드를 만들거나 채울지 물어보고, 동의하면 `bootstrap --apply` (보드 자체가 없으면 `gh project create` + `gh project link` 먼저) 로 셋업한 뒤 등록한다. 거부하면 보드 없이 issue 만 생성한다. 일괄 생성 스크립트는 비대화형이라 좌표가 없으면 보드 등록만 skip 하고 (이슈는 생성됨) 경고하며, 멱등 재실행 시 이슈 생성은 skip 하고 보드 등록만 backfill 한다.

보드 좌표 (owner/number) 는 repo 변수 `DCNESS_PROJECT_NUMBER` / `DCNESS_PROJECT_OWNER` 에 저장한다 — GitHub Actions `vars.*` 와 동일 저장소라 CI lifecycle workflow 와 단일 SSOT 다. `/init-dcness` bootstrap 이 `gh variable set` 으로 저장하고, 등록 경로는 `gh variable get` 으로 읽는다. 조회 우선순위: `--project`/`--owner` 플래그 → `DCNESS_PROJECT_*` env → `gh variable get` → owner 는 repo owner fallback.

### 작업 시작 — Status=In progress

특정 GitHub issue 를 대상으로 `/spec`, `/design`, `/impl`, `/ux` 같은 설계나 구현 흐름을 실제 시작하면 메인은 시작 직전에 Project item 을 `Status=In progress` 로 이동한다. Project 번호와 owner 를 알 수 없으면 추측하지 말고 `/init-dcness` bootstrap 을 먼저 수행한다.

```bash
node scripts/github_project_lifecycle.mjs start-work \
  --repo OWNER/REPO \
  --owner OWNER \
  --project PROJECT_NUMBER \
  --issue ISSUE_NUMBER \
  --apply
```

`--apply` 없이 실행하면 현재 Status 를 읽고 status drift 를 보고한다. 메시지는 어떤 issue 의 어떤 field 를 고쳐야 하는지 포함한다.

```text
issue #663: status drift on Project field Status. expected=In progress, actual=Todo.
```

### PR merge 후처리 — Status=Done

default branch 로 PR merge 가 끝난 뒤 후처리 경로는 PR body 또는 GitHub closing issue reference 에서 완료 후보 issue 를 찾고 `Status=Done` 으로 이동한다.

```bash
node scripts/github_project_lifecycle.mjs pr-merged \
  --repo OWNER/REPO \
  --owner OWNER \
  --project PROJECT_NUMBER \
  --pr PR_NUMBER \
  --apply
```

완료 후보는 `Closes #N`, `Fixes #N`, `Resolves #N` 또는 GitHub 가 실제 close 후보로 제공한 issue 뿐이다. `Part of #N` 은 완료 신호가 아니다. `Part of #N` 만 있는 PR 은 issue 를 `Done` 으로 옮기지 않는다.

`--apply` 없이 실행하면 `Status=Done` 누락을 drift 로 보고한다. 메시지는 어떤 issue 와 어떤 field 를 고쳐야 하는지 포함한다.

```text
issue #663: status drift on Project field Status. expected=Done, actual=In progress.
```

### IssueType / repo label drift

issue 는 Project `IssueType` 과 같은 repo label 을 정확히 하나 가져야 한다. 값이 어긋나면 어떤 issue 에서 어떤 값이 다른지 보고한다.

```bash
node scripts/github_project_lifecycle.mjs validate-issue \
  --repo OWNER/REPO \
  --owner OWNER \
  --project PROJECT_NUMBER \
  --issue ISSUE_NUMBER
```

예:

```text
issue #663: Project IssueType=feature, repo label=bug. Set Project IssueType and exactly one matching repo label to the same value.
```

### CI/CD harness

`/init-dcness` 는 선택적으로 `github-project-lifecycle` thin workflow 를 활성 repo 에 설치한다. 이 workflow 는 본 repo 의 composite action 을 호출해 issue label/type drift 를 PR/issue 이벤트에서 검증하고, merge 된 PR 의 완료 후보 issue 를 `Done` 으로 보정한다. Project v2 쓰기에는 `project` scope 가 필요하므로 사용자 repo 는 `DCNESS_PROJECT_TOKEN` secret 과 `DCNESS_PROJECT_NUMBER` / `DCNESS_PROJECT_OWNER` variables 를 설정해야 한다. token 이 없으면 workflow 는 drift 검출 중심으로 실패 메시지를 남긴다.

## 미등록 허용 모드

프로젝트가 미등록 모드 (spike / 잡탕 epic 등) 채택 시 stories.md 상단:

```
**GitHub Epic Issue:** 미등록 (사유: <spike / 잡탕 / …>)
```

story 이슈도 보류하면 각 Story 헤더 직하에 같은 방식으로 명시한다.

```
**GitHub Issue:** 미등록 (사유: <spike / 잡탕 / …>)
```

명시 없는 미등록 = 위반. 발견 시 backfill 의무 — 메인이 [`git-spec.md`](git-spec.md#이슈-등록-양식) 따라 `mcp__github__create_issue` 1회 호출 + stories.md 번호 patch.

## 멱등성 (등록 전 매치 체크)

`mcp__github__create_issue` 전: stories.md 의 `**GitHub Epic Issue:**` / `**GitHub Issue:**` 매치 검사. 링크 있으면 skip. stories.md 가 이슈 등록 상태의 SSOT.

## 마일스톤 파라미터 — tool 별 타입 차이

**⚠️ tool 별 milestone 파라미터 타입이 다름** — 혼동 시 silent fail 또는 422 오류:

| Tool | `milestone` 파라미터 | jq 추출 |
|---|---|---|
| `mcp__github__create_issue` | **number** (숫자) | `--jq '.[] | select(.title=="Epics") | .number'` |
| `gh issue create --milestone <X>` | **name** (문자열 title) | `--jq '.[] | select(.title=="Epics") | .title'` |

매 세션 1회 조회 (프로젝트별 number 다를 수 있음 — 캐싱 X):

```bash
gh api repos/{owner}/{repo}/milestones --jq '.[] | {number, title}'
```

근거:
- `gh issue create --help` → `-m, --milestone name` (gh CLI v2.x 기준)
- `mcp__github__create_issue` schema → `milestone: integer` (number 만)

**스크립트 예** ([`scripts/create_epic_story_issues.sh`](../../scripts/create_epic_story_issues.sh)) 는 `gh issue create` 사용 → title 추출 필요. mcp tool 호출은 number 추출 필요.

## mid-flow 누락 차단 (pre-flight gate)

`/impl-loop` / `/design` (ux-architect / system-architect / Story/공통 module-architect 단위) 진입 시 부모 epic stories.md 상단 매치 강제:

- `**GitHub Epic Issue:** [#\d+]` (정식 등록), 또는
- `**GitHub Epic Issue:** 미등록 (사유: …)` ([미등록 허용 모드](#미등록-허용-모드))

매치 0건 → 즉시 STOP + 사용자 보고. silent skip ("이슈 번호 없음 — 생략하고 진행") 금지.

story 이슈 부재 시 동일 패턴:

- Story N 헤더 직하 `**GitHub Issue:** [#\d+]` (정식 등록), 또는
- Story N 헤더 직하 `**GitHub Issue:** 미등록 (사유: …)` 매치

## 참조

- 산출물 위치·양식·계층 SSOT (epic 폴더 안에 어떤 docs 가 사는가): [`deliverables-map.md`](deliverables-map.md)
- 등록·트레일러·완료 *룰* SSOT: [`git-spec.md`](git-spec.md) 의 이슈 등록 양식·PR 트레일러·이슈 완료 규칙
- 분기 규칙 / 핸드오프: 각 loop skill 의 `<skill>-routing.md` (예: [`../../skills/impl-loop/impl-loop-routing.md`](../../skills/impl-loop/impl-loop-routing.md))
- loop 진입 spec: 각 skill 본문 `skills/<skill>/SKILL.md` 의 `## Loop` contract. 공통 실행 절차 = [`loop-procedure.md`](loop-procedure.md#진입-모델)
- 용어 기준: [`terms.md`](terms.md)
- spec skill (메인 직접): [`../../skills/spec/SKILL.md`](../../skills/spec/SKILL.md)
- system-architect (impl 목차 표 SSOT): [`../../agents/system-architect.md`](../../agents/system-architect.md)
- module-architect (impl 본문 detail per task): [`../../agents/module-architect.md`](../../agents/module-architect.md)
- engineer: [`../../agents/engineer.md`](../../agents/engineer.md) — task = 1 PR
