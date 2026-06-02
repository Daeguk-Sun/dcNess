---
name: impl-loop
description: impl task list (architect-loop §4.2 Step 4 module-architect × K 산출물) 를 메인 Claude 한 세션 안에서 오케스트레이션으로 task 한 개씩 순차 처리하는 스킬. 메인이 한 세션 안에서 직렬 진행 — 각 task = 1 PR + 1 이슈 close. 사용자가 "전부 구현", "/impl-loop", "task 다 돌려", "epic 전체 구현", "/architect-loop 후 자동", "끝까지 구현" 등을 말할 때 반드시 이 스킬을 사용한다. 각 task 가 분리 PR = `/run-review` 도 task 별 분리 분석 자연. clean run 만 자동 진행, 걸리는 게 생기면 (사용자 개입 필수) 즉시 정지. /architect-loop 종료 후 K 개 task 한 번에 처리하고 싶을 때.
---

# Impl Loop Skill — 한 세션 안에서 다중 task 오케스트레이션

## Loop
`impl-task-loop × N` ([orchestration.md §4.8](../docs/plugin/orchestration.md) — 다중 task chain). 메인 Claude 가 한 세션 안에서 task 를 한 개씩 순차 진행. 각 task 의 inner loop = `impl-task-loop` (orchestration §4.3) — [`commands/impl.md`](impl.md) 본문 의무를 그대로 따른다.

## Inputs (메인이 사용자에게 받아야 할 정보)
- task list 또는 epic 경로 (예: `docs/milestones/v0.2/epics/epic-01-*/impl/*.md` glob)
- (선택) `--retry-limit N` — task 당 자동 재시도 한도 (default 3, 0 = 첫 실패 즉시 정지)
- (선택) `--escalate-on <signals>` — 즉시 정지 신호 (default `blocked`)

## 비대상 (다른 skill 추천)
- task 1개 → `/impl`
- spec / design → `/product-plan` 또는 `/architect-loop`

## 워크트리 (기본 켜짐)
Skill 진입 시 자동 `EnterWorktree(name="impl-loop-{ts_short}")` 1회. 모든 task 가 같은 worktree cwd 에서 직렬 진행 — git 충돌 X. 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시에만 건너뜀. 자세히 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.

**chain 누적 초기화 (#525)**: skill 진입 직후 (EnterWorktree 후) `dcness-helper prev-tasks-reset` 1회 호출 — 직전 chain 의 `[PREVIOUS_TASKS]` 잔재 제거. 까먹어도 FIFO cap(10) 으로 자연 완화되나 명시 호출 권장.

**Base ref 분기 (MUST, #424)**: `docs/stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 = 통합 브랜치 모드. EnterWorktree default (`worktree.baseRef=fresh` = origin/main 기반) 가 sub-PR base 와 mismatch → 사전 `git worktree add -b <new> <path> origin/<integration>` + `EnterWorktree(path=<path>)` 패턴으로 worktree base 정합. 절차 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.

## 사전 read (lazy — 필요시만, #400)
정상 흐름은 본 skill 본문 + 인용된 docs §번호 만으로 진행. 본문에 있는 catastrophic / Pre-flight gate 룰이 1차. *룰 모호 / 분기 발생* 시에만 `docs/plugin/loop-procedure.md` / `orchestration.md` §4.3 + §4.8 / `issue-lifecycle.md` 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

## Pre-flight gate (skill 진입 직후, 1회)
[`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §6 매치 강제 — 부모 epic stories.md 의 epic/story 이슈 매치 부재 시 즉시 STOP + 사용자 보고. silent skip 금지.

## 강제 사전 — TaskCreate / TaskUpdate (사용자 가시성, MUST)

본 skill 의 모든 step (각 task 진입 + 각 sub-step 전환) 은 Claude Code 의 **TaskCreate / TaskUpdate 호출과 한 묶음**. 자율 skip 금지.

**WHY**: dcness helper `begin-step` / `end-step` 은 **dcness 내부 트래킹** (메인 컨텍스트 외, conveyor state 파일만 갱신, 사용자 UI 불가시). TaskCreate / TaskUpdate 는 **Claude Code UI 에 사용자가 직접 보는 진행 표시** — 별 역할, 중복 X, 보완 관계. 둘 다 호출 의무.

**catastrophic 안티패턴**: "begin-step 으로 트래킹 충분하다 자율 판단해서 TaskCreate skip" — 사용자가 진행 상태 불가시 → "왜 task 안 만들고 셀프로 돌려?" 지적 회귀. 본 룰 추가 사유.

**호출 시점** (skip 불가):
- skill 진입 직후 (`Pre-flight gate` 통과 후, 절차 1번 진입 *전*) — task list 전체 생성 (§ 진행 뷰)
- 각 task 진입 직전 — task 헤더 `TaskUpdate(status=in_progress)`
- 각 sub-step 전환 — sub-step `TaskUpdate(status=in_progress | completed)`
- task 완료 → task 전환 — § 진행 뷰 의 "다시 그리기" 절차 (4 단계) 그대로

자세한 형식 + 다시 그리기 절차 = §진행 뷰.

## 절차 — 한 세션 안에서 순차 진행 (Hybrid A, #446)

**각 task = 독립 `impl-task-loop` run.** task 진입마다 [`loop-procedure.md`](../docs/plugin/loop-procedure.md) §1~§6 의 1 사이클 (`begin-run impl` → Hybrid A 2-step → `end-run`) 을 1회 돈다. **N task = N run = N run dir = N review.md** — task별 로그·`/run-review` 격리. `/impl-loop` 자체는 자기 run 을 갖지 않는 driver 다. 워크트리만 outer 1회 (§워크트리). task 리스트 표시 = §진행 뷰.

> **분기 룰 (단순화, #446 후속)** — impl 파일 **존재 여부** 1차원만 본다.
> - impl 파일 **있음** → build-worker 직진 (2-step: build-worker + pr-reviewer)
> - impl 파일 **없음** → module-architect 가 먼저 impl 파일 생성 → build-worker 진입 (3-step: module-architect + build-worker + pr-reviewer)
>
> 양식 (정식 위치 / bugfix / 자유 형식) 자체 구분 X — build-worker 가 *내용* 보고 자율 판단 (정보 충분 시 진행, 부족 시 `SPEC_GAP_FOUND`).
>
> **자동 폴백**: build-worker 가 진행 중 `SPEC_GAP_FOUND` 던지면 메인이 module-architect 호출 → impl 파일 보강 → build-worker 재시도 (cycle ≤ 2).
>
> `/impl` 단발 호출은 본 분기 미적용 — 4-agent 모델 유지 (엄정성 우선 의도된 티어링).

1. **glob 매치 + 정렬 → 실행 전 계획 확인 (dry preview)** — `impl/NN-*.md` prefix 기준 직렬 순서 확정 후, **task1 진입 *전* 실행 계획을 1회 표로 echo**. 사용자 가시성 + 잘못된 순서·범위 사전 포착용 (executor `--dry-run` 패턴 이식, #526).
   - 각 task frontmatter (`story:` / `task_index:`) awk 추출 + PR 트레일러 (Closes/Part of) 판정 = [`git-spec.md`](../docs/plugin/git-spec.md) §8.3 + [`loop-procedure.md`](../docs/plugin/loop-procedure.md) §3.4 의 awk one-liner 그대로 재사용. impl 파일 frontmatter 부재 (자유 형식 input) 시 해당 칸 `—`.
   - echo 형식 (재사용 UI 패턴 = [`product-plan.md`](product-plan.md) Step 5 `📄` 마커):
     ```
     📋 실행 계획 (K task)
     | # | 모듈 | impl 파일 | task_index | PR 트레일러 | sub-step |
     |---|------|----------|-----------|-----------|----------|
     | 1 | <slug> | `NN-<slug>.md` | <i/total 또는 —> | Part of #<story> | build-worker · pr-reviewer |
     | … |
     전체: K task · 예상 PR K개
     ```
     `sub-step` 칸 = impl 파일 존재 시 `build-worker · pr-reviewer` (2), 부재 시 `module-architect · build-worker · pr-reviewer` (3).
   - **확인 강도 (task 수 임계값)** — dcness clean-run 자동성과 사용자 확인의 절충:
     - task **< 10** → 계획 표만 echo 후 **자동 task1 진입** (멈춤 X).
     - task **≥ 10** → 계획 표 echo + `진행할까요? (Y/n)` 1회 확인 후 진입. 임계값 10 = §"세션 분할 권장" 표 (≤9 single / 10~19 / ≥20) 와 정합.
     - **yolo 모드** (발화에 `yolo` / `auto` / `끝까지` / `막힘 없이` / `다 알아서`, [`loop-procedure.md`](../docs/plugin/loop-procedure.md) yolo 키워드) → task 수 무관 echo 후 자동 진입 (Y/n skip).
2. **task 한 개씩** — 아래 a~e 를 task N 이 완전히 끝난 (PR 머지 + 이슈 close) 뒤에만 task N+1 진입. 한 번에 한 task.
   1. **진입 직전 1회 확인** — 이미 머지됐거나 부분 진행된 task 검출 (issue #346):
      ```bash
      TASK_SLUG=$(basename "<task-path>" .md)
      git log --oneline --grep "$TASK_SLUG" | head -5
      tail -50 "<task-path>"
      ```
      이미 머지됨 → 해당 task skip + 다음 task. 부분 진행 + tail section 후속 결정 → 그 내용을 진행 컨텍스트에 반영 후 정상 진입.
   2. **begin-run + build-worker step** — 메인이 `begin-run impl` 호출 → `begin-step build-worker` → `Agent(build-worker, prompt=<impl 경로 + task slug + RUN_ID + (begin-step stdout 의 `[PREVIOUS_TASKS]` 섹션 있으면 그대로 포함, #525)>)` → 반환 prose 의 결론 분기:
      - `PASS` → step 3 진입
      - `SPEC_GAP_FOUND` → 분기 — build-worker prose 의 *추정 분량 메타* (small/medium/large) 기반:
        - **small** (1 enum 값 / 1 필드 / 1 메서드 시그니처 추가) → 메인이 직접 Edit (`docs/impl/NN-*.md` 또는 `docs/domain-model.md`) + build-worker 재호출. cycle 카운트 불포함 (경량 예외). 외부 사용자 [F4 실측 사례](https://github.com/alruminum/dcNess/issues/506) 정합.
        - **medium / large** (multiple field / 새 module / 도메인 모델 변경) → module-architect (보강) → build-worker 재호출 (cycle ≤ 2).
      - `TESTS_FAIL` → engineer (단발 4-agent 진입, attempt < 3) 또는 사용자 위임
      - `IMPLEMENTATION_ESCALATE` → 사용자 위임
      이후 `end-step build-worker`. worker 안 phase 별 prose (`build-test.md` / `build-impl.md` / `build-validate.md`) 는 worker 자체 Write — [`loop-procedure.md §3.2.1`](../docs/plugin/loop-procedure.md).
   3. **git/PR 생성 (메인)** — worker prose 의 commit message + PR 본문 초안을 임시 파일로 박고 `scripts/pr-create.sh` 통합 호출:
      ```bash
      # worker prose 에서 추출한 본문을 임시 파일로
      cat > /tmp/pr-body-<slug>.md <<'PR'
      <worker prose 의 PR 본문 그대로>
      PR
      cat > /tmp/commit-msg-<slug>.md <<'COMMIT'
      <worker prose 의 commit message 그대로>
      COMMIT

      # 한 명령으로 branch + add + commit + push + pr create
      bash scripts/pr-create.sh \
        --branch <branch_prefix>/<task-slug> \
        --base <base> \
        --title "<...>" \
        --body-file /tmp/pr-body-<slug>.md \
        --commit-msg-file /tmp/commit-msg-<slug>.md
      ```
      `branch_prefix` = `orchestration.md §4.3 branch_prefix decision rule` 정합. base 분기 = `git-spec.md §6` 정합 (통합 브랜치 모드 매치 시 그 값). 분리 명령 (`git checkout -b` / `git add` / `git commit` / `git push` / `gh pr create` 각각 호출) 은 *비권장* — 메인 turn 누적 회수 영역.
   4. **pr-reviewer step + 머지** — `begin-step pr-reviewer` → `Agent(pr-reviewer, prompt=<PR 번호 + impl 경로 + 구현 파일 목록>)` → `PASS` 시 `bash scripts/pr-finalize.sh <PR>` 호출 (gh pr merge --auto + watch + main sync 자동). `FAIL` 시 engineer POLISH 단발 진입 (cycle ≤ 2). 이후 `end-step pr-reviewer`.
   5. **end-run + 다음 task 진입 — `next-task` 통합 호출 (issue #471)** — 마지막 task 가 아닌 경우 `dcness-helper next-task` 1회 호출. helper 가 (이전 run end-run + previous review.md stdout + 새 run begin-run) 통합 처리 → 메인은 stdout 의 `[new] run_id` 만 받아 다음 task 의 `begin-step build-worker` 즉시 진입. *마지막* task = `next-task` 대신 `end-run` 단독 호출. 본 helper 가 task 경계 ~27 turn 영역 (review echo + 다음 task 자율 진입 준비) 을 1 turn 으로 압축.
      ```bash
      # 마지막 task 가 아닐 때
      bash "${CLAUDE_PLUGIN_ROOT}/scripts/dcness-helper" next-task --entry-point impl

      # 마지막 task
      bash "${CLAUDE_PLUGIN_ROOT}/scripts/dcness-helper" end-run
      ```
      메인 컨텍스트에 박는 echo 는 본 skill §"review 출력 재정의 (#446)" 의 5줄 요약. 원본 review.md 는 `<run_dir>/review.md` 디스크 그대로 (next-task stdout 의 본문 = ground truth).
3. **enum 별 분기**:
   - `clean` → next-task 호출 (위 §5) → 다음 task 진입
   - `error` → 자동 재시도 (한도 `--retry-limit`, default 3). 한도 초과 시 정지 + 사용자 위임.
   - `blocked` → 즉시 정지 + 사용자 위임.
4. **전체 완료** → 보고 (처리 N/N + 각 PR URL). 본 시점 *이후* 메인이 자율 작업 (자율 발견 이슈 등록 / cleanup / 시간 분석 / 측정 등) 진입 시 진입 *전* `dcness-helper post-task-begin --reason "<사유>"` 호출 의무 — task 영역 측정 ROI 와 분리 marker (issue #472).

### impl 파일 부재 시 — module-architect 선두 자동 진입

impl 파일 부재 시 §2.ii 의 `begin-step build-worker` 직전에 `begin-step module-architect` → `Agent(module-architect, prompt=<task 컨텍스트 + impl 파일 생성 위치>)` → 결론 `PASS` 시 impl 파일 생성 확인 후 `end-step module-architect` → 정상 build-worker 진입. module-architect 결론 `ESCALATE` 시 사용자 위임. 사용자 자율 형식 input (impl 파일 부재) 의 표준 흐름.

build-worker 가 진행 중 `SPEC_GAP_FOUND` 던지는 경우도 동일 — module-architect 호출 → impl 파일 보강 → build-worker 재호출 (cycle ≤ 2). attempt 한도 초과 시 사용자 위임.

## 진행 뷰 (task 리스트)

사용자가 *현재 진행 페이즈* 를 한눈에 보도록 task 리스트를 관리한다. Task 시스템 = 평탄 리스트 (부모/자식 필드 X) + 생성순 표시 — 중첩은 subject 들여쓰기로 흉내낸다.

완료 task 는 한 줄, 현재 task 만 sub-step 펼침, 예정 task 는 대기 줄:

```
✓ task1 · <모듈명>
▾ task2 · <모듈명>          ← 현재 (in_progress)
   ㄴ build-worker          ← sub-step (Hybrid A 모드)
   ㄴ pr-reviewer
○ task3 · <모듈명>          ← 예정 (pending)
```

impl 파일 부재 시 sub-step 3건 (`module-architect` / `build-worker` / `pr-reviewer`).

- outer 헤더 subject = `task<i> · <모듈명>` (모듈명 = impl 파일 slug 또는 `## 변경 요약`)
- sub-step subject = `   ㄴ <agent>` (앞 공백 3칸 = 들여쓰기 흉내). in_progress 시 `activeForm` 에 현재 작업 명시 (예: `build-worker <모듈> phase 2 build-impl 중`)
- sub-step 수 = **2 (impl 파일 존재)** / **3 (impl 파일 부재: module-architect 선두 추가)**

**진입 시 (MUST — §강제 사전 정합)** — TaskCreate 를 이 순서로: `task1 헤더` → `task1 sub × 2 (impl 있음) 또는 × 3 (impl 없음)` → `task2 헤더` → … → `taskN 헤더`. task1 헤더만 in_progress. **skip 시 사용자 가시성 손실 = catastrophic 안티패턴** (§강제 사전).

**task i 진행 중 (MUST)** — 그 task 의 `impl` run 은 TaskCreate skip (sub-step task 이미 존재 — loop-procedure §2). conveyor 진행에 맞춰 sub-step 을 TaskUpdate (pending → in_progress → completed) 호출 의무. Hybrid A 경우 build-worker 안의 3 phase (build-test / build-impl / build-validate) 는 outer sub-step `build-worker` 하나로 묶임 — `activeForm` 에 phase 표시.

**task i 완료 → task i+1 (다시 그리기 — task 수 별 분기)**:

| 총 task 수 | 절차 | 비용 (TaskCreate 호출) |
|---|---|---|
| **≤ 10** | 4 단계 완전 다시 그리기 (아래 1~4) — 가시성 우선 | 매 task ~N 호출 |
| **11~20** | 3 단계 부분 다시 그리기 (1~3, 재생성 skip) — 다음 task 헤더만 in_progress 전환 | 매 task ~3 호출 |
| **> 20** | 최소 갱신 — sub-step deleted + 다음 task 헤더 in_progress 만 | 매 task ~2 호출 |

4 단계 (완전 다시 그리기):
1. task i 의 sub-step 전부 `TaskUpdate(status=deleted)` — 완료 task 는 헤더 한 줄로 접음
2. task i 헤더 `TaskUpdate(status=completed)`
3. task i+1 ~ N 헤더 `TaskUpdate(status=deleted)`
4. TaskCreate 를 이 순서로: `task(i+1) 헤더(in_progress)` → `task(i+1) sub × 2 (또는 × 5)` → `task(i+2) 헤더` → … → `taskN 헤더`

생성순 = 표시순 + 중간삽입 불가 → 완료 헤더 뒤에 [현재 헤더 + sub-step + 남은 헤더] 를 다시 그려야 sub-step 이 부모 밑에 온다 (3·4 단계 = 다시 그리기 이유).

> **trade-off 근거**: 외부 사용자 [F9 실측](https://github.com/alruminum/dcNess/issues/507) — task 27 에서 4 단계 매번 실행 시 TaskCreate ~27 × N 호출 = 무시 못 할 비용. task > 20 부터는 부모-자식 표시 어색해도 호출 비용 절감 우선. 사용자 가시성 (어디까지 진행했나) 은 task 헤더 in_progress / completed 표시만으로 충분. Task UI "after taskId" 옵션 (근본 fix) 은 Claude Code 시스템 영역 — dcness 영역 밖.

**마지막 task 완료** — sub-step deleted + 헤더 completed. 전체가 `✓` 한 줄씩.

> retry / POLISH 는 기존 sub-step task 재활용 (loop-procedure §3.3.1) — 신규 TaskCreate X.

## review 출력 재정의 (#446)

`/impl-loop` driver 안에서는 [`commands/impl.md`](impl.md) §종료 조건 의 review.md *원본 그대로 출력 MUST* 가 **driver 범위 안에서 재정의** 된다. 매 task 마다 review.md 전수를 메인 컨텍스트에 출력하면 N task = N × review.md 누적 → cache_read 폭주 (실측 기준선 ~280 turn/task 중 post-Agent 47 turn 의 주범 중 하나).

**메인 컨텍스트 출력** — 5줄 요약 (Hybrid A 기본 형식):

```
[task<i> · <slug>] <clean|error|blocked>
build-worker: <N tests RED→GREEN · M files +X -Y · validate PASS|FAIL> · pr-reviewer: <LGTM|FAIL>
finding: <PASS 시 "없음" / FAIL·NICE TO HAVE 시 1-2 문장>
PR <#NNN> merged · closes #<MMM>
next: <다음 task slug 진입 | 정지 사유>
```

impl 파일 부재로 module-architect 선두 진입한 경우 2번째 줄은 `module-architect: <PASS|ESCALATE> · build-worker: <N tests RED→GREEN · M files +X -Y · validate PASS|FAIL> · pr-reviewer: <LGTM|FAIL>`.

**5줄 형식 강제 메커니즘** — pr-reviewer prose return 의 last block 에 본 5줄 template 그대로 박는 의무 ([`agents/pr-reviewer.md`](../agents/pr-reviewer.md) §산출물 정보 의무 정합). 메인은 prose 본 block 을 chat 에 *그대로 echo* — 자유 형식 단축 금지. 외부 사용자 [F8 실측](https://github.com/alruminum/dcNess/issues/507) 에서 메인이 자유 한 줄 출력 (예: "[task07] clean · PR #23 merged · LGTM") 회귀 — 사후 분석 시 어디까지 진행했는지 한눈에 안 들어옴 차단.

**디스크** — `<run_dir>/review.md` 는 end-run 안전망이 이미 원본 그대로 저장 ([`commands/impl.md:134`](impl.md) 정합). `/run-review` 진단 / compaction 후 재진입 시 디스크에서 read.

**메인 인사이트** ([`commands/impl.md`](impl.md) §종료 조건 의 자율 1줄 인사이트) 는 본 요약 뒤에 *선택* 1줄 쓸 수 있다 — 작성하면 누적 학습 신호, 생략해도 회귀 X.

> `/impl` 단발 호출 (driver 부재) 은 review.md 원본 그대로 출력 MUST 유지 — rigor 우선. 본 재정의는 `/impl-loop` 한정.

## false-clean 차단 (MUST, #431)
task 를 clean 으로 표기하기 *전*, code-validator 가 PASS 를 냈고 pr-reviewer 가 실행된 뒤 *메인 Claude 가* PR 생성·머지까지 마쳤는지 메인이 직접 확인한다. 셋 중 하나라도 흔적이 없으면 clean 아님 → `blocked` 강등 + 사용자 보고. (pr-reviewer 자체는 `tools: Read, Glob, Grep` 만 — commit/push/PR 권한 없음. test-engineer + engineer 만 호출하고 commit/push/PR 없이 prose "PASS" 박고 종료하는 안티패턴 — 실측 회귀 사례.)

## compaction 중 진행 (안전망)
긴 epic 진행 중 메인 컨텍스트가 auto-compaction 될 수 있다. 루프 진행 상태는 메인 컨텍스트가 아니라 conveyor state 파일 (`live.json` / `.by-pid-current-run/` / `run-NN` / `current_step`) 이 SSOT — compaction 돼도 진행 손실은 0. compaction 직후 자신이 impl-loop 도중이라고 판단되면 run state 를 재read 해서 현재 task index + step 을 식별하고 그 지점부터 재개한다.

### 세션 분할 권장 + 자동 /smart-compact 진입 (외부 사용자 [F13](https://github.com/alruminum/dcNess/issues/507) 영역)

epic 크기에 따라 세션 분할 / compaction 발화 권고:

| 총 task 수 | 권고 |
|---|---|
| ≤ 9 | single-session 진행. compaction 발화 가능성 낮음. |
| 10~19 | single-session 가능, 단 task 절반 (5/10, 10/20) 진입 시점에 메인이 chat 으로 사용자에게 *"context 사용량 60%+ 추정 — /smart-compact 권장"* 1줄 안내 (사용자 명시 호출 트리거). |
| ≥ 20 | **multi-session 진입 권장** — epic 을 절반/3분할 (예: task 1-10 / 11-20 / 21-27) 로 쪼개서 별 세션 진행. conveyor state SSOT 가 task 경계 재개를 보장. 메인이 impl-loop 진입 시점에 사용자에게 분할 안내. |

**sub-agent prose 디스크 저장 + chat echo 분리**: build-worker / pr-reviewer prose 는 매 task `<run_dir>/build-{test,impl,validate}.md` + `<run_dir>/review.md` 디스크에 이미 저장됨. 메인 chat 에는 §"review 출력 재정의" 의 5줄 요약만 echo — sub-agent prose 본문 전수 echo 금지 (compaction trigger). 사용자 / 메인이 깊은 영역 필요 시 디스크에서 직접 Read (`/run-review` 진단).

## git 권한
worktree branch 안 commit / push / PR 생성·머지 = **메인 Claude 전담**. engineer / build-worker / test-engineer 등 sub-agent 는 git commit/push/branch + `gh pr create/merge` 금지 — 코드 변경만 (worker 의 경우 PR 본문·commit message *초안* 만 prose return 에 작성, 실제 명령은 메인). main 직접 commit / push = ❌ (main-block hook 차단). 상세 = [`git-spec.md`](../docs/plugin/git-spec.md) §6 + [`loop-procedure.md`](../docs/plugin/loop-procedure.md) §3.4 + [`agents/build-worker.md`](../agents/build-worker.md) §권한 경계.

## 후속 라우팅
- 각 task clean → 다음 task 자동 진입
- error → 자동 재시도 (한도까지). 한도 초과 시 정지 + 사용자 위임
- blocked → 즉시 정지 + 사용자 위임 (재호출 또는 수동 처리)
- 전체 완료 → 보고 (처리 N/N + 각 PR URL)

## 한계
- task 의존성 자동 판단 X (직렬 진행 — SD impl 목차 순서 / list 순서 = 의존 표현)
- multi-task resume — 한도 초과 / blocked 후 재실행 시, 이미 머지된 task 는 §"진입 직전 1회 확인" 으로 자동 검출·skip → 남은 task 부터 재개

## 안티패턴 (회귀 방지)
- ❌ task N 개를 한 sub-agent 호출에 묶어 한 번에 처리 — task 별 PR / 이슈 close 분리가 깨지고 `/run-review` 분석 단위가 붕괴. 한 번에 한 task. (build-worker 는 1 task 통합 — 본 안티패턴과 충돌 X)
- ❌ task 를 동시 병렬 진행 — git 충돌 + 메인 누적 컨텍스트 cache_read 비용 폭주 ([#216](https://github.com/alruminum/dcNess/issues/216) — pre-dcness 시기 사례 \$1,531 / 단일 세션). v1 spec = 직렬.
- ❌ build-worker prose PASS 만 보고 phase prose 자체 Write 확인 skip — `<run_dir>/build-test.md` / `build-impl.md` / `build-validate.md` 3개 파일 실존 검증 의무. 부재 시 worker 가 phase 의무 위반 → `blocked` 강등.
- ❌ Hybrid A 에서 build-worker 가 `Agent(pr-reviewer)` 또는 `git commit` 직접 호출 — 권한 경계 위반. 메인이 별도 turn 으로 처리.
- ❌ code-validator / pr-reviewer skip 하고 prose "PASS" — false-clean (#431). §"false-clean 차단" 참조. Hybrid A 의 경우 build-worker phase 3 self-validate + 메인의 pr-reviewer 호출 모두 확인.
- ❌ 한 task 의 PR 머지 전 다음 task 진입 — task 간 의존 깨짐.
- ❌ escalate 신호 무시하고 다음 task 진행 — 사용자 부재 환경에서 추측 진행 = 폭주.
- ❌ /impl-loop 전체 완료 후 자율 작업 (이슈 등록 / cleanup / 분석) 진입 시 `post-task-begin` marker 누락 — task ROI 측정에 본 영역 turn 합산되어 평균 task turn 왜곡 (#472 영역). 자율 진입 *전* `dcness-helper post-task-begin --reason "<사유>"` 호출 의무.
- ❌ **TaskCreate / TaskUpdate skip — `begin-step` 트래킹으로 충분 자율 판단** (catastrophic). dcness helper = 내부 state (사용자 UI 불가시), TaskCreate = Claude Code UI 표시 (사용자 가시). 둘 다 호출 의무 = §강제 사전. skip 회귀 = "왜 task 안 만들고 셀프로 돌려?" 사용자 지적 패턴.

## Hybrid A 모드 — 실측 진입 (#446 Step 4 + 후속 단순화)

`/impl-loop` 메인 컨텍스트 누적 절감 목적의 Hybrid A 모드 활성 — 본 skill 의 §절차 가 build-worker 2-step 시퀀스를 기본으로 진행. impl 파일 부재 시 module-architect 선두 자동 진입 (3-step). 양식 (정식 위치 / bugfix / 자유 형식) 자체 구분 X — build-worker 가 *내용* 보고 자율 판단 (#446 트랙 후속 단순화).

설계 참조:
- worker 시스템 프롬프트: [`agents/build-worker.md`](../agents/build-worker.md)
- 진입 모드 분기: [`docs/plugin/orchestration.md §4.3·§4.8`](../docs/plugin/orchestration.md)
- phase prose 자체 Write 규약: [`docs/plugin/loop-procedure.md §3.2.1`](../docs/plugin/loop-procedure.md)
- 결론 가이드: [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §3.1 / ALLOW_MATRIX: [`harness/agent_boundary.py`](../harness/agent_boundary.py)

**실측 미완 — 사용자 협력 측정 진입**: #446 Step 3 통과 기준 (메인 turn ≤ 100, 엄정성 유지) 의 실측 검증 미완. 본 릴리즈 (0.2.28) 가 *측정 진입* 용도. 사용자가 `/impl-loop <task>` 1회 호출 → 새 세션 JSONL → `python3 scripts/measure_main_turns.py <sid>.jsonl` 로 측정 → 결과에 따라:
- ≤ 100 turn (엄정성 유지) → 그대로 유지 → Step 6 사후 검증
- > 100 turn 또는 엄정성 미달 → 후보 경로 (4-agent) 로 복귀 PR + 0.2.29 hotfix

트랙 SSOT = [issue #446](https://github.com/alruminum/dcNess/issues/446).

## 참고
- 다중 task chain 스펙: [`orchestration.md §4.8`](../docs/plugin/orchestration.md)
- 각 task inner loop: [`orchestration.md §4.3`](../docs/plugin/orchestration.md) (`impl-task-loop`) + [`commands/impl.md`](impl.md)
- Hybrid A worker 시스템 프롬프트: [`agents/build-worker.md`](../agents/build-worker.md)
- 트랙 SSOT: [issue #446](https://github.com/alruminum/dcNess/issues/446)
