---
name: spec
description: 새 기능 / PRD 변경 / 큰 기획을 받아 메인 Claude 가 사용자와 직접 그릴미 대화하며 `docs/prd.md` 초안 작성 → 사용자 초안 확인 → 기술 검토 필요 영역에 항목이 있으면 `/tech-review` preflight 실행 → tech-review 결과를 반영해 PRD 최종화 → epic 단위 `docs/epics/epic-NN-<slug>/stories.md` 작성 → 사용자 최종 OK → `product-acceptance:SPEC_ACCEPTANCE` → PR 머지 → 이슈 등록 여부 확인 → `/design` 권고 시퀀스로 진행하는 `/spec` 절차. 구현 진입은 `/impl` 이 구현 경로를 판정하고, story/epic 구현 완료 후 `/acceptance` 로 제품 검수한다.
---

# Spec Skill — PRD / Story 작성 절차

본 스킬은 사용자-facing 기본 공개 진입점의 `/spec` 이다. 기본 공개 진입점은 `/spec -> /design -> /impl -> /acceptance` 다.

흐름 요약: PRD 초안 → 사용자 초안 확인 → 기술 검토 필요 영역에 항목이 있으면 `/tech-review` preflight → PRD 최종화 → stories.md → `product-acceptance:SPEC_ACCEPTANCE` → PR 머지 → 이슈 등록 여부 확인 → `/design`.

분기 규칙 SSOT 는 [`spec-routing.md`](spec-routing.md) 다. 본 파일은 Step 운전 절차만 담는다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../docs/plugin/terms.md) 를 확인한다.

## References

- PRD 템플릿: [`templates/prd.md`](templates/prd.md)
- 그릴미 / AC / 기술 검토 필요 영역 작성 기준: [`spec-prd-reference.md`](spec-prd-reference.md)
- stories.md 형식 / Story 크기 가이드: [`spec-stories-reference.md`](spec-stories-reference.md)
- branch / PR / issue 등록 명령 예시: [`spec-delivery-reference.md`](spec-delivery-reference.md)
- skill 간 분기 / 재진입 / 단방향 관례: [`spec-routing.md`](spec-routing.md)
- 용어 사전: [`docs/plugin/terms.md`](../../docs/plugin/terms.md)

## 작성 절차 (메인 직접)

### Step 0 — 사전 read

정상 흐름은 본 파일과 필요한 reference 만 읽고 진행한다. 분기 판단이 필요하면 [`spec-routing.md`](spec-routing.md)를 확인한다.

### Step 1 — 사용자와 그릴 대화

메인이 사용자와 직접 대화한다. 목표는 핵심 분기에서 `shared understanding` 에 도달하는 것이다. 질문은 한 번에 하나씩 하고, 코드로 확인 가능한 것은 코드베이스에서 확인한다.

그릴 강도와 PRD 템플릿 작성 기준은 [`spec-prd-reference.md`](spec-prd-reference.md)를 따른다.

### Step 2 — PRD 초안 작성

메인이 [`templates/prd.md`](templates/prd.md)를 문서 템플릿으로 사용해 `docs/prd.md` 를 초안으로 Write/Edit 한다. 변경은 섹션 단위 patch 로 한다.

`docs/prd.md` 초안 작성 → 사용자 초안 확인 흐름을 반드시 거친다. 초안에는 PRD 작성 중 이미 판단한 **기술 검토 필요 영역**을 포함한다. 검토 항목 0 개면 "해당 없음" 으로 닫는다.

### Step 3 — 사용자 PRD 초안 확인

PRD 초안 작성 직후 사용자에게 확인을 받는다.

```text
PRD 초안 작성 완료:
- docs/prd.md

검토 후 결정:
- OK → Step 4 tech-review preflight 확인
- patch 필요 → 어떤 섹션 / 어떤 내용 알려주세요
```

사용자 patch 요청 시 `docs/prd.md` 해당 섹션을 patch 한 뒤 다시 Step 3 으로 돌아온다.

### Step 4 — tech-review preflight 확인과 실행

메인이 PRD 초안의 **기술 검토 필요 영역**을 확인한다. 이 단계에서 외부 의존 / 비용 / 실현성 기준을 새로 판정하지 않는다. 그 기준은 Step 2 PRD 초안 작성 때 이미 적용되어 있어야 한다.

- 검토 항목 0 개 또는 "해당 없음" → Step 5 PRD 최종화
- 검토 항목 1 개 이상 → `/tech-review` preflight 진입

기술 검토 필요 영역 작성 기준은 [`spec-prd-reference.md`](spec-prd-reference.md#기술-검토-필요-영역-작성-기준)를 따른다.

```text
PRD 초안의 기술 검토 필요 영역에 검토 항목이 있어 PRD 최종화 / stories.md 작성 / 이슈 등록 전에 /tech-review 를 먼저 진행합니다.

입력:
- docs/prd.md 의 기술 검토 필요 영역

진행할까요? (Y/n)
```

분기:

- 사용자 Y 또는 명시 진행 → `/tech-review` 실행. tech-reviewer 가 `docs/prd.md` 를 읽고 `docs/tech-review.md` 를 생성/갱신하며 evidence/report 는 `.dcness-work/reviews/` 에 저장한다.
- `/tech-review` PASS + 사용자 2차 OK → Step 5
- `/tech-review` FAIL / NO_GO / PRD 재기술 → 메인이 `docs/prd.md` 를 섹션 단위 patch 한 뒤 필요하면 `/tech-review` 재실행
- 사용자 n / 보류 / ESCALATE → 사용자 위임. PRD 최종화 / stories.md 작성 / PR 머지 / 이슈 등록으로 진행하지 않는다.

### Step 5 — PRD 최종화

메인이 `docs/prd.md` 를 최종 PRD 로 업데이트한다. 별도 `prd-final.md` 는 만들지 않는다.

- tech-review preflight 가 없었으면 사용자 확인을 통과한 초안을 최종으로 취급한다.
- tech-review preflight 가 있었으면 `docs/tech-review.md` 의 verdict / 스펙 조정 권고 / 사용자 2차 OK 내용을 PRD 에 반영한다.
- 미해결 기술 질문이 남아 있으면 최종화하지 않는다.

### Step 6 — stories.md 작성

최종 PRD 기준으로 epic 단위 `docs/epics/epic-NN-<slug>/stories.md` 를 작성한다.

산출 형식은 [`spec-stories-reference.md`](spec-stories-reference.md)를 따른다. Story 분할과 순서도 같은 reference 의 사용자 검증 가능한 동작 증분 / 얇은 골격 우선 기준을 따른다.

stories.md 작성 직후 메인은 활성 프로젝트 루트에서 `node "$PLUGIN_ROOT/scripts/aggregate_index_map.mjs"` 를 실행해 `docs/index.md` 의 `## 에픽` 생성 표를 갱신한다. 이 갱신이 빠지면 새 epic PR 이 doc-sync 게이트에서 stale 로 막힌다.

### Step 7 — 사용자 최종 OK 체크포인트

PRD 최종본 + 필요한 tech-review 산출물 + stories.md 작성 완료 후 사용자에게 확인을 받는다.

```text
최종 확인:
- docs/prd.md — PRD 최종본
- `docs/epics/epic-NN-<slug>/stories.md` — Epic + N Story
- docs/tech-review.md — 기술 검토 결과 (기술 검토 필요 영역에 항목이 있었을 때)

검토 후 결정:
- OK → Step 8 product-acceptance:SPEC_ACCEPTANCE
- patch 필요 → 어떤 섹션 / 어떤 내용 알려주세요
```

사용자 patch 요청 시 해당 섹션을 patch 한다. 기술 검토 필요 영역 영향이 있으면 Step 4 로 돌아가고, 없으면 Step 7 로 돌아온다.

### Step 8 — product-acceptance:SPEC_ACCEPTANCE

사용자 최종 OK 후, branch 만들기 전 메인이 `product-acceptance` agent 를 `SPEC_ACCEPTANCE` mode 로 호출한다.

```text
mode: SPEC_ACCEPTANCE
검수 단위: 현재 /spec 산출물
기준 문서:
- docs/prd.md
- docs/epics/epic-NN-<slug>/stories.md
- docs/tech-review.md (있으면)

목적:
이 spec 이 이후 설계/구현/검수에 충분히 닫혔는지 확인한다.
좋은 아이디어인지 평가하지 말고, AC binary 여부, 검수 증거 기준,
외부 의존/보안/권한/데이터 질문 누락, Story/Epic 분할 명확성,
Story 분할·순서가 사용자 검증 가능한 동작 증분인지를 본다.
full E2E 검증은 MVP /spec 이행 범위 밖이다.
```

- `PASS` → Step 9
- `FAIL` → gap 보고 + 메인 patch 후 Step 7
- `ESCALATE` → 기준 문서/권한/사용자 결정 부족 보고 후 사용자 위임

### Step 9 — 통합 브랜치 그릴

PRD/stories.md 검증 완료 후 branch 만들기 전 사용자에게 작업 전략을 묻는다.

- `a` 일반 → `docs/<slug>` 브랜치로 Step 10
- `b` 통합 브랜치 → `feature/<slug>` 생성 후 `docs/<slug>_prd` sub-PR 로 Step 10

통합 브랜치 선택 시 stories.md 상단에 `**Base Branch:** feature/<slug>` 를 추가한다.

### Step 10 — branch + commit + PR + 머지

Step 9 의 선택에 따라 PRD/stories.md PR 을 만들고 머지한다.

명령 예시는 [`spec-delivery-reference.md`](spec-delivery-reference.md)를 따른다. preflight 를 실행했다면 PR 에 `docs/tech-review.md` 를 포함한다. `.dcness-work/reviews/` 는 git-tracked PR 대상이 아니다.

### Step 11 — 이슈 등록 trigger (선택)

PR 머지 완료 후 사용자에게 확인한다.

```text
PRD + stories.md 머지 완료. 이제 GitHub epic + story 이슈를 등록할까요? (Y/n)
```

- 사용자 Y → [`spec-delivery-reference.md`](spec-delivery-reference.md#이슈-등록)의 `scripts/create_epic_story_issues.sh` 흐름 실행. 실행 전 보드(Project) 좌표·field 를 점검해 없거나 불완전하면 사용자에게 보드 셋업을 물어보고(거부 시 보드 없이 이슈만 생성), 스크립트가 생성된 epic/story 를 보드에 `Status=Todo`·`IssueType`·`Priority=major` 로 등록한다
- 사용자 n → 이슈 등록 보류. `/design` pre-flight 가 통과하도록 stories.md 의 epic/story issue marker 를 `**GitHub Epic Issue:** 미등록 (사유: …)` / `**GitHub Issue:** 미등록 (사유: …)` 형태로 남긴다. 기존 marker 가 없으면 별도 doc patch PR 로 marker 를 머지한 뒤 Step 12 로 간다.

이슈 등록 또는 미등록 marker 변경분은 별도 commit + PR 또는 사용자 자율이다.

### Step 12 — `/design` 권고

이슈 등록 완료 또는 보류 marker 확인 후 메인이 사용자에게 confirm 한다.

```text
PRD + stories.md + tech-review 상태 확인 완료.
이슈 등록: 완료 또는 보류 marker 확인 완료.

다음 단계 — 설계 루프:
→ /design <epic-path>

단방향 관례:
/design 진입 후 tech-reviewer 재호출은 비권장.
기술 검토 필요 영역에 항목이 있었다면 PRD 확정 / stories.md 작성 / 이슈 등록 전에 /tech-review preflight 로 이미 확정했어야 함.

진행할까요? (Y/n)
```

사용자 Y → `/design` 진입. 사용자 n → 사용자가 나중에 직접 호출한다.

## 워크트리

`/spec` 은 워크트리 자동 진입 안 함. 기획·설계는 동시 다중 batch 충돌 회피 목적 부재. 메인 working tree 에서 별도 branch 를 따고 직접 진행한다.
