# Handoff Matrix — Agent Routing 가이드 / Retry / Escalate / 권한

> **Status**: ACTIVE
> **Scope**: dcness 컨베이어의 *agent 측 강제 영역* SSOT — agent 결론 prose 를 보고 메인 Claude 가 다음 단계 결정할 때 참조하는 자연어 routing 가이드 / retry 한도 / escalate 카탈로그 / 접근 권한.
> **Cross-ref**: 시퀀스 spec + 7 loop 행별 풀스펙 = [`orchestration.md`](orchestration.md) §2~§4. 절차 mechanics = [`loop-procedure.md`](loop-procedure.md).

---

## 1. Agent 결론 → 다음 agent 결정 가이드 (자연어)

> agent 12 종 — §1.1 ~ §1.12 sub-section. 평탄화·흡수 이력: architect 는 system-architect + module-architect 두 에이전트로 평탄화, validator 는 code-validator + architecture-validator 두 에이전트로 평탄화, security-reviewer 는 pr-reviewer §F-Security + architect 의 위협 모델 가정·invariant 로 흡수, design-critic 은 사용자 직접 PICK 으로 대체 + 클리셰 회피는 design.md §8 + code-validator grep 으로 흡수, product-planner 는 메인 Claude 가 사용자와 직접 그릴미 대화로 PRD/stories.md 작성 — 컨텍스트 손실 회피, plan-reviewer 폐기 (이슈 #515) — tech-reviewer 가 선행 기술 검증 담당 (작업 명세 형식 / 책임 2축 / Bash·Write 권한 / 증거물 + HTML 리포트). build-worker 는 `/impl-loop` Hybrid A (#446) 도입과 함께 신규. agent 가 자기 prose 에 결론 + 권장 다음 단계를 자유롭게 쓴다. 메인 Claude 는 그 prose 와 본 가이드를 비교해 다음 호출을 결정한다. 본 가이드는 형식 강제가 아니라 *판단 보조*. 가능한 결론 표현은 agent 별로 다양 — 의미만 맞으면 OK ([`orchestration.md`](orchestration.md) §0 정체성 정합).

> **이슈 #280 정착 후 작동 모델**:
> - agent 는 prose 마지막 단락에 *어떤 결과로 끝났는지 + 메인이 누구를 부르는 게 적절한지* 자기 언어로 명시.
> - 메인은 prose + 본 §1 가이드만으로 routing 결정. enum 형식 검증 없음.
> - prose 가 모호하거나 결론을 추출 못 하면 메인이 사용자에게 위임 (prose 본문 "결정 불가" 명시, issue #392 — routing_telemetry cascade marker 폐기).

> 🔴 **Drift 룰 (3-way cross-ref 강제)** — 본 §1 의 agent 결론 → 다음 호출 매핑 갱신 시 (1) [`orchestration.md`](orchestration.md) §4 의 해당 loop 시퀀스 (2) [`../../agents/<agent>.md`](../../agents/) 본문 `## 결론 + 권장 다음 단계` 섹션 — **3 위치 모두 동시 갱신 의무**. 같은 enum→destination 매핑이 세 시각 (agent 단위 vs loop 단위 vs agent 본문 SSOT) 에 분리 박혀 있어 한쪽만 갱신하면 drift 위험. 신 agent 추가 / 기존 enum 추가 / cycle 한도 변경 3 케이스 적용. agent 본문이 enum 의 진본 — handoff-matrix §1 은 routing 가이드, orchestration §4 는 loop sequence view.

### 1.1 tech-reviewer

PRD 선행 기술 검증 (`/tech-review` 스킬 안). 책임 2 축 — (1) 기술 제약 검토 (사용 가능 / 비용 / 라이선스 / 불가 시 대안 2개) (2) 용도별 스펙 깎기 (MVP 강등 / 고도화 제안). 산출 3 종 (`docs/tech-review.md` 본문 + `docs/tech-review/evidence/**` + `docs/tech-review/report.html`). 세 가지 결과:

- **검토 완료** (`PASS`) → 메인이 사용자에게 산출물 (HTML 리포트) 확인 요청 → 사용자 2 차 OK 후 `/architect-loop` 권고 echo.
- **검토 일부 불가** (`FAIL`) → 정식 항목 충족 X (4 항목 누락 / 대안 2 개 미발견 등). 메인이 사용자와 분기 토론: (a) PRD patch + `/tech-review` 재호출 / (b) 격리 후보 격상 + 재호출 / (c) 항목 polish 후 재호출.
- **검토 실행 불가** (`ESCALATE`) → 사용자 위임. 사유: WebFetch 차단 / 외부 API 인증 부재 / 권한 부족 / 사용자 환경 의존 도구 부재.

> Note: 옛 product-planner sub-agent 폐기 (메인 Claude 가 사용자와 직접 그릴미). 옛 plan-reviewer 폐기 (이슈 #515 — 8 차원 + 모드 + 사후 self-check 룰 누적 복잡도). tech-reviewer 는 stateless — 한 호출 = 한 본문 작성. 재호출 cycle 종료 신호 = 사용자 OK 만 (자가 ESCALATE 탐지 / cycle 카운터 룰 폐기). 단방향 catastrophic — `/architect-loop` 진입 후 본 agent 재호출 금지 ([`orchestration.md`](orchestration.md) §2.1.4).

### 1.2 ux-architect

UX Flow 정의 / 변경 / refine. 산출 *전* 5 카테고리 self-check 의무 (외부 validator 부재 — 자가검증). 다음 4 결과:

- **UX Flow 신규 완성 / 변경분 patch 완료 + self-check PASS** → system-architect.
- **UI refine 완료 (기존 디자인 다듬기)** → 사용자 승인 후 designer SCREEN.
- **Flow 정의 불가 (PRD 모순 등) 또는 self-check 2 cycle 후에도 FAIL** → escalate (사용자 위임).

### 1.3 system-architect

전체 시스템 그림 hub — root `docs/architecture.md` (기술 스택 + 외부 의존 + 전체 모듈 토폴로지) + root `docs/adr.md` (전체 시스템 수준 의사결정) + epic 단위 architecture.md (모듈 목록 + 의존 그래프 + 공통 task 목록 + Story → 모듈 매핑) + epic 단위 adr.md (epic 영역 결정) + epic 단위 domain-model.md (bounded context = epic). 책임 좁힘 (이슈 [#511](https://github.com/alruminum/dcNess/issues/511)) — Story → task 분할은 module-architect 영역. 공통 SSOT [`docs/plugin/module-design-principles.md`](module-design-principles.md) 의무 read.

- **PASS** — 시스템 그림 산출 완료 → architecture-validator 1차 (Step 3.5).
- **ESCALATE** — 기술 제약 충돌 / PRD 위반 → 사용자 위임 (`/product-plan` 재진입 권고).

### 1.4 module-architect

Story (또는 공통 task) 단위 설계 hub — 한 호출 = 한 단위 = N 개 impl 파일 작성 + 단위 안 task 식별 + 의존 순서 결정 + cross-task interface 정합 검증 + 도메인 sync. 호출자 컨텍스트 (신규 Story / 공통 task / 버그픽스 / 기존 impl 보강 / 문서 동기화) 에 따라 분량·범위 자율 판단. 공통 SSOT [`docs/plugin/module-design-principles.md`](module-design-principles.md) 의무 read.

- **PASS** — impl 설계문서 작성/수정 완료. 다음 단계는 컨텍스트:
  - architect-loop 안 = 다음 단위 (Story 또는 공통) 있으면 module-architect 재호출, 마지막 단위면 architecture-validator 2차 (Step 5) 진입 → loop 종료 (PR 생성/머지)
  - impl-task-loop fallback = test-engineer
  - 버그픽스 케이스 = engineer (simple)
  - 보강 케이스 = engineer 재진입
  - 문서 동기화 케이스 = 후속 없음
- **ESCALATE** — PRD 변경 필요 (`/product-plan` 재진입) / 기술 제약 충돌 (사용자) / 권한·도구 부족 (사용자).

**호출 단위 (architect-loop 안)**: 1 호출 = 1 단위 (Story 1 개 또는 공통 task 묶음) = N 개 impl 파일. K = Story 수 + 공통 호출 1 회 (있으면) 또는 0 회. batch 모드 폐기 — Story 묶음 자체가 batch 의 본질 해결 (이슈 [#511](https://github.com/alruminum/dcNess/issues/511) 본질 해결로 자연 폐기).

**self-check cross-task interface (PASS 게이트)**: 본 단위 안 task 가 같은 단위 안 다른 task 의 함수/Protocol 을 호출하면, 호출 시그니처 ↔ producer 시그니처 grep 으로 직접 확인 + prose 증거 명시. 본 항목 부재 → 외부 reviewer (architecture-validator 2차) 가 *Story 간* 시야에서 다시 검증.

### 1.5 engineer

구현 hub. 결과 종류:

- **구현 완료 (기능 검증 가능)** → code-validator (impl 파일 경로로 full/bugfix scope 자동 분기).
- **부분 구현 (분량 초과로 split 필요)** → engineer 재호출 (split 한도 3, 새 context window — DCN-30-34).
- **SPEC GAP 발견 (스펙 모호 / 부족)** → module-architect (보강 케이스, attempt < 2). 한도 초과면 escalate.
- **테스트 실패 (재구현 필요)** → engineer 재시도 (attempt < 3). 한도 초과면 escalate.
- **POLISH 단계 마무리** → pr-reviewer 재호출.
- **escalate** (구현 불가 / 한도 초과) → 사용자 위임.

### 1.6 test-engineer

테스트 코드 선작성 (TDD). 결과:

- **테스트 준비 완료** → engineer (attempt 0 진입).
- **스펙 부족해 테스트 작성 불가** → module-architect (보강 케이스).

### 1.7 designer

UI 시안 1개 생성. 다중 시안 비교·점수 심사 단계 폐기 (사용자가 마지막 PICK 하므로 critic 대리 판단 중복). 환경 감지 = `docs/design.md` frontmatter `medium: pencil|html`. 결과:

- **시안 준비 완료** → 사용자 직접 확인 (Pencil 캔버스 또는 `design-variants/<screen>-v<N>.html`). 사용자 PICK 후 다음 단계 (test 또는 impl).
- **시안 거절** → 사용자가 designer 재호출 자유 결정 (한도 명시 X).
- **시안 생성 불가** → escalate (사용자 위임).

### 1.8 code-validator

impl 계획 ↔ 구현 코드 일치 검증. impl 파일 경로 (`docs/impl/NN-*.md` 또는 `docs/bugfix/#N-slug.md`) 로 full/bugfix scope 자동 분기. 결론 3종:

- **PASS** → pr-reviewer.
- **FAIL** → engineer 재시도 (attempt < 3).
- **ESCALATE** → impl 계획 + 대체 소스 모두 부재 / 재시도 한도 초과. 본문 사유 명시 → 메인이 사유 보고 module-architect (보강 케이스) 호출 또는 사용자 위임.

### 1.9 architecture-validator

system-architect / module-architect 산출물의 자가검증 사각지대 외부 reviewer. 4 영역 — **Placeholder Leak + Cross-Story Interface 정합성 + 공통 SSOT 룰 위반 + Implementation Simulation (사전부검)**. Spike Gate 폐기 (이슈 [#511](https://github.com/alruminum/dcNess/issues/511)) — tech-reviewer 가 PRD 단계에서 외부 의존 검증 cover.

`/architect-loop` 안에서 두 시점에 호출:

- **Step 3.5 (1차)** — system-architect PASS 직후. Placeholder Leak + 공통 SSOT 룰 자동 영역 검증. Cross-Story Interface / Implementation Simulation 은 N/A (impl 파일 미작성).
- **Step 5 (2차)** — module-architect × K 다 끝난 후. Cross-Story Interface 정합성 + Implementation Simulation (대표 impl task 2~3 개 cold-seat 시뮬레이션 — 표시 없는 암묵 gap) + Placeholder Leak 재검증.

결론 3종:

- **PASS** (Step 3.5) → module-architect × K (공통 task 있으면 공통부터, 이후 Story 순차).
- **PASS** (Step 5) → architect-loop Step 6 (PR + 머지).
- **FAIL** (Step 3.5) → system-architect 재진입 (cycle 한도 2). 본문에 placeholder 위치 / Must 기능 직결 / 공통 SSOT 룰 위반 위치 명시.
- **FAIL** (Step 5) → 해당 module-architect 재진입 (Cross-Story Interface 영역 또는 Implementation Simulation gap 보강) 또는 system-architect 재진입 (모듈 의존 그래프 영역). cycle ≤ 2
- **ESCALATE** → 재설계 1 cycle 후에도 동일 FAIL → 사용자 위임.

### 1.10 pr-reviewer

merge 직전 코드 품질 + 보안 코드 패턴 심사:

- **PASS** → CI PASS 후 메인이 즉시 regular merge.
- **변경 요청** → engineer POLISH 재호출.

### 1.11 qa

이슈 분류 hub. 5 결과:

- **기능 버그** → module-architect (버그픽스 케이스).
- **간단 cleanup** → engineer 직접 (light).
- **디자인 이슈** → designer 또는 ux-architect (REFINE).
- **알려진 이슈** → 후속 없음.
- **분류 불가 (escalate)** → 사용자 위임.

### 1.12 build-worker (`/impl-loop` 한정)

`/impl-loop` driver 의 task 1개의 build 단계 (test + impl + self-validate) 통합 worker. `/impl` 단발 호출에서는 미사용 (4-agent 모델 유지). 4 결과:

- **PASS** → 메인이 git/PR 생성 → pr-reviewer Agent 호출.
- **SPEC_GAP_FOUND** → module-architect (보강 케이스, cycle ≤ 2).
- **TESTS_FAIL** → engineer 재시도 또는 사용자 위임 (worker 내부 attempt 한도 3 이미 소진).
- **IMPLEMENTATION_ESCALATE** → 사용자 위임.

권한 경계 = engineer + test-engineer 합집합. git/PR/pr-reviewer 호출 금지 (메인 위임). 자세히 = [`agents/build-worker.md`](../../agents/build-worker.md).

---

## 2. Retry 한도

> RWHarness `harness-architecture.md` §4.3 핵심 상수 + impl_loop 정책 정합. dcNess 는 boolean Flag 대신 `.claude/harness-state/<run_id>/.attempts.json` 카운터로 표현.

| 항목 | 한도 | 초과 시 |
|---|---|---|
| engineer attempt (TESTS_FAIL → 재시도) | 3 | `IMPLEMENTATION_ESCALATE` |
| engineer split (IMPL_PARTIAL → 재호출, DCN-30-34) | 3 | `IMPLEMENTATION_ESCALATE` (작업 분해 부족 — module-architect 재진입 권고 / Story 분할 재검토) |
| engineer SPEC_GAP_FOUND → module-architect (보강) → engineer 재진입 | 2 | `IMPLEMENTATION_ESCALATE` |
| code-validator FAIL → engineer 재진입 | engineer attempt 흡수 | engineer attempt 한도 (3) 도달 시 escalate |
| architecture-validator FAIL → system-architect 재진입 | 2 cycle | 사용자 위임 |
| pr-reviewer FAIL → POLISH 라운드 | 2 | 사용자 escalate |
| build-worker phase 2 (TESTS_FAIL → src retry, `/impl-loop` 한정) | 3 (worker 내부) | `TESTS_FAIL` emit → 메인이 engineer 재호출 또는 사용자 위임 |
| ESCALATE 누적 (동일 fail_type) | 2 | module-architect (보강 케이스) 자동 호출 |

`.attempts.json` = fail_type → 카운터 매핑 (예: `{"code_validation": 2, "spec_gap": 1}`). force-retry 시 리셋.

---

## 3. Escalate 조건 카탈로그

다음 결론 enum 수신 시 **메인 Claude / driver 가 즉시 사용자 보고 후 대기** ([`orchestration.md`](orchestration.md) §0 정합 — 자동 복구 금지):

| Enum | 출처 agent | 의미 |
|---|---|---|
| `IMPLEMENTATION_ESCALATE` | engineer | 재시도 한도 초과 또는 구현 불가 |
| `UX_FLOW_ESCALATE` | ux-architect | UX Flow 정의 불가 (PRD 모순 등) |
| `ESCALATE` | designer | 시안 생성 불가 (외부 의존 부재 / 컨텍스트 모호 / 권한 부족) |
| `SCOPE_ESCALATE` | qa | 이슈 범위가 분류 enum 5개 모두 해당 안 됨 |
| `ESCALATE` | system-architect / module-architect | 기술 제약 충돌 / PRD 변경 필요 / 권한 부족 (본문 사유 명시) |

자동 재시도 / 우회 금지. 사용자 명시 결정 후만 진행.

---

## 4. 접근 권한 매트릭스

> dcness 의 두 번째 강제 영역 = "접근 영역" ([`orchestration.md`](orchestration.md) §0 정합).

> 🔴 **Drift 룰 (양방향 cross-ref 강제)** — 본 §4.1 ALLOW_MATRIX 또는 §4.2 READ_DENY_MATRIX 갱신 시 [`../../agents/<agent>.md`](../../agents/) 본문 `## 권한 경계` 섹션도 동시 갱신 의무. agent 본문이 자기 권한 경계의 자세한 (catastrophic) 명세 + 본 §4 는 매트릭스 view. 신 agent 추가 / 권한 path 추가·변경 시 양쪽 갱신. agent 본문이 진본, §4 는 일람표.

### 4.1 Write/Edit 허용 경로 (ALLOW_MATRIX)

| 에이전트 | 허용 경로 |
|---|---|
| engineer | `src/**` |
| system-architect | `docs/architecture.md` + `docs/adr.md` + `docs/milestones/**/architecture.md` + `docs/milestones/**/adr.md` + `docs/milestones/**/domain-model.md` + 분리 detail 파일 (`docs/architecture/<topic>.md`, `docs/domain/<aggregate>.md`) |
| module-architect | `docs/milestones/**/impl/**` + `docs/milestones/**/architecture.md` + `docs/milestones/**/domain-model.md` + `docs/bugfix/**` |
| designer | `design-variants/<screen-id>-v<N>.html` + `docs/design.md` (Components 섹션 + frontmatter `components` 토큰 한정 — 시스템 레벨 토큰은 ux-architect 영역) |
| test-engineer | `src/__tests__/**`, `*.test.*`, `*.spec.*` |
| ux-architect | `docs/ux-flow.md` + `docs/design.md` 시스템 레벨 (Colors / Typography / Layout / Shapes / Elevation 섹션 + frontmatter `colors` / `typography` / `rounded` / `spacing` 토큰 — components 영역은 designer 전용) |
| qa | (Issue tracker mutation 만, 파일 X) |
| build-worker (`/impl-loop` 한정) | engineer + test-engineer 합집합 (`src/**`, `src/__tests__/**`, `*.test.*`, `*.spec.*`) + phase prose `<run_dir>/build-{test,impl,validate}.md` |
| code-validator / architecture-validator / pr-reviewer | (없음 — 판정 전용) |
| tech-reviewer | `docs/tech-review.md` + `docs/tech-review/**` (evidence 파일 + report.html). 그 외 모든 경로 Write 금지. |

### 4.2 Read 금지 경로 (READ_DENY_MATRIX)

| 에이전트 | 금지 |
|---|---|
| designer | `src/` |
| test-engineer | `src/` (impl 외), 도메인 문서 |
| tech-reviewer | `src/`, `docs/impl/`, `docs/architecture.md`, `docs/adr.md` |

### 4.3 인프라 패턴 (전 에이전트 공통 차단)

전 sub-agent 의 인프라 path Write 차단 (`.claude/`, `hooks/`, `harness/*.py`, `docs/plugin/*.md`, `scripts/*.mjs`, repo root `CLAUDE.md` 등). 정확한 패턴 = **코드 SSOT [`harness/agent_boundary.py`](../../harness/agent_boundary.py) `DCNESS_INFRA_PATTERNS`**.

> **`CLAUDE.md` 보호 (회귀 방지)**: 외부 활성 프로젝트의 repo root `CLAUDE.md` (메인 Claude 가 매 turn 자동 read 하는 SSOT) 는 본 패턴에 포함되어 sub-agent Write 차단. 메인 Claude 직접 편집 (active_agent 미설정 = 통과) 또는 `.no-dcness-guard` opt-out 마커로만 우회 가능.

인프라 프로젝트(`is_infra_project()` True) 에선 위 패턴 해제 (dcness 자체 작업 시 본 SSOT 들도 편집 가능해야 함).

### 4.4 인프라 프로젝트 판정

RWHarness 4 신호 OR 정합:

1. `DCNESS_INFRA=1` 환경변수
2. 마커 파일 `~/.claude/.dcness-infra` 존재
3. `CLAUDE_PLUGIN_ROOT` 환경변수 non-empty
4. `cwd.resolve() == Path("/Users/<user>/project/dcness")` (또는 화이트리스트 매칭)

> **코드 강제**: `harness/agent_boundary.py` 가 본 spec 의 SSOT 구현. `hooks/file-guard.sh` (PreToolUse Edit/Write/Read/Bash) + `hooks/post-agent-clear.sh` (PostToolUse Agent) 가 활성화. opt-out 마커 = `.no-dcness-guard` (cwd) — 사용자 임시 우회.

---

## 5. 참조

- [`orchestration.md`](orchestration.md) — 시퀀스 catalog (§2 게이트 + §3 진입 경로 + §4 7 loop 행별 풀스펙)
- [`loop-procedure.md`](loop-procedure.md) — Step 0~8 mechanics
- [`orchestration.md`](orchestration.md) §0 — 강제 영역 2가지 (대 원칙)
- `agents/*.md` — 각 agent 의 결론 prose 표현 가이드
- `harness/signal_io.py` / `harness/interpret_strategy.py` — 옛 enum 추출 인프라 (이슈 #284 폐기 진행 중)
- (issue #392 — `harness/routing_telemetry.py` 폐기. baseline 비교 끝남 + cascade marker 실측 0건)
