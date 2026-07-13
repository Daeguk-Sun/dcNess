# spec 분기 규칙 SSOT

> **Status**: ACTIVE
> **Scope**: `/spec` 공개 진입점의 skill 간 이동·재진입·escalate·단방향 관례·비대상 추천 진본. 본 skill 은 **메인 Claude 직접 작업** 이라 내부 구현 agent 매핑은 거의 없다. 단 `/spec` 이행 기준 검수로 `product-acceptance:SPEC_ACCEPTANCE` 를 호출한다. skill 간 시퀀스는 PRD 초안 → 사용자 초안 확인 → 기술 검토 필요 영역에 항목이 있으면 `/tech-review` preflight → PRD 최종화 → stories.md → SPEC_ACCEPTANCE → PR 머지 → 이슈 등록 여부 확인 → `/design` → `/impl` → `/acceptance` 다. 진행 절차(Step) 는 [`SKILL.md`](SKILL.md).
> **Cross-ref**: 순서 차단 훅 보존 = [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) · 강제 영역 = [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md) · 용어 기준 = [`terms.md`](../../docs/plugin/terms.md).

## 읽는 법

본 skill 은 메인이 사용자와 직접 그릴미 대화하며 산출물을 만든다. 진행 절차와 체크포인트 응답 분기는 [`SKILL.md`](SKILL.md)가 소유한다. 이 문서는 Step 내부 분기를 다시 그리지 않고, skill 간 이동과 재진입 경계만 정한다. 형식 강제가 아니라 *판단 보조* — 의미만 맞으면 된다. 모호하면 사용자에게 위임한다.

## 소유권 분리

- **Step 내부 분기** — [`SKILL.md`](SKILL.md)가 소유한다. PRD 초안 확인, tech-review preflight 실행 여부, 최종 OK, SPEC_ACCEPTANCE 결과 처리, PR 머지, 이슈 등록 marker 기록은 Step 절차 안에서 판단한다.
- **skill 간 이동** — 이 문서가 소유한다. `/tech-review` preflight, `product-acceptance:SPEC_ACCEPTANCE`, `/design`, `/impl`, `/acceptance` 로 넘어가는 경계를 설명한다.
- **PRD 작성 기준** — [`spec-prd-reference.md`](spec-prd-reference.md)가 소유한다. 그릴미 질문 축, PRD 기록 위치, 기능 나열·유저 시나리오, 기술 검토 필요 영역 기준은 여기서 반복하지 않는다. Story AC 작성 기준은 [`spec-stories-reference.md`](spec-stories-reference.md)가 소유한다.

## skill 간 이동

- `/tech-review` 는 PRD 최종화 / stories 작성 / PR 머지 / 이슈 등록 전에 실행되는 preflight 다. PRD 초안의 기술 검토 필요 영역에 검토 항목이 없으면 skip 하고 PRD 최종화로 간다. **`/design` 진입 후 `/tech-review` 재호출은 비권장** (단방향 관례 — 코드 강제 아님, [escalate · 재진입 · 단방향 관례](#escalate-재진입-단방향-관례)).
- `product-acceptance:SPEC_ACCEPTANCE` 는 PRD 최종본 + stories.md + 필요한 tech-review 산출물이 이후 설계/구현/검수에 충분히 닫혔는지 확인한다. 좋은 아이디어인지 평가하지 않고, full E2E 검증은 MVP `/spec` 이행 범위 밖이다.
- `/spec` 종료 경로는 PR 머지 → 이슈 등록 여부 확인 → `/design` 권고다. 이슈 등록 보류 시, 이슈 등록 보류 marker 는 stories.md 의 `미등록 (사유: …)` marker 로 남겨 `/design` pre-flight 와 정합시킨다. 다음 명시 호출은 사용자 trigger (`/design`) — 자동 진입 X.
- `/design` 이후 구현 진입은 `/impl`, story/epic 구현 완료 후 제품 검수는 `/acceptance` 가 담당한다.

## escalate · 재진입 · 단방향 관례

escalate 계열 수신 시 **메인이 즉시 사용자 보고 후 대기** (자동 복구 / 우회 / 재시도 금지 — [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md) 강제 영역).

- **기존 PRD 변경** → 본 skill 재진입. `Edit` 도구 *섹션 단위 patch* 의무 (Write 통째 X — 기존 PRD 의 모르는 부분 silent 변경 위험).
- **PRD 위반 / 범위 escalate** → 설계·구현 단계의 agent (system-architect / module-architect / ux-architect / build-worker) 가 PRD 불일치·범위 모호를 발견하면 작업 중단 + `/spec` 재진입 권고로 본 skill 로 되돌아온다 (해당 agent 가 직접 PRD 수정 X).
- **`UX_REFINE_READY` 후속** — ux-architect 가 REFINE 분기로 끝나면 designer 호출 (그 분기 규칙은 [`../design/design-routing.md`](../design/design-routing.md) 영역 — 본 skill 은 PRD 단계라 여기서 끝).

### 단방향 관례 — `/design` 진입 후 `/tech-review` 재호출 비권장

기술 NO_GO (사용 불가 / 비용 초과 / 라이선스 결격) 발견은 PRD 최종화 전에 **`/tech-review` preflight** 로 확정한다. `/design` 진입 후엔 전역 `/tech-review` 재진입이 관례상 비권장 — 코드 강제 아닌 자연어 관례 ([`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) 의 tech-review 자연어 관례). `/design` 도중 미검증 외부 의존이 발견되면 그쪽 `NEW_DEP_ESCALATE` 4안으로 처리한다 ([`../design/design-routing.md`](../design/design-routing.md#escalate-처리)).

## 비대상 (다른 skill 추천)

- 버그 수정 / 한 줄 수정 → `/impl`
- GitHub issue 초안/등록 → `/to-issue`
- 디자인만 → `docs/design-variants/` seed 보장 후 designer 직접 (`docs/design-variants/drafts/*.html` static HTML draft)
- 이미 PRD/stories.md 머지 완료 → PRD 의 **기술 검토 필요 영역**과 `docs/tech-review.md` 존재 여부를 먼저 확인. 미검증 검토 항목이 남았으면 `/design` 으로 가지 말고 `/spec` 재진입 또는 `/tech-review` preflight 로 회수한다.

## 후속 (skill 종료 후)

- PRD 최종본 + stories.md + 필요한 tech-review 산출물 완성 + PR 머지 → 이슈 등록 여부 확인 → `/design` → `/impl` → `/acceptance`
- 기술 검토 필요 영역이 "해당 없음" 인 PRD → `/tech-review` skip + PRD 최종화 + stories.md 작성
- 기존 PRD 변경 → 본 skill 재진입 (`Edit` 섹션 단위 patch 의무)
