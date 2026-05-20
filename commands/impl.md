---
name: impl
description: impl task (architect-loop §4.2 Step 4 module-architect × K 산출물) 1개를 받아 정식 impl 루프 (default = test-engineer → engineer → code-validator → pr-reviewer · fallback = module-architect 선두 추가) 자동 진행하는 스킬. 사용자가 "구현해줘", "/impl <task>", "이 task 구현", "impl 루프", "버그픽스", "한 줄 수정" 등을 말할 때 반드시 이 스킬을 사용한다. /architect-loop 의 후속 — architect-loop 가 `impl/NN-*.md` 본문 detail 까지 채운 산출물의 task list 1개씩 처리. 버그픽스 케이스 = /issue-report 분류 후 본 스킬 fallback path (module-architect 선두 추가) 진입.
---

# Impl Skill

## Loop
`impl-task-loop` ([orchestration.md §2.1 / §4.3](../docs/plugin/orchestration.md)).
UI 디자인 mid-loop 필요 시 → `impl-ui-design-loop` (orchestration §4.4) 자동 전환.

## Inputs (메인이 사용자에게 받아야 할 정보)
- task 경로 (필수, 예: `docs/milestones/v0.2/epics/epic-01-*/impl/01-*.md`)
- 이슈 번호 (있으면)
- attempt 한도 확인 (engineer 3 / POLISH 2 / module-architect 보강 cycle 2 — 기본값)

## 비대상 (다른 skill 추천)
- spec / design 단계 → `/product-plan` (PRD) 또는 `/architect-loop` (설계)
- 다중 task 자동 chain → `/impl-loop`
- task 부재 (계획 X) → `/issue-report` (분류 후 impl-task-loop fallback) 또는 `/product-plan`

## 진입 모드 — default vs fallback (위치 도장)
- task 경로 매치 + 정식 위치 (`docs/milestones/v\d+/epics/epic-\d+-*/impl/\d+-*.md`) 파일 존재 → **default**: test-engineer 직진 (module-architect skip).
- 매치 실패 / 파일 부재 → **fallback**: module-architect 1번 호출 후 test-engineer 진입.
- 근거: architect-loop §4.2 의 Step 4 (module-architect × K) 가 정식 위치 impl 파일 본문 detail 까지 채움. 정식 경로 + 파일 존재 = 통과 보장 (위치 자체가 도장).

## Inner loop 4-step 모두 호출 (MUST — false-clean 차단, #431)

default 시퀀스 = **test-engineer → engineer (IMPL) → code-validator → pr-reviewer**. 4 단계 *모두 호출* 의무.

❌ 안티패턴 (jajang epic 19 task 06 사단, #431 결함 3): test-engineer + engineer 만 호출하고 commit/push/PR 안 만들고 prose "PASS" 박고 종료. 자식 spawn 의 핵심 보장 (1 자식 = 1 PR + 1 이슈 close) 깨짐 + 메인이 수동 commit/push/PR 강요됨.

✅ 정상 흐름:
1. test-engineer (TESTS_WRITTEN) → 테스트 선작성
2. engineer:IMPL (IMPL_DONE) → 구현 + 테스트 PASS
3. **code-validator (PASS)** — impl 계획 ↔ 구현 정합 검증
4. **pr-reviewer (LGTM)** — 코드 품질·보안 + commit/push/PR 생성·머지

후반 2 단계 (3+4) skip 차단:
- task 를 clean 으로 표기하기 *전*, code-validator 가 PASS 를 냈고 pr-reviewer 가 실행돼 PR 이 생성·머지됐는지 메인이 직접 확인. 흔적 부재 시 → false-clean 의심 → `blocked` 강등 + 사용자 개입 (#431)

## 후속 라우팅
- 본 loop clean → 자동 commit/PR (branch prefix = orchestration §4.3 decision rule: feat/chore/fix)
- 주의사항 → 사용자 결정 (수동 7b)
- multi-task chain 필요 → `/impl-loop`

## 사전 read (lazy — 필요시만, #400)
정상 흐름은 본 skill 본문 + 인용된 docs §번호 만으로 진행. 본문에 박힌 catastrophic / Pre-flight gate / agent boundary 룰이 1차. *룰 모호 / 분기 발생* 시에만 `docs/plugin/loop-procedure.md` / `orchestration.md` §4.3 / `handoff-matrix.md` / `issue-lifecycle.md` 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

## 워크트리 (기본 켜짐)
Step 0 진입 시 자동 `EnterWorktree(name="impl-{ts_short}")`. 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시에만 건너뜀. 자세히 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.

**Base ref 분기 (MUST, #424)**: `docs/stories.md` `**Base Branch:** feature/<slug>` 마커 매치 시 통합 브랜치 모드 — outer worktree base ref 도 integration branch 와 정합 필요. 절차 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.1.

## Pre-flight gate (Step 0 직후)
[`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §6 매치 강제 — 부모 epic stories.md 상단 `**GitHub Epic Issue:** [#\d+]` 또는 `미등록 (사유: …)` 매치 0건 시 즉시 STOP + 사용자 보고. silent skip 금지.

## 부모 이슈 본문 read 의무 (MUST)

Pre-flight gate 통과 후, 매치된 epic / story / task 이슈 번호 *각 본문 read 의무*:

```bash
gh issue view <epic-num> | head -80
gh issue view <story-num> | head -80
gh issue view <task-num> | head -80
```

이슈 본문에 수용 기준 / 추가 컨텍스트 / 결정 사항이 박혀있을 수 있음. read 안 하면 *impl 파일 누락 컨텍스트* 미인지 위험.

근거: `/impl-loop` 다중 task 진행 시에도 동일 — 매 task 부모 이슈 본문 read 의무 ([#375](https://github.com/alruminum/dcNess/issues/375)).

## impl 파일 사전 read 의무 (MUST — module-architect 7 원칙 + cost-aware #436)

`/impl` 진입 시 engineer / test-engineer 가 impl 파일의 `## 사전 준비` 섹션 따라 다음 파일 read 의무. **단 통째 read 금지** — `CLAUDE.md` (글로벌) §cost-aware 행동 (#402) 정합: 200 line 초과 doc 은 grep + offset/limit 부분 read.

| 항목 | read 범위 |
|---|---|
| `docs/architecture.md` | 200 line 초과 시 본 task 의 `task_index` 에 해당하는 § 만 grep + offset read (예: `grep -n "## 3\." docs/architecture.md` 로 위치 잡고 offset). 100 line 이하면 통째 OK |
| `docs/adr.md` | 본 task 영향 ADR 만 read (예: `grep "ADR-19A\|ADR-19E" docs/adr.md` 후 매치 줄 ±10 line). 부재 시 silent skip |
| `docs/prd.md` | 본 task 의 Story 항목 § 만. 통째 read 금지 |
| 의존 task 머지 PR | `gh pr view <num> --json body --jq '.body' | head -20` — 1~2줄 결정 사항만 필요. 통째 body json 금지 (이슈 #436) |
| 형제 PR 환기 (같은 epic) | `gh pr list --search "[epic<N>]" --state merged --limit 10 --json title,url` 로 *title + url 만* 1회 훑음. body 통째 read 금지 — 인터페이스 변경 의심되면 그때 `--json body` 단건 fetch |
| 의존 모듈 (수정 X 영역) | **grep + 시그니처만** read. 예: `grep "^export" path/to/file.ts | head -10` + 매치 줄 ±2 line. 통째 read 금지 — 본 task 가 수정하지 않는 영역의 구현 디테일 불요 |
| 의존 모듈 (수정 영역) | 통째 read OK |

→ agent prompt 에 impl 파일 경로 박으면 agent 가 위 룰 따라 자체 read. *메인 Claude 가 사전 inject* 불필요 (impl 파일 안 진입 prompt 가 강제).

**추가 — 메인 직접 read 의무 (강조 + cost-aware, #436)**: 메인 Claude 는 *진입 분기 판단* 에 필요한 **최소** 만 read. agent prompt 경로 박는 것 외에 메인이 통째 read 하지 말 것 — agent 가 자체 read 함.

- 메인 진입 분기 판단 필요 정보 = (a) 이번 task 의 Scope (impl 파일 § Scope grep) / (b) 의존 task 산출물 위치 (impl 파일 § 사전 준비 grep) / (c) ADR 위반 의심 시 해당 ADR 만 grep.
- `docs/architecture.md` / `docs/adr.md` *통째 read* 금지 (이슈 #436 실측 — task 진입 직후 80k messages / 12% context 누적, 코드 1줄 안 썼는데). 부분 read 의무.
- 정합: `CLAUDE.md` §cost-aware 행동 (#402) — "큰 plan/docs 통째 read 회피 → grep + offset/limit. sub-agent 위임 우선 (메인 직접 도구 ↓ → 메인 cache_read 누적 ↓)".

## 진입 직전 — task 진행 상태 1회 확인 (MUST, issue #346)

본 task 가 *이미 머지된 상태* 인지 또는 *부분 진행 후 후속 정보* 가 plan 본문 (특히 tail section) 에 박혀있는지 1회 확인. 발견 시 wasted run 회피.

```bash
# 1. git log 에 task slug 머지 흔적
TASK_SLUG=$(basename "<task-path>" .md)
git log --oneline --grep "$TASK_SLUG" | head -5

# 2. plan tail section read — "Option α 채택 결과" / "§13.1" / "후속 갱신" 같은 후속 결정 기록
tail -50 "<task-path>"
```

결과 발견 시:
- 이미 머지됨 → 사용자 보고 + skill 종료 (재진입 X)
- 부분 진행 + 후속 결정 → tail section 내용을 진행 컨텍스트에 inject + 정상 진입

근거: jajang Epic 12 task 02 사례 (2026-05-09) — 이미 머지된 task 를 재진입 시도 → 3 분 + 컨텍스트 5% wasted. 진입 *전* 30 초 확인이 사후 회복보다 압도적 저비용.

## 절차
[`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1~§6 + [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §4.3 (`impl-task-loop` 풀스펙) 따름. UI 감지 시 §4.4 (`impl-ui-design-loop`).

### PR 생성 직전 — base 분기 체크 (MUST)

`gh pr create` 직전 `docs/stories.md` 상단 `**Base Branch:**` 줄 매치 1회 확인:
- 매치 → `gh pr create --base <매치 값>` (통합 브랜치 케이스, sub-PR base = `feature/<slug>`)
- 매치 없음 → `gh pr create --base main` (default, trunk-based)

근거: 통합 브랜치 모드는 *epic issue body / stories.md 마커* 로 자연어 표현 (`commands/product-plan.md` Step 6.5). 메인 Claude 의 *읽기 행위* 만으로 분기 — mode 플래그 없음. 까먹으면 sub-PR 이 잘못된 base 로 가서 epic atomic transaction 깨짐.

## 종료 조건 (MUST — 메인 Claude 의무)

> ⚠️ **함정 경고**: §3.4 에서 PR merge 까지 자동 완료된다. 메인 본능 "merge = 작업 끝" 으로 *반드시* 다음 명령을 skip 한다. skip = 자동 회고 마비 → 다음 run 회귀 방지 기능 손실.

PR merge 직후 *반드시* 다음 1개 명령 실행 (issue #396 — 단일화):

```bash
"$HELPER" end-run
```

- end-run 안전망 (`session_state.py:1001`) 이 finalize-run --auto-review 자동 발사 → `<run_dir>/review.md` 저장 + stderr `[REVIEW_READY] <path>` 신호 emit.
- (예전 2개 명령 — `finalize-run --expected-steps <N> --auto-review` + `end-run` — 폐기. end-run 1개로 단순화)

**REVIEW_READY 후속 — echo MUST**: stderr `[REVIEW_READY] <run_dir>/review.md` 감지 시 `review.md` 본문을 *character-for-character* 세션 응답에 복사 ([`loop-procedure.md`](../docs/plugin/loop-procedure.md) §6). 압축 / 요약 / 재배치 / 마크다운 테이블 → ASCII 변환 절대 금지. dcness echo 룰 MUST (DCN-30-15).

**메인 인사이트 (자율, issue #396)**: review.md 끝의 `## 📝 메인 인사이트` prompt 보고 *구체적 학습 1줄* 박을 수 있음:

```bash
"$HELPER" insight <agent>[-<mode>] "<자연어 한 줄>"
# 예: "$HELPER" insight engineer-IMPL "🚨 stub 파일로 TDD guard 우회 — 절대 반복 X"
```

- agent+mode 별 FIFO 10 한도. 다음 run begin-step 자동 inject.
- 미박음 = noop (자율, 강제 X). 박으면 다음 run 학습 환류.

근거: §3.4 PR merge 자동 완료 후 메인이 review echo 를 skip 하는 회귀가 반복 발생. hook 미진입 영역이므로 본문 강제로 보완 + 자율 인사이트 매커니즘 안내.
