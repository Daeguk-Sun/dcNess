# Git Spec

> dcNess plug-in 활성화 프로젝트의 **git / PR / 이슈 등록 규칙** 단일 SSOT.
> 본 문서 = *룰 (양식·키워드)* SSOT. *흐름·메커니즘 (gh API 호출 / 멱등성 / pre-flight gate)* 은 [`issue-lifecycle.md`](issue-lifecycle.md).

## 브랜치

| 타입 | 패턴 | 예시 |
|---|---|---|
| 스토리 작업 impl | `feature/epic{N}_story{N}_{desc}` | `feature/epic3_story2_create_mcp_server` |
| 자유 feature / 통합 브랜치 | `feature/{desc}` | `feature/local_dsp`, `feature/integration_branch_pattern` |
| 버그픽스 | `fix/issue{N}_{desc}` | `fix/issue32_duplicate_touch` |
| 버그픽스 (복수 이슈) | `fix/issue{N}_{M}_{desc}` | `fix/issue32_45_duplicate_touch` |
| 문서 | `docs/{desc}` | `docs/update_api_spec`, `docs/sync-readme` |

- `{desc}` 기본 제약 (모든 패턴 공통): **소문자 시작 + `[a-z0-9_-]` + 최소 3자**.
  - `_` 또는 `-` 구분자 택1 권장 (한 브랜치 안에서 일관). 둘 다 통과.
  - 공백·특수문자·대문자 금지.
  - **`feature/{desc}` 의 desc 는 `epic{N}_story` 로 시작 불가** — 그 형태는 strict 스토리 패턴(`feature/epic{N}_story{N}_{desc}`, desc ≥3자·story 숫자)만 통과한다. malformed 스토리 브랜치(`feature/epic7_story2_ui` 처럼 desc<3자 / story 비숫자)가 generic 으로 새는 것을 [`check_git_naming.mjs`](../../scripts/check_git_naming.mjs) 부정선행이 차단.
- `feature/{desc}` 의 용도 = (1) 단발 feature, (2) **통합 브랜치** (epic 단위 long-lived feature branch + sub-PR 누적 → 마지막 한 방 main 머지). 통합 브랜치 의도는 epic issue body / stories.md 상단에 `**Base Branch:** feature/{slug}` 1줄 마커로 명시. 자세한 흐름은 [`skills/product-plan/SKILL.md`](../../skills/product-plan/SKILL.md) Step 6.5/7 + 본 spec 의 [PR 트레일러](#pr-트레일러-part-of-closes).
- **공통 task (epic 단위, story 없음)**: `feature/epic{N}_common_{desc}` — `feature/{desc}` 의 epic-traceable 특수형 (module-architect 공통 호출 산출물 = `story: 공통` / `task_index: —`). 게이트는 generic feature 로 통과 (`_common` 은 `_story` 가 아니라 위 부정선행에 안 걸림). 예: `feature/epic7_common_theme_tokens`. 제목 = `[feature] {설명}`, 트레일러 = `Part of #<epic>` (부모 = epic 단일 룰, task-index trailer omit, [기본 룰](#기본-룰)).
- main 직접 push 금지. 항상 branch → PR → merge.
- 브랜치는 merge 후에도 삭제하지 않는다.

## 커밋 제목

| 타입 | 형식 | 예시 |
|---|---|---|
| 스토리 작업 impl | `[epic{N}][story{N}] {설명}` | `[epic4][story3] mcp 세팅` |
| epic 단위 (통합 → main 머지) | `[epic{N}] {설명}` | `[epic19] Local DSP 통합 머지` |
| 자유 feature | `[feature] {설명}` | `[feature] 통합 브랜치 패턴 지원` |
| 버그픽스 | `[issue-{N}] {설명}` | `[issue-32] 중복 터치 수정` |
| 문서 | `[docs] {설명}` | `[docs] API 스펙 업데이트` |

- `{설명}`: 명사형 또는 동사원형으로 간결하게 한 줄.

## 커밋 메시지 본문

빈 섹션은 `-` 로 채운다.

```
## 관련 이슈 번호
<!-- 본 commit 이 속한 PR 이 가리키는 이슈. 단순 정보 (auto-close 발동 X — 기본 룰 참조) -->
#NNN

## 작업내용
<!-- 변경된 파일 목록 + 수정사항 -->
-

## Test Plan
- [ ] 관련 테스트 추가/갱신/전체 통과
- [ ] 회귀 검증
```

> 상세 컨텍스트 (배경 / 원인 / 결정 근거) 는 PR body 가 SSOT — [PR 본문](#pr-본문) 참조. 1 commit = 1 PR 빈도가 높은 dcness 패턴 정합 — 중복 작성 방지.

## PR 제목

| 타입 | 형식 | 예시 |
|---|---|---|
| 스토리 작업 impl | `[epic{N}][story{N}] {설명}` | `[epic4][story3] mcp서버를 생성합니다.` |
| epic 단위 (통합 → main 머지) | `[epic{N}] {설명}` | `[epic19] Local DSP 통합 머지` |
| 자유 feature | `[feature] {설명}` | `[feature] 통합 브랜치 패턴 지원` |
| 버그픽스 | `[issue-{N}] {설명}` | `[issue-32] 중복터치 개선` |
| 문서 | `[docs] {설명}` | `[docs] API 스펙 업데이트` |

## PR 본문

빈 섹션은 `-` 로 채운다. multi-commit PR 시 — 양식을 commit 별로 반복하거나, `## 작업내용` 안에 commit 별 bullet 으로 정리.

```markdown
## 관련 이슈 번호
<!-- 트레일러 룰 (기본 룰):
     - 중간 task → Part of #N
     - 마지막 task → Closes #N
     - epic 마지막 task → Closes #story + Closes #epic
     - issue 없는 infra/follow-up → Document-Exception-PR-Close: <사유>
     under-link 보다 over-close 사고가 더 큼 — default 는 안전한 Part of -->
Part of #N

## 배경 및 문제
<!-- WHY: 왜 이 PR 이 필요한가. 가능하면 히스토리 포함 -->
-

## 원인 (해당 시)
<!-- 버그픽스 / RCA 케이스만 작성. 단순 feature 추가는 생략 또는 `-` -->
-

## 작업내용
<!-- WHAT: 하위 commit 들 제목·내용 종합 -->
-

## 결정 근거
<!-- 검토한 대안, 채택 이유. 단순 변경이면 `-` -->
-

## Test Plan
<!-- 하위 commit Test Plan 종합. 머지 직전 메인이 종합 갱신 -->
- [ ] 관련 테스트 추가/갱신/전체 통과
- [ ] 회귀 검증

## 참고
-
```

## Git 절차

```
1. git checkout -b {브랜치명} {base}
   # base 분기 — docs/stories.md 상단 `**Base Branch:**` 매치 → 해당 값, 매치 없음 → main
2. (작업 + 커밋)
3. git push -u origin {브랜치명}
4. gh pr create --base {base} --title "..." --body "..."
   # base 분기 룰 step 1 과 동일 — 통합 브랜치 모드면 sub-PR base = 통합 브랜치
5. "$PLUGIN_ROOT/scripts/pr-finalize.sh"   # 머지 + CI 대기 + main sync 자동 (한 명령)
```

> 통합 브랜치 케이스 — stories.md 상단에 `**Base Branch:** feature/{slug}` 마커가 박혀있으면 모든 sub-PR 의 base = 그 통합 브랜치. 마지막 통합 → main 머지 PR 만 base = main + body 에 `Closes #{epic}` + `Closes #{story1...N}` 일괄 박음 ([통합 브랜치 케이스](#통합-브랜치-케이스-base-main-sub-pr-의-auto-close-한계-must)).

`pr-finalize.sh` 내부:
- `gh pr merge --auto --merge` (auto-merge 토글)
- `gh pr checks --watch` (CI 결과 대기)
- auto-merge 완료 대기 (GitHub 백그라운드 lag)
- `git checkout main && git pull` (자동 sync)
- (예정) Test Plan 종합 — 하위 commit 들의 `## Test Plan` 자동 수집·중복 제거·PR body 갱신

argument 없이 호출 시 current branch 의 open PR 자동 검출. 명시 시 `pr-finalize.sh <PR_NUMBER>`.

- **CI FAIL 시**: pr-finalize 가 exit 1 + 안내. 원인 파악 후 수정 커밋 → 재검증.
- **working tree dirty**: pr-finalize 가 사용자 확인 후 main sync skip 옵션.
- **레거시 패턴** (수동 4 명령) 도 작동 — 단 권장 X (메인 Claude 가 까먹어 main sync 누락 사례).

---

## 이슈 등록 (양식)

### 시점

메인 Claude 가 PRD/stories.md/tech-review.md 스켈레톤 작성 + 사용자 1 차 OK + PR 머지 완료 후 *사용자 confirm trigger* 로 epic + story 이슈 *연속* 생성 ([`skills/product-plan/SKILL.md`](../../skills/product-plan/SKILL.md) Step 8). 자동화 스크립트 = [`scripts/create_epic_story_issues.sh`](../../scripts/create_epic_story_issues.sh) — stories.md parse + epic/story 이슈 생성 + sub-issue API 연결 한 명령으로 처리. 별도 호출 (구 ISSUE_SYNC) X.

### Epic 이슈

- **레이블**: `epic` + `v0N` + `epic-NN-<slug>` (3중)
  - `v0N` = PRD 마일스톤 버전, 소문자 2자리 (예: `v01`)
  - `epic-NN-<slug>` = 에픽 풀네임 라벨 (예: `epic-11-monkey-design-review`). 미존재 시 GitHub 자동 생성
- **마일스톤**: `Epics`
- **제목**: `[epic] <epic 한 줄 요약>`
- **본문**: 목표 + 선행조건 + **완료 기준 (epic 단위 수용 기준 — 검증 가능한 조건, 사용자가 GitHub UI 에서 확인)**. 진척 체크리스트 X (stories.md 가 SSOT)
- **stories.md 기록 (상단)**:
  ```
  **GitHub Epic Issue:** [#NNN](https://github.com/{owner}/{repo}/issues/NNN)
  ```

### Story 이슈

- **레이블**: `story` + `v0N` + `epic-NN-<slug>` (3중, epic 과 `epic-NN-<slug>` 공유)
- **마일스톤**: `Story`
- **제목**: `[story] <story 한 줄 요약>`
- **본문**: `As a / I want / So that` 만 (user story). 수용 기준 (Story 단위) / 대상 화면 / 동작 명세 박지 않음 — architecture.md + impl 파일 영역. 태스크 체크리스트 X (stories.md 가 SSOT)
- **순서**: epic 생성 완료 후 story 1, 2, … 순차
- **stories.md 기록**:
  - 각 story 헤더 직하: `**GitHub Issue:** [#MMM](url)`
  - 파일 하단 `## 관련 이슈` 테이블:
    ```
    | 스토리 | GitHub Issue |
    |---|---|
    | Epic | [#NNN](url) |
    | Story 1 | [#MMM](url) |
    ```

> sub-issue API 연결·멱등성 메커니즘 = [`issue-lifecycle.md`](issue-lifecycle.md#sub-issue-연결-epic-story-gh-api-메커니즘).

### Task — GitHub 이슈 없음

task 는 별도 GitHub 이슈 만들지 않음 — PR 자체가 추적 단위. 트레일러 룰 = [PR 트레일러 (Part of / Closes)](#pr-트레일러-part-of-closes).

---

## PR 트레일러 (Part of / Closes)

### 기본 룰

- **중간 task PR**: `Part of #story-issue` (Development 섹션 자동 연결 X — 언급만)
- **story 마지막 task PR**: `Closes #story-issue`
- **epic 마지막 story 마지막 task PR**: `Closes #story-issue` + `Closes #epic-issue` (한 줄당 1개 또는 comma 분리)
- **`task-index: <i>/<total>` trailer**: impl 파일 frontmatter `task_index` 값 그대로 1줄 박는다 (build-worker 가 PR 본문 초안 작성 시점에). CI 게이트 [`scripts/check_pr_body.mjs`](../../scripts/check_pr_body.mjs) 가 본 trailer 로 "Story 마지막 task PR 인가" 식별 → `i == total` 이면 `Closes`/`Fixes`/`Resolves` 1+ 강제 (`Part of` 단독 FAIL). 공통 task (`task_index: —`) 는 trailer omit (게이트 fallback path 통과).

> **반드시 PR body 에 박는다 (commit message 아님)** — 본 프로젝트는 regular merge 채택 ([Git 절차](#git-절차), squash 금지). regular merge 시 GitHub auto-close 는 *PR body* 또는 *squash merge commit message* 만 인식. commit message 안 `Closes #N` 은 머지 commit 에 들어가도 auto-close 발동 X. 본 룰 mechanical 강제 = [`scripts/check_pr_body.mjs`](../../scripts/check_pr_body.mjs) + `.github/workflows/pr-body-validation.yml` (init-dcness Step 2.6 으로 사용자 repo 배포).
>
> **예외**: issue 없는 infra-only / follow-up split PR 등은 PR body 에 `Document-Exception-PR-Close: <사유>` line 박으면 게이트 우회. `:` + 사유 1단어 이상 동일 line 강제.

### 통합 브랜치 케이스 — base ≠ main sub-PR 의 auto-close 한계 (MUST)

stories.md 상단에 `**Base Branch:** feature/<slug>` 마커 박힌 epic (= 통합 브랜치 모드, [`skills/product-plan/SKILL.md`](../../skills/product-plan/SKILL.md) Step 6.5/7) 의 sub-PR 은 *base = `feature/<slug>`* 로 머지된다. **GitHub auto-close 는 base = default branch (main) 인 PR 만 인식** — base ≠ main sub-PR 의 PR body `Closes #N` 은 머지 시 발동 X.

흐름:

1. **각 sub-PR (base = `feature/<slug>`)** — PR body 에 평소대로 `Part of #<story>` / `Closes #<story>` 박되 머지 시 *발동 안 됨* 전제. `Document-Exception-PR-Close: 통합 브랜치 sub-PR — main 머지 시 일괄 close` 박아 `check_pr_body.mjs` 게이트 우회 가능 (자유 선택).
2. **마지막 통합 → main 머지 PR (base = main)** — PR body 에 **모든 story + epic 을 일괄 close**:
   ```
   Closes #<story1>
   Closes #<story2>
   ...
   Closes #<storyN>
   Closes #<epic>
   ```
   main 머지 시 GitHub 가 일괄 처리. *bulk close = epic atomic transaction 의도와 정합* — main 입장에선 epic 전체가 한 시점에 들어옴.

근거: GitHub 의 [linking-a-pull-request-to-an-issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) 문서 — *"The pull request must be on the default branch."* 통합 브랜치 base sub-PR 은 미충족.

> 별도 자동화 (sub-issue API 기반 base 무관 close 정책) 는 *추후* 자매 이슈에서 다룸. 본 단락은 *최소 명문화* — 통합 브랜치 모드 진입 사용자가 *마지막 머지 PR 에 bulk close* 박는 패턴만 인지하면 충분.

### 적용 절차 — PR 생성 직전 사전 체크 (impl 파일 frontmatter 기반)

판정 입력 = **impl 파일 frontmatter `task_index: <i>/<total>` + `story: <N>`**. module-architect × K 시점 (architect-loop) 에 박힘. `task_index` 의미 = 그 Story 안 task 의 순번 / 그 Story 의 총 task 수 (옛 의미: 옛 `## impl 목차` 표 행 위치 → 폐기, 이슈 [#511](https://github.com/alruminum/dcNess/issues/511)). 공통 task 는 `task_index: —`. stories.md `[ ]` 카운트 룰 폐기 (2026-05-12) — 새 stories.md 양식엔 task `[ ]` 자체 없음 (user story 만, [`skills/product-plan/SKILL.md`](../../skills/product-plan/SKILL.md#storiesmd-산출물-단순화-user-story-만) stories.md 산출물 절).

1. **task 파일 frontmatter read** — `task_index: 3/3` + `story: 1`
2. **본 task 가 Story 마지막인지 판정** — `i == total` 이면 마지막
3. **본 Story 가 epic 마지막인지 판정** — gh API 1 회: `gh issue list --label "epic-NN-<slug>" --milestone Story --state open --json number --jq 'length'` 가 1 (= 본 Story 만 OPEN) 이면 본 task 머지 시 epic 도 close 예정
4. **분기**:
   - i == total + epic 마지막 story → `Closes #${STORY_ISSUE}` + `Closes #${EPIC_ISSUE}`
   - i == total + epic 중간 story → `Closes #${STORY_ISSUE}`
   - i < total → `Part of #${STORY_ISSUE}`

bash one-liner ([`loop-procedure.md`](loop-procedure.md#impl-task-loop-commit-구조) commit3 단계 안):

```bash
TASK_FILE="docs/milestones/.../impl/NN-*.md"
TASK_INDEX=$(awk '/^task_index:/ {gsub(/[",]/,""); print $2; exit}' "$TASK_FILE")
I="${TASK_INDEX%/*}"
TOTAL="${TASK_INDEX#*/}"
```

### Development 섹션 역방향 업데이트

`Closes #story-issue` PR 생성 시 필수. `Closes #story-issue` PR 생성과 동시에, 이전 `Part of #story-issue` PR 들을 찾아 body 앞에 `Fixes #story-issue` 를 추가한다. 이미 머지된 PR body 업데이트는 issue close 를 재발동하지 않으며 Development 섹션에 소급 반영된다.

```bash
ISSUE=<story-issue-number>
REPO=<owner>/<repo>
gh search prs --repo "$REPO" "Part of #$ISSUE" --json number --jq '.[].number' \
  | while read num; do
      cur=$(gh pr view "$num" --repo "$REPO" --json body --jq '.body')
      gh pr edit "$num" --repo "$REPO" --body "Fixes #$ISSUE
$cur"
    done
```

---

## 이슈 완료 규칙

### Story 완료

- **조건**: story 의 모든 impl task PR merge
- **Close**: 마지막 task PR body `Closes #story-issue` → GitHub 자동 close (regular merge auto-close)
- 메인 Claude 사후 작업 없음 — stories.md `[x]` 체크 룰 폐기 (2026-05-12, [`loop-procedure.md`](loop-procedure.md#step-45-폐기-2026-05-12))

### Epic 완료

- **조건**: epic 의 모든 story closed
- **Close 시점**: 마지막 story 의 마지막 task PR — 메인이 PR 생성 *직전* 1회 사전 체크:
  ```bash
  gh issue list --label epic-NN-<slug> --milestone Story --state open
  ```
  → 이 task merge 시 마지막 story close 예정이면, PR body 에 `Closes #epic-issue` 도 동봉
- 메인 Claude 사후 작업 없음 — `backlog.md` 자체 폐기 (2026-05-12, GitHub epic issue close 가 SSOT)
- 별도 wrap-up PR 만들지 않음

### API 직접 close 절대금지

`mcp__github__update_issue state:closed` 호출 금지 (epic / story 모두). 반드시 PR body `Closes #N` — [기본 룰](#기본-룰) 참조 (regular merge auto-close 인식 한계).

---

## 참조

- lifecycle 흐름·메커니즘 (sub-issue API / 멱등성 / 마일스톤 조회 / pre-flight gate): [`issue-lifecycle.md`](issue-lifecycle.md)
- 라우팅 / 핸드오프: 각 loop skill 의 `<skill>-routing.md` (예: [`../../skills/impl-loop/impl-loop-routing.md`](../../skills/impl-loop/impl-loop-routing.md))
- loop 인덱스: [`loop-procedure.md`](loop-procedure.md#한눈-인덱스-loop-진입-ssot) (각 loop 풀스펙 = 해당 skill 본문 `skills/<skill>/SKILL.md`)
- product-plan skill (메인 직접): [`../../skills/product-plan/SKILL.md`](../../skills/product-plan/SKILL.md)
- system-architect (모듈 토폴로지 + 공통 task 목록 SSOT): [`../../agents/system-architect.md`](../../agents/system-architect.md)
- module-architect (Story 안 task 분할 + impl 파일 N 개 산출 SSOT): [`../../agents/module-architect.md`](../../agents/module-architect.md)
- module-architect (impl 본문 detail per task): [`../../agents/module-architect.md`](../../agents/module-architect.md)
- engineer: [`../../agents/engineer.md`](../../agents/engineer.md#1-task-1-pr-engineer-는-src-만) 1 task = 1 PR
