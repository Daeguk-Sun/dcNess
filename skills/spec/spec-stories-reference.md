# Spec Stories Reference

`/spec` 이 최종 PRD 기준으로 epic 단위 `stories.md` 를 만들 때 쓰는 참고 자료다. 실행 순서는 [`SKILL.md`](SKILL.md), 분기는 [`spec-routing.md`](spec-routing.md) 가 진본이다.

## stories.md 산출물

PRD 작성과 필요한 tech-review preflight 완료 후 메인이 epic 단위 `docs/epics/epic-NN-<slug>/stories.md` 를 작성한다. 1개 `stories.md` 는 1개 epic 영역이다. `epic-NN` 번호는 프로젝트 전역에서 증가하고, milestone 은 경로가 아니라 frontmatter `milestone: vNN` 로 기록한다.

각 Story 본문은 `As a / I want / So that` + Story AC 목록으로 쓴다. Story AC 는 제품 언어의 검증 약속이며 `Given <상황>, When <행동>, Then <검증 가능한 결과>`로 닫는다.

- 대상 화면 / 동작 명세 = root `docs/architecture.md`, epic 단위 `architecture.md`, impl 파일 책임
- 수용 기준 Story 단위 = stories.md 의 Story AC
- 수용 기준 task 단위 = Story AC 를 실행 언어로 번역한 impl 파일의 `REQ-NNN` 표
- 수용 기준 epic 단위 = stories.md 의 `## Epic` 섹션 `완료 기준`

## Story AC 작성

- 각 Story AC 에 안정 ID `AC-NNN` 을 붙인다. `001`부터 시작하는 프로젝트 전역 순번이며 Story 이동·분할·재정렬 뒤에도 한번 부여하면 불변이다.
- 같은 `AC-NNN` 을 다른 Story 에 재사용하지 않는다. 삭제된 AC 번호도 다른 약속에 재할당하지 않는다.
- `잘 동작한다`, `구현이 완료된다` 같은 일반론 대신 조건과 관찰 결과가 binary 로 갈리는 Given/When/Then 문장을 쓴다.
- agent 가 스스로 검증할 수 있는 항목만 Story AC 로 둔다. 명령 종료코드로 판정 가능하면 `[command]`, 파일·화면·로그·문서를 읽어 판정 가능하면 `[agent-read]` 로 표시한다.
- 사람이 직접 판단해야 하는 항목은 AC 체크박스에 넣지 않고 별도 `**사람 확인 안내:**` 목록으로 분리한다. 이 목록은 agent 가 대신 체크하지 않는다.
- 경로, 파일 포맷, 공개 인터페이스 형태처럼 제품 Story AC 로 환원되지 않는 기술 계약은 억지 AC 로 만들지 않는다. 설계 단계의 소수 `기술 REQ` 로 분리한다.

Story AC 가 검증 체인의 origin 이다. module-architect 는 제품 REQ 마다 `(from AC-NNN)` 출처를 적고, architecture-validator 는 Story AC 전항목이 하나 이상의 REQ 로 커버되는지와 무출처 REQ 가 없는지 대조한다.

Epic 완료 기준도 같은 검증 주체 분류를 사용한다. `scripts/create_epic_story_issues.sh` 는 `[command]`/`[agent-read]` Epic 완료 기준과 Story AC 를 GitHub issue body 에서만 미체크 checklist 로 materialize 한다. stories.md 의 안정 ID·목록 형태는 바꾸지 않으며, 검증 주체가 없으면 입력 오류로 중단한다.

## Story 크기 가이드

module-architect 의 `/design` epic-batch 호출은 전체 Story 를 한 컨텍스트에서 읽고, 각 Story 를 구현 가능한 impl 파일 묶음으로 산출한다.

- Story 1개당 예상 task 는 5개 이하 권장
- 큰 Story 는 결제 / 환불 / 정산처럼 분할 권고
- cross-cutting Story 는 Story 본문 끝에 `**영향 모듈**: <목록>` 표시

## Story 분할 기준 — 사용자 검증 가능한 동작 증분

Story 분할의 1차 목표는 기능 영역이나 구현 레이어가 아니라, 각 Story 완료 시 사용자가 실제 제품 경계(UI/API/CLI/worker entrypoint/통합 wiring)에서 직접 확인할 수 있는 동작 증분이다. task 수준 기준([`docs/plugin/agents/_shared/module-design-principles.md`](../../docs/plugin/agents/_shared/module-design-principles.md) 의 Product Behavior Slices — 제품 동작 수직 슬라이스)과 같은 원칙의 Story 수준 적용이다.

- 각 Story 는 "완료되면 사용자가 무엇을 실행하거나 확인할 수 있는가" 에 답해야 한다. 답이 "다른 Story 와 합쳐져야 동작" 이면 부품 Story 다.
- 기능 영역 단위(예: 인테이크 / 렌더 / 업로드 / 오디오) 분할, 레이어 단위(ports / adapter / usecase) 분할은 부품 Story 묶음 신호다 — 동작 증분 단위로 재분할한다.
- 부품 Story 가 불가피하면(공통 인프라 등) Story AC 또는 epic 완료 기준 근처에 어느 후행 Story 에서 그 동작이 확인되는지 명시한다.
- 직접 실행 경계가 없는 라이브러리/SDK 는 공개 API 사용 예제(컴파일·실행 가능한)가 제품 경계다.

## Story 순서 기준 — 얇은 골격 우선

- 첫 Story가 얇은 end-to-end 제품 골격(walking skeleton)을 세운다 — 입력에서 결과까지 한 줄로 통과하는 최소 동선. UI 가 있는 제품이면 최소 UI 동선을 포함한다. 첫 Story에서 불가능하다면 그 기술적·제품적 사유를 epic `완료 기준` 근처에 명시한다.
- 순서 축에서 골격의 닫힘은 모든 PRD 기능의 완성이 아니라 최소 동선이 최종 사용자 가치 경계를 실제 통과한 시점이다. PRD 기능 일부가 후속 Story에 남아 있어도 첫 Story의 최소 동선이 최종 사용자 가치 경계를 통과하면 순서 결함이 아니다. 후속 기능의 누락·AC coverage는 순서 축과 별개의 gap으로 평가한다.
- 이후 Story 는 골격 위에 확인 가능한 증분을 쌓는다 — 어느 Story 에서 멈춰도 그때까지의 동작을 사용자가 직접 돌려볼 수 있게 한다.
- 의존 순서만으로 정렬해 사용자 확인 가능한 동작이 마지막 Story 까지 밀리는 순서(부품을 다 만든 뒤에야 처음 동작)는 그대로 두지 않는다 — 순서를 바꾸거나 Story 를 병합하고, 불가피하면 그 사유를 epic `완료 기준` 근처에 남긴다.
- PRD 목표·유저 시나리오와 Story AC 에서 핵심 제품 약속을 먼저 식별하고, 그 약속의 첫 end-to-end 동작 검증이 어느 Story 에서 닫히는지 확인한다. 첫 Story가 최종 사용자 가치 경계까지 닫히지 않으면, 명세에 더 이른 골격이 불가능한 사유가 있는지 확인한다. 사유 없이 뒤 Story에서 처음 닫히면 그 뒤 Story가 마지막 Story가 아니어도 순서 결함이다.
- 각 Story 에 독립적인 하위 동작 증분이 있거나 완전한 흐름의 기능을 기술적 의존 순서대로 구현한다는 사실은 순서 결함을 해소하지 않는다. 명세에 적히지 않은 기술적 의존 순서를 검수자가 불가능 사유로 만들어내지 않는다.
- 핵심 제품 약속은 최종 산출·전달 경계까지 포함한다. Story AC 에 export, upload, publish, download, delivery 같은 최종 사용자 가치 경계가 있으면 중간 렌더·미리보기만으로 닫힌 것으로 보지 않고, 그 경계가 처음 검증되는 Story 를 기준으로 순서를 판단한다.

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
1. [command] <실행 명령과 종료코드로 검증 가능한 조건 1>
2. [agent-read] <산출물·화면·로그·문서를 읽어 검증 가능한 조건 2>
3. ...

**GitHub Epic Issue:** (이슈 등록 후 `[#NNN]`, 보류 시 `미등록 (사유: …)`)

---

### Story 1 — <story 한 줄 요약>

**GitHub Issue:** (이슈 등록 후 `[#NNN]`, 보류 시 `미등록 (사유: …)`)

**As a** <user>,
**I want** <action>,
**So that** <benefit>.

**Acceptance criteria:**
- AC-001 [command]: Given <상황>, When <행동>, Then <검증 가능한 결과>
- AC-002 [agent-read]: Given <상황>, When <관찰>, Then <검증 가능한 결과>

**사람 확인 안내:**
- <사람 판단이 꼭 필요한 경우에만 쓴다. 없으면 섹션 생략>

---

### Story 2 — ...
```

## 유효성

모든 stories.md는 `As a / I want / So that`와 typed Story AC를 함께 가져야 한다. Story AC가 없으면 `scripts/report_ac_coverage.mjs`가 실패하며 design 전에 문서를 현행 양식으로 갱신한다.
