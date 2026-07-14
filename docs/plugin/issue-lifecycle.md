# Issue Lifecycle

> **Status**: ACTIVE
> **Scope**: GitHub 이슈 lifecycle 운영·메커니즘 SSOT. 등록 양식·트레일러 키워드·완료 *룰* 은 [`git-spec.md`](git-spec.md) 의 이슈 등록 양식·PR 트레일러·이슈 완료 규칙 참조 — 본 문서는 *어떻게 실행하느냐* (gh API 호출 / 멱등성 / pre-flight gate) 만 다룬다.

## 이슈 계층

```
epic issue ─┬─ story issue ── (task: local commit, 이슈 없음)
            └─ story issue ── (task: local commit, 이슈 없음)
```

- **epic** = 1 개 `docs/epics/epic-NN-<slug>/stories.md` 영역 (epic 단위 stories.md 1 개 = 1 epic)
- **story** = epic 단위 stories.md 안의 Story N 단위
- **task** = `docs/epics/epic-NN-*/impl/NN-*.md` 단위. 완료 경계는 local commit 이며 GitHub 이슈 X
- **story** = task commit 묶음의 PR 경계. 단일 story는 base=`main` PR 1개, 다중 story/epic은 story branch stack의 story별 PR이다.
- **epic** = story PR × N + tracked 마감 보정이 있을 때만 QA PR 1개. epic 구현을 단일 PR로 묶거나 story PR을 자동 merge하지 않는다.

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

task 는 GitHub 이슈 X — local commit sha 로 추적하고, story/epic 연결·close 는 [`git-spec.md`](git-spec.md#pr-트레일러-part-of-closes) PR 트레일러를 따른다.

## Issue pre-create validation

에이전트 workflow 가 `gh issue create` 를 실행하기 전에는 Issue Brief 본문과 repo label 매핑을 로컬에서 먼저 검증한다. 이 검증은 사람의 GitHub UI issue 생성을 막는 hard gate 가 아니다. 목적은 dcNess/Codex/Claude workflow 가 issue 생성 전에 같은 문서 형식과 IssueType/Priority/label 계약을 따르도록 하는 것이다. Acceptance criteria 체크박스는 `[command]` 또는 `[agent-read]` 로 분류된 agent-verifiable 항목만 허용하고, human verification 은 별도 안내에 체크박스 없이 둔다.

```bash
node "$PLUGIN_ROOT/scripts/check_issue_body.mjs" \
  --body-file <brief.md> \
  --labels "<IssueType>"

gh issue create --title "<title>" --body-file <brief.md> --label "<IssueType>"
```

`scripts/check_issue_body.mjs` 가 실패하면 `gh issue create` 를 실행하지 않는다. 실제 issue 생성 preflight 는 `--labels` 를 함께 넘겨 label 계약까지 검증하고, 본문 초안만 점검할 때만 `--body-only` 를 명시한다. GitHub issue 생성·등록은 직접 `gh issue create` 대신 `/to-issue` 를 기본 경로로 사용한다 (작업 흐름 중 자발적으로 남기는 후속 이슈 포함). `/to-issue` 외 대화나 agent workflow 가 issue 를 생성하는 경우에도 같은 pre-create validation 을 통과하고 IssueType 라벨을 붙여야 한다.

`--require-complete` 는 새 CI hard gate 가 아니라 close 직전 메인이 같은 validator 를 재사용하는 로컬 감사 옵션이다. `--acceptance-only` 와 함께 쓰면 Issue Brief 와 Story/Epic issue body 에 공통으로 적용되며, target GitHub issue AC 에 미체크 항목이 하나라도 있으면 실패한다. close 감사는 Acceptance criteria 와 human verification 의 bold field·Markdown heading 섹션을 모두 인식하고, `-`·`*`·`+` 체크박스 불릿을 같은 checklist 문법으로 집계한다.

reader 결과는 한 경계에서 해석한다. 전항목이 `[command]`/`[agent-read]` 인 현행 body만 정확한 `PASS`로 자동 close를 허용한다. 검증 주체 미기재 AC 또는 Acceptance criteria가 없는 구양식 body는 exit 0의 `REVIEW`로 읽어 기존 issue를 migration 없이 열어둘 수 있게 하지만, 이 결과는 자동 close 권한이 아니다. agent는 legacy 항목을 추론·체크·재분류하지 않고 `human verification 대기`로 보고한다. 사용자가 의미와 완료를 명시적으로 확인하면 body를 소급 변환하지 않고 그 확인을 close 근거로 사용할 수 있다. 신규 writer는 계속 typed checklist만 생성하며, 실제 미체크 항목이나 현행 typed 일반론 AC는 실패한다.

## Issue/label Status lifecycle

계약 축 정의의 SSOT 는 [`github-project.md`](github-project.md) 이다. 본 절은 issue 등록, `/spec`, `/design`, `/impl`, `/ux`, PR merge 후처리가 issue/label 상태를 어떻게 갱신하는지만 다룬다. GitHub Project v2 보드는 선택적 사람용 파생 뷰이며, 기계 필수 경로가 아니다.

### 이슈 등록 — open + IssueType label

issue 생성 시 `epic`, `feature`, `story`, `task`, `subTask`, `bug` 중 정확히 하나의 IssueType label 을 붙인다. Priority 는 Issue Brief 본문의 `Priority` 줄이 진본이며 priority label 은 만들지 않는다. 새 issue 의 Status 의미는 `open` + `in-progress` label 없음, 즉 `Todo` 다.

선택적으로 Project 보드를 쓰는 repo 는 사람용 보드 미러를 위해 `register-issue` 로 Project item 을 backfill 할 수 있다. 이 경로는 item 이 없으면 추가하고 `Status=Todo` + `IssueType` + `Priority` 를 설정한다.

```bash
node scripts/github_project_lifecycle.mjs register-issue \
  --repo OWNER/REPO --owner OWNER --project PROJECT_NUMBER \
  --issue ISSUE_NUMBER --issue-type epic|story [--priority major] --apply
```

보드 (Project) 나 field/option 이 없거나 불완전해도 **issue 생성은 막지 않는다.** 일괄 생성 스크립트는 비대화형이라 좌표가 없으면 보드 등록만 skip 하고 issue 는 생성한다. 멱등 재실행 시 이슈 생성은 skip 하고 선택적 보드 등록만 backfill 한다.

### 다음 작업 조회 — read-only

`/next-work` 는 open issue 목록의 label 과 body 를 읽어 L1→L2→L3 계층 후보를 결정한다. 이 명령은 read-only 유틸리티라 `--apply` 를 받지 않고 issue/label/Project/PR 상태를 변경하지 않는다.

```bash
node scripts/github_project_lifecycle.mjs next-work --repo OWNER/REPO
```

- L1: `in-progress` label 이 붙은 open issue 전부.
- L2: L1 을 제외한 blocker/critical issue. 단 **story 는 제외** — story 는 priority 와 무관하게 소속 epic 의 설계 phase 로 다음 액션이 결정되므로 항상 L3 로 흘려보낸다(L2 승격 시 phase 판정 우회).
- L3: story → feature → task → bug 순. story 는 `epic-NN-<slug>` label 의 NN 오름차순, 같은 epic 안에서는 issue 번호 오름차순이다. feature/task/bug 는 Priority rank 후 issue 번호 오름차순이다.
- L3 story 는 epic 단위로 로컬 설계 산출물(`docs/epics/epic-NN-<slug>/architecture.md` + `impl/NN-*.md`) 존재를 확인해 다음 액션을 구분한다. **설계 미완 epic** 은 story 를 impl 후보로 내밀지 않고 `/design <epic-path>` 를 제시하고, **설계 완료 epic** 만 story 를 impl 후보(L3)로 승격한다. UI epic 에서 `ux-flow.md` 는 있으나 full design pack 이 없으면 **ux 완료 · system 미완** 으로 표시하되 다음 액션은 여전히 `/design <epic-path>` 다. 로컬 산출물은 *현재 git checkout* 의 repo 를 서술하므로 대상 repo 가 현재 checkout(git remote) 과 다르면(`--repo`/`GH_REPO` override) 로컬 phase 판정을 쓰지 않고 보류한다.
- `subTask` 는 독립 후보에서 제외한다. body 의 `Part of #N` 부모가 L1 에 있으면 해당 부모 아래에 중첩 표시한다.

GitHub 조회가 실패하면 실패를 명시하고 로컬 대안 경로를 안내한다. `docs/index.md` 는 live 상태를 복제하지 않고 issue/label 상태, epic/story issue, `/next-work` 를 가리키는 정적 포인터만 둔다. 기존 `docs/index.md` 에 해당 포인터 섹션이 없으면 `/init-dcness` 가 파일을 덮지 않고 섹션만 append 한다.

### 작업 시작 — in-progress label

특정 GitHub issue 를 대상으로 `/spec`, `/design`, `/impl`, `/ux` 같은 설계나 구현 흐름을 실제 시작하면 메인은 시작 직전에 `in-progress` label 을 붙인다. Project 좌표가 설정된 repo 에서는 label 전이 뒤에 Project item `Status=In progress` 이동을 best-effort 로 1회 시도한다. 좌표 부재는 정상 skip 이고, item 부재·권한 실패·field/option 불일치·API 실패는 warning 으로만 보고한다.

```bash
node scripts/github_project_lifecycle.mjs start-work \
  --repo OWNER/REPO \
  --issue ISSUE_NUMBER \
  --apply
```

Project 미러까지 원하면 `--owner` / `--project` 를 명시하거나 repo variable `DCNESS_PROJECT_NUMBER` / `DCNESS_PROJECT_OWNER` 를 둔다. `--apply` 없이 실행하면 `in-progress` label 잔존 여부와, Project 좌표가 있는 경우 Status drift warning 을 함께 보고한다. 이때 명령의 실패 판정은 label 상태만 본다.

### PR merge 후처리 — close + label cleanup

close 를 발동하는 PR 의 CI와 최종 review 증거가 확정된 뒤, merge 전 메인은 진입 preflight 에서 한 번 읽어 보관한 target GitHub issue AC snapshot 과 구현·검증 증거를 완료 후보 issue 별로 전수 대조한다. task/story 진행 중 issue 를 다시 조회하거나 수정하지 않는다. story-close acceptance verdict에서 자동 판정 및 `(JOURNEY)`로 충족된 typed AC만 메인이 체크하고 `사람 확인 안내`는 미체크로 둔다. 이 체크박스 write는 issue별 close 경계에서 한 번 수행한다. 갱신 body 는 각각 다음 명령으로 감사한다.

```bash
node "$PLUGIN_ROOT/scripts/check_issue_body.mjs" \
  --body-file <issue-body.md> \
  --acceptance-only \
  --require-complete
```

정확한 `PASS`면 typed 자동 항목의 close 감사가 끝난다. `REVIEW`면 legacy reader가 본문을 성공적으로 읽은 것이며 close 완료 신호가 아니다. 사람 판정·검증 주체 미기재·no-AC 항목은 agent가 체크하거나 재분류하지 않고 잔여 human verification 목록을 보고 merge 전에 정지한다. 이는 구현 실패인 `blocked`가 아니라 `human verification 대기`다.

default branch 로 PR merge 가 끝난 뒤 GitHub closing reference 가 issue close 를 발동한다. 후처리 경로는 PR body 또는 GitHub closing issue reference 에서 완료 후보 issue 를 찾고, `in-progress` label 을 제거한다. Project 좌표가 설정된 repo 에서는 label 제거 뒤에 Project item `Status=Done` 이동을 best-effort 로 1회 시도한다. 보드 미러 실패는 warning 으로만 보고하고 label cleanup 성공을 실패로 바꾸지 않는다.

```bash
node scripts/github_project_lifecycle.mjs pr-merged \
  --repo OWNER/REPO \
  --pr PR_NUMBER \
  --apply
```

완료 후보는 `Closes #N`, `Fixes #N`, `Resolves #N` 또는 GitHub 가 실제 close 후보로 제공한 issue 뿐이다. `Part of #N` 은 완료 신호가 아니다. `Part of #N` 만 있는 PR 은 issue close 도, `in-progress` label 제거도 수행하지 않는다.

### IssueType / repo label drift

issue 는 IssueType repo label 을 정확히 하나 가져야 하며, closed issue 에 `in-progress` label 이 남아 있으면 drift 다. `/next-work` 후보 선정과 drift 실패 판정은 보드를 읽지 않는다. 단, Project 좌표가 설정된 경우 drift 리포트는 보드 상태를 best-effort 로 읽어 Project `IssueType`/`Status`/`Priority` 불일치를 warning 으로만 출력할 수 있다.

```bash
node scripts/github_project_lifecycle.mjs validate-issue \
  --repo OWNER/REPO \
  --issue ISSUE_NUMBER
```

예:

```text
issue #663: closed issue retains in-progress label; remove in-progress.
[dcness-project] WARN: issue #663: Project IssueType=feature, repo label=bug. Set Project IssueType and exactly one matching repo label to the same value.
```

### CI/CD harness

`/init-dcness` 는 선택적으로 `github-project-lifecycle` thin workflow 를 활성 repo 에 설치한다. 이 workflow 는 본 repo 의 composite action 을 호출해 issue label/type drift 를 PR/issue 이벤트에서 검증하고, merge 된 PR 의 완료 후보 issue 에서 `in-progress` label 을 제거한다. Project v2 미러를 쓰는 repo 만 `DCNESS_PROJECT_TOKEN` secret 과 `DCNESS_PROJECT_NUMBER` / `DCNESS_PROJECT_OWNER` variables 가 필요하다. token 이 없거나 Project API 가 실패하면 Project 미러만 warning 으로 skip 되고 issue/label lifecycle 은 GitHub token 권한으로 계속 동작한다.

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
- build-worker: [`../../agents/build-worker.md`](../../agents/build-worker.md) — task = 1 local commit
