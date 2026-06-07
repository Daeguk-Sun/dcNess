# architect-loop 라우팅 SSOT

> **Status**: ACTIVE
> **Scope**: `/architect-loop` skill **단일 전용** 라우팅 진본 — 이 skill 안 agent (ux-architect / system-architect / architecture-validator / module-architect / designer) 의 결론 → 다음 호출 + retry 한도 + escalate 처리. 진행 절차(Step) 는 [`SKILL.md`](SKILL.md).
> **Cross-ref**: catastrophic 보존 = [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) · 권한 경계 = [`agent_boundary.py`](../../harness/agent_boundary.py).

## 읽는 법

agent 는 일을 마치면 prose 마지막 단락에 *어떤 결과로 끝났는지 + 사유* 를 자기 언어로 적는다. 메인 Claude 가 그 prose 를 읽고 아래 매핑으로 다음 호출을 정한다. 이 문서는 형식 강제가 아니라 *판단 보조* — 의미만 맞으면 된다. prose 가 모호하면 사용자에게 위임한다.

라우팅은 **skill 이 소유**한다. agent 는 결론(enum)만 내고, "그 결론이면 다음 누구" 는 본 문서가 정한다. 같은 agent 가 다른 skill (impl 등) 에 나와도 그건 *그 skill 의 라우팅* 이지 본 문서 영역이 아니다.

## 라우팅 그래프

```mermaid
flowchart TB
  UX[ux-architect] -->|UX_FLOW_READY| SA[system-architect]
  UX -->|UX_REFINE_READY| DS[designer]
  SA -->|PASS| AV1[architecture-validator 1차]
  AV1 -->|PASS| MA[module-architect × K]
  MA -->|PASS × K| AV2[architecture-validator 2차]
  AV2 -->|PASS| M([PR · 머지 → /impl 안내])
  AV1 -->|FAIL ≤2| SA
  AV2 -->|"FAIL: SYSTEM_BOUNDARY ≤2"| SA
  AV2 -->|"FAIL: CONTRACT_PROPAGATION · TASK_LOCAL ≤2"| MA
  SA -->|NEW_DEP_ESCALATE| U((사용자 · 3안))
  MA -->|NEW_DEP_ESCALATE| U
  UX -.->|UX_FLOW_ESCALATE| U
  SA -.->|ESCALATE| U
  MA -.->|ESCALATE| U

  classDef produce fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
  classDef verify fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
  classDef user fill:#eeeeee,stroke:#757575,color:#212121
  class UX,SA,DS,MA produce
  class AV1,AV2 verify
  class U user
```

> 파랑 = 생산 agent · 초록 = 검증 agent · 회색 = 사용자 위임. 점선 = escalate. 엣지의 `≤N` = retry 한도 ([retry 한도](#retry-한도)).
>
> tech-reviewer 는 architect-loop 진입 *전* (`/tech-review` skill) 단계라 본 그래프에 없다. architect-loop 진입 후 tech-reviewer 재호출은 **하지 않는다** — architect-loop 안엔 tech-reviewer 가 없고, `/tech-review` 재진입도 자연어 관례상 비권장 (코드 강제 아님, [escalate 처리](#escalate-처리)).

## 결론 → 다음 호출 매핑

| agent | 결론 → 다음 호출 |
|---|---|
| **ux-architect** | `UX_FLOW_READY` → system-architect · `UX_REFINE_READY` → designer · `UX_FLOW_ESCALATE` → 사용자. (UI-less epic 이면 메인이 호출 안 함 — [`SKILL.md`](SKILL.md) UI-less 분기) |
| **system-architect** | `PASS` → architecture-validator(1차) · `ESCALATE` → 사용자(`/spec` 재진입, `/product-plan` 호환) · `NEW_DEP_ESCALATE` → 3안([escalate 처리](#escalate-처리)) |
| **architecture-validator** | `PASS`(1차) → module-architect × K · `PASS`(2차) → SKILL.md Step 6 PR · `FAIL` → finding 분류별 재진입([finding 분류 라우팅](#finding-분류-라우팅)) · `ESCALATE` → 사용자 |
| **module-architect** | `PASS` → 다음 단위 module-architect / (마지막이면) architecture-validator 2차 · `SPEC_GAP_FOUND` → module-architect 보강([retry 한도](#retry-한도)) · `ESCALATE` → 사용자 · `NEW_DEP_ESCALATE` → 3안([escalate 처리](#escalate-처리)) |
| **designer** | `PASS` → 사용자 PICK · `ESCALATE` → 사용자. (UX_REFINE 분기 진입 시) |

표만으로 안 풀리는 맥락:

- **module-architect 호출 단위** = 1 Story 또는 공통 task 묶음 → epic 전체에서 `K = Story 수 + 공통 호출` 회 반복. self-check 의 cross-task interface 점검이 PASS 게이트.
- **architecture-validator 2시점** — 1차(Step 3.5) = system 산출물 기준으로 요구사항 출처, 설계 표준, Contract Ledger 충분성, freeze 가능성 검토. 2차(Step 5) = impl 문서까지 포함해 요구사항 출처 충실도, 계약과 인터페이스, 구현 가능성, drift와 scope, 표현 수준 검토. Must finding 마다 분류(`SYSTEM_BOUNDARY` / `CONTRACT_PROPAGATION` / `TASK_LOCAL`) 동반.

## finding 분류 라우팅

> drift 비용 분리의 핵심 — architecture-validator FAIL 을 "어느 레벨로 rollback?" 이 아니라 **finding 분류** 로 라우팅한다. 같은 FAIL 도 분류에 따라 비용이 크게 갈린다. 분류 진본 = [`agents/architecture-validator.md` finding 분류](../../agents/architecture-validator.md#finding-분류).

| finding 분류 | 뜻 | 재진입 대상 | 비고 |
|---|---|---|---|
| `SYSTEM_BOUNDARY` | 큰 그림(상위 경계)이 틀림 — 도메인 invariant / port 소비자 / usecase ownership / root ADR / storage policy 잘못 | **system-architect** 재진입 | 비싼 재설계. **system 재진입의 유일한 기본 사유.** |
| `CONTRACT_PROPAGATION` | 결정은 맞는데 stale 사본이 문서마다 남음 (전파 누락) | **module-architect `mode=contract_sweep`** | 동기화 sweep. **system 재설계 아님.** canonical 값 + sweep 키워드를 prompt 에 박아 전달 |
| `TASK_LOCAL` | 특정 impl task 문서만 틀림 — 예시 / depends_on / 수용기준 / requirements / Implementation Detail Leak | **module-architect** 보강 (해당 task) | 그 task 만 |

- **"system-architect 재진입은 `SYSTEM_BOUNDARY` 일 때만 기본값"** — stale 문구 전파 누락은 `CONTRACT_PROPAGATION` 으로 처리(sweep), system 재설계로 끌어올리지 않는다. system 문서는 1차 PASS 후 freeze ([`SKILL.md`](SKILL.md) system freeze).
- **`CONTRACT_AMENDMENT` 은 라우팅 enum 이 아니다** — module-architect 가 Step 4 에서 public contract 를 바꿀 때 취하는 자연어 행동 의무 (Contract Ledger 갱신 / "변경 없음" 명시). 라우팅 결정은 위 3 분류로만.

## retry 한도

| 재시도 경로 | 한도 | 초과 시 |
|---|---|---|
| ux-architect self-check FAIL → ux-architect 재진입 (prose 내부) | 2 cycle | 사용자 위임 |
| architecture-validator FAIL → architect 재진입 | 2 cycle | 사용자 위임 |
| module-architect `SPEC_GAP_FOUND` → 보강 → 신규 케이스 재진입 | 2 cycle | 사용자 위임 |

> **architecture-validator FAIL 재진입 대상 = finding 분류별** ([finding 분류 라우팅](#finding-분류-라우팅)) — **1차**는 검증 대상이 system-architect 산출물이라 기본적으로 **system-architect** 재진입이다. **2차**는 분류로 분기한다. `SYSTEM_BOUNDARY`(모듈 경계·의존 그래프 포함) → **system-architect**, `CONTRACT_PROPAGATION` → **module-architect `mode=contract_sweep`**, `TASK_LOCAL` → **module-architect** 보강.
> cycle 발생 시 **working tree only — commit X.** PASS 후에만 commit (cycle 도중 산출물은 덮어쓰기 전제).

> **finding 수용 자세** (점 패치 X, 근본 재설계) — 같은 영역 finding 이 2회+ 반복되면 점 패치 retry 로 한도를 소진하지 말고 근본 원인을 짚어 그 영역을 재설계한다. 진본 = [`loop-procedure.md` finding 수용 원칙](../../docs/plugin/loop-procedure.md#finding-수용-원칙-점-패치-금지-근본-수정).

## escalate 처리

escalate 계열 결론(`UX_FLOW_ESCALATE` / `ESCALATE` / `NEW_DEP_ESCALATE`) 수신 시 **메인이 즉시 사용자 보고 후 대기** (자동 복구 / 우회 / 재시도 금지 — [`../../CLAUDE.md`](../../CLAUDE.md) 강제 영역).

- **기술 스택 그릴미 미합의** (Step 2.9 — 사용자가 스택 결정 못 냄 / 보류) → loop 진행 보류 + 사용자 위임 (강제 자율 결정 X). system-architect PASS 후 스택 번복 원하면 새 cycle 신설 X — 기존 system-architect 재진입 (또는 `ESCALATE` → `/spec` 재진입, `/product-plan` 호환) 재활용.
- **`*_ESCALATE`** → 사용자 위임.

### NEW_DEP_ESCALATE — 3안 (단순 대기 아님)

system-architect / module-architect 가 **architect-loop 도중 tech-review 미검증 새 외부 의존을 발견** 했을 때. loop 자동 중단 X. 메인이 사용자에게 3안 제시:

1. **채택 + 수동 검증** — 사용자 승인 → 해당 architect 재진입 (architecture.md/adr.md 에 "사용자 승인, tech-review 미경유" 흔적 명시)
2. **대안 기술 우회** — 이미 tech-review 검증된 대안 지정 → architect 재진입
3. **전체 원점 회귀** — `/design` (`/architect-loop` 호환) 중단 + `/spec` (`/product-plan` 호환) 재진입 + 새 tech-review

(1)·(2) 재진입 cycle ≤ 2. **어느 옵션이든 tech-reviewer 재호출 없음** — architect-loop 안엔 tech-reviewer 가 없어 호출 경로 자체 부재 (재호출 비권장은 코드 강제 아닌 자연어 관례, [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) 의 tech-review 자연어 관례).

## 후속 (loop 종료 후)

- 본 loop clean → 자동 commit/PR + 머지 → 사용자에게 "`/impl <epic-path>` 로 구현 진입할까요?" 안내
- 주의사항 → 사용자 결정 (수동)
- spec gap 발견 + cycle 한도 초과 → 사용자 위임 (`/spec` 재진입 권고 (`/product-plan` 호환))
