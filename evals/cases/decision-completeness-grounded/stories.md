---
epic: epic-01-request-approval
milestone: v01
---

# Story Backlog

## Epic — 비용 요청 승인

**목표**: 구성원이 요청을 제출하고 지정된 승인 주체의 결과를 확인한다.
**완료 기준**:
1. [command] 제출부터 승인 또는 반려 결과 확인까지 실제 흐름 smoke가 종료코드 0으로 끝난다.

**GitHub Epic Issue:** 미등록 (사유: eval fixture)

### Story 1 — 요청 제출부터 승인 결과 확인

**GitHub Issue:** 미등록 (사유: eval fixture)

**As a** 구성원,
**I want** 비용 요청을 제출하고 승인 또는 반려 결과를 확인하길,
**So that** 지급 가능 여부와 다음 행동을 알 수 있다.

**Acceptance criteria:**
- AC-001 [command]: Given 조직 소유자가 지정한 승인 담당자 또는 사전 지정 대리자와 유효한 비용 요청, When 요청을 제출하고 담당자가 처리하면, Then 구성원 화면에 승인 또는 반려 상태와 처리자가 표시된다.
- AC-002 [agent-read]: Given 반려된 요청, When 상세를 확인하면, Then 반려 이유와 재제출 가능 여부가 표시된다.
- AC-003 [command]: Given 이미 처리된 같은 요청의 재시도, When 처리 명령을 다시 실행하면, Then 기존 결과를 반환하고 지급 대기는 하나만 존재한다.
- AC-004 [command]: Given 처리 완료 후 5년이 지난 요청과 증빙, When 보존 정리를 실행하면, Then 둘이 삭제되고 감사 기록에 삭제 시각이 남는다.
