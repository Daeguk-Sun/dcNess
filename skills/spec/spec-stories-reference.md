# Spec Stories Reference

`/spec` 이 최종 PRD 기준으로 epic 단위 `stories.md` 를 만들 때 쓰는 참고 자료다. 실행 순서는 [`SKILL.md`](SKILL.md), 분기는 [`spec-routing.md`](spec-routing.md) 가 진본이다.

## stories.md 산출물

PRD 작성과 필요한 tech-review preflight 완료 후 메인이 epic 단위 `docs/milestones/vNN/epics/epic-NN-<slug>/stories.md` 를 작성한다. 1개 `stories.md` 는 1개 epic 영역이다.

새 작성 시 본문은 `As a / I want / So that` 만 쓴다. `대상 화면·컴포넌트` / `동작 명세` / `수용 기준 (Story 단위)` 섹션은 쓰지 않는다.

- 대상 화면 / 동작 명세 = root `docs/architecture.md`, epic 단위 `architecture.md`, impl 파일 책임
- 수용 기준 task 단위 = impl 파일의 `REQ-NNN` 표
- 수용 기준 epic 단위 = stories.md 의 `## Epic` 섹션 `완료 기준`

## Story 크기 가이드

module-architect 한 호출은 한 Story 단위이고, 보통 N개 impl 파일을 산출한다.

- Story 1개당 예상 task 는 5개 이하 권장
- 큰 Story 는 결제 / 환불 / 정산처럼 분할 권고
- cross-cutting Story 는 Story 본문 끝에 `**영향 모듈**: <목록>` 표시

## Template

```markdown
# Story Backlog

## Epic — <epic 한 줄 요약>

**목표**: <epic 의 비즈니스 목적 한 단락>
**선행 조건**: <있으면>
**완료 기준** (epic 단위 수용 기준):
1. <검증 가능한 조건 1>
2. <검증 가능한 조건 2>
3. ...

**GitHub Epic Issue:** (이슈 등록 후 `[#NNN]`, 보류 시 `미등록 (사유: …)`)

---

### Story 1 — <story 한 줄 요약>

**GitHub Issue:** (이슈 등록 후 `[#NNN]`, 보류 시 `미등록 (사유: …)`)

**As a** <user>,
**I want** <action>,
**So that** <benefit>.

---

### Story 2 — ...
```

## 구버전 호환성

기존 외부 활성 프로젝트의 옛 양식 stories.md 는 그대로 허용한다. 새 작성 시만 본 단순화 룰을 적용한다. read 시 parser 는 `As a / I want / So that` 매치만 의무로 본다.
