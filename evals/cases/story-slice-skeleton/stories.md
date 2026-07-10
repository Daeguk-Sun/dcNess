---
epic: epic-01-shorts-skeleton
milestone: v01
---

# Story Backlog

## Epic — 쇼츠 영상 자동 생성

**목표**: 1인 크리에이터가 프롬프트 입력만으로 쇼츠 영상을 생성·업로드할 수 있게 한다.
**선행 조건**: YouTube 테스트 채널 최초 1회 연결(OAuth) — Story 1 골격 실행 전 fixture 로 제공
**완료 기준** (epic 단위 수용 기준):
1. [command] 프롬프트 입력 → 9:16 영상 생성 → 업로드까지 한 흐름의 smoke가 종료코드 0으로 끝난다.

**GitHub Epic Issue:** 미등록 (사유: eval fixture)

---

### Story 1 — 프롬프트 → 무음 영상 비공개 업로드 골격 동선

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** 주제 프롬프트를 입력하면 고정 템플릿의 무음 9:16 영상 1편이 비공개로 업로드되길,
**So that** 입력부터 최종 전달 경계까지 전체 흐름을 처음부터 직접 확인할 수 있다.

**Acceptance criteria:**
- AC-001 [command]: Given OAuth 연결된 테스트 채널과 주제 프롬프트, When 골격 smoke를 실행하면, Then 무음 9:16 영상이 비공개로 게시되고 종료코드가 0이다.

---

### Story 2 — 나레이션 오디오 증분

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** Story 1 골격 위에서 업로드 영상에 나레이션이 입혀지길,
**So that** 소리 있는 쇼츠를 바로 확인할 수 있다.

**Acceptance criteria:**
- AC-002 [command]: Given Story 1의 업로드 동선, When 나레이션 증분 smoke를 실행하면, Then 게시된 mp4에 오디오 트랙이 있고 decoder probe가 종료코드 0이다.

---

### Story 3 — YouTube 업로드 복구 증분

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** 업로드 쿼터 초과 시 재시도 시점을 안내받길,
**So that** 게시 실패를 성공으로 오인하지 않고 복구할 수 있다.

**Acceptance criteria:**
- AC-003 [agent-read]: Given 업로드 쿼터 초과 응답, When 실패 결과를 확인하면, Then 다음 재시도 가능 시점과 미게시 상태가 표시된다.
