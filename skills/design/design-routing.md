# design 분기 규칙 SSOT

> **Status**: ACTIVE
> **Scope**: `/design` skill **단일 전용** 분기 규칙 진본 — 이 skill 안 agent (ux-architect / system-architect / architecture-validator / module-architect / designer) 의 결론 → 다음 호출 + retry 한도 + escalate 처리. 진행 절차(Step) 는 [`SKILL.md`](SKILL.md).
> **Cross-ref**: 순서 차단 훅 보존 = [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) · 권한 경계 = [`agent_boundary.py`](../../harness/agent_boundary.py) · 용어 기준 = [`terms.md`](../../docs/plugin/terms.md).

## 읽는 법

agent 는 일을 마치면 prose 마지막 단락에 *어떤 결과로 끝났는지 + 사유* 를 자기 언어로 적는다. 메인 Claude 가 그 prose 를 읽고 아래 매핑으로 다음 호출을 정한다. 이 문서는 형식 강제가 아니라 *판단 보조* — 의미만 맞으면 된다. prose 가 모호하면 사용자에게 위임한다.

분기 규칙은 **skill 이 소유**한다. agent 는 결론(enum)만 내고, "그 결론이면 다음 누구" 는 본 문서가 정한다. 같은 agent 가 다른 skill (impl 등) 에 나와도 그건 *그 skill 의 분기 규칙* 이지 본 문서 영역이 아니다.

## 분기 그래프

```mermaid
flowchart TB
  UX[ux-architect] -->|UX_FLOW_READY| SA[system-architect]
  UX -->|UX_REFINE_READY| DS[designer]
  SA -->|PASS| AV1[architecture-validator 1차]
  AV1 -->|PASS: 공통 task 있음| MA_COMMON[module-architect common]
  AV1 -->|PASS: 공통 task 없음| MA_STORY[module-architect Story N]
  MA_COMMON -->|PASS| AV_COMMON[architecture-validator 공통 단위]
  AV_COMMON -->|PASS| MA_STORY
  MA_STORY -->|PASS| AV_STORY[architecture-validator Story 단위]
  AV_STORY -->|PASS: 다음 Story| MA_STORY
  AV_STORY -->|PASS: 마지막 Story| AV_FINAL[architecture-validator cross-story 통합]
  AV_FINAL -->|PASS| M([PR · 머지 → /impl 안내])
  AV1 -->|FAIL ≤2| SA
  AV_COMMON -->|"FAIL: SYSTEM_BOUNDARY ≤2"| SA
  AV_COMMON -->|"FAIL: CONTRACT_PROPAGATION · TASK_LOCAL ≤2"| MA_COMMON
  AV_STORY -->|"FAIL: SYSTEM_BOUNDARY ≤2"| SA
  AV_STORY -->|"FAIL: CONTRACT_PROPAGATION · TASK_LOCAL ≤2"| MA_STORY
  AV_FINAL -->|"FAIL: SYSTEM_BOUNDARY ≤2"| SA
  AV_FINAL -->|"FAIL: CONTRACT_PROPAGATION · TASK_LOCAL ≤2"| MA_STORY
  SA -->|NEW_DEP_ESCALATE| U((사용자 · 3안))
  MA_COMMON -->|NEW_DEP_ESCALATE| U
  MA_STORY -->|NEW_DEP_ESCALATE| U
  UX -.->|UX_FLOW_ESCALATE| U
  SA -.->|ESCALATE| U
  MA_COMMON -.->|ESCALATE| U
  MA_STORY -.->|ESCALATE| U

  classDef produce fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
  classDef verify fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
  classDef user fill:#eeeeee,stroke:#757575,color:#212121
  class UX,SA,DS,MA_COMMON,MA_STORY produce
  class AV1,AV_COMMON,AV_STORY,AV_FINAL verify
  class U user
```

> 파랑 = 생산 agent · 초록 = 검증 agent · 회색 = 사용자 위임. 점선 = escalate. 엣지의 `≤N` = retry 한도 ([retry 한도](#retry-한도)).
>
> tech-reviewer 는 design 진입 *전* (`/tech-review` skill) 단계라 본 그래프에 없다. design 진입 후 tech-reviewer 재호출은 **하지 않는다** — design 안엔 tech-reviewer 가 없고, `/tech-review` 재진입도 자연어 관례상 비권장 (코드 강제 아님, [escalate 처리](#escalate-처리)).

## 결론 → 다음 호출 매핑

| agent | 결론 → 다음 호출 |
|---|---|
| **ux-architect** | `UX_FLOW_READY` → system-architect · `UX_REFINE_READY` → designer · `UX_FLOW_ESCALATE` → 사용자. (UI-less epic 이면 메인이 호출 안 함 — [`SKILL.md`](SKILL.md) UI-less 분기) |
| **system-architect** | `PASS` → architecture-validator(1차) · `ESCALATE` → 사용자(`/spec` 재진입) · `NEW_DEP_ESCALATE` → 3안([escalate 처리](#escalate-처리)) |
| **architecture-validator** | `PASS`(1차) → 공통 task 있으면 module-architect(common), 없으면 Story 1 module-architect · `PASS`(공통/Story 단위) → 해당 단위 freeze + 다음 단위 module-architect / 마지막 Story 면 architecture-validator(cross-story 통합) · `PASS`(cross-story 통합) → SKILL.md Step 6 PR · `FAIL` → finding 분류별 재진입([finding 분류 분기](#finding-분류-분기)) · `ESCALATE` → 사용자 |
| **module-architect** | `PASS` → architecture-validator(현재 공통/Story 단위) · `SPEC_GAP_FOUND` → module-architect 보강([retry 한도](#retry-한도)) · `ESCALATE` → 사용자 · `NEW_DEP_ESCALATE` → 3안([escalate 처리](#escalate-처리)) |
| **designer** | `PASS` → 사용자 PICK · `ESCALATE` → 사용자. (UX_REFINE 분기 진입 시) |

표만으로 안 풀리는 맥락:

- **module-architect 호출 단위** = 공통 task 묶음 0~1개 + Story 1개씩. 각 module-architect `PASS` 는 곧장 같은 단위 architecture-validator 로 이어지며, validator `PASS` 전에는 다음 module-architect 를 호출하지 않는다.
- **architecture-validator 시점** — 1차(Step 3.5) = system 산출물 기준으로 요구사항 출처, 설계 표준, Contract Ledger 충분성, 구현 순서(첫 제품 경계 동작 앞당김), freeze 가능성 검토. 공통/Story 단위 검증(Step 4) = 방금 작성한 impl 문서와 frozen system/이전 단위의 계약 정합성 검토. cross-story 통합(Step 5) = 모든 단위 freeze 뒤 Story 간 compose/wiring, forward-ref 회수, Contract Ledger sweep, Cross-Story Lessons 일관성, cold-seat 구현 가능성 검토. Must finding 마다 분류(`SYSTEM_BOUNDARY` / `CONTRACT_PROPAGATION` / `TASK_LOCAL`) 동반.
- **교훈 누적 전달** — 단위 검증에서 확정된 횡단 규칙은 SSOT 문서 기록 + 포인터 전달을 기본으로 한다. prompt 직접 전달은 미기록 결정 예외에 한정하고, 큰 본문을 매 Story prompt 에 반복하지 않는다.

## finding 분류 분기

> drift 비용 분리의 핵심 — architecture-validator FAIL 을 "어느 레벨로 rollback?" 이 아니라 **finding 분류** 로 분기한다. 같은 FAIL 도 분류에 따라 비용이 크게 갈린다. 분류 진본 = [`agents/architecture-validator.md` finding 분류](../../agents/architecture-validator.md#finding-분류).

| finding 분류 | 뜻 | 재진입 대상 | 비고 |
|---|---|---|---|
| `SYSTEM_BOUNDARY` | 큰 그림(상위 경계)이 틀림 — 도메인 invariant / port 소비자 / usecase ownership / root ADR / storage policy 잘못 | **system-architect** 재진입 | 비싼 재설계. **system 재진입의 유일한 기본 사유.** |
| `CONTRACT_PROPAGATION` | 결정은 맞는데 stale 사본이 문서마다 남음 (전파 누락) | **module-architect `mode=contract_sweep`** | 동기화 sweep. **system 재설계 아님.** canonical 값(진본 = Contract Ledger) + sweep 키워드를 prompt 로 전달 (전파 대상 식별용 — prompt 가 진본이 아니라 Ledger 가 진본) |
| `TASK_LOCAL` | 특정 impl task 문서만 틀림 — 예시 / depends_on / 수용기준 / requirements / Implementation Detail Leak | **module-architect** 보강 (해당 task) | 그 task 만 |

- **"system-architect 재진입은 `SYSTEM_BOUNDARY` 일 때만 기본값"** — stale 문구 전파 누락은 `CONTRACT_PROPAGATION` 으로 처리(sweep), system 재설계로 끌어올리지 않는다. system 문서는 1차 PASS 후 freeze ([`SKILL.md`](SKILL.md) system freeze).
- **`CONTRACT_AMENDMENT` 은 분기 enum 이 아니다** — module-architect 가 Step 4 에서 public contract 를 바꿀 때 취하는 자연어 행동 의무 (Contract Ledger 갱신 / "변경 없음" 명시). 분기 결정은 위 3 분류로만.

## retry 한도

| 재시도 경로 | 한도 | 초과 시 |
|---|---|---|
| ux-architect self-check FAIL → ux-architect 재진입 (prose 내부) | 2 cycle | 사용자 위임 |
| architecture-validator FAIL → architect 재진입 | 2 cycle | 사용자 위임 |
| module-architect `SPEC_GAP_FOUND` → 보강 → 신규 케이스 재진입 | 2 cycle | 사용자 위임 |

> **architecture-validator FAIL 재진입 대상 = finding 분류별** ([finding 분류 분기](#finding-분류-분기)) — **1차**는 검증 대상이 system-architect 산출물이라 기본적으로 **system-architect** 재진입이다. **공통/Story 단위 검증과 cross-story 통합 검증**은 분류로 분기한다. `SYSTEM_BOUNDARY`(모듈 경계·의존 그래프 포함) → **system-architect**, `CONTRACT_PROPAGATION` → **module-architect `mode=contract_sweep`**, `TASK_LOCAL` → **module-architect** 보강.
> cycle 발생 시 **working tree only — commit X.** PASS 후에만 commit (cycle 도중 산출물은 덮어쓰기 전제).

> **finding 수용 자세** (점 패치 X, 근본 재설계) — 같은 영역 finding 이 2회+ 반복되면 점 패치 retry 로 한도를 소진하지 말고 근본 원인을 짚어 그 영역을 재설계한다. 진본 = [`loop-procedure.md` finding 수용 원칙](../../docs/plugin/loop-procedure.md#finding-수용-원칙-점-패치-금지-근본-수정).

## escalate 처리

escalate 계열 결론(`UX_FLOW_ESCALATE` / `ESCALATE` / `NEW_DEP_ESCALATE`) 수신 시 **메인이 즉시 사용자 보고 후 대기** (자동 복구 / 우회 / 재시도 금지 — [`../../CLAUDE.md`](../../CLAUDE.md) 강제 영역).

- **기술 스택 그릴미 미합의** (Step 2.9 — 사용자가 스택 결정 못 냄 / 보류) → loop 진행 보류 + 사용자 위임 (강제 자율 결정 X). system-architect PASS 후 스택 번복 원하면 새 cycle 신설 X — 기존 system-architect 재진입 (또는 `ESCALATE` → `/spec` 재진입) 재활용.
- **`*_ESCALATE`** → 사용자 위임.

### NEW_DEP_ESCALATE — 3안 (단순 대기 아님)

system-architect / module-architect 가 **design 도중 tech-review 미검증 새 외부 의존을 발견** 했을 때. loop 자동 중단 X. 메인이 사용자에게 3안 제시:

1. **채택 + 수동 검증** — 사용자 승인 → 해당 architect 재진입 (architecture.md/adr.md 에 "사용자 승인, tech-review 미경유" 흔적 명시)
2. **대안 기술 우회** — 이미 tech-review 검증된 대안 지정 → architect 재진입
3. **전체 원점 회귀** — `/design` 중단 + `/spec` 재진입 + 새 tech-review

(1)·(2) 재진입 cycle ≤ 2. **어느 옵션이든 tech-reviewer 재호출 없음** — design 안엔 tech-reviewer 가 없어 호출 경로 자체 부재 (재호출 비권장은 코드 강제 아닌 자연어 관례, [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) 의 tech-review 자연어 관례).

## 후속 (loop 종료 후)

- 본 loop clean → 자동 commit/PR + 머지 → 사용자에게 "`/impl <epic-path>` 로 구현 진입할까요?" 안내
- 주의사항 → 사용자 결정 (수동)
- spec gap 발견 + cycle 한도 초과 → 사용자 위임 (`/spec` 재진입 권고)
