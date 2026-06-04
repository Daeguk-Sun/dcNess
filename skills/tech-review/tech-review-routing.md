# tech-review 라우팅 SSOT

> **Status**: ACTIVE
> **Scope**: `/tech-review` skill **단일 전용** 라우팅 진본 — tech-reviewer 의 결론 (PASS / FAIL / ESCALATE) → 다음 호출 + 사용자 2차 OK 분기 + cycle 재진입 + **단방향 관례 (재진입 비권장)** + 비대상 + 후속. 진행 절차(Step) 는 [`SKILL.md`](SKILL.md). tech-reviewer 는 tech-review 전용 agent 라 본 문서가 유일 진본 (맥락 분기 없음).
> **Cross-ref**: 단방향 관례 (코드 강제 아님) = [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) 의 tech-review 자연어 관례 · 강제 영역 = [`../../CLAUDE.md`](../../CLAUDE.md).

## 읽는 법

tech-reviewer 는 stateless — PRD + 스켈레톤을 받아 본문을 채우고 prose 결론 (PASS / FAIL / ESCALATE) 을 낸다. 메인 Claude 가 그 결론을 사용자에게 echo 하고, 사용자 2차 OK 응답 (OK / patch / 격상 / polish) 에 따라 다음을 정한다. cycle 컨텍스트는 메인이 재호출 prompt 에 명시 (tech-reviewer 가 기억 못 함). 이 문서는 형식 강제가 아니라 *판단 보조* — 의미만 맞으면 된다.

## 라우팅 그래프

```mermaid
flowchart TB
  TR[tech-reviewer] -->|PASS| CP{사용자 2차 OK · Step 3}
  TR -->|FAIL| RW[기본 권고: PRD patch / 격상 / polish → 재검토]
  TR -.->|ESCALATE| U((사용자 위임))
  CP -->|1. OK| AL([/architect-loop 권고 → 종료])
  CP -->|2. PRD 재기술| P1[메인: prd.md patch] --> TR
  CP -->|3. 격리 후보 격상| P2[메인: 스켈레톤 격상] --> TR
  CP -->|4. 항목 polish| P3[메인: 스켈레톤 polish 메모] --> TR
  RW --> TR
  RW -.->|사용자 명시적 위험 감수 only| AL
  AL -.->|진입 후 재호출 비권장 자연어 관례| X[[단방향 관례 — 코드 강제 아님]]

  classDef verify fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
  classDef main fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
  classDef user fill:#eeeeee,stroke:#757575,color:#212121
  class TR verify
  class P1,P2,P3,RW main
  class U,CP user
```

> 초록 = 검증 agent · 파랑 = 메인 patch 작업 · 회색 = 사용자 체크포인트 / 위임. 점선 = escalate / catastrophic 경계.
>
> **PASS** → 사용자 2차 OK 체크포인트 (OK 면 진행, 사용자가 polish 요청도 가능). **FAIL** → 기본 권고 = patch/격상/polish 후 재검토 (실패한 의존 검증이 silent 하게 통과되지 않도록 — 메인이 FAIL + 미해결 항목 echo 의무). 사용자가 *명시적 위험 감수* 를 선택할 때만 FAIL 상태로 진행 가능. **ESCALATE** → 정상 체크포인트 우회, 사용자 위임 only (검증 자체가 불가능했으므로 게이트 통과 판정 불가).

## 결론 → 다음 호출 매핑

| 입력 | 다음 |
|---|---|
| **tech-reviewer PASS** | → 메인이 산출물 echo → 사용자 2차 OK 체크포인트 (Step 3). OK → `/architect-loop` |
| **tech-reviewer FAIL** | → 메인이 *FAIL + 미해결 항목* 명시 echo → **기본 권고 = PRD patch / 격상 / polish 후 Step 1 재검토** (Step 4 옵션 2/3/4). 사용자가 *명시적 위험 감수* OK 선택 시에만 진행 (silent 통과 금지) |
| **tech-reviewer ESCALATE** | → 정상 체크포인트 우회 — 사용자 위임 only (외부 검증 실행 불가 / 권한 밖 / 결론 추출 불가 → 게이트 통과 판정 자체 불가) |
| **사용자 2차 OK — 1. OK** | → Step 5 종료 + `/architect-loop` 권고 |
| **사용자 — 2. PRD 재기술** | → 메인 `prd.md` patch (+ 필요 시 스켈레톤) → **Step 1 재진입** (cycle 컨텍스트 prompt 명시) |
| **사용자 — 3. 격리 후보 격상** | → 메인 스켈레톤 격상 → **Step 1 재진입** |
| **사용자 — 4. 항목 polish** | → 메인 스켈레톤 polish 메모 → **Step 1 재진입** |

> tech-reviewer 는 issue 생성·git mutation 없음 — PRD/스켈레톤 patch 는 모두 **메인**이 수행 후 재호출.

## 단방향 관례 (재진입 비권장)

`/architect-loop` 진입 *후* `/tech-review` (tech-reviewer) 재호출은 **관례상 비권장** — 코드 강제 아닌 *자연어 관례* (메인/사용자 자율 판단, [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) 의 tech-review 자연어 관례).

**왜 단방향?**
- tech-reviewer 단계 = *마지막 기술 검증 기회*. 검증 충실 의무 가중 (증거물 / HTML 리포트 룰의 가치 근거).
- architect-loop 진입 후 역방향 회귀 = ping-pong 사고 패턴 (옛 plan-reviewer cycle 한도 룰이 누적된 원인, 이슈 [#515](https://github.com/alruminum/dcNess/issues/515)).

**architect-loop 도중 미검증 새 외부 의존 발견 시 → `NEW_DEP_ESCALATE` 3안** (tech-reviewer 재호출 *없이*):
1. **채택 + 수동 검증** — 사용자 승인 → 해당 architect 재진입
2. **대안 기술 우회** — tech-review 기검증 대안 지정 → architect 재진입
3. **전체 원점 회귀** — `/architect-loop` 중단 + `/product-plan` 재진입 + 새 tech-review

(1)·(2) cycle ≤ 2. **어느 옵션이든 tech-reviewer 재호출 0** — architect-loop 안엔 tech-reviewer 가 없어 NO_GO 판정 자체 불가 — 그래서 "전체 회귀 only" 가 아니라 사용자 선택 3안. 상세 흐름 = [`../architect-loop/architect-loop-routing.md`](../architect-loop/architect-loop-routing.md#escalate-처리).

## 비대상 (다른 skill 추천)

- PRD 미작성 / 스켈레톤 부재 → `/product-plan` 먼저
- 설계 단계 진입 → `/architect-loop`
- 구현 단계 진입 → `/impl-loop`
- 버그 / 이슈 → `/issue-report`

## 후속 (skill 종료 후)

- tech-review 통과 + 사용자 OK → `/architect-loop` (설계 루프 — 권장)
- tech-review 실패 (FAIL / ESCALATE) → 메인 + 사용자 patch 토론 → Step 1 재진입
- tech-review 완료 후 *기술 자체 폐기* 결정 → `/product-plan` 재진입 (PRD 자체 수정)
