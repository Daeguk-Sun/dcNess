# impl-loop 분기 규칙 SSOT

> **Status**: ACTIVE
> **Scope**: `/impl-loop` skill **단일 전용** 분기 규칙 진본 — 이 skill 안 agent/내부 step (test-engineer / engineer / impl-validator / build-worker / module-architect / canvas-design / product-acceptance) 의 결론 → 다음 호출 + retry 한도 + escalate 처리. 진행 절차(Step) 는 [`SKILL.md`](SKILL.md).
> **Cross-ref**: 순서 차단 훅 보존 = [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) · 권한 경계 = [`agent_boundary.py`](../../harness/agent_boundary.py) · 용어 기준 = [`terms.md`](../../docs/plugin/terms.md).

## 읽는 법

agent 는 일을 마치면 prose 마지막 단락에 *어떤 결과로 끝났는지 + 사유* 를 자기 언어로 적는다. 메인 Claude 가 그 prose 를 읽고 아래 매핑으로 다음 호출을 정한다. 이 문서는 형식 강제가 아니라 *판단 보조* — 의미만 맞으면 된다. prose 가 모호하면 사용자에게 위임한다.

분기 규칙은 **skill 이 소유**한다. agent 는 결론(enum)만 내고, "그 결론이면 다음 누구" 는 본 문서가 정한다. 같은 agent 가 다른 skill 에 나와도 그건 *그 skill 의 분기 규칙* 이지 본 문서 영역이 아니다.

**scope vs 엔진** — scope(story/epic)는 story-run state 와 PR 경계를 정하고, 엔진(풀 경로 / build-worker)은 각 task 구현 step 안의 시퀀스를 정한다 ([story/epic runner state](SKILL.md#storyepic-runner-state-1019)). 본 분기 규칙은 *엔진별* task step 결론과 merge review 경계 결론→다음을 다룬다. chain 의 task 경계 분기(`clean`/`error`/`blocked`)는 [chain 모드 task 경계 분기](#chain-모드-task-경계-분기).

**엔진 디폴트와 고위험 task 승격** — frontmatter 부재 시 기본 엔진 = build-worker 이며 개수와 무관하다. build-worker 는 비용 절감 엔진이지 보안 경계가 아니다. 고위험 trigger 는 **구현 시점 위험** 기준으로만 본다. 이 엔진 판정 기준은 [`module-architect`](../../docs/plugin/agents/module-architect/module-architect-agent.md) 가 소유하며, [`workflow-router.md`](../../docs/plugin/workflow-router.md) high-risk trigger 표는 설계 선행 판정 전용이다. 구현 시점 위험 = migration/destructive change, auth/security/PII/compliance(규제·보안 의미 한정), public API breakage, 외부 HTTP·네트워크 어댑터, URL·파일·사용자 입력 등 신뢰 경계 밖 입력 파싱, 신규 3rd-party dependency·외부 서비스 도입. cross-module / cross-story interface, 플랫폼 SDK 표준 사용, 플랫폼 런타임 권한 요청 흐름, decision 으로 이미 합의된 invariant 구현은 단독 승격 사유가 아니다. 일반 UI/문구/순수 내부 도메인 task 는 build-worker 경량 경로를 유지한다. 수직 슬라이스 + 플랫폼 SDK 표준 사용 + 런타임 권한 요청 흐름만 있으면 `engine: 2agent`; destructive schema 변경 또는 신뢰 경계 밖 입력 파싱이면 `engine: 4agent`. **이 판정의 진본 = impl 문서 frontmatter 의 `risk`/`engine` (#703)**: frontmatter `risk: high` → 풀 경로 승격, frontmatter `engine: 4agent` → 풀 경로 · `engine: 2agent` → build-worker. 설계자(module-architect)가 task 를 자르는 시점에 박은 값이라 진입마다 재추론하지 않는다. 단 **유효한 단일 값일 때만** 신뢰한다 — 템플릿 placeholder(`risk: normal|high|low` 처럼 `|` 포함)·빈 값은 부재로 간주해 추론으로 떨어진다([`SKILL.md`](SKILL.md) placeholder 가드). frontmatter 에 risk 필드가 **없거나 placeholder 일 때만** 메인이 같은 구현 시점 위험 기준으로 추론한다(하위호환). 어느 경로든 결과를 task1 진입 전 dry preview 표의 `risk / engine / reason` 열에 남기고, `risk: high` slug 를 `wave-plan --high-risk` 입력으로 도출한다([병렬 wave](SKILL.md#병렬-wave-opt-in-chain-한정)). 구현 시점 위험 trigger 는 build-worker 선호보다 우선하며, 사용자 엄정 발화 override(`엄정|꼼꼼|제대로|풀|rigor`)도 풀 경로 승격 사유다. build-worker 디폴트는 디폴트 근거(`reason=engine 미지정 + 고위험 trigger 없음`)를, 풀 경로 승격은 `reason` 에 승격 근거를 기록한다.

**verify-only 예외** — task 산출물이 코드 변경이 아니라 검증 결과이고 검증 exit 0 + 변경 0 이면 PR 생성이 정상적으로 생략된다. 이때 `impl-validator:VERIFY_ONLY` prose `PASS` 기록을 clean 증거로 삼고 `pr-create.sh` 를 호출하지 않는다. 검증 실패나 BROKEN 확인 시 일반 impl 수정 경로로 전환한다.

**impl-validator 머지 리뷰 단위** — `impl-validator` 는 story 내부 구현 단계 검증자가 아니라 merge candidate diff 를 보는 머지 리뷰어다. 단일 story 또는 `/impl` PR 은 그 PR diff 를 본다. 다중 story / epic / 통합 브랜치처럼 여러 story PR 또는 fix PR 이 하나의 invocation 결과를 이루면 개별 PR 을 순차 리뷰하지 않고, 마지막 통합→main 머지 전 합쳐진 diff 를 1회 통합 리뷰한다. 아래 그래프의 story PR edge 는 현재 runner 의 가장 가까운 merge boundary 표현이며, #1023 방향의 배치 driver 에서는 invocation 끝의 combined diff 리뷰로 해석한다.

## 분기 그래프

### 엔진 A — 풀 경로 (승격 전용)

```mermaid
flowchart TB
  TE[test-engineer] -->|TESTS_WRITTEN| EN[engineer:IMPL]
  EN -->|IMPL_DONE| TC[task commit/mark]
  TC -->|story ready| MG[메인 PR 생성]
  MG --> IV[impl-validator]
  IV -->|PASS| M([메인 regular merge])
  IV -->|PASS · close 발동 PR| PA[product-acceptance]
  PA -->|PASS| M
  PA -->|FAIL ≤3 · auto-fixable gap| EN
  PA -.->|ESCALATE / round 초과 / 비자동 gap| U
  IV -->|FAIL spec-gap ≤3| EN
  IV -->|FAIL quality-gap ≤2| ENP[engineer:POLISH]
  ENP -->|POLISH_DONE| IV
  EN -->|TESTS_FAIL ≤3| EN
  EN -->|SPEC_GAP_FOUND ≤2| MA[module-architect]
  MA -->|PASS| TE
  EN -.->|IMPLEMENTATION_ESCALATE| U((사용자))
  IV -.->|ESCALATE| U

  classDef produce fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
  classDef verify fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
  classDef user fill:#eeeeee,stroke:#757575,color:#212121
  class TE,EN,ENP,MA produce
  class IV,PA verify
  class U user
```

> advanced fallback (deep task 보강 필요) → MA 선두 1 step 추가. 이것은 Lite direct 구현이 아니라 deep task 보강 경로다. UI 감지 → engine 무관 canvas-design 선두. canvas-design 은 main-owned checkpoint 이며 helper begin/end-step 비대상이다. draft 가 필요할 때 실제 Agent 호출은 별도 `begin-step designer` 로 연다. 사용자 PICK 은 draft 가 실제 생성된 경우 canvas-design 내부에서만 수행하며, canvas-design `PASS` → 선택 엔진 구현 step.

### 엔진 B — build-worker (디폴트)

```mermaid
flowchart TB
  BW[build-worker] -->|PASS| TC2[task commit/mark]
  TC2 -->|story ready| MG([메인 PR 생성])
  MG --> IV2[impl-validator]
  IV2 -->|PASS| M2([메인 regular merge])
  IV2 -->|PASS · close 발동 PR| PA2[product-acceptance]
  PA2 -->|PASS| M2
  PA2 -->|FAIL ≤3 · auto-fixable gap| EN2
  PA2 -.->|ESCALATE / round 초과 / 비자동 gap| U2
  IV2 -->|FAIL quality-gap ≤2| ENP2[engineer:POLISH] --> MGP([메인 commit/push to PR branch]) --> IV2
  IV2 -->|FAIL spec-gap ≤3| EN2
  BW -->|SPEC_GAP_FOUND small| ME([메인 직접 Edit]) --> BW
  BW -->|SPEC_GAP_FOUND medium·large ≤2| MA2[module-architect] -->|PASS| BW
  BW -->|TESTS_FAIL ≤3| EN2[engineer] -->|IMPL_DONE| TC2
  IV2 -->|PASS · 기존 PR 있음| MGF([메인 commit/push to PR branch]) --> IV2
  BW -->|VALIDATION_BLOCKED| GV([메인 게이트 대행 실행])
  GV -->|exit 0| TC2
  GV -->|게이트 FAIL ≤3| EN2
  BW -.->|IMPLEMENTATION_ESCALATE| U2((사용자))
  MA2 -.->|ESCALATE| U2

  classDef produce fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
  classDef verify fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
  classDef user fill:#eeeeee,stroke:#757575,color:#212121
  class BW,EN2,ENP2,MA2 produce
  class IV2,PA2 verify
  class U2 user
```

> 파랑 = 생산 agent · 초록 = 검증 agent · 회색 = 사용자 위임. 점선 = escalate. 엣지의 `≤N` = retry 한도 ([retry 한도](#retry-한도)).
> build-worker 는 git/PR/impl-validator 직접 호출 금지 — 권한 = engineer + test-engineer 합집합, git/PR 은 메인 위임 ([`agent_boundary.py`](../../harness/agent_boundary.py)). deep task 보강 필요 시 module-architect 선두 (3-step).
> **TESTS_FAIL 폴백 = 검증 복원 (MUST)**: build-worker 가 self-validate 미통과(TESTS_FAIL)면 engineer 가 마저 구현하되, build-worker phase 3 self-validate 가 건너뛴 검증을 merge review 경계의 **impl-validator 가 대신 수행**한다. engineer `IMPL_DONE` → task commit/mark → 메인 PR 생성 → impl-validator `PASS` 후에만 merge 한다. 검증 없이 degraded 산출이 PR 되는 경로 차단 (원본 `commands/impl-loop.md` "engineer 단발 진입" 정합).
> **VALIDATION_BLOCKED 폴백 = 메인 게이트 대행 (MUST)**: build-worker 가 환경 제약(도구 차단·의존성 부재 등)으로 검증 명령을 실행하지 못했다고 보고하면, 메인이 worker 가 남긴 검증 명령을 같은 cwd(worktree)에서 직접 실행해 종료코드로 판정을 복원한다. exit 0 → `PASS` 와 동일 진행(task commit/mark → 다음 task 또는 merge review 경계) · 게이트 FAIL → engineer 재시도(TESTS_FAIL 경로 합류, ≤3) · 메인에서도 실행 불가 → 사용자 위임. 검증 미실행 상태로 PR 진행 금지 — 정적 분석만으로 PASS 를 흡수하는 false-clean 차단. chain 에서 대행 exit 0 으로 진행할 때는 다음 task 인계용 한 줄 요약(`prev-tasks-append`)도 메인이 대신 남긴다 (worker 는 PASS 일 때만 남기므로 누락되면 다음 task 의 `[PREVIOUS_TASKS]` 가 빈다). headless build-worker 의 `VALIDATION_BLOCKED` 는 `ledger.jsonl` 의 `blocked/category=headless_validation_blocked` 이벤트로도 확인한다.

## 결론 → 다음 호출 매핑

| agent | 결론 → 다음 호출 |
|---|---|
| **test-engineer** | `TESTS_WRITTEN`(=PASS) → engineer(attempt 0) · `SPEC_GAP_FOUND` → module-architect(보강) |
| **engineer** | task 구현 step `IMPL_DONE` → task commit/mark 후 다음 task 또는 merge review 경계 · merge review finding 수정 `IMPL_DONE`/`POLISH_DONE` → 메인 commit/push to PR branch 후 impl-validator 재검증 · `IMPL_PARTIAL` → engineer(분할 — retry 아님, 상한 없음 [retry 한도](#retry-한도)) · `SPEC_GAP_FOUND` → module-architect(보강, ≤2) · `TESTS_FAIL` → engineer 재시도(≤3) · `IMPLEMENTATION_ESCALATE` → 사용자 |
| **impl-validator** | merge review 경계에서 `PASS` → (CI PASS 후) 메인 regular merge — **단 story/epic close 발동 PR 은 merge 전 product-acceptance 선행** ([마감 acceptance 분기](#마감-acceptance-분기)) · `FAIL`(`[spec-gap]` 포함) → 해당 diff 의 원인 task/branch 를 구현 수정 경로로 재진입(≤3) · `FAIL`(`[quality-gap]`만) → 품질 수정 경로 → **메인 commit/push to PR branch 또는 fix PR** → impl-validator 재검증(≤2) · `ESCALATE`(spec 부재) → module-architect(보강) · 그 외 `ESCALATE` → 사용자. impl 문서 경로와 merge candidate diff 로 scope 자동 분기 |
| **build-worker** | task step `PASS` → `dcness-story-runner mark --status completed --commit <sha>` 후 다음 task 또는 merge review 경계 · `SPEC_GAP_FOUND` → 분량 메타 분기(아래) · `TESTS_FAIL` → engineer(마저 구현) → **`IMPL_DONE` → task commit/mark** (merge review 경계에서 impl-validator 가 검증 복원 — 검증 없이 PR 금지) 또는 attempt 한도 초과 시 사용자 · `VALIDATION_BLOCKED` → **메인이 worker 가 남긴 검증 명령을 직접 실행(게이트 대행)** — exit 0 → task commit/mark · 게이트 FAIL → engineer 재시도(TESTS_FAIL 경로 합류, ≤3) · 메인도 실행 불가 → 사용자 · `IMPLEMENTATION_ESCALATE` → 사용자 |
| **module-architect** | `PASS` → (impl 파일 생성·보강 후) build-worker 또는 test-engineer · `ESCALATE` → 사용자 |
| **canvas-design** | `PASS` → 선택 엔진 구현 step(build-worker 또는 test-engineer) · `ESCALATE` → 사용자. main-owned checkpoint 라 helper begin/end-step 비대상이며, draft 생성 시 실제 designer Agent 는 별도 `begin-step designer` 로 호출한다. 사용자 PICK 은 canvas-design 내부 조건부 절차로 처리한다. 산출물은 `docs/design-variants/<screen-id>.html` 확정본 + `canvas.html` frame 등록 + node-id 매핑. draft 재생성 한도 X |
| **product-acceptance** | close 발동 story/epic PR 한정 (impl-validator PASS 후 · pr-finalize 전, [마감 acceptance 분기](#마감-acceptance-분기)). `PASS` → 메인 pr-finalize 머지 (epic 마감은 STORY → EPIC 2회 모두 PASS 후) · `FAIL` (auto-fixable gap: PRD/AC 미충족, 검수 증거 부족, 스모크 실패, mock-only green / 동작 증거 부족, 명확한 구현 보강으로 닫히는 사용자 동선 부적합) → engineer:IMPL 재진입(gap 수정 — POLISH 아님, run 의 `--design-doc` 사전 조건 사용) → story PR 에 commit/push → impl-validator 재검증 → product-acceptance 재검수 (round ≤3) · `FAIL` (설계 결함·범위 재정의·사용자/UX 선택 필요·보안/권한/데이터 gap) 또는 round 초과 → 정지 + 사용자 위임 · `ESCALATE` → 정지 + 사용자 위임 |

**build-worker `SPEC_GAP_FOUND` 분량 메타 분기** (외부 사용자 [F4 실측](https://github.com/alruminum/dcNess/issues/506)):
- **small** (1 enum 값 / 1 필드 / 1 메서드 시그니처) → 메인이 직접 Edit (대상 epic `impl/NN-*.md` / `domain-model.md`) + build-worker 재호출. **cycle 카운트 불포함** (경량 예외).
- **medium / large** (multiple field / 새 module / 도메인 모델 변경) → module-architect (보강) → build-worker 재호출 (cycle ≤2).

## retry 한도

| 재시도 경로 | 한도 | 초과 시 |
|---|---|---|
| engineer attempt (TESTS_FAIL → 재시도) | 3 | `IMPLEMENTATION_ESCALATE` |
| engineer SPEC_GAP_FOUND → module-architect 보강 → engineer 재진입 | 2 | `IMPLEMENTATION_ESCALATE` |
| impl-validator `FAIL`(`[spec-gap]` 포함) → engineer:IMPL 재진입 | engineer attempt 흡수 | engineer attempt 한도(3) 도달 시 escalate |
| impl-validator `FAIL`(`[quality-gap]`만) → engineer:POLISH 라운드 | 2 | 사용자 escalate |
| build-worker `SPEC_GAP_FOUND`(medium/large) → module-architect 보강 → build-worker 재진입 | 2 | 사용자 위임 |
| build-worker `VALIDATION_BLOCKED` → 메인 대행 게이트 FAIL → engineer 재진입 | engineer attempt 흡수 | engineer attempt 한도(3) 도달 시 사용자 위임 |
| build-worker phase 2 (TESTS_FAIL → src retry, worker 내부) | 3 (worker 내부) | `TESTS_FAIL` emit → 메인이 engineer 재호출 또는 사용자 위임 |
| chain task 자동 재시도 (`--retry-limit`) | 3 (default, 0 = 첫 실패 즉시 정지) | 정지 + 사용자 위임 |
| product-acceptance `FAIL` → gap 수정 → 재검수 round (story/epic 경계당 독립 카운트) | 3 | 정지 + 사용자 위임 |

> **분할(IMPL_PARTIAL)은 retry 아님** — engineer 가 단일 호출에 다 못 끝내 남은 작업을 명시하고 재호출되는 것. attempt 카운터 미소비, 상한 없음 (자율 판단). 실패 재시도(retry, 한도 있음)와 구분.
> cycle 발생 시 **working tree only — commit X.** PASS 후에만 commit.
> `.attempts.json` = fail_type → 카운터 매핑. force-retry 시 리셋.

> **finding 수용 자세** (점 패치 X, 근본 재설계) — impl-validator finding 이 같은 task 의 같은 파일·주제·위험 클래스에서 2회+ 반복되면 단순 POLISH 재진입을 멈추고 "클래스형 결함 의심 — 점 수정 금지"를 명시한다. 코드 내 root cause 가 보이면 근본 재설계 후 1회 재검증하고, 스펙·설계 차원이면 `SPEC_GAP_FOUND` 로 module-architect 보강한다. root cause 를 특정할 수 없거나 retry 한도에 닿으면 사용자 escalate 다. 진본 = [`loop-procedure.md` finding 수용 원칙](../../docs/plugin/loop-procedure.md#finding-수용-원칙-점-패치-금지-근본-수정).

## 마감 acceptance 분기

story/epic close 를 실제 발동하는 PR 의 impl-validator `PASS` 후 · pr-finalize(머지) *전* 에 product-acceptance 검수를 끼운다 (절차·경계 판정·시점 전제조건 = [`SKILL.md` 마감 acceptance](SKILL.md#마감-acceptance) — 병렬 peer 는 같은 story sibling 완료 확인 후, 통합 브랜치 모드는 sub-PR 이 아니라 마지막 main 머지 PR 전). 기본 ON, `--no-acceptance` 명시 run 만 비대상. epic 마감 PR 은 `STORY_ACCEPTANCE` → `EPIC_ACCEPTANCE` 직렬 2회 — 앞이 PASS 못 닫으면 뒤로 진행하지 않는다.

책임 소재: impl-validator 는 계획 대비 구현 정합과 merge candidate diff 위험을 함께 본다. 여러 PR 이 합쳐진 story 동작과 여러 story 가 합쳐진 epic 동작·사용자 동선은 마감 product-acceptance 가 맡는다. 핵심 AC 가 mock-only green 으로만 뒷받침되고 실제 제품 경계(API/CLI/UI/통합 wiring/compile-time contract)가 확인되지 않았으면 gap 이다. UI story/epic 은 확정 목업 경로와 구현 화면 스크린샷 또는 동등한 화면 증거 경로를 prompt 에 담아 product-acceptance 가 Read 로 양쪽을 열고 레이아웃 계층·상태(default/empty/error 등)·토큰 대응을 판정하게 한다. 화면 증거가 없으면 `화면 증거 부재`, 확정 목업과 구조적으로 어긋나면 `목업 불일치` gap 이다. 핵심 AC 가 실행되더라도 non-developer 대상 사용자가 내부 schema/payload/config shape 를 조립해야만 수행할 수 있으면 사용자 동선 부적합 gap 이다.

마감 acceptance 대상 story PR run 은 `begin-run impl --acceptance-required` marker 를 기록한다. 이 marker 가 있어야 Stop hook 이 impl-validator 를 종료 agent 로 보지 않고 product-acceptance 분기 turn 을 재발화한다. 비대상 run / `--no-acceptance` / verify-only 는 marker 를 기록하지 않아 기존 종료 동작을 유지한다.

standalone `/acceptance` 의 분기 규칙([`acceptance-routing.md`](../acceptance/acceptance-routing.md) — 자동 수정 X, 보고만)과 **별개** — 같은 agent 지만 inline 검수의 결론→다음은 본 문서가 소유한다 (위 "분기 규칙은 skill 이 소유" 원칙). inline 검수에서 gap 수정 루프가 도는 이유: 마감 PR 이 아직 열려 있어 gap 수정이 같은 PR 의 commit 으로 수렴 가능한 시점이기 때문이다.

**`FAIL` → gap 분류 분기** (gap taxonomy = [`acceptance-routing.md`](../acceptance/acceptance-routing.md) 기준):

| gap 종류 | 다음 |
|---|---|
| PRD / AC 미충족 · 검수 증거 부족 · 스모크 실패 (auto-fixable) | engineer:IMPL 재진입(gap 수정 — POLISH 아님: POLISH 는 impl-validator finding 전용·로직 변경 금지 모드, [`engineer-agent.md`](../../docs/plugin/agents/engineer/engineer-agent.md) 정합). build-worker 엔진도 run 시작 시 `--design-doc <task impl 문서>` 를 기록하므로 engineer gate 를 통과한다. → `IMPL_DONE` → lint/build/test green → 메인 commit/push to PR branch → impl-validator 재검증 → product-acceptance 재검수 (round ≤3) |
| mock-only green / 동작 증거 부족 (auto-fixable) | engineer:IMPL 재진입. 핵심 AC 를 닫을 수 있는 자동 동작 증거를 추가한다. 사람 E2E 만 요구하지 않고 정적 타입검사/compile, 실데이터(non-mock) 통합 테스트, UI 자동화, API/CLI smoke 중 AC 성격에 맞는 증거를 보강한다. |
| 화면 증거 부재 (auto-fixable) | engineer:IMPL 재진입. 프로젝트가 선택한 UI 자동화, visual smoke, 스크린샷 산출물 등 실제 구현 화면 증거를 추가한다. dcNess 는 스크린샷 생성 도구를 배포하지 않고, 증거 요구와 판정만 담당한다. |
| 목업 불일치 (구현 보강으로 닫힘) | engineer:IMPL 재진입. 확정 목업 대비 레이아웃 계층, 상태(default/empty/error 등), 토큰 대응을 맞추거나 의도적 차이를 구현/검수 증거에 명시한다. |
| 목업 불일치 (사용자/UX 선택 필요) | 정지 + 사용자 위임 (`/ux` 후보 제시) |
| 사용자 동선 부적합 / 내부 계약 노출 (명확한 구현 보강) | engineer:IMPL 재진입. 대상 사용자에게 맞는 제품 언어의 입력/진행 동선을 추가하고, 내부 schema/payload/config shape 조립을 사용자 흐름 밖으로 숨기거나 공개 계약으로 정리한다. |
| 사용자 동선 부적합 / 내부 계약 노출 (사용자/UX 선택 필요) | 정지 + 사용자 위임 (`/ux`·`/design`·`/spec` 회수 후보 제시) |
| 설계 결함 / 범위 재정의 필요 | 정지 + 사용자 위임 (`/design` 회수 또는 요구사항 명확화 후보 제시) |
| 성능 병목 / 리팩토링 필요 | 정지 + 사용자 위임 (마감 PR 범위 초과 가능성 — follow-up `/to-issue` 후보 제시. 사용자가 본 PR 범위 내 수정을 지시한 경우에만 auto-fixable 루프 재사용) |
| 보안 / 권한 / 데이터 리스크 | 정지 + 사용자 위임 |
| UX 미완성 | 정지 + 사용자 위임 (`/ux` 후보 제시) |

- gap 수정도 [finding 수용 자세](#retry-한도) 를 따른다 — 같은 클래스 gap 이 반복되면 점 패치 대신 root cause 를 의심한다.
- 정적 타입검사나 compile gate 가 의미 있는 stack 인데 증거에 없으면 product-acceptance 가 품질 게이트 warning 으로 남긴다. warning 자체는 자동 FAIL 이 아니지만, 핵심 AC wiring/contract 검증 부재와 결합하면 `mock-only green / 동작 증거 부족` gap 으로 승격한다.
- 개발자용 CLI/API 의 JSON/config 입력은 대상 사용자에게 자연스러운 공개 계약이면 허용한다. 단 예제·필드 의미·오류 메시지 없이 내부 shape 만 노출되면 warning 또는 `사용자 동선 부적합 / 내부 계약 노출` gap 으로 승격한다.
- **gap 수정 commit 후 재검수는 마감 시퀀스 처음부터** — epic 마감에서 STORY PASS → EPIC FAIL 로 수정 commit 이 생겼으면, 그 commit 이 마지막 story 의 동작을 바꿀 수 있으므로 이전 STORY PASS 는 stale 다. `STORY_ACCEPTANCE` 부터 다시 돌린다. clean 게이트가 인정하는 STORY/EPIC PASS 흔적은 *마지막 acceptance gap 수정 commit 이후* 의 PASS 만이다.
- round 카운트는 story 경계와 epic 경계가 독립이다 (STORY round ≤3, EPIC round ≤3). round = "FAIL → gap 수정 → 재검수" 사이클 기준 — epic fix 에 따른 확인용 STORY 재검수(수정 없음)는 STORY round 를 소비하지 않는다.
- round 초과 → 정지 + 사용자 위임: 남은 gap 목록 + follow-up 분리 후보 + 머지/보류 판단 지점을 보고한다. 사용자 결정(머지 강행 / gap 수정 계속 / follow-up 분리) 전 pr-finalize 금지.
- `ESCALATE` (기준 문서·구현 증거 부족) → 정지 + 사용자 위임 (하드스톱).
- chain 에서 acceptance 정지는 해당 task 의 `blocked` 와 동일하게 다음 task 진입을 막는다 — 검수 안 된 story 위에 다음 story 를 쌓지 않는다.

## escalate 처리

escalate 계열 결론 수신 시 **메인이 즉시 사용자 보고 후 대기** (자동 복구 / 우회 / 재시도 금지 — [`../../CLAUDE.md`](../../CLAUDE.md) 강제 영역). **단 아래 impl-validator `ESCALATE`(사유: spec 부재) 만 예외** — 그 외 모든 escalate 는 하드스톱.

- **`IMPLEMENTATION_ESCALATE`** (engineer / build-worker attempt 한도 초과) → 사용자 위임 (하드스톱).
- **`ESCALATE`** (module-architect / canvas-design) → 사용자 위임 (하드스톱).
- **impl-validator `ESCALATE` = 하드스톱 예외, 사유별 분기** ([`loop-procedure.md`](../../docs/plugin/loop-procedure.md#enum-분기) 정합): *사유 = spec 부재* → module-architect(보강 케이스) 자동 호출 (spec 갭 메움이지 trust boundary 우회 아님) · *사유 = 재시도 한도 초과 등 그 외* → 사용자 위임 (하드스톱). prose 에 사유가 모호하면 사용자 위임이 기본.
- **`blocked`** (chain task — false-clean 의심 / 권한 위반 / phase prose 부재) → 즉시 정지 + 사용자 위임 ([chain 모드 task 경계 분기](#chain-모드-task-경계-분기)).
- **product-acceptance `ESCALATE` / `FAIL`(round 초과·비자동 gap)** → 정지 + 사용자 위임 (하드스톱 — [마감 acceptance 분기](#마감-acceptance-분기)).

## chain 모드 task 경계 분기

chain (N task) 에서 *각 task step* 의 종료 결론에 따른 다음 task 또는 merge review 경계 진입 ([chain 모드](SKILL.md#chain-모드-storyepic-task-오케스트레이션)):

| task 결론 | 다음 |
|---|---|
| `clean` | `dcness-story-runner mark --status completed --commit <sha>` → 다음 task 또는 merge review 경계 |
| `error` | 자동 재시도 (한도 `--retry-limit`, default 3). 한도 초과 시 정지 + 사용자 위임 |
| `blocked` | 즉시 정지 + 사용자 위임 (재호출 또는 수동 처리) |

- task `clean` 판정 게이트 = selected implementation engine 이 PASS 이고 lint/build/test 근거가 있거나, build-worker `VALIDATION_BLOCKED` 를 메인 게이트 대행 exit 0 으로 복원한 상태. 대행 증거 없는 `VALIDATION_BLOCKED` 진행은 false-clean 으로 `blocked` 강등.
- story PR `clean` 판정 게이트 = story 의 모든 task completed + impl-validator PASS + 메인 PR 생성·머지 완료 흔적. 셋 중 하나 부재 → false-clean → `blocked` 강등, #431.
- **story/epic close 발동 PR 의 `clean` 판정 게이트에는 product-acceptance PASS 흔적이 추가된다** (epic 마감은 STORY + EPIC 둘 다, `--no-acceptance` 명시 run 제외) — 흔적 부재, 또는 PASS 가 마지막 acceptance gap 수정 commit *이전* 의 stale 흔적이면 false-clean 으로 `blocked` 강등 ([마감 acceptance 분기](#마감-acceptance-분기)).
- verify-only task 의 `clean` 판정 게이트 = `impl-validator:VERIFY_ONLY` prose PASS + 검증 명령 exit 0 증거 + `git status --porcelain` 변경 0. 이 경우 PR 생성·머지 흔적은 요구하지 않는다.
- 전체 완료 → 보고 (처리 task N/N + story PR URL 목록).

## 후속 (loop 종료 후)

- single clean → review.md 원본 echo (rigor) + 자율 insight 1줄 (선택).
- chain clean → 5줄 요약 echo (task 별) + 전체 완료 보고. 자율 작업 진입 전 `post-task-begin` marker (#472).
- error / blocked + 한도 초과 → 사용자 위임.
- spec gap + cycle 한도 초과 → 사용자 위임 (module-architect 보강 또는 `/design` 재진입 권고).
