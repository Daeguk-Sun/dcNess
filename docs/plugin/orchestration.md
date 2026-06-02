# Orchestration Rules — dcNess SSOT

> **Status**: ACTIVE
> **Scope**: dcNess 가 plugin 으로 배포돼 *사용자 프로젝트* 에서 활성화될 때의 시퀀스 / 진입 경로 / 7 loop 행별 풀스펙 SSOT.
> **본 문서 = "what"** (어떤 시퀀스 / 어떤 loop / 라우팅 / retry — §3). **mechanics ("how")** = [`loop-procedure.md`](loop-procedure.md). **권한 강제 ("who")** = [`harness/agent_boundary.py`](../../harness/agent_boundary.py) (코드) + 각 `agents/<agent>.md` `## 권한 경계`.

---

## 0. 정체성 — 강제하는 것 / 강제 안 하는 것

> **🔴 대 원칙** (dcness 의 SSOT — 매 세션 SessionStart inject 로 자동 노출):
> **harness 가 강제하는 것은 단 2가지 — (1) 작업 순서, (2) 접근 영역. 그 외 모두 agent 자율.**
> - **작업 순서** = 시퀀스 (code-validator → engineer → pr-reviewer 등) + retry 정책
> - **접근 영역** = file path 경계 (agent-boundary ALLOW/READ_DENY) + 외부 시스템 mutation 차단 (push, gh issue, plugin 디렉토리)
> - **출력 형식 / handoff 형식 / preamble 구조 / marker / status JSON / Flag = agent 자율, harness 강제 X.**

### 안티패턴 (룰 추가 시 피하기)

1. **룰이 룰을 부르는 reactive cycle** — 신규 룰 추가 전 기존 룰 제거 가능성 먼저 검토. 추가→제거 비대칭이 기술 부채.
2. **강제 vs 권고 혼동** — 강제(block) = catastrophic 만. 권고(warn) = 형식 위반 / 비용 폭증 등은 측정 + 경고 + 사용자 개입. 권고 → 강제 자동 승격 금지.
3. **에이전트 자율성 침해** — agent prompt 안 강제 형식 박기 금지. 결론 + 이유 명확히 쓰도록 가이드만 (형식이 아니라 의미).
4. **불필요한 흐름 강제** — 시퀀스 보존은 catastrophic 만. 시퀀스 내부 행동 = 에이전트 자율.

본 SSOT 는 위 2 개 강제 영역만 정의. 형식 강제 (마커 / status JSON / Flag) 는 도입 안 함.

---

## 1. 적용 모드

dcNess 가 plugin (`dcness@dcness`) 으로 사용자 프로젝트에 활성화된 환경. 다음 모두 강제:

- 본 문서 §2 시퀀스 (catastrophic 보존)
- 권한 경계 (`harness/agent_boundary.py` ALLOW / READ_DENY / INFRA — agent-boundary hook 으로 강제)
- src/ 외 mutation 차단 + plugin-write-guard + READ_DENY

> dcness 자체 저장소 작업은 본 SSOT 미적용 — `CLAUDE.md §0` 가 진본.

---

## 2. 시퀀스

### 2.1 catastrophic 시퀀스 (보존 의무 — 원칙)

> 🔴 **진본 이전**: catastrophic 4룰 (§2.1.1 / §2.1.3 / §2.1.4 / §2.1.5) 의 내용·강제주체 진본 = [`hooks.md`](hooks.md) §3.2. 룰 ID 번호 체계는 `harness/hooks.py` / `catastrophic-gate.sh` 가 보존. 원칙 — "흐름 강제는 catastrophic 시퀀스만, 그 외 모든 시퀀스 = agent 자율". §2.1.4 단방향 + `NEW_DEP_ESCALATE` 3안 = §3.3.

> 시퀀스 mermaid (기획 / 설계 / 구현) 는 폐기 — 각 시퀀스 풀스펙은 해당 `commands/*.md` 본문. catastrophic 보존 = [`hooks.md`](hooks.md) §3.2, 라우팅 = §3.1.

---

## 3. 라우팅 한눈표 + Retry 한도

> dcness 강제 영역 중 *작업 순서* 의 핵심 view (§0 정합). agent 12 종이 prose 마지막 단락에 *어떤 결과로 끝났는지 (+ 사유)* 자기 언어로 명시 → 메인이 prose + 아래 한눈표로 다음 호출 결정 (enum 형식 검증 없음 — 이슈 #280). prose 가 모호하거나 결론을 추출 못 하면 사용자 위임 (prose 본문 "결정 불가" 명시 — issue #392). 본 표는 형식 강제가 아니라 *판단 보조* — 의미만 맞으면 OK (§0 정체성 정합).
>
> 🔴 **라우팅 진본 (1-way)** — `agent 결론 → 다음 호출` 매핑은 **본 §3.1 한눈표가 단일 진본**. `agents/<agent>.md` 본문은 자기 결론 vocabulary(enum + 판단 기준 + 사유)만 명시하고 다음 호출은 미주장. 본 문서 §4 는 loop 조립(시퀀스) view — 라우팅 매핑 미중복(step 순서 / allowed_enums / commit 지점 등 loop 고유 정보만). 라우팅 갱신(신 agent / enum / cycle 한도)은 본 §3.1 한 곳만 고치면 된다.
>
> 평탄화·흡수 이력: architect → system-architect + module-architect 2분할, validator → code-validator + architecture-validator 2분할, security-reviewer → pr-reviewer §F-Security 흡수, design-critic → 사용자 PICK + design.md §8/code-validator grep, product-planner → 메인 직접 그릴미, plan-reviewer 폐기(이슈 #515) → tech-reviewer 가 선행 기술 검증, build-worker 신규(#446).

### 3.1 routing 한눈표

| agent | 주요 결론 → 다음 호출 |
|---|---|
| tech-reviewer | PASS → (사용자 2차 OK) → `/architect-loop` 권고 / FAIL → PRD patch·항목 polish 후 재호출 / ESCALATE → 사용자. **단방향**: `/architect-loop` 진입 후 재호출 금지 (§2.1.4) |
| ux-architect | UX_FLOW_READY → system-architect / UX_REFINE_READY → designer / UX_FLOW_ESCALATE → 사용자. **UI-less epic 이면 메인이 호출 안 함** ([`commands/architect-loop.md`](../../commands/architect-loop.md) UI-less 분기) |
| system-architect | PASS → architecture-validator 1차 / ESCALATE → 사용자(`/product-plan`) / NEW_DEP_ESCALATE → 3안 (§3.3) |
| module-architect | PASS → (컨텍스트별: 다음 단위 module-architect / test-engineer / engineer / 후속 없음) / ESCALATE → 사용자 / NEW_DEP_ESCALATE → 3안 (§3.3). 호출 단위 = 1 Story 또는 공통 task 묶음, K = Story 수 + 공통 호출. self-check cross-task interface = PASS 게이트 |
| engineer | IMPL_DONE → code-validator / IMPL_PARTIAL → engineer(분할 — retry 아님, 상한 없음 §3.2) / SPEC_GAP_FOUND → module-architect(보강, ≤ 2) / TESTS_FAIL → engineer 재시도(≤ 3) / POLISH_DONE → pr-reviewer / IMPLEMENTATION_ESCALATE → 사용자 |
| test-engineer | PASS → engineer(attempt 0) / SPEC_GAP_FOUND → module-architect(보강) |
| designer | PASS → 사용자 PICK → (test 또는 impl) / ESCALATE → 사용자. 환경 감지 = `docs/design.md` frontmatter `medium`. 재호출 한도 X (사용자 자유) |
| code-validator | PASS → pr-reviewer / FAIL → engineer 재시도(≤ 3) / ESCALATE → module-architect(보강) 또는 사용자. impl 경로로 full/bugfix scope 자동 분기 |
| architecture-validator | PASS(1차) → module-architect × K / PASS(2차) → architect-loop Step 6 / FAIL → 해당 architect 재진입(cycle ≤ 2) / ESCALATE → 사용자. 두 시점 호출 — 1차(Step 3.5) = Placeholder + 공통 SSOT, 2차(Step 5) = Cross-Story Interface + Impl Simulation + Origin Anchor + Placeholder 재검증 |
| pr-reviewer | PASS → (CI PASS 후) 메인 즉시 regular merge / 변경 요청 → engineer POLISH |
| qa | FUNCTIONAL_BUG → module-architect(버그픽스) / CLEANUP → engineer(light) / DESIGN_ISSUE → designer·ux-architect(REFINE) / KNOWN_ISSUE → 종료 / SCOPE_ESCALATE → 사용자 |
| build-worker (`/impl-loop` 한정) | PASS → 메인 git/PR → pr-reviewer / SPEC_GAP_FOUND → module-architect(≤ 2) / TESTS_FAIL → engineer 재시도 또는 사용자 / IMPLEMENTATION_ESCALATE → 사용자. 권한 = engineer + test-engineer 합집합, git/PR/pr-reviewer 호출 금지(메인 위임). `/impl` 단발 미사용 |

> 각 agent 의 진입 입력 / 산출물 / self-check 의무 / 결론 prose 표현 상세 = `agents/<agent>.md` 본문 진본. Spike Gate 폐기(이슈 #511) — tech-reviewer 가 PRD 단계 외부 의존 검증 cover.

### 3.2 Retry 한도

> RWHarness `harness-architecture.md` §4.3 핵심 상수 + impl_loop 정책 정합. dcNess 는 boolean Flag 대신 `.claude/harness-state/<run_id>/.attempts.json` 카운터로 표현.
>
> ⚠️ **분할(IMPL_PARTIAL)은 retry 아님** — engineer 가 단일 호출에 다 못 끝내 남은 작업을 명시하고 재호출되는 것 (`agents/engineer.md` 작업 분할 — DCN-30-38). attempt 카운터 미소비, **상한 없음 (자율 판단)**. 실패 재시도(retry, 한도 있음)와 구분.

| 항목 | 한도 | 초과 시 |
|---|---|---|
| engineer attempt (TESTS_FAIL → 재시도) | 3 | `IMPLEMENTATION_ESCALATE` |
| engineer SPEC_GAP_FOUND → module-architect (보강) → engineer 재진입 | 2 | `IMPLEMENTATION_ESCALATE` |
| code-validator FAIL → engineer 재진입 | engineer attempt 흡수 | engineer attempt 한도 (3) 도달 시 escalate |
| architecture-validator FAIL → architect 재진입 | 2 cycle | 사용자 위임 |
| pr-reviewer FAIL → POLISH 라운드 | 2 | 사용자 escalate |
| build-worker phase 2 (TESTS_FAIL → src retry, `/impl-loop` 한정) | 3 (worker 내부) | `TESTS_FAIL` emit → 메인이 engineer 재호출 또는 사용자 위임 |
| ESCALATE 누적 (동일 fail_type) | 2 | module-architect (보강 케이스) 자동 호출 |

`.attempts.json` = fail_type → 카운터 매핑 (예: `{"code_validation": 2, "spec_gap": 1}`). force-retry 시 리셋.

### 3.3 Escalate 처리

escalate 결론 enum (`IMPLEMENTATION_ESCALATE` / `UX_FLOW_ESCALATE` / `ESCALATE` / `SCOPE_ESCALATE` / `NEW_DEP_ESCALATE`) 수신 시 **메인 / driver 가 즉시 사용자 보고 후 대기** (§0 — 자동 복구 / 우회 / 재시도 금지). 각 enum 의 출처 agent·의미 = §3.1 표 + 해당 agent 본문. escalate 분기 풀스펙(architect-loop) = [`commands/architect-loop.md`](../../commands/architect-loop.md) `## 분기 / cycle (요약)`.

`NEW_DEP_ESCALATE` (system-architect / module-architect — architect-loop 도중 tech-review 미검증 새 외부 의존 발견) 만 예외적으로 "단순 대기"가 아니라 메인이 사용자에게 **3안 메뉴** 제시 — (1) 채택+수동검증 → architect 재진입 / (2) 대안 기술 우회 → architect 재진입 / (3) 전체 원점 회귀 (`/architect-loop` 중단 + `/product-plan` 재진입 + 새 tech-review). (1)/(2) cycle ≤ 2. **어느 옵션이든 tech-reviewer 재호출 없음 (§2.1.4 단방향 catastrophic 보존)**. 흐름 = [`commands/architect-loop.md`](../../commands/architect-loop.md) `## 분기 / cycle (요약)`.

---

## 4. Loop 카탈로그 (이전됨)

> 🔴 **진본 이전**: loop 한눈 인덱스 (entry_point / task_list / advance / clean_enum / expected_steps) = [`loop-procedure.md`](loop-procedure.md) §7.0. 각 loop 의 Step 별 풀스펙 (allowed_enums / 분기 / sub_cycles / branch_prefix) = 해당 `commands/*.md` 본문 + loop-procedure §3 (commit 구조 / sub_cycles 명명). 결론 → 다음 호출 라우팅 = §3.1.

---

## 5. 강제 vs 자율 vs 권고

- **강제 (코드)**: §2.1 catastrophic 시퀀스 + 권한 경계 (`harness/agent_boundary.py` ALLOW / READ_DENY / DCNESS_INFRA_PATTERNS). escalate 결론은 자동 복구 금지.
- **자율 (agent)**: prose 형식 / handoff 페이로드 구조 / preamble / agent 가 사용하는 도구 순서 (단 §4 권한 안).
- **권고 (강제 X)**: §3.1 라우팅 / §3.2 retry 한도 — 측정 + 사용자 개입.

자세히 = 본 문서 §0 + §3 (라우팅 / retry / escalate).

---

## 6. 코드 Driver

§2.1 catastrophic = `hooks/catastrophic-gate.sh` (PreToolUse Agent) 강제. 메인 Claude = 시퀀스 결정자. **7 hook 전체 시점·차단·우회 메커니즘 SSOT** = [`hooks.md`](hooks.md).

---

## 7. 참조
- [`loop-procedure.md`](loop-procedure.md) — 루프 실행 Step 0~8 mechanics
- [`hooks.md`](hooks.md) — 7 hook (catastrophic-gate / file-guard / tdd-guard / stop-end-run / session-start / post-agent-clear / post-file-op-trace) 시점·차단·우회 SSOT (코드 강제 백본)
- 본 문서 §0 — 강제 영역 2가지 + 안티패턴 4건 (옛 dcness-rules.md §1 흡수)
- [`loop-procedure.md`](loop-procedure.md) §3 — cross-cutting 룰 (echo / 자가점검 / REDO 분류 / yolo)
- [`../../CLAUDE.md`](../../CLAUDE.md) — 작업 절차 + 게이트 SSOT

> 역사 자료 (Prose-Only 원전 proposal / 코드 driver 디자인 / plugin 배포 dry-run / RWHarness 모듈 분류 등) 는 [`../../README.md`](../../README.md) 의 "참조 문서" 표 (`docs/archive/` 영역) 참조.
- `agents/*.md` — 각 agent prose writing guide + 결론 enum 출처 (system-architect / module-architect / engineer / test-engineer / code-validator / architecture-validator / designer / ux-architect / tech-reviewer / pr-reviewer / qa)
- `harness/signal_io.py` — prose 파일 I/O (write_prose / read_prose). 옛 enum 추출 (interpret_signal) 폐기 (prose-only)
- RWHarness `docs/harness-spec.md` §4.2/§4.3 + `harness-architecture.md` §3 — 시퀀스 / 핸드오프 매트릭스 출처
