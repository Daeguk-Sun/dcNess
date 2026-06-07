# acceptance 라우팅 SSOT

> **Status**: ACTIVE
> **Scope**: `/acceptance` skill 단일 전용 라우팅 진본. MVP 범위는 story / epic 제품 검수다. 진행 절차는 [`SKILL.md`](SKILL.md).

## 라우팅 그래프

```mermaid
flowchart TB
  IN[/acceptance input/] --> UNIT{검수 단위?}
  UNIT -->|story| SA[product-acceptance:STORY_ACCEPTANCE]
  UNIT -->|epic| EA[product-acceptance:EPIC_ACCEPTANCE]
  UNIT -->|불명확| U((사용자에게 입력 요청))

  SA -->|PASS| SP[story 완료 후보 보고]
  SA -->|FAIL| SG[story gap 목록 + 후속 라우팅]
  SA -->|ESCALATE| U

  EA -->|PASS| EP[epic 완료 후보 보고]
  EA -->|FAIL| EG[epic gap 목록 + 후속 라우팅]
  EA -->|ESCALATE| U

  SG -.->|자동 수정 X| NEXT1[/impl 또는 /design 회수 후보]
  EG -.->|자동 issue 생성 X| NEXT2[/impl · /design · /ux · security/ops 후속 후보]

  classDef verify fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
  classDef report fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
  classDef user fill:#eeeeee,stroke:#757575,color:#212121
  class SA,EA verify
  class SP,SG,EP,EG report
  class U user
```

## 결론 → 다음 행동

| 입력 | 다음 |
|---|---|
| `product-acceptance:STORY_ACCEPTANCE` `PASS` | story 완료 후보로 보고. 자동 close 는 하지 않는다. |
| `product-acceptance:STORY_ACCEPTANCE` `FAIL` | AC / PR / test evidence gap 을 보고하고 `/impl` 또는 `/design` 회수 후보를 제안한다. |
| `product-acceptance:EPIC_ACCEPTANCE` `PASS` | epic 완료 후보로 보고. 자동 close 는 하지 않는다. |
| `product-acceptance:EPIC_ACCEPTANCE` `FAIL` | PRD Must, cross-story gap, security/ops risk 를 보고하고 후속 라우팅을 제안한다. |
| `ESCALATE` | 기준 문서, 구현 PR 목록, 권한, 사용자 결정 부족을 보고하고 대기한다. |

## 깊이 차이

Story acceptance 는 가볍게 AC / PR / test evidence 중심으로 돈다. story마다 full product/security/performance audit 을 강제하지 않는다.

Epic acceptance 는 PRD Must, cross-story gap, security/ops risk 를 포함한다. 여러 story가 합쳐질 때 생기는 흐름, 권한, 데이터, 운영 위험을 본다.

## Gap 처리

`FAIL` 은 끝이 아니라 다음 작업 단위로 돌아가기 위한 보고다.

- 자동 수정하지 않는다.
- 자동 issue 생성하지 않는다.
- 사용자 승인 없이 GitHub issue 를 만들지 않는다.
- gap 은 기준 문서, 구현 증거, 누락 사실, 후속 라우팅을 포함한다.

후속 라우팅은 MVP 에서 prose 보고만 한다. acceptance gap issue 생성과 자동 연결은 후속 단계에서 다룬다.

## Non-goals

- full E2E 검증은 MVP 범위 밖이다.
- Lite `/impl` 단발 작업을 `/acceptance` 로 강제하지 않는다.
- 기존 `code-validator`, `architecture-validator`, `pr-reviewer` 를 대체하지 않는다.
