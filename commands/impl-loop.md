---
name: impl-loop
description: impl task list (architect-loop §4.2 Step 4 module-architect × K 산출물) 를 메인 Claude in-session 오케스트레이션으로 task 한 개씩 순차 처리하는 스킬. 메인이 한 세션 안에서 직렬 진행 — 각 task = 1 PR + 1 이슈 close. 사용자가 "전부 구현", "/impl-loop", "task 다 돌려", "epic 전체 구현", "/architect-loop 후 자동", "끝까지 구현" 등을 말할 때 반드시 이 스킬을 사용한다. 각 task 가 분리 PR = `/run-review` 도 task 별 분리 분석 자연. clean run 만 자동 진행, 걸리는 게 생기면 (사용자 개입 필수) 즉시 정지. /architect-loop 종료 후 K 개 task 한 번에 처리하고 싶을 때.
---

# Impl Loop Skill — in-session 다중 task 오케스트레이션

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

**Base ref 분기 (MUST, #424)**: `docs/stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 = 통합 브랜치 모드. EnterWorktree default (`worktree.baseRef=fresh` = origin/main 기반) 가 sub-PR base 와 mismatch → 사전 `git worktree add -b <new> <path> origin/<integration>` + `EnterWorktree(path=<path>)` 패턴으로 worktree base 정합. 절차 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.

## 사전 read (lazy — 필요시만, #400)
정상 흐름은 본 skill 본문 + 인용된 docs §번호 만으로 진행. 본문에 박힌 catastrophic / Pre-flight gate 룰이 1차. *룰 모호 / 분기 발생* 시에만 `docs/plugin/loop-procedure.md` / `orchestration.md` §4.3 + §4.8 / `handoff-matrix.md` / `issue-lifecycle.md` 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read baseline 감축.

## Pre-flight gate (skill 진입 직후, 1회)
[`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §6 매치 강제 — 부모 epic stories.md 의 epic/story 이슈 매치 부재 시 즉시 STOP + 사용자 보고. silent skip 금지.

## 절차 — in-session 순차 진행

**각 task = 독립 `impl-task-loop` run.** task 진입마다 [`commands/impl.md`](impl.md) 본문 의무대로 [`loop-procedure.md`](../docs/plugin/loop-procedure.md) §1~§6 의 1 사이클 (`begin-run impl` → 4-step → `end-run`) 을 1회 돈다. **N task = N run = N run dir = N review.md** — task별 로그·`/run-review` 격리. `/impl-loop` 자체는 자기 run 을 갖지 않는 driver 다. 워크트리만 outer 1회 (§워크트리). task 리스트 표시 = §진행 뷰.

1. **glob 매치 + 정렬** — `impl/NN-*.md` prefix 기준 직렬 순서 확정.
2. **task 한 개씩** — 아래 a~d 를 task N 이 완전히 끝난 (PR 머지 + 이슈 close) 뒤에만 task N+1 진입. 한 번에 한 task.
   1. **진입 직전 1회 확인** — 이미 머지됐거나 부분 진행된 task 검출 (issue #346):
      ```bash
      TASK_SLUG=$(basename "<task-path>" .md)
      git log --oneline --grep "$TASK_SLUG" | head -5
      tail -50 "<task-path>"
      ```
      이미 머지됨 → 해당 task skip + 다음 task. 부분 진행 + tail section 후속 결정 → 그 내용을 진행 컨텍스트에 반영 후 정상 진입.
   2. **impl-task-loop 진행** — [`commands/impl.md`](impl.md) 본문 의무 그대로 `begin-run impl` → test-engineer → engineer (IMPL) → code-validator → pr-reviewer. 4 단계 *모두 호출* MUST. 정식 위치 impl 파일 부재 시 fallback (module-architect 선두 추가). 워크트리는 outer 1회 — task별 EnterWorktree 재진입 X.
   3. **PR 생성 + 머지 + 이슈 close** — [`commands/impl.md`](impl.md) §"PR 생성 직전 — base 분기 체크" + [`git-naming-spec.md`](../docs/plugin/git-naming-spec.md) 따름. 1 task = 1 PR = 1 이슈 close.
   4. **end-run + review echo (digest override)** — [`commands/impl.md`](impl.md) §종료 조건 따름. 단 메인 컨텍스트에 박는 echo 는 본 skill §"review echo override (#446)" 의 5줄 digest 로 *override* — verbatim review.md 는 `<run_dir>/review.md` 디스크 그대로 (이미 저장).
3. **enum 별 분기**:
   - `clean` → 다음 task 진입
   - `error` → 자동 재시도 (한도 `--retry-limit`, default 3). 한도 초과 시 정지 + 사용자 위임.
   - `blocked` → 즉시 정지 + 사용자 위임.
4. **전체 완료** → 보고 (처리 N/N + 각 PR URL).

## 진행 뷰 (task 리스트)

사용자가 *현재 진행 페이즈* 를 한눈에 보도록 task 리스트를 관리한다. Task 시스템 = 평탄 리스트 (부모/자식 필드 X) + 생성순 표시 — 중첩은 subject 들여쓰기로 흉내낸다.

완료 task 는 한 줄, 현재 task 만 sub-step 펼침, 예정 task 는 대기 줄:

```
✓ task1 · <모듈명>
▾ task2 · <모듈명>          ← 현재 (in_progress)
   ㄴ test-engineer         ← sub-step
   ㄴ engineer
   ㄴ code-validator
   ㄴ pr-reviewer
○ task3 · <모듈명>          ← 예정 (pending)
```

- outer 헤더 subject = `task<i> · <모듈명>` (모듈명 = impl 파일 slug 또는 `## 변경 요약`)
- sub-step subject = `   ㄴ <agent>` (앞 공백 3칸 = 들여쓰기 흉내). in_progress 시 `activeForm` 에 현재 작업 명시 (예: `engineer <모듈> 구현 중`)
- sub-step 수 = 4 (default) / 5 (fallback: module-architect 선두)

**진입 시** — TaskCreate 를 이 순서로: `task1 헤더` → `task1 sub × 4` → `task2 헤더` → … → `taskN 헤더`. task1 헤더만 in_progress.

**task i 진행 중** — 그 task 의 `impl` run 은 TaskCreate skip (sub-step task 이미 존재 — loop-procedure §2). conveyor 진행에 맞춰 sub-step 을 TaskUpdate (pending → in_progress → completed).

**task i 완료 → task i+1 (rebuild)**:
1. task i 의 sub-step 전부 `TaskUpdate(status=deleted)` — 완료 task 는 헤더 한 줄로 collapse
2. task i 헤더 `TaskUpdate(status=completed)`
3. task i+1 ~ N 헤더 `TaskUpdate(status=deleted)`
4. TaskCreate 를 이 순서로: `task(i+1) 헤더(in_progress)` → `task(i+1) sub × 4` → `task(i+2) 헤더` → … → `taskN 헤더`

생성순 = 표시순 + 중간삽입 불가 → 완료 헤더 뒤에 [현재 헤더 + sub-step + 남은 헤더] 를 다시 그려야 sub-step 이 부모 밑에 온다 (3·4 단계 = rebuild 의 이유).

**마지막 task 완료** — sub-step deleted + 헤더 completed. 전체가 `✓` 한 줄씩.

> retry / POLISH 는 기존 sub-step task 재활용 (loop-procedure §3.3.1) — 신규 TaskCreate X.

## review echo override (#446)

`/impl-loop` driver 안에서는 [`commands/impl.md`](impl.md) §종료 조건 의 review.md *verbatim echo MUST* 가 **driver-scope override** 된다. 매 task 마다 review.md 전수를 메인 컨텍스트에 echo 하면 N task = N × review.md 누적 → cache_read 폭주 (jajang 실측 baseline ~280 turn/task 중 post-Agent 47 turn 의 주범 중 하나).

**메인 컨텍스트 echo** — 5줄 digest:

```
[task<i> · <slug>] <clean|error|blocked>
test-engineer: <N tests, RED→GREEN|SPEC_GAP> · engineer: <M files, +X -Y> · code-validator: <PASS|FAIL> · pr-reviewer: <LGTM|FAIL>
finding: <PASS 시 "없음" / FAIL·NICE TO HAVE 시 1-2 문장>
PR <#NNN> merged · closes #<MMM>
next: <다음 task slug 진입 | 정지 사유>
```

**디스크** — `<run_dir>/review.md` 는 end-run 안전망이 이미 verbatim 저장 ([`commands/impl.md:134`](impl.md) 정합). `/run-review` 진단 / compaction 후 재진입 시 디스크에서 read.

**메인 인사이트** ([`commands/impl.md`](impl.md) §종료 조건 의 자율 1줄 인사이트) 는 본 digest 뒤에 *선택* 1줄 박을 수 있다 — 작성하면 누적 학습 신호, 생략해도 회귀 X.

> `/impl` 단발 호출 (driver 부재) 은 verbatim MUST 그대로 — rigor 우선. 본 override 는 `/impl-loop` 한정.

## false-clean 차단 (MUST, #431)
task 를 clean 으로 표기하기 *전*, code-validator 가 PASS 를 냈고 pr-reviewer 가 실행돼 PR 이 생성·머지됐는지 메인이 직접 확인한다. 둘 중 하나라도 흔적이 없으면 clean 아님 → `blocked` 강등 + 사용자 보고. (test-engineer + engineer 만 호출하고 commit/push/PR 없이 prose "PASS" 박고 종료하는 안티패턴 — jajang epic 19 task 06 사단.)

## compaction 중 진행 (안전망)
긴 epic 진행 중 메인 컨텍스트가 auto-compaction 될 수 있다. 루프 진행 상태는 메인 컨텍스트가 아니라 conveyor state 파일 (`live.json` / `.by-pid-current-run/` / `run-NN` / `current_step`) 이 SSOT — compaction 돼도 진행 손실은 0. compaction 직후 자신이 impl-loop 도중이라고 판단되면 run state 를 재read 해서 현재 task index + step 을 식별하고 그 지점부터 재개한다.

## git 권한
worktree branch 안 commit / push / PR 생성·머지 = 메인 Claude (또는 권한 보유 agent). engineer 등 sub-agent 는 git commit/push/branch 금지 — 코드 변경만. main 직접 commit / push = ❌ (main-block hook 차단). 상세 = [`git-naming-spec.md`](../docs/plugin/git-naming-spec.md) §6 + [`loop-procedure.md`](../docs/plugin/loop-procedure.md) §3.4.

## 후속 라우팅
- 각 task clean → 다음 task 자동 진입
- error → 자동 재시도 (한도까지). 한도 초과 시 정지 + 사용자 위임
- blocked → 즉시 정지 + 사용자 위임 (재호출 또는 수동 처리)
- 전체 완료 → 보고 (처리 N/N + 각 PR URL)

## 한계
- task 의존성 자동 판단 X (직렬 진행 — SD impl 목차 순서 / list 순서 = 의존 표현)
- multi-task resume — 한도 초과 / blocked 후 재실행 시, 이미 머지된 task 는 §"진입 직전 1회 확인" 으로 자동 검출·skip → 남은 task 부터 재개

## 안티패턴 (회귀 방지)
- ❌ task N 개를 한 sub-agent 호출에 묶어 한 번에 처리 — task 별 PR / 이슈 close 분리가 깨지고 `/run-review` 분석 단위가 붕괴. 한 번에 한 task.
- ❌ task 를 동시 병렬 진행 — git 충돌 + 메인 누적 컨텍스트 cache_read 비용 폭주 ([#216](https://github.com/alruminum/dcNess/issues/216) — pre-dcness 시기 사례 \$1,531 / 단일 세션). v1 spec = 직렬.
- ❌ code-validator / pr-reviewer skip 하고 prose "PASS" — false-clean (#431). §"false-clean 차단" 참조.
- ❌ 한 task 의 PR 머지 전 다음 task 진입 — task 간 의존 깨짐.
- ❌ escalate 신호 무시하고 다음 task 진행 — 사용자 부재 환경에서 추측 진행 = 폭주.

## Hybrid A 모드 (활성화 대기, #446)

`/impl-loop` 메인 컨텍스트 누적 절감 목적의 Hybrid A 모드 (build-worker 통합 worker + pr-reviewer 독립 2-step) 가 설계 완료 — [`agents/build-worker.md`](../agents/build-worker.md) + [`docs/plugin/orchestration.md §4.3·§4.8`](../docs/plugin/orchestration.md) + [`docs/plugin/loop-procedure.md §3.2.1`](../docs/plugin/loop-procedure.md) + [`docs/plugin/handoff-matrix.md §1.12·§4.1`](../docs/plugin/handoff-matrix.md) (PR #448).

**본 릴리즈 (0.2.27) 한정 — Hybrid A 활성화 보류**. `/impl-loop` 진입 시 본 skill 의 §절차 4-agent 시퀀스 ([`commands/impl.md`](impl.md) 본문 의무 그대로) 만 동작. 이유 = #446 Step 3 프로토타입 (jajang 1-task 실측 gate) 미완 — 실측 검증 전 사용자 환경 회귀 위험 회피.

활성화 시점 = Step 3 gate (메인 turn ≤ 100, rigor 유지) 통과 후 별 PR. 트랙 SSOT = [issue #446](https://github.com/alruminum/dcNess/issues/446).

## 참고
- 다중 task chain 스펙: [`orchestration.md §4.8`](../docs/plugin/orchestration.md)
- 각 task inner loop: [`orchestration.md §4.3`](../docs/plugin/orchestration.md) (`impl-task-loop`) + [`commands/impl.md`](impl.md)
- Hybrid A worker 시스템 프롬프트 (활성화 대기): [`agents/build-worker.md`](../agents/build-worker.md)
- 트랙 SSOT: [issue #446](https://github.com/alruminum/dcNess/issues/446)
