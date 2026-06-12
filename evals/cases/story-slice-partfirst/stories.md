# Story Backlog

## Epic — 쇼츠 영상 자동 생성

**목표**: 1인 크리에이터가 프롬프트 입력만으로 쇼츠 영상을 생성·업로드할 수 있게 한다.
**선행 조건**: 없음
**완료 기준** (epic 단위 수용 기준):
1. 프롬프트 입력 → 9:16 영상 생성 → 업로드까지 한 흐름이 동작한다.

**GitHub Epic Issue:** 미등록 (사유: eval fixture)

---

### Story 1 — 인테이크 모듈

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** 주제 입력 스키마와 인테이크 포트 계층이 정의되길,
**So that** 이후 모듈이 입력 데이터를 소비할 수 있다.

---

### Story 2 — 템플릿 엔진

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** 장면 템플릿 엔진과 어댑터 계층이 구현되길,
**So that** 렌더 모듈이 장면 데이터를 받을 수 있다.

---

### Story 3 — 오디오 처리 모듈

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** 나레이션 합성 유즈케이스 계층이 구현되길,
**So that** 렌더 모듈이 audio_mode 산출물을 소비할 수 있다.

---

### Story 4 — 렌더 파이프라인

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** 9:16 렌더 파이프라인이 구현되길,
**So that** 업로드 모듈이 완성 영상을 받을 수 있다.

---

### Story 5 — 업로드와 통합 배선

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** YouTube 업로드와 전체 모듈 통합 배선이 구현되길,
**So that** 프롬프트 입력부터 업로드까지 처음으로 동작한다.
