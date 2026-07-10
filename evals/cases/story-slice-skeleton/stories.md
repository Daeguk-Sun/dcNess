# Story Backlog

## Epic — 쇼츠 영상 자동 생성

**목표**: 1인 크리에이터가 프롬프트 입력만으로 쇼츠 영상을 생성·업로드할 수 있게 한다.
**선행 조건**: YouTube 채널 최초 1회 연결(OAuth) — Story 3 업로드 전 완료
**완료 기준** (epic 단위 수용 기준):
1. 프롬프트 입력 → 9:16 영상 생성 → 업로드까지 한 흐름이 동작한다.

**GitHub Epic Issue:** 미등록 (사유: eval fixture)

---

### Story 1 — 프롬프트 → 무음 영상 골격 동선

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** 주제 프롬프트를 입력하면 고정 템플릿의 무음 9:16 영상 1편이 생성되길,
**So that** 입력부터 결과 파일까지 전체 흐름을 처음부터 직접 확인할 수 있다.

**Acceptance criteria:**
- AC-001 [command]: Given 주제 프롬프트, When 생성 버튼을 누르면, Then 무음 9:16 mp4를 다운로드할 수 있다.

---

### Story 2 — 나레이션 오디오 증분

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** Story 1 골격 위에서 생성 영상에 나레이션이 입혀지길,
**So that** 소리 있는 쇼츠를 바로 확인할 수 있다.

**Acceptance criteria:**
- AC-002 [command]: Given Story 1의 생성 동선, When 영상을 재생하면, Then 나레이션이 들린다.

---

### Story 3 — YouTube 업로드 증분

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 크리에이터,
**I want** 생성된 영상을 버튼 한 번으로 YouTube 에 업로드하길,
**So that** 생성부터 게시까지 한 동선으로 끝낼 수 있다.

**Acceptance criteria:**
- AC-003 [command]: Given 생성 완료 화면, When 업로드 버튼을 누르면, Then 내 채널에 비공개 영상이 게시된다.
