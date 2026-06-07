# product-plan 라우팅 SSOT

> **Status**: ACTIVE
> **Scope**: `/product-plan` 및 호환 alias `/spec` skill 라우팅 진본. 본 skill 은 **메인 Claude 직접 작업** (product-planner sub-agent 폐기) 이라 내부 구현 agent 매핑은 거의 없다. 단 `/spec` 이행 기준 검수로 `product-acceptance:SPEC_ACCEPTANCE` 를 호출한다. skill 간 시퀀스 (PRD → SPEC_ACCEPTANCE → `/tech-review` → `/design` (`/architect-loop` 호환) → `/impl` → `/acceptance`) + 체크포인트 분기 + 재진입 + escalate + 단방향 관례 + 비대상 추천이 라우팅의 전부다. 진행 절차(Step) 는 [`SKILL.md`](SKILL.md).
> **Cross-ref**: catastrophic 보존 = [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) · 강제 영역 = [`../../CLAUDE.md`](../../CLAUDE.md).

## 읽는 법

본 skill 은 메인이 사용자와 직접 그릴미 대화하며 산출물을 만든다. 각 Step 끝 *사용자 체크포인트* 의 응답(OK / patch / Y / n) 에 따라 다음 단계가 갈린다. 이 문서는 그 분기와 skill 간 이동을 정한다. 형식 강제가 아니라 *판단 보조* — 의미만 맞으면 된다. 모호하면 사용자에게 위임한다.

## skill 시퀀스 그래프

```mermaid
flowchart TB
  PP[/spec 또는 /product-plan · 메인 직접/] --> CP1{1차 OK?}
  CP1 -->|patch| PP
  CP1 -->|OK| SA[product-acceptance:SPEC_ACCEPTANCE]
  SA -->|FAIL| PP
  SA -->|ESCALATE| U((사용자 위임))
  SA -->|PASS| MERGE[PR 머지 + 이슈 등록]
  MERGE --> DEP{외부 의존 ≥1?}
  DEP -->|0개| AL[/design/]
  DEP -->|≥1| TR[/tech-review/]
  TR --> CP2{2차 OK?}
  CP2 -->|NO_GO / 보류| U((사용자 위임))
  CP2 -->|OK| AL
  AL --> SH[/impl/]
  SH --> PA[/acceptance/]
  PP -.->|PRD 변경| PP
  PP -.->|범위·PRD 위반 escalate| U

  classDef main fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
  classDef next fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
  classDef user fill:#eeeeee,stroke:#757575,color:#212121
  class PP,SA main
  class TR,AL,SH,PA next
  class U user
```

> 파랑 = 본 skill (메인 직접) · 초록 = 후속 skill · 회색 = 사용자 위임. 점선 = 재진입 / escalate.
>
> `/tech-review` 는 본 skill *종료 후* 단계다. 외부 의존 0 개 PRD 면 skip 하고 바로 `/design` (`/architect-loop` 호환). **`/design` 진입 후 `/tech-review` 재호출은 비권장** (단방향 관례 — 코드 강제 아님, [escalate · 재진입 · 단방향 관례](#escalate-재진입-단방향-관례)).

## 체크포인트 → 다음 단계 매핑

| 체크포인트 (SKILL.md Step) | 응답 → 다음 |
|---|---|
| **1차 OK** (Step 5) | `OK` → Step 5.5 `product-acceptance:SPEC_ACCEPTANCE` · `patch` → 해당 섹션 Edit 후 Step 5 재진입 |
| **SPEC_ACCEPTANCE** (Step 5.5) | `PASS` → Step 6 (통합 브랜치 그릴) → Step 7 머지 · `FAIL` → gap patch 후 Step 5 재진입 · `ESCALATE` → 사용자 위임 |
| **이슈 등록** (Step 8) | `Y` → `create_epic_story_issues.sh` 실행 → Step 9 · `n` → 이슈 등록 보류 (사용자 자율) |
| **`/tech-review` 권고** (Step 9) | 외부 의존 0 개 → skip + 바로 `/design` 권고 echo · `Y` → `/tech-review` 진입 · `/tech-review` 종료 + 2차 OK → `/design` 권고 echo (`/architect-loop` 호환) |

표만으로 안 풀리는 맥락:

- **`/spec` / `/product-plan` 종료 시점** = PRD/stories.md/tech-review 스켈레톤이 `SPEC_ACCEPTANCE` 를 통과한 뒤 머지 + (선택) 이슈 등록 완료. 다음 명시 호출은 사용자 trigger (`/tech-review` 또는 `/design`; `/architect-loop` 호환) — 자동 진입 X.
- **`SPEC_ACCEPTANCE` 의미** = 좋은 아이디어인지 평가하는 단계가 아니라, 이후 구현과 검수가 가능한 spec 인지 확인하는 단계다. full E2E 검증은 MVP `/spec` 이행 범위 밖이다.
- **외부 의존 0 개 분기** = tech-review.md 스켈레톤이 "외부 의존 없음 — `/tech-review` skip" 상태면 `/tech-review` 단계 전체 skip.

## escalate · 재진입 · 단방향 관례

escalate 계열 수신 시 **메인이 즉시 사용자 보고 후 대기** (자동 복구 / 우회 / 재시도 금지 — [`../../CLAUDE.md`](../../CLAUDE.md) 강제 영역).

- **기존 PRD 변경** → 본 skill 재진입. `Edit` 도구 *섹션 단위 patch* 의무 (Write 통째 X — 기존 PRD 의 모르는 부분 silent 변경 위험).
- **PRD 위반 / 범위 escalate** → 설계·구현 단계의 agent (system-architect / module-architect / ux-architect / engineer) 가 PRD 불일치·범위 모호를 발견하면 작업 중단 + `/spec` 재진입 권고 (`/product-plan` 호환) 로 본 skill 로 되돌아온다 (해당 agent 가 직접 PRD 수정 X).
- **`UX_REFINE_READY` 후속** — ux-architect 가 REFINE 분기로 끝나면 designer 호출 (그 라우팅은 [`../architect-loop/architect-loop-routing.md`](../architect-loop/architect-loop-routing.md) 영역 — 본 skill 은 PRD 단계라 여기서 끝).

### 단방향 관례 — `/design` 진입 후 `/tech-review` 재호출 비권장

기술 NO_GO (사용 불가 / 비용 초과 / 라이선스 결격) 발견은 **`/tech-review` 단계에서 확정** 하는 게 좋다. `/design` (`/architect-loop` 호환) 진입 후엔 tech-reviewer 재호출이 관례상 비권장 — 코드 강제 아닌 자연어 관례 ([`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) 의 tech-review 자연어 관례). design/architect-loop 도중 미검증 외부 의존이 발견되면 그쪽 `NEW_DEP_ESCALATE` 3안으로 처리 ([`../architect-loop/architect-loop-routing.md`](../architect-loop/architect-loop-routing.md#escalate-처리)) — 어느 옵션이든 tech-reviewer 재호출 없음.

## 비대상 (다른 skill 추천)

- 버그 → `/issue-report` (qa 분류)
- 한 줄 수정 / 버그픽스 → `/impl` 또는 새 미분류 버그면 `/issue-report`
- 디자인만 → designer 직접 (Pencil 또는 `design-variants/*.html`)
- 이미 PRD/stories.md 머지 완료 → **먼저 외부 의존 검증 상태 확인**. 외부 의존 0개 (tech-review.md 스켈레톤이 "외부 의존 없음" 명시) *또는* `/tech-review` 통과 상태면 → 설계 `/design` (`/architect-loop` 호환) · 구현 `/impl` · 제품 검수 `/acceptance` (deep task 파일이 있으면 내부적으로 `/impl-loop` 위임). 미검증 외부 의존이 남았으면 → **먼저 `/tech-review`** (design 진입 후엔 tech-reviewer 재호출이 관례상 비권장이므로, [단방향 관례](#단방향-관례-design-진입-후-tech-review-재호출-비권장))

## 후속 (skill 종료 후)

- PRD/stories/tech-review 스켈레톤 완성 + 머지 + 이슈 등록 → `/tech-review` (선행 기술 검증) → 사용자 2차 OK → `/design` (`/architect-loop` 호환) → `/impl` → `/acceptance`
- 외부 의존 0 개 PRD → `/tech-review` skip + 바로 `/design` (`/architect-loop` 호환)
- 기존 PRD 변경 → 본 skill 재진입 (`Edit` 섹션 단위 patch 의무)
