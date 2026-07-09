---
depth: simple|std|deep
design: optional|required
story: <N|공통>
task_index: <i>/<total>|—
risk: normal|high|low   # 구현 시점 위험 등급. high = migration/destructive, 보안·규제 auth/PII, public API breakage, 외부 HTTP, 신뢰 경계 밖 입력 파싱, 신규 3rd-party/외부 서비스. 부재 시 impl-loop 진입에서 메인이 추론(하위호환)
engine: 2agent|4agent   # 권장 엔진. 2agent = build-worker(경량) · 4agent = 풀 경로(test-engineer→engineer→impl-validator). risk: high → 4agent
risk_reason:            # 자연어 한 줄 — 판정 근거. 예: "외부 HTTP", "신뢰 경계 밖 입력 파싱", "auth/PII", "destructive schema 변경" / 고위험 아니면 "고위험 trigger 없음"
depends_on:             # [<NN-slug>, ...] 선행 task (contract/ordering 의존 흡수). 선행 없으면 [] 로 명시. 비운 채로 두면(미작성) 미상 → 병렬에서 직렬 강등
---

# <NN-task-slug>

## 사전 준비

- 읽을 문서 (task-specific docs 만 남긴다):
  - `docs/conventions.md` (코드 변경 task 기본)
  - `docs/epics/<epic>/stories.md` (해당 Story/공통 task 근거)
  - `docs/epics/<epic>/architecture.md` (module responsibility / public interface / Story -> 모듈 매핑)
  - `docs/modules/<module-id>/architecture.md` (affected owner module 한정)
  - `docs/modules/<module-id>/conventions.md` (affected owner module 한정)
  - `docs/decisions/NNNN-slug.md` (해당 계약/결정만)
  - `docs/epics/<epic>/domain-model.md` / `docs/design.md` / `docs/design-variants/<screen-id>.html` (task가 직접 쓰는 경우만)
- 읽을 코드:
  -

> 전역 고정 문서 목록을 복제하지 않는다. 단, `docs/conventions.md` 는 코드 변경 task 의 전역 코딩 규약 전달 경로이므로 기본으로 둔다. 선행 task 는 frontmatter `depends_on` 이 단일 SSOT 다 (병렬 독립성 판정 입력).

## 무엇을 만드나

- 구현 대상과 Story 완료 시 실제로 검증되는 동작 (1-2줄):
- 제품 경계(UI/API/CLI/worker entrypoint/통합 wiring):
- 첫 동작 증거 지점:

## 왜 만드나

- PRD/Story 근거와 병렬성보다 동작 슬라이스를 우선한 결정 (1-2줄):
- Story 마지막 task까지 밀리면 warning / 불가피한 이유 / 후속 검증:

## 디자인 참조

> UI task 한정. `design: required` 이거나 UI 기준 확보 분기가 `기준 있음` / `신규 시각 구조 + 기준 없음` 으로 판정된 task 는 확정 목업 경로와 핵심 node-id 매핑을 적는다. non-UI task 는 이 섹션 전체를 삭제한다.

- 확정 목업 경로: `docs/design-variants/<screen-id>.html` 또는 해당 없음
- canvas 경로: `docs/design-variants/canvas.html` 또는 해당 없음
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
- owner/entrypoint 요약 (entrypoint task 한정; 비-entrypoint task 는 생략):
  - owner flow/module:
  - entrypoint role:
  - state owner:
  - validation path:

## 수용 기준

> 검증은 기본적으로 실행 가능한 명령이다. manual QA 는 명령 변환 불가 사유와 관찰 증거를 같이 적을 때만 허용한다.

| REQ | 내용 | 검증 명령 | 통과 조건 |
|---|---|---|---|
| REQ-001 |  | `(TEST) <command>` |  |
| REQ-UI-001 |  | `(MANUAL QA: 명령 변환 불가 사유=<reason>) <관찰 증거>` |  |

## 주의사항

- 모듈 설계 주의: Deep module / DI·의존 주입 / 공개 노출 범위 / 의존 차단 중 이 task 가 반드시 지킬 제약만 적는다.
- public contract 의미는 module responsibility / public interface 와 decision 문서에 두고, impl 문서에는 링크만 남긴다.
- 구현 세부(pseudo-code, private helper name, forced test-function name)를 선점하지 않는다.
