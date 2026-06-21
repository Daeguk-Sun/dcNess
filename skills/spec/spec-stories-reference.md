# Spec Stories Reference

`/spec` 이 최종 PRD 기준으로 epic 단위 `stories.md` 를 만들 때 쓰는 참고 자료다. 실행 순서는 [`SKILL.md`](SKILL.md), 분기는 [`spec-routing.md`](spec-routing.md) 가 진본이다.

## stories.md 산출물

PRD 작성과 필요한 tech-review preflight 완료 후 메인이 epic 단위 `docs/epics/epic-NN-<slug>/stories.md` 를 작성한다. 1개 `stories.md` 는 1개 epic 영역이다. `epic-NN` 번호는 프로젝트 전역에서 증가하고, milestone 은 경로가 아니라 frontmatter `milestone: vNN` 로 기록한다.

새 작성 시 본문은 `As a / I want / So that` + `**완료 시 확인 가능한 동작**:` 한 줄만 쓴다. `대상 화면·컴포넌트` / `동작 명세` / `수용 기준 (Story 단위)` 섹션은 쓰지 않는다.

- 대상 화면 / 동작 명세 = root `docs/architecture.md`, epic 단위 `architecture.md`, impl 파일 책임
- 수용 기준 task 단위 = impl 파일의 `REQ-NNN` 표
- 수용 기준 epic 단위 = stories.md 의 `## Epic` 섹션 `완료 기준`

## Story 크기 가이드

module-architect 한 호출은 한 Story 단위이고, 보통 N개 impl 파일을 산출한다.

- Story 1개당 예상 task 는 5개 이하 권장
- 큰 Story 는 결제 / 환불 / 정산처럼 분할 권고
- cross-cutting Story 는 Story 본문 끝에 `**영향 모듈**: <목록>` 표시

## Story 분할 기준 — 사용자 검증 가능한 동작 증분

Story 분할의 1차 목표는 기능 영역이나 구현 레이어가 아니라, 각 Story 완료 시 사용자가 실제 제품 경계(UI/API/CLI/worker entrypoint/통합 wiring)에서 직접 확인할 수 있는 동작 증분이다. task 수준 기준([`agents/_shared/module-design-principles.md`](../../agents/_shared/module-design-principles.md) 의 Product Behavior Slices — 제품 동작 수직 슬라이스)과 같은 원칙의 Story 수준 적용이다.

- 각 Story 는 "완료되면 사용자가 무엇을 실행하거나 확인할 수 있는가" 에 답해야 한다. 답이 "다른 Story 와 합쳐져야 동작" 이면 부품 Story 다.
- 기능 영역 단위(예: 인테이크 / 렌더 / 업로드 / 오디오) 분할, 레이어 단위(ports / adapter / usecase) 분할은 부품 Story 묶음 신호다 — 동작 증분 단위로 재분할한다.
- 부품 Story 가 불가피하면(공통 인프라 등) `**완료 시 확인 가능한 동작**:` 줄에 어느 후행 Story 에서 그 동작이 확인되는지 명시한다.
- 직접 실행 경계가 없는 라이브러리/SDK 는 공개 API 사용 예제(컴파일·실행 가능한)가 제품 경계다.

## Story 순서 기준 — 얇은 골격 우선

- 첫 Story(또는 가능한 한 앞 Story)가 얇은 end-to-end 제품 골격(walking skeleton)을 세운다 — 입력에서 결과까지 한 줄로 통과하는 최소 동선. UI 가 있는 제품이면 최소 UI 동선을 포함한다.
- 이후 Story 는 골격 위에 확인 가능한 증분을 쌓는다 — 어느 Story 에서 멈춰도 그때까지의 동작을 사용자가 직접 돌려볼 수 있게 한다.
- 의존 순서만으로 정렬해 사용자 확인 가능한 동작이 마지막 Story 까지 밀리는 순서(부품을 다 만든 뒤에야 처음 동작)는 그대로 두지 않는다 — 순서를 바꾸거나 Story 를 병합하고, 불가피하면 그 사유를 epic `완료 기준` 근처에 남긴다.

## Template

```markdown
---
epic: epic-NN-<slug>
milestone: vNN
---

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

**완료 시 확인 가능한 동작**: <이 Story 머지 후 사용자가 제품 경계에서 직접 실행/확인할 수 있는 것>

---

### Story 2 — ...
```

## 구버전 호환성

기존 외부 활성 프로젝트의 옛 양식 stories.md 는 그대로 허용한다. 새 작성 시만 본 단순화 룰을 적용한다. read 시 parser 는 `As a / I want / So that` 매치만 의무로 본다.

`**완료 시 확인 가능한 동작**:` 줄이 없는 기존 stories.md 도 그대로 허용한다. parser 의무 매치는 여전히 `As a / I want / So that` 만이다.
