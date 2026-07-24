# Git Spec

> dcNess plug-in 활성화 프로젝트의 **git / PR / 이슈 등록 규칙** 단일 SSOT.
> 본 문서 = *룰 (양식·키워드)* SSOT. *흐름·메커니즘 (gh API 호출 / 멱등성 / pre-flight gate)* 은 [`issue-lifecycle.md`](issue-lifecycle.md).
> 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때는 [`terms.md`](terms.md) 를 확인한다.

## 브랜치

| 타입 | 패턴 | 예시 |
|---|---|---|
| 스토리 작업 impl | `feature/epic{N}_story{N}_{desc}` | `feature/epic3_story2_create_mcp_server` |
| 자유 feature | `feature/{desc}` | `feature/local_dsp`, `feature/story_stack_review` |
| 버그픽스 | `fix/issue{N}_{desc}` | `fix/issue32_duplicate_touch` |
| 버그픽스 (복수 이슈) | `fix/issue{N}_{M}_{desc}` | `fix/issue32_45_duplicate_touch` |
| 문서 | `docs/{desc}` | `docs/update_api_spec`, `docs/sync-readme` |

- `{desc}` 기본 제약 (모든 패턴 공통): **소문자 시작 + `[a-z0-9_-]` + 최소 3자**.
  - `_` 또는 `-` 구분자 택1 권장 (한 브랜치 안에서 일관). 둘 다 통과.
  - 공백·특수문자·대문자 금지.
  - **`feature/{desc}` 의 desc 는 `epic{N}_story` 로 시작 불가** — 그 형태는 strict 스토리 패턴(`feature/epic{N}_story{N}_{desc}`, desc ≥3자·story 숫자)만 통과한다. malformed 스토리 브랜치(`feature/epic7_story2_ui` 처럼 desc<3자 / story 비숫자)가 generic 으로 새는 것을 [`check_git_naming.mjs`](../../scripts/check_git_naming.mjs) 부정선행이 차단.
- `feature/{desc}` 는 story가 없는 단발 feature에 사용한다. `/impl-loop` 다중 story는 long-lived 누적 브랜치를 만들지 않고 아래 [story 브랜치 스택](#story-브랜치-스택) 규칙을 따른다.
- **공통 task 묶음 (epic 단위, story 없음)**: `feature/epic{N}_common_{desc}` — `feature/{desc}` 의 epic-traceable 특수형 (module-architect 공통 호출 산출물 = `story: 공통` / `task_index: —`). 게이트는 generic feature 로 통과 (`_common` 은 `_story` 가 아니라 위 부정선행에 안 걸림). 예: `feature/epic7_common_theme_tokens`. 제목 = `[feature] {설명}`, PR 트레일러 = `Part of #<epic>` ([기본 룰](#기본-룰)).
- main 직접 push 금지. 항상 branch → PR → merge.
- 브랜치는 merge 후에도 삭제하지 않는다.

## 커밋 제목

| 타입 | 형식 | 예시 |
|---|---|---|
| 스토리 작업 impl | `[epic{N}][story{N}] {설명}` | `[epic4][story3] mcp 세팅` |
| epic 단위 | `[epic{N}] {설명}` | `[epic19] Local DSP 마감 보정` |
| 자유 feature | `[feature] {설명}` | `[feature] story stack 검토 지원` |
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

모든 구현 흐름은 독립 검토 가능한 의미 단위로 commit 을 쪼갠다. 적용 대상은 `/impl` main-direct·headless 구현, `/impl-loop` build-worker task local commit, review finding 대응 commit, fix PR commit 을 모두 포함한다.

- 각 commit 은 hook 을 통과할 수 있는 일관된 상태여야 한다. 테스트가 깨진 중간 저장용 commit 은 금지한다.
- 변경량이 크면 테스트/결정적 helper/문서 surface/후속 cleanup 처럼 리뷰어가 단계별로 따라갈 수 있는 단위로 나눈다.
- 서로 다른 이슈, story, public surface 변경, generated deploy 경로를 한 commit 에 섞지 않는다. 불가피하면 PR body 에 묶은 이유를 적는다.
- push, PR 생성, merge, issue mutation 의 소유 경계는 각 workflow 규칙을 따른다. commit 분할 규칙이 build-worker 에게 외부 상태 변경 권한을 주지 않는다.

## PR 제목

| 타입 | 형식 | 예시 |
|---|---|---|
| 스토리 작업 impl | `[epic{N}][story{N}] {설명}` | `[epic4][story3] mcp서버를 생성합니다.` |
| epic 단위 | `[epic{N}] {설명}` | `[epic19] Local DSP 마감 보정` |
| 자유 feature | `[feature] {설명}` | `[feature] story stack 검토 지원` |
| 버그픽스 | `[issue-{N}] {설명}` | `[issue-32] 중복터치 개선` |
| 문서 | `[docs] {설명}` | `[docs] API 스펙 업데이트` |

## PR 본문

빈 섹션은 `-` 로 채운다. multi-commit PR 시 — 양식을 commit 별로 반복하거나, `## 작업내용` 안에 commit 별 bullet 으로 정리.

```markdown
## 관련 이슈 번호
<!-- 트레일러 룰 (기본 룰):
     - 단일 story → Closes #story (epic 마지막이면 Closes #epic 동봉)
     - story 브랜치 스택 PR → 생성 시 직전 story branch base, merge 시 main 리타겟 후 Closes #story
     - QA PR → tracked 보정이 있으면 Part of #epic, epic close를 발동하는 마지막 PR이면 Closes #epic
     - issue 없는 infra/follow-up 또는 journey_deferred production-only → Document-Exception-PR-Close: <사유>
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
   # 단일 story/자유 작업 base = main
   # 다중 story/epic base = 첫 story는 main, 이후 story는 직전 story branch
2. (작업 + 커밋)
3. git push -u origin {브랜치명}
4. gh pr create --base {base} --title "..." --body "..."
   # 다중 story PR은 생성 시 stack base를 유지해 순수 story diff를 보인다.
   # /impl-loop는 final tip 수렴·review·acceptance·AC audit·tree-preserving consolidate 뒤 clean branch를 push하고 이 단계를 처음 수행한다.
5. 필요한 review/acceptance/AC close audit 완료 후 host repo merge policy를 따른다.
   # /impl-loop 다중 story stack은 loop 자동 merge 없이 사용자 merge gate를 기다린다.
6. 다중 story stack에서 merge 승인이 열린 PR만 base=main 리타겟 + main rebase 후 "$PLUGIN_ROOT/scripts/pr-finalize.sh"
```

### story 브랜치 스택

다중 story/epic의 구현 topology는 `story1(base=main) → story2(base=story1) → …` 브랜치 스택이다.

- **PR 생성 시**: `/impl-loop`는 먼저 첫 story branch를 `main`, 이후 story branch를 직전 story 브랜치 base로 쌓는다. final tip 수렴·review·acceptance·AC audit·tree-preserving consolidate 뒤 첫 story PR은 `main`, 이후 story PR은 봉인한 직전 story 브랜치를 base로 clean cut한다. 선행 story commit이 비교 기준에 포함되므로 각 PR diff는 해당 story만 보인다.
- **다음 story 시작 시**: 직전 story tip/base만 봉인하고 PR을 만들거나 merge하지 않은 채 직전 story 브랜치 tip에서 새 story 브랜치를 만든다. loop의 자동 merge는 0회이며 사용자가 유일한 merge gate다.
- **PR 머지 시점**: 사용자가 순서대로 merge를 승인하면 해당 PR을 base=`main` 으로 리타겟하고 최신 `main` 위로 리베이스한다. regular merge가 보존한 선행 story SHA는 리베이스에서 중복 적용되지 않는다.
- **downstream restack**: main rebase로 현재 story tip이 바뀌면 아직 열린 downstream branch를 새 tip 위에 순서대로 restack하고 `--force-with-lease`로 갱신한다. 충돌 해결이 최종 tree를 바꾸면 통합 review/acceptance를 다시 수행한다.
- **QA PR**: story가 2개 이상이고 final tip 수렴·검수 중 tracked cross-cutting fix 또는 flow/manifest 보정이 있으면 마지막 story 브랜치에서 QA 브랜치를 만든다. acceptance·AC audit·consolidate 뒤 story PR과 함께 cut하며, tracked 변경이 없으면 빈 PR을 만들지 않는다.
- **merge 순서**: story1 → story2 → … → QA PR(있으면). 각 PR의 close/acceptance/AC audit은 PR cut 전에 끝나며, main 리타겟·리베이스 뒤 tree identity가 그대로인지 확인한다. tree가 바뀌면 stale 규칙에 따라 수렴·review·acceptance·audit을 다시 수행한다.

`pr-finalize.sh` 내부:
- **pr-finalize 호출 = 머지 확정** — 별도 최종 승인 UI 없이 아래 merge 절차를 수행한다. 호출 전 PR diff/CI/마감 acceptance/사용자 확인이 필요한 흐름은 먼저 끝낸다.
- peer claim guard 확인 (`merge-lock acquire`) — claim 없는 일반 PR 은 `mode=serial` 로 기존 흐름 유지. claim 이 있으면 repo-level mutex + 같은 story prior `task_index` 완료 evidence 를 확인한 뒤 merge 진입 ([`parallel-policy.md`](parallel-policy.md)).
- `gh pr merge --auto --merge` (auto-merge 토글)
- `gh pr checks --watch` (CI 결과 대기)
- auto-merge 완료 대기 (GitHub 백그라운드 lag)
- peer claim 이 있으면 completed 기록 (`merge-lock complete`)
- `git fetch origin <default>` 후 default branch worktree fast-forward
- clean linked feature worktree 와 stale worktree admin entry 를 안전 조건 안에서 정리하고, dirty/non-fast-forward/checkout 충돌은 `preserved` 목록에 이유와 함께 남긴다.
- **base ≠ default branch PR 거부** — `pr-finalize.sh`는 merge 전에 fail-fast한다. `/impl-loop` story PR은 사용자 승인 뒤 main으로 리타겟·리베이스해야만 helper를 호출할 수 있다.
- (예정) Test Plan 종합 — 하위 commit 들의 `## Test Plan` 자동 수집·중복 제거·PR body 갱신

argument 없이 호출 시 current branch 의 open PR 자동 검출. 명시 시 `pr-finalize.sh <PR_NUMBER>`.

- **CI FAIL 시**: pr-finalize 가 exit 1 + 안내. 원인 파악 후 수정 커밋 → 재검증.
- **working tree dirty**: pr-finalize 가 사용자 확인 후 main sync skip 옵션.
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
- **본문**: 목표 + 선행조건 + **완료 기준** (epic 단위 수용 기준, `[command]`/`[agent-read]`). stories.md 가 계약 SSOT 이고, 생성 스크립트가 GitHub issue body 에서만 close 감사용 체크리스트로 materialize 한다.
- **stories.md 기록 (상단)**:
  ```
  **GitHub Epic Issue:** [#NNN](https://github.com/{owner}/{repo}/issues/NNN)
  ```

### Story 이슈

- **레이블**: `story` + `vNN` + `epic-NN-<slug>` (3중, epic 과 `epic-NN-<slug>` 공유)
- **마일스톤**: `Story`
- **제목**: `[story] <story 한 줄 요약>`
- **본문**: `As a / I want / So that` + Story AC 목록(`AC-NNN`, Given/When/Then, 검증 주체 `[command]` 또는 `[agent-read]`). `AC-NNN` 은 프로젝트 전역 순번이며 한번 부여하면 불변이다. 생성 스크립트는 GitHub issue body 의 Story AC 에만 미체크 체크박스를 붙여 close 감사를 가능하게 하고, stories.md 원문은 바꾸지 않는다. 사람 판정 항목은 AC 체크박스가 아닌 `사람 확인 안내`로 분리한다. 대상 화면 / 상세 동작 명세 / task 체크리스트는 넣지 않는다 — architecture.md + impl 파일 영역. Story AC 없는 stories.md는 유효하지 않다.
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
- **story PR**: 단일/다중 run 모두 `Closes #story-issue`를 넣는다. 다중 story PR은 생성 시 stack base라 close가 아직 발동하지 않고, merge 직전 main 리타겟 후 해당 story만 닫는다.
- **journey deferred production-only PR**: env 선검증 또는 수렴 한도에서 사용자가 해당 journey 검수를 분리했다면 story/epic issue를 닫지 않는다. `Part of #issue`와 `Document-Exception-PR-Close: journey deferred human verification/follow-up`을 넣고 `Closes`는 붙이지 않는다.
- **epic close**: QA PR이 있으면 QA PR, 없으면 마지막 story PR에 `Closes #epic-issue`를 넣는다. 마지막 close PR은 stack 전체의 review/acceptance/AC audit이 끝난 뒤에만 merge한다.
- **QA PR**: epic close 전에는 `Part of #epic-issue`, epic close를 실제 발동하는 마지막 PR이면 `Closes #epic-issue`를 쓴다. receipt/log/screenshot은 tracked PR 산출물이 아니다.
- **공통 task 묶음**: 별도 story issue가 없으므로 `Part of #epic-issue`를 사용한다.

> **반드시 PR body 에 박는다 (commit message 아님)** — 본 프로젝트는 regular merge 채택 ([Git 절차](#git-절차), squash 금지). regular merge 시 GitHub auto-close 는 *PR body* 또는 *squash merge commit message* 만 인식. commit message 안 `Closes #N` 은 머지 commit 에 들어가도 auto-close 발동 X. 본 룰 mechanical 강제 = [`scripts/check_pr_body.mjs`](../../scripts/check_pr_body.mjs) + `.github/workflows/pr-body-validation.yml` (`/init-dcness` 선택형 workflow 로 사용자 repo 배포).
>
> **예외**: issue 없는 infra-only / follow-up split PR과 위 `journey_deferred` production-only PR은 PR body 에 `Document-Exception-PR-Close: <사유>` line 박으면 게이트를 통과한다. `:` + 사유 1단어 이상 동일 line 강제. 그 밖의 story stack PR은 예외가 아니며 `Closes #story`를 사용한다.

### 적용 절차 — story/base 판정

1. impl 파일 frontmatter의 `story`로 PR grouping key를 찾는다. 숫자 story인데 `task_index`가 `i/total` 형식이 아니면 설계 metadata drift로 중지하지만, `i == total` 여부는 PR 경계를 결정하지 않는다.
2. `dcness-story-runner next-action`의 `pr_base`를 사용한다. 첫 story는 `default-branch(main)`, 이후 story는 직전 `story-branch`다.
3. 숫자 story PR은 생성 base와 무관하게 `Closes #story`를 사용한다. 단, run-local `journey_deferred` target AC가 남은 production-only PR은 위 예외 사유와 `Part of`만 사용한다. 공통 task 묶음은 `Part of #epic`이다.
4. QA PR 유무를 확정한 뒤 epic close trailer를 마지막 merge 대상 PR에 둔다. merge 직전에는 해당 PR을 main으로 리타겟·리베이스하고 close audit을 수행한다.

**한 명령 구현 = [`scripts/pr-trailer.sh`](../../scripts/pr-trailer.sh)** — `"$PLUGIN_ROOT/scripts/pr-trailer.sh" <story의 impl파일>` 이 story 트레일러 블록을 stdout 으로 출력한다. stack base는 runner가 소유하며, 어떤 task 파일을 넘겨도 같은 story PR 트레일러가 나오고 `task-index` trailer는 출력하지 않는다.

---

## 이슈 완료 규칙

`Closes` 가 발동할 target issue 는 plan이나 Story AC 와 별개의 **target GitHub issue AC** 마감 계약을 가진다. 구현 경로는 plan ∪ target GitHub issue AC 를 충족해야 하며, close 직전 typed 체크박스를 모두 check 한 body 가 `check_issue_body.mjs --acceptance-only --require-complete` 의 정확한 `PASS`를 받아야 한다. AC 부재·검증 주체 미기재·미충족·미체크 body는 실패하며, close 전에 현행 typed AC로 갱신한다. agent는 의미를 임의 추론해 체크하지 않는다.

### Story 완료

- **구현 완료 조건**: story 의 모든 impl task가 local commit으로 `completed`. PR 생성·머지는 runner state 수명에 영향을 주지 않는다.
- **close 완료 조건**: task 완료와 별도로 target GitHub issue AC 전항목 충족·체크 감사가 PASS. Story AC 는 REQ 설계 trace 의 원천이고, target GitHub issue AC 는 실제 issue close 계약이다.
- **단일 story close**: acceptance와 issue AC write/audit 뒤 base=`main` story PR을 처음 만들고 body `Closes #story-issue` → merge 시 GitHub 자동 close.
- **다중 story close**: final stack tip의 story별 acceptance와 issue AC write/audit을 독립 수행한 뒤 story PR을 clean cut한다. 사용자 승인 뒤 순서대로 main 리타겟·리베이스하고 tree identity를 확인한 `Closes #story-issue` PR이 story별 close를 발동한다.
- 메인 Claude 사후 작업 없음 — stories.md `[x]` 체크 룰 폐기 (2026-05-12, 옛 Step 4.5 동기화 step 폐기, 상세는 git history)

### Epic 완료

- **조건**: epic 의 모든 story task commit 완료 + 스택 tip vs main review/acceptance PASS
- **단일 story close 시점**: acceptance와 issue AC audit 뒤 story→main PR 생성 *직전* 1회 사전 체크:
  ```bash
  gh issue list --label epic-NN-<slug> --milestone Story --state open
  ```
  → 이 story merge 시 마지막 story close 예정이면, PR body 에 `Closes #epic-issue` 도 동봉
- **다중 story close 시점**: QA PR이 있으면 QA PR, 없으면 마지막 story PR이 epic close를 발동한다. 최초 PR cut 전에 epic acceptance와 AC audit을 완료하고, main 리타겟·리베이스 뒤 tree identity가 바뀌면 stale 처리한다.
- 메인 Claude 사후 작업 없음 — `backlog.md` 자체 폐기 (2026-05-12, GitHub epic issue close 가 SSOT)
- 별도 변경 없는 wrap-up/QA PR은 만들지 않는다. tracked 마감 보정이 없으면 마지막 story PR이 epic close를 담당한다.

### API 직접 close 절대금지

`mcp__github__update_issue state:closed` 호출 금지 (epic / story 모두). 반드시 PR body `Closes #N` — [기본 룰](#기본-룰) 참조 (regular merge auto-close 인식 한계).

> `pr-finalize.sh`는 base ≠ default branch PR을 merge 전에 거부한다. story stack은 main 리타겟·리베이스 뒤 PR body `Closes`가 GitHub auto-close를 발동하게 하며, helper가 issue를 직접 닫지 않는다.

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
