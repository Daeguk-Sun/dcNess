# Handoff Matrix — Agent Routing 가이드 / Retry / Escalate / 권한

> **Status**: ACTIVE
> **Scope**: dcness 컨베이어의 *agent 측 강제 영역* SSOT — agent 결론 prose 를 보고 메인 Claude 가 다음 단계 결정할 때 참조하는 자연어 routing 가이드 / retry 한도 / escalate 카탈로그 / 접근 권한.
> **Cross-ref**: 시퀀스 spec + 7 loop 행별 풀스펙 = [`orchestration.md`](orchestration.md) §2~§4. 절차 mechanics = [`loop-procedure.md`](loop-procedure.md).

---

## 1. Agent 결론 → 다음 agent 결정 가이드 (자연어)

> agent 12 종. agent 가 prose 마지막 단락에 *어떤 결과로 끝났는지 + 메인이 누구를 부르는 게 적절한지* 자기 언어로 명시 → 메인이 prose + 아래 한눈표로 routing 결정 (enum 형식 검증 없음 — 이슈 #280). prose 가 모호하거나 결론을 추출 못 하면 사용자 위임 (prose 본문 "결정 불가" 명시 — issue #392). 본 가이드는 형식 강제가 아니라 *판단 보조* — 의미만 맞으면 OK ([`orchestration.md`](orchestration.md) §0 정체성 정합).
>
> **enum 진본 = `agents/<agent>.md` 본문 `## 결론 + 권장 다음 단계` 섹션.** 본 §1 한눈표는 그 요약 view — 분기 상세·진입 입력·self-check 의무는 각 agent 본문 참조.
>
> 평탄화·흡수 이력: architect → system-architect + module-architect 2분할, validator → code-validator + architecture-validator 2분할, security-reviewer → pr-reviewer §F-Security 흡수, design-critic → 사용자 PICK + design.md §8/code-validator grep, product-planner → 메인 직접 그릴미, plan-reviewer 폐기(이슈 #515) → tech-reviewer 가 선행 기술 검증, build-worker 신규(#446).

> 🔴 **Drift 룰 (2-way)** — agent 결론 → 다음 호출 매핑은 **`agents/<agent>.md` 본문이 진본**. 본 §1 한눈표 + [`orchestration.md`](orchestration.md) §4 loop 시퀀스는 그 view. 매핑 갱신 시 agent 본문을 먼저 고치고 view 를 동기. 신 agent 추가 / enum 추가 / cycle 한도 변경 시 적용.

### 1.0 routing 한눈표

| agent | 주요 결론 → 다음 호출 |
|---|---|
| tech-reviewer | PASS → (사용자 2차 OK) → `/architect-loop` 권고 / FAIL → PRD patch·항목 polish 후 재호출 / ESCALATE → 사용자. **단방향**: `/architect-loop` 진입 후 재호출 금지 ([`orchestration.md`](orchestration.md) §2.1.4) |
| ux-architect | UX_FLOW_READY → system-architect / UX_REFINE_READY → designer / UX_FLOW_ESCALATE → 사용자. **UI-less epic 이면 메인이 호출 안 함** ([`orchestration.md`](orchestration.md) §4.2 UI-less 분기) |
| system-architect | PASS → architecture-validator 1차 / ESCALATE → 사용자(`/product-plan`) / NEW_DEP_ESCALATE → 3안 (§3) |
| module-architect | PASS → (컨텍스트별: 다음 단위 module-architect / test-engineer / engineer / 후속 없음) / ESCALATE → 사용자 / NEW_DEP_ESCALATE → 3안 (§3). 호출 단위 = 1 Story 또는 공통 task 묶음, K = Story 수 + 공통 호출. self-check cross-task interface = PASS 게이트 |
| engineer | IMPL_DONE → code-validator / IMPL_PARTIAL → engineer(split ≤ 3) / SPEC_GAP_FOUND → module-architect(보강, ≤ 2) / TESTS_FAIL → engineer 재시도(≤ 3) / POLISH_DONE → pr-reviewer / IMPLEMENTATION_ESCALATE → 사용자 |
| test-engineer | PASS → engineer(attempt 0) / SPEC_GAP_FOUND → module-architect(보강) |
| designer | PASS → 사용자 PICK → (test 또는 impl) / ESCALATE → 사용자. 환경 감지 = `docs/design.md` frontmatter `medium`. 재호출 한도 X (사용자 자유) |
| code-validator | PASS → pr-reviewer / FAIL → engineer 재시도(≤ 3) / ESCALATE → module-architect(보강) 또는 사용자. impl 경로로 full/bugfix scope 자동 분기 |
| architecture-validator | PASS(1차) → module-architect × K / PASS(2차) → architect-loop Step 6 / FAIL → 해당 architect 재진입(cycle ≤ 2) / ESCALATE → 사용자. 두 시점 호출 — 1차(Step 3.5) = Placeholder + 공통 SSOT, 2차(Step 5) = Cross-Story Interface + Impl Simulation + Origin Anchor + Placeholder 재검증 |
| pr-reviewer | PASS → (CI PASS 후) 메인 즉시 regular merge / 변경 요청 → engineer POLISH |
| qa | FUNCTIONAL_BUG → module-architect(버그픽스) / CLEANUP → engineer(light) / DESIGN_ISSUE → designer·ux-architect(REFINE) / KNOWN_ISSUE → 종료 / SCOPE_ESCALATE → 사용자 |
| build-worker (`/impl-loop` 한정) | PASS → 메인 git/PR → pr-reviewer / SPEC_GAP_FOUND → module-architect(≤ 2) / TESTS_FAIL → engineer 재시도 또는 사용자 / IMPLEMENTATION_ESCALATE → 사용자. 권한 = engineer + test-engineer 합집합, git/PR/pr-reviewer 호출 금지(메인 위임). `/impl` 단발 미사용 |

> NEW_DEP_ESCALATE 3안 처리 = §3. Spike Gate 폐기(이슈 #511) — tech-reviewer 가 PRD 단계 외부 의존 검증 cover. 각 agent 의 진입 입력 / 산출물 / self-check 의무 / 결론 prose 표현 상세 = `agents/<agent>.md` 본문 진본.

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
| `NEW_DEP_ESCALATE` | system-architect / module-architect | architect-loop 도중 tech-review 미검증 새 외부 의존 발견 → 메인이 3안 제시 (채택+수동검증 → architect 재진입 / 대안 기술 우회 → architect 재진입 / 전체 원점 회귀). **tech-reviewer 재호출 없음 (단방향 catastrophic 보존)** |

자동 재시도 / 우회 금지. 사용자 명시 결정 후만 진행.

> `NEW_DEP_ESCALATE` 처리는 "보고 후 단순 대기"가 아니라 메인이 사용자에게 **3안 메뉴**를 제시하는 점이 일반 `ESCALATE` 와 다르다. (1)/(2) 선택 시 해당 architect 재진입 (cycle ≤ 2), (3) 선택 시 loop 중단 + `/product-plan` 재진입. 흐름 상세 = [`commands/architect-loop.md`](../../commands/architect-loop.md) `## 분기 / cycle (요약)`.

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
- `agents/*.md` — 각 agent 결론 enum 진본 (`## 결론 + 권장 다음 단계` 섹션) + prose 표현 가이드
- `harness/signal_io.py` / `harness/interpret_strategy.py` — 옛 enum 추출 인프라 (이슈 #284 폐기 진행 중)
- (issue #392 — `harness/routing_telemetry.py` 폐기. baseline 비교 끝남 + cascade marker 실측 0건)
