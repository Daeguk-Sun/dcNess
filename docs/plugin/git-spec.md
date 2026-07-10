# Git Spec

> dcNess plug-in 활성화 프로젝트의 **git / PR / 이슈 등록 규칙** 단일 SSOT.
> 본 문서 = *룰 (양식·키워드)* SSOT. *흐름·메커니즘 (gh API 호출 / 멱등성 / pre-flight gate)* 은 [`issue-lifecycle.md`](issue-lifecycle.md).
> 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때는 [`terms.md`](terms.md) 를 확인한다.

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
- `feature/{desc}` 의 용도 = (1) 단발 feature, (2) **통합 브랜치** (epic 단위 long-lived feature branch + sub-PR 누적 → 마지막 한 방 main 머지). 통합 브랜치 의도는 epic issue body / stories.md 상단에 `**Base Branch:** feature/{slug}` 1줄 마커로 명시. 자세한 흐름은 [`skills/spec/SKILL.md`](../../skills/spec/SKILL.md) Step 9/10 + 본 spec 의 [PR 트레일러](#pr-트레일러-part-of-closes).
- **공통 task 묶음 (epic 단위, story 없음)**: `feature/epic{N}_common_{desc}` — `feature/{desc}` 의 epic-traceable 특수형 (module-architect 공통 호출 산출물 = `story: 공통` / `task_index: —`). 게이트는 generic feature 로 통과 (`_common` 은 `_story` 가 아니라 위 부정선행에 안 걸림). 예: `feature/epic7_common_theme_tokens`. 제목 = `[feature] {설명}`, PR 트레일러 = `Part of #<epic>` ([기본 룰](#기본-룰)).
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

## 의미 단위 커밋 분할

모든 구현 흐름은 독립 검토 가능한 의미 단위로 commit 을 쪼갠다. 적용 대상은 `/impl` 메인 직접 구현, `/impl-loop` build-worker task local commit, review finding 대응 commit, fix PR commit 을 모두 포함한다.

- 각 commit 은 hook 을 통과할 수 있는 일관된 상태여야 한다. 테스트가 깨진 중간 저장용 commit 은 금지한다.
- 변경량이 크면 테스트/결정적 helper/문서 surface/후속 cleanup 처럼 리뷰어가 단계별로 따라갈 수 있는 단위로 나눈다.
- 서로 다른 이슈, story, public surface 변경, generated deploy 경로를 한 commit 에 섞지 않는다. 불가피하면 PR body 에 묶은 이유를 적는다.
- push, PR 생성, merge, issue mutation 의 소유 경계는 각 workflow 규칙을 따른다. commit 분할 규칙이 build-worker 에게 외부 상태 변경 권한을 주지 않는다.

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
     - 단일 story → Closes #story (epic 마지막이면 Closes #epic 동봉)
     - 통합 브랜치 story sub-PR → Part of #story + main bulk-close exception
     - 통합 → main → 모든 story + epic 을 Closes
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
   # base 분기 — epic 단위 stories.md (impl task 경로의 `epic-NN-<slug>/stories.md`)
   #            상단 `**Base Branch:**` 매치 → 해당 값 (통합 브랜치 모드면 사전 `git fetch origin <값>` 후 그 ref 기반), 매치 없음 → main
2. (작업 + 커밋)
3. git push -u origin {브랜치명}
4. gh pr create --base {base} --title "..." --body "..."
   # base 분기 룰 step 1 과 동일 — 통합 브랜치 모드면 sub-PR base = 통합 브랜치
5. "$PLUGIN_ROOT/scripts/pr-finalize.sh"   # 머지 + CI 대기 + default worktree sync/cleanup 자동 (한 명령)
```

> 통합 브랜치 케이스 — stories.md 상단에 `**Base Branch:** feature/{slug}` 마커가 박혀있으면 모든 sub-PR 의 base = 그 통합 브랜치. 마지막 통합 → main 머지 PR 만 base = main + body 에 `Closes #{epic}` + `Closes #{story1...N}` 일괄 박음 ([통합 브랜치 케이스](#통합-브랜치-케이스-base-main-sub-pr-의-auto-close-한계-must)).

`pr-finalize.sh` 내부:
- **pr-finalize 호출 = 머지 확정** — 별도 최종 승인 UI 없이 아래 merge 절차를 수행한다. 호출 전 PR diff/CI/마감 acceptance/사용자 확인이 필요한 흐름은 먼저 끝낸다.
- peer claim guard 확인 (`merge-lock acquire`) — claim 없는 일반 PR 은 `mode=serial` 로 기존 흐름 유지. claim 이 있으면 repo-level mutex + 같은 story prior `task_index` 완료 evidence 를 확인한 뒤 merge 진입 ([`parallel-policy.md`](parallel-policy.md)).
- `gh pr merge --auto --merge` (auto-merge 토글)
- `gh pr checks --watch` (CI 결과 대기)
- auto-merge 완료 대기 (GitHub 백그라운드 lag)
- peer claim 이 있으면 completed 기록 (`merge-lock complete`)
- `git fetch origin <default>` 후 default branch worktree fast-forward (통합 브랜치 sub-PR 이면 origin/<base> 도 fetch)
- clean linked feature worktree 와 stale worktree admin entry 를 안전 조건 안에서 정리하고, dirty/non-fast-forward/checkout 충돌은 `preserved` 목록에 이유와 함께 남긴다.
- **통합 브랜치 sub-PR (base ≠ default branch) 자동 인지** — CI 체크 0개 정상 처리 + 머지 후 PR body close 선언 기반 issue close 보정 ([통합 브랜치 케이스](#통합-브랜치-케이스-base-main-sub-pr-의-auto-close-한계-must))
- (예정) Test Plan 종합 — 하위 commit 들의 `## Test Plan` 자동 수집·중복 제거·PR body 갱신

argument 없이 호출 시 current branch 의 open PR 자동 검출. 명시 시 `pr-finalize.sh <PR_NUMBER>`.

- **CI FAIL 시**: pr-finalize 가 exit 1 + 안내. 원인 파악 후 수정 커밋 → 재검증.
- **working tree dirty**: pr-finalize 가 사용자 확인 후 main sync skip 옵션.
- **레거시 패턴** (수동 4 명령) 도 작동 — 단 권장 X (메인 Claude 가 까먹어 main sync 누락 사례).

---

## 이슈 등록 (양식)

### 시점

메인 Claude 가 `/spec` 산출물(PRD 최종본 + stories.md + 필요한 tech-review 산출물)을 PR 머지한 뒤, 사용자 confirm trigger 로 epic + story 이슈를 연속 생성한다 ([`skills/spec/SKILL.md`](../../skills/spec/SKILL.md) Step 11). 자동화 스크립트 = [`scripts/create_epic_story_issues.sh`](../../scripts/create_epic_story_issues.sh) — stories.md parse + epic/story 이슈 생성 + sub-issue API 연결 한 명령으로 처리. 별도 호출 (구 ISSUE_SYNC) X.

### Epic 이슈

- **레이블**: `epic` + `vNN` + `epic-NN-<slug>` (3중)
  - `vNN` = stories frontmatter `milestone: vNN` 값 (예: `v01`)
  - `epic-NN-<slug>` = 에픽 풀네임 라벨 (예: `epic-11-design-review`). 미존재 시 GitHub 자동 생성
- **마일스톤**: `Epics`
- **제목**: `[epic] <epic 한 줄 요약>`
- **본문**: 목표 + 선행조건 + **완료 기준 (epic 단위 수용 기준 — 검증 가능한 조건, 사용자가 GitHub UI 에서 확인)**. 진척 체크리스트 X (stories.md 가 SSOT)
- **stories.md 기록 (상단)**:
  ```
  **GitHub Epic Issue:** [#NNN](https://github.com/{owner}/{repo}/issues/NNN)
  ```

### Story 이슈

- **레이블**: `story` + `vNN` + `epic-NN-<slug>` (3중, epic 과 `epic-NN-<slug>` 공유)
- **마일스톤**: `Story`
- **제목**: `[story] <story 한 줄 요약>`
- **본문**: `As a / I want / So that` + Story AC 목록(`AC-NNN`, Given/When/Then, 검증 주체 `[command]` 또는 `[agent-read]`). `AC-NNN` 은 프로젝트 전역 순번이며 한번 부여하면 불변이다. 사람 판정 항목은 AC 체크박스가 아닌 `사람 확인 안내`로 분리한다. 대상 화면 / 상세 동작 명세 / task 체크리스트는 넣지 않는다 — architecture.md + impl 파일 영역. Story AC 가 없는 구양식 stories.md 는 소급 변환하지 않고 그대로 허용한다.
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

task 는 별도 GitHub 이슈를 만들지 않는다. build-worker 의 local commit sha 가 완료·resume 추적 단위이고, story 가 PR 경계다. 트레일러 룰 = [PR 트레일러 (Part of / Closes)](#pr-트레일러-part-of-closes).

---

## PR 트레일러 (Part of / Closes)

### 기본 룰

- **task**: local commit 이므로 PR trailer 없음. `task_index` 는 story 내부 설계 순서이며 PR close 판정 입력이 아니다.
- **단일 story run**: base=`main` story PR 1개. `Closes #story-issue`; 이 story가 epic 마지막이면 `Closes #epic-issue`도 동봉한다.
- **다중 story/epic run**: story마다 통합 브랜치 대상 sub-PR 1개. `Part of #story-issue`와 `Document-Exception-PR-Close: 통합 브랜치 story sub-PR — main 머지 시 일괄 close`를 넣는다.
- **통합→main PR**: 대상 story 전부와 epic을 `Closes`로 일괄 선언한다.
- **공통 task 묶음**: 별도 story issue가 없으므로 `Part of #epic-issue`를 사용한다.

> **반드시 PR body 에 박는다 (commit message 아님)** — 본 프로젝트는 regular merge 채택 ([Git 절차](#git-절차), squash 금지). regular merge 시 GitHub auto-close 는 *PR body* 또는 *squash merge commit message* 만 인식. commit message 안 `Closes #N` 은 머지 commit 에 들어가도 auto-close 발동 X. 본 룰 mechanical 강제 = [`scripts/check_pr_body.mjs`](../../scripts/check_pr_body.mjs) + `.github/workflows/pr-body-validation.yml` (`/init-dcness` 선택형 workflow 로 사용자 repo 배포).
>
> **예외**: issue 없는 infra-only / follow-up split PR 등은 PR body 에 `Document-Exception-PR-Close: <사유>` line 박으면 게이트 우회. `:` + 사유 1단어 이상 동일 line 강제.

### 통합 브랜치 케이스 — base ≠ main sub-PR 의 auto-close 한계 (MUST)

stories.md 상단에 `**Base Branch:** feature/<slug>` 마커 박힌 epic (= 통합 브랜치 모드, [`skills/spec/SKILL.md`](../../skills/spec/SKILL.md) Step 9/10) 의 story sub-PR 은 *base = `feature/<slug>`* 로 머지된다. **GitHub auto-close 는 base = default branch (main) 인 PR 만 인식**한다.

흐름:

1. **각 story sub-PR (base = `feature/<slug>`)** — `Part of #<story>`만 사용해 story를 조기 close하지 않는다. sub-PR은 메인이 통합 브랜치로 머지하고, 다음 story branch는 **갱신된 통합 브랜치에서 재분기**한다.
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

### 적용 절차 — story/base 판정

1. impl 파일 frontmatter의 `story`로 PR grouping key를 찾는다. 숫자 story인데 `task_index`가 `i/total` 형식이 아니면 설계 metadata drift로 중지하지만, `i == total` 여부는 PR 경계를 결정하지 않는다.
2. stories.md의 `**Base Branch:**`가 없으면 단일 story base=`main`; 있으면 story sub-PR base=통합 브랜치다.
3. base=`main`이면 `Closes #story`, 통합 브랜치면 `Part of #story` + bulk-close exception을 사용한다. 공통 task 묶음은 `Part of #epic`이다.
4. 통합→main PR은 대상 story issue 목록과 epic issue를 모두 `Closes`로 적는다.

**한 명령 구현 = [`scripts/pr-trailer.sh`](../../scripts/pr-trailer.sh)** — `"$PLUGIN_ROOT/scripts/pr-trailer.sh" <story의 impl파일>` 이 story/base 트레일러 블록을 stdout 으로 출력한다 (`--base` 모드는 stories.md marker 기반 PR base 출력). 어떤 task 파일을 넘겨도 같은 story PR 트레일러가 나오며 `task-index` trailer는 출력하지 않는다.

---

## 이슈 완료 규칙

### Story 완료

- **구현 완료 조건**: story 의 모든 impl task가 local commit으로 `completed`. PR 생성·머지는 runner state 수명에 영향을 주지 않는다.
- **단일 story close**: base=`main` story PR body `Closes #story-issue` → merge 시 GitHub 자동 close.
- **통합 브랜치 close**: story sub-PR은 `Part of`로 누적하고 마지막 통합→main PR에서 story 전부를 일괄 close.
- 메인 Claude 사후 작업 없음 — stories.md `[x]` 체크 룰 폐기 (2026-05-12, 옛 Step 4.5 동기화 step 폐기, 상세는 git history)

### Epic 완료

- **조건**: epic 의 모든 story task commit 완료 + 통합 review/acceptance PASS
- **단일 story close 시점**: story→main PR 생성 *직전* 1회 사전 체크:
  ```bash
  gh issue list --label epic-NN-<slug> --milestone Story --state open
  ```
  → 이 story merge 시 마지막 story close 예정이면, PR body 에 `Closes #epic-issue` 도 동봉
- **다중 story close 시점**: 마지막 통합→main PR body에 모든 story + epic close를 동봉
- 메인 Claude 사후 작업 없음 — `backlog.md` 자체 폐기 (2026-05-12, GitHub epic issue close 가 SSOT)
- 별도 변경 없는 wrap-up PR은 만들지 않는다. 통합→main PR은 story sub-PR 누적 결과를 main에 전달하는 merge PR이다.

### API 직접 close 절대금지

`mcp__github__update_issue state:closed` 호출 금지 (epic / story 모두). 반드시 PR body `Closes #N` — [기본 룰](#기본-룰) 참조 (regular merge auto-close 인식 한계).

> **예외 (유일)**: 통합 브랜치 sub-PR 머지 시 `pr-finalize.sh` 의 close 보정. base ≠ default branch 라 GitHub auto-close 가 구조적으로 발동 불가한 케이스에서, *PR body 의 close 선언을 근거로* 스크립트가 기계 보정하는 것이다 — 선언 없는 issue 를 임의로 닫는 직접 close 가 아니므로 본 금지의 취지(close 근거를 PR body 선언으로 일원화)를 유지한다.

---

## 참조

- lifecycle 흐름·메커니즘 (sub-issue API / 멱등성 / 마일스톤 조회 / pre-flight gate): [`issue-lifecycle.md`](issue-lifecycle.md)
- 분기 규칙 / 핸드오프: 각 loop skill 의 `<skill>-routing.md` (예: [`../../skills/impl-loop/impl-loop-routing.md`](../../skills/impl-loop/impl-loop-routing.md))
- loop 진입 spec: 각 skill 본문 `skills/<skill>/SKILL.md` 의 `## Loop` contract + `<skill>-routing.md`. 공통 실행 절차 = [`loop-procedure.md`](loop-procedure.md#진입-모델)
- spec skill (메인 직접): [`../../skills/spec/SKILL.md`](../../skills/spec/SKILL.md)
- system-architect (모듈 토폴로지 + 공통 task 목록 SSOT): [`../../agents/system-architect.md`](../../agents/system-architect.md)
- module-architect (Story 안 task 분할 + impl 파일 N 개 산출 SSOT): [`../../agents/module-architect.md`](../../agents/module-architect.md)
- module-architect (impl 본문 detail per task): [`../../agents/module-architect.md`](../../agents/module-architect.md)
- build-worker: [`../../docs/plugin/agents/build-worker/build-worker-agent.md`](../../docs/plugin/agents/build-worker/build-worker-agent.md#권한-경계) task local commit
