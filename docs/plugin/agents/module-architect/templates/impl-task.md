---
design: optional|required
story: <N|공통>
task_index: <i>/<total>|—
depends_on:             # [<NN-slug>, ...] 선행 의존 그래프의 단일 SSOT. semantic produces/consumes 는 아래 owner/entrypoint 요약에 기록. 선행 없으면 [] 로 명시. 비운 채로 두면(미작성) 미상 → 병렬에서 직렬 강등
---

# <NN-task-slug>

> 파일명 `NN-<task-slug>.md` 의 zero-padded `NN` 은 이 설계 pack 의 전역 serial traversal 순번이다. path 정렬 결과가 `depends_on` 위상 순서를 지키고, 같은 `story` 값의 task 를 하나의 연속 block 으로 배치해야 한다. `task_index` 는 Story 내부 순번이므로 파일명 `NN` 과 별개다.

## 사전 준비

- 읽을 문서 (task-specific docs 만 남긴다):
  - `docs/conventions.md` (코드 변경 task 기본)
  - `docs/epics/<epic>/stories.md` (해당 Story/공통 task 근거)
  - `docs/epics/<epic>/architecture.md` (module responsibility / public interface / Story -> 모듈 매핑)
  - `docs/modules/<module-id>/architecture.md` (affected owner module 한정)
  - `docs/modules/<module-id>/conventions.md` (affected owner module 한정)
  - `docs/decisions/NNNN-slug.md` (해당 계약/결정만)
  - `docs/epics/<epic>/domain-model.md` / `docs/design.md` / `docs/design-variants/screens/<screen-id>.html` (task가 직접 쓰는 경우만)
- 읽을 코드:
  -

> 전역 고정 문서 목록을 복제하지 않는다. 단, `docs/conventions.md` 는 코드 변경 task 의 전역 코딩 규약 전달 경로이므로 기본으로 둔다. 선행 의존 그래프는 frontmatter `depends_on` 이 단일 SSOT 다(병렬 독립성 판정 입력). serial traversal 은 파일명 `NN-`, Story 내부 완료 위치는 `task_index` 가 소유한다. 생산·소비하는 상태 의미는 아래 owner/entrypoint 요약에서 복구한다.

## 무엇을 만드나

- 구현 대상과 Story 완료 시 실제로 검증되는 동작 (1-2줄):
- 제품 경계(UI/API/CLI/worker entrypoint/통합 wiring):
- 첫 동작 증거 지점:

### replacement/refactor/migration cleanup (해당 task만, 일반 feature는 이 절 삭제)

- 기존 표면 → 새 표면 관계:
- 제거 후보 (call site / DI / route / registration / resource / test double / suppression 중 해당 항목):
- 의도적으로 보존할 seam과 이유 / owner:

## 왜 만드나

- PRD/Story 근거와 병렬성보다 동작 슬라이스를 우선한 결정 (1-2줄):
- 첫 제품 동작 증거가 Story 마지막 task까지 밀리면 warning / 불가피한 이유:
- Story 마지막 task 한정 — Story AC 전항목 실행 검증 책임과 검증 동선:

## 디자인 참조

> UI task 한정. `design: required` 이거나 UI 기준 확보 분기가 `기준 있음` / `신규 시각 구조 + 기준 없음` 으로 판정된 task 는 확정 목업 경로, 핵심 디자인 토큰, 핵심 node-id 매핑을 적는다. 핵심 디자인 토큰은 색/spacing/typography 를 node-id 매핑과 나란히 남긴다. non-UI task 는 이 섹션 전체를 삭제한다.

- 확정 목업 경로: `docs/design-variants/screens/<screen-id>.html` 또는 해당 없음
- 보드 진입점: `docs/design-variants/README.md` 또는 해당 없음
- 핵심 디자인 토큰:
  - 색 토큰: `<docs/design.md colors.* token>` → `<앱 theme/component 적용 지점>`
  - spacing 토큰: `<docs/design.md spacing.* token>` → `<앱 layout/component 적용 지점>`
  - typography 토큰: `<docs/design.md typography.* token>` → `<앱 text style 적용 지점>`
- 핵심 `data-node-id` → 구현 컴포넌트/상태:
  - `<screen-id>.<node>` → `<component or state>`
- 목업 대비 의도적 차이:
  -

## Scope

### 수정 허용

> 기본값은 owner module directory grant 다. **한 bullet = 정확히 하나의 repo-relative 파일 경로 또는 끝 `/` 디렉토리**이고, 모듈 작업은 `src/<owner-module>/` 처럼 owner module directory 를 끝 `/` 로 연다. 그 디렉토리 안의 신규 파일은 구현자 재량이다. 같은 owner directory 를 여러 task 가 나눠 병렬/분할 구현할 때만 file-level path 로 좁힌다. 테스트 grant 는 test root 전체(예: `app/src/test/java/<root-package>/`)가 아니라 owner module 에 대응하는 하위 디렉토리(예: `app/src/test/java/<root-package>/<owner-module>/`)로 좁힌다. 대응 하위 경로를 특정할 수 없는 공통 기반 task 만 넓은 테스트 grant 를 허용하고 `# 사유: ...`처럼 사유를 주석으로 남긴다. 부가 설명은 `# 주석` 또는 blockquote 로 적는다.

- `src/<owner-module>/`

### 수정 금지

-

## 인터페이스

- 계약/결정 링크:
  - module: `<module-id>` (`docs/epics/<epic>/architecture.md` 모듈 목록)
  - decision: `docs/decisions/NNNN-slug.md` 또는 해당 없음
- task 내부 한정 private interface:
- owner/entrypoint 요약 (entrypoint task 한정 또는 cross-task state producer/consumer task):
  - owner flow/module:
  - entrypoint role: # 해당 시
  - state owner:
  - produced transition:
  - consumer / consumed state:
  - validation path:

## 수용 기준

> 제품 REQ 는 Story AC 를 task 실행 언어로 번역하고 출처에 `(from AC-NNN)` 을 반드시 적는다. Story AC 로 환원되지 않는 스키마·인터페이스 형태 같은 소수 기술 계약만 `기술 REQ` + `(technical: <환원 불가 이유>)`로 구분한다. 검증은 실행 가능한 명령, `(AGENT READ)` 관찰 증거, 또는 실제 앱 실행이 필요한 `(JOURNEY)` flow로 닫고, 사람 판정 항목은 REQ 에 넣지 않는다.

| REQ | 유형 | 내용 | 출처 | 검증 명령 | 통과 조건 |
|---|---|---|---|---|---|
| REQ-001 | Story AC |  | `(from AC-001)` | `(TEST) <command>` |  |
| REQ-002 | Story AC |  | `(from AC-002)` | `(AGENT READ) <관찰 대상과 방법>` |  |
| REQ-003 | Story AC | 로그인→홈 진입 | `(from AC-003)` | `(JOURNEY) <flow/매니페스트 경로>` | receipt outcome=PASS, app_started·journey_executed·assertion.passed=true, 대상 AC 전부 덮음, UI 경계면 `ux_integrity` 판정 요소가 `within_safe_area=true`·`occluded_by` 없음 |
| REQ-TECH-001 | 기술 REQ |  | `(technical: <Story AC로 환원 불가한 이유>)` | `(TEST) <command>` |  |

> `(JOURNEY)`는 실제 앱/디바이스를 띄워야 하는 자동화 검증이다. 각 `(JOURNEY)` REQ는 project-local 매니페스트에 materialize할 `acceptance_environment`(`automation: automated | human_verification`, worker 실행 컨텍스트의 `requirements[].probe`, 선택 `prepare`)와 flow/seed/runner/manifest/env adapter의 `harness_paths`를 이 표의 검증 명령 또는 통과 조건에서 경로와 함께 선언한다. UI 경계 `(JOURNEY)`는 요소가 보인다는 조건만으로 통과 조건을 쓰지 않고, 판정 근거가 될 화면 요소와 그 요소가 시스템 chrome·상위 레이어에 가리지 않아야 한다는 UX 정합성 조건(`ux_integrity`)을 함께 선언한다. 위 `디자인 참조` 절에 확정 목업이 있으면 핵심 `data-node-id` 를 그 판정 요소로 지목해 목업 기준과 journey 판정을 잇는다. task 구현 호출은 flow·매니페스트를 작성하고, 모든 task 뒤 fresh build-worker 수렴 호출이 tip에서 실행·관찰·수정하며, product-acceptance는 별도 sealed 실행으로 판정한다. 사람 눈이 반드시 필요한 항목은 가짜 journey로 만들지 않고 `automation: human_verification`과 기존 REQ 밖 `사람 확인 안내`로 분리한다.
>
> negative 동작 계약은 대응하는 양성 프록시 event를 REQ 통과 조건에 명시한다. 양성 프록시가 없거나 관찰 창이 sub-second인 상태, 순수 위치·픽셀 판정은 flaky한 `(JOURNEY)`로 만들지 않고 `사람 확인 안내`로 분리한다.

> `task_index: i/total` 에서 `i == total` 인 Story 마지막 task 는 해당 Story AC 전항목을 이 표에서 다시 인용하고 실제 실행·관찰하는 종합 검증 REQ 를 둔다. 앞 task 에서 검증한 항목도 마지막 task 전수 검증에서 생략하지 않는다. `story: 공통` task 에는 이 의무를 적용하지 않는다.

## 주의사항

- 모듈 설계 주의: Deep module / DI·의존 주입 / 공개 노출 범위 / 의존 차단 중 이 task 가 반드시 지킬 제약만 적는다.
- public contract 의미는 module responsibility / public interface 와 decision 문서에 두고, impl 문서에는 링크만 남긴다.
- 계약 전문을 복제하지 않더라도 이 task가 담당하는 transition, 실패 책임, 검증 acceptance는 생략하지 않는다.
- 구현 세부(pseudo-code, private helper name, forced test-function name)를 선점하지 않는다.
