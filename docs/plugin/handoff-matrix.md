# Handoff Matrix — Agent Routing 가이드 / Retry / Escalate / 권한

> **Status**: ACTIVE
> **Scope**: dcness 컨베이어의 *agent 측 강제 영역* SSOT — agent 결론 prose 를 보고 메인 Claude 가 다음 단계 결정할 때 참조하는 자연어 routing 가이드 / retry 한도 / escalate 카탈로그 / 접근 권한.
> **Cross-ref**: 시퀀스 spec + 7 loop 행별 풀스펙 = [`orchestration.md`](orchestration.md) §2~§4. 절차 mechanics = [`loop-procedure.md`](loop-procedure.md).

---

## 1. Agent 결론 → 다음 agent 결정 가이드 (자연어)

> agent 12 종 — §1.1 ~ §1.12 sub-section. 평탄화·흡수 이력: architect 는 system-architect + module-architect 두 에이전트로 평탄화, validator 는 code-validator + architecture-validator 두 에이전트로 평탄화, security-reviewer 는 pr-reviewer §F-Security + architect 의 위협 모델 가정·invariant 로 흡수, design-critic 은 사용자 직접 PICK 으로 대체 + 클리셰 회피는 design.md §8 + code-validator grep 으로 흡수, product-planner 는 메인 Claude 가 사용자와 직접 그릴미 대화로 PRD/stories.md 작성 — 컨텍스트 손실 회피, plan-reviewer 가 외부 검증 담당. build-worker 는 `/impl-loop` Hybrid A (#446) 도입과 함께 신규. agent 가 자기 prose 에 결론 + 권장 다음 단계를 자유롭게 쓴다. 메인 Claude 는 그 prose 와 본 가이드를 비교해 다음 호출을 결정한다. 본 가이드는 형식 강제가 아니라 *판단 보조*. 가능한 결론 표현은 agent 별로 다양 — 의미만 맞으면 OK ([`orchestration.md`](orchestration.md) §0 정체성 정합).

> **이슈 #280 정착 후 작동 모델**:
> - agent 는 prose 마지막 단락에 *어떤 결과로 끝났는지 + 메인이 누구를 부르는 게 적절한지* 자기 언어로 명시.
> - 메인은 prose + 본 §1 가이드만으로 routing 결정. enum 형식 검증 없음.
> - prose 가 모호하거나 결론을 추출 못 하면 메인이 사용자에게 위임 (prose 본문 "결정 불가" 명시, issue #392 — routing_telemetry cascade marker 폐기).

> 🔴 **Drift 룰 (3-way cross-ref 강제)** — 본 §1 의 agent 결론 → 다음 호출 매핑 갱신 시 (1) [`orchestration.md`](orchestration.md) §4 의 해당 loop 시퀀스 (2) [`../../agents/<agent>.md`](../../agents/) 본문 `## 결론 + 권장 다음 단계` 섹션 — **3 위치 모두 동시 갱신 의무**. 같은 enum→destination 매핑이 세 시각 (agent 단위 vs loop 단위 vs agent 본문 SSOT) 에 분리 박혀 있어 한쪽만 갱신하면 drift 위험. 신 agent 추가 / 기존 enum 추가 / cycle 한도 변경 3 케이스 적용. agent 본문이 enum 의 진본 — handoff-matrix §1 은 routing 가이드, orchestration §4 는 loop sequence view.

### 1.1 plan-reviewer

PRD 외부 검증 (`FULL` 모드 default / `PRE_CHECK` 모드 — `/product-plan` 스킬의 Spike Pre-Check 단계). 세 가지 결과:

- **PRD 승인** (`PASS`) → 메인이 사용자에게 confirm 받고 다음 단계 진입 (system-architect 또는 이슈 등록). `PRE_CHECK` 모드면 PRD 작성 진입.
- **PRD 변경 요청** (`FAIL`) → 메인이 findings 항목별 *수용/거절 권장* + 사용자 confirm → 수용 항목만 메인이 `docs/prd.md` / `docs/stories.md` Edit patch. 재 review 필요 시 plan-reviewer 재호출 (cycle ≤ 2). `PRE_CHECK` 모드면 사용자 입력 재정리.
- **판정 불가** (`ESCALATE`) → 사용자 위임. 4 트리거: 외부 검증 실행 불가 / 권한 경계 밖 정보 의존 / cycle 한도 직전 동일 finding 반복 / `EXTERNAL_VERIFIED` URL 부재 PASS 시도.

> Note: 옛 product-planner sub-agent 폐기. PRD/stories.md 작성은 메인 Claude 가 사용자와 직접 그릴미 대화로 진행 (`commands/product-plan.md`). 컨텍스트 손실 회피 + 인터랙션 풀 보존. plan-reviewer 만 외부 검증으로 sub-agent 유지.

### 1.2 ux-architect

UX Flow 정의 / 변경 / refine. 산출 *전* 5 카테고리 self-check 의무 (외부 validator 부재 — 자가검증). 다음 4 결과:

- **UX Flow 신규 완성 / 변경분 patch 완료 + self-check PASS** → system-architect.
- **UI refine 완료 (기존 디자인 다듬기)** → 사용자 승인 후 designer SCREEN.
- **Flow 정의 불가 (PRD 모순 등) 또는 self-check 2 cycle 후에도 FAIL** → escalate (사용자 위임).

### 1.3 system-architect

전체 시스템 설계 hub — 도메인 모델 + 모듈 구조 + 기술 스택 + Story → impl 매핑 표 + Spike Gate. 기술 에픽 케이스는 [`agents/system-architect.md`](../../agents/system-architect.md) 본문 참조.

- **PASS** — 시스템 설계 산출 (`docs/architecture.md` + `## impl 목차` 표) 완료 → architecture-validator.
- **ESCALATE** — 기술 제약 충돌 / Spike FAIL / PRD 위반 → 사용자 위임 (`/product-plan` 재진입 권고).

### 1.4 module-architect

모듈/태스크 단위 설계 hub. 호출자 컨텍스트 (신규 story / 버그픽스 / 기존 impl 보강 / 문서 동기화) 에 따라 분량·범위 자율 판단.

- **PASS** — impl 설계문서 작성/수정 완료. 다음 단계는 컨텍스트:
  - architect-loop 안 = impl 목차 다음 행 있으면 module-architect 재호출, 마지막 행이면 loop 종료 (PR 생성/머지) → impl-task-loop 진입
  - impl-task-loop fallback = test-engineer
  - 버그픽스 케이스 = engineer (simple)
  - 보강 케이스 = engineer 재진입
  - 문서 동기화 케이스 = 후속 없음
- **ESCALATE** — PRD 변경 필요 (`/product-plan` 재진입) / 기술 제약 충돌 (사용자) / 권한·도구 부족 (사용자).

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

system-architect 산출물의 자가검증 사각지대 (Placeholder Leak + Spike Gate 2 항목) 외부 reviewer. 결론 3종:

- **PASS** → module-architect × N (impl 목차 첫 행부터 순차).
- **FAIL** → system-architect 재진입 (cycle 한도 2). 본문에 placeholder 위치 / Must 기능 직결 / spike 권고 명시.
- **ESCALATE** → system-architect 재설계 1 cycle 후에도 동일 FAIL → 사용자 위임.

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
| engineer split (IMPL_PARTIAL → 재호출, DCN-30-34) | 3 | `IMPLEMENTATION_ESCALATE` (작업 분해 부족 — system-architect 재진입 권고 / impl 목차 분할 재검토) |
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
| `ESCALATE` | system-architect / module-architect | 기술 제약 충돌 / PRD 변경 필요 / Spike FAIL / 권한 부족 (본문 사유 명시) |

자동 재시도 / 우회 금지. 사용자 명시 결정 후만 진행.

---

## 4. 접근 권한 매트릭스

> dcness 의 두 번째 강제 영역 = "접근 영역" ([`orchestration.md`](orchestration.md) §0 정합).

> 🔴 **Drift 룰 (양방향 cross-ref 강제)** — 본 §4.1 ALLOW_MATRIX 또는 §4.2 READ_DENY_MATRIX 갱신 시 [`../../agents/<agent>.md`](../../agents/) 본문 `## 권한 경계` 섹션도 동시 갱신 의무. agent 본문이 자기 권한 경계의 자세한 (catastrophic) 명세 + 본 §4 는 매트릭스 view. 신 agent 추가 / 권한 path 추가·변경 시 양쪽 갱신. agent 본문이 진본, §4 는 일람표.

### 4.1 Write/Edit 허용 경로 (ALLOW_MATRIX)

| 에이전트 | 허용 경로 |
|---|---|
| engineer | `src/**` |
| system-architect / module-architect | `docs/**` |
| designer | `design-variants/<screen-id>-v<N>.html` + `docs/design.md` (Components 섹션 + frontmatter `components` 토큰 한정 — 시스템 레벨 토큰은 ux-architect 영역) |
| test-engineer | `src/__tests__/**`, `*.test.*`, `*.spec.*` |
| ux-architect | `docs/ux-flow.md` + `docs/design.md` 시스템 레벨 (Colors / Typography / Layout / Shapes / Elevation 섹션 + frontmatter `colors` / `typography` / `rounded` / `spacing` 토큰 — components 영역은 designer 전용) |
| qa | (Issue tracker mutation 만, 파일 X) |
| build-worker (`/impl-loop` 한정) | engineer + test-engineer 합집합 (`src/**`, `src/__tests__/**`, `*.test.*`, `*.spec.*`) + phase prose `<run_dir>/build-{test,impl,validate}.md` |
| code-validator / architecture-validator / pr-reviewer / plan-reviewer | (없음 — 판정 전용) |

### 4.2 Read 금지 경로 (READ_DENY_MATRIX)

| 에이전트 | 금지 |
|---|---|
| designer | `src/` |
| test-engineer | `src/` (impl 외), 도메인 문서 |
| plan-reviewer | `src/`, `docs/impl/`, `docs/architecture.md` |

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
