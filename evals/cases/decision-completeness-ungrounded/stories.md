---
epic: epic-01-request-approval
milestone: v01
---

# Story Backlog

## Epic — 비용 요청 승인

**목표**: 구성원이 요청을 제출하고 승인 결과와 증빙 보존 상태를 확인한다.
**완료 기준**:
1. [command] 제출부터 승인 또는 반려 결과 확인까지 실제 흐름 smoke가 종료코드 0으로 끝난다.

**GitHub Epic Issue:** 미등록 (사유: eval fixture)

### Story 1 — 요청 제출부터 승인 결과 확인

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 구성원,
**I want** 비용 요청을 제출하고 승인 또는 반려 결과를 확인하길,
**So that** 지급 가능 여부와 다음 행동을 알 수 있다.

**Acceptance criteria:**
- AC-001 [command]: Given 유효한 비용 요청, When 요청을 제출하고 등록된 승인 담당자가 처리하면, Then 구성원 화면에 승인 또는 반려 상태와 처리자가 표시된다.
- AC-002 [command]: Given 제출된 증빙, When 제출일로부터 30일이 지나면, Then 증빙이 삭제되고 상세 화면에 삭제 상태가 표시된다.
