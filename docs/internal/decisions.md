# 설계 결정 기록

> dcNess self 전용 문서다. plug-in 배포물이 아니다.
> 코드와 규칙만 읽어서는 알 수 없는 "왜 이렇게 정했는가"를 한 곳에 모은 색인이다.
> 각 결정의 상세 내용은 근거 칸의 문서와 이슈가 진본이다. 이 문서는 그 내용을 복제하지 않는다.

## 쓰는 방법

- 기존 규칙을 바꾸거나 없애려고 할 때 먼저 이 문서에서 그 규칙의 이유를 확인한다.
- 새 결정을 내리면 표에 한 줄을 추가한다. 결정, 이유, 근거 세 칸을 모두 채운다.
- 이유를 확인하지 못한 결정은 이유 칸에 "기록 없음"이라고 적는다. 이유를 추측해서 적지 않는다.
- 결정을 뒤집으면 줄을 지우지 않는다. [뒤집은 결정](#뒤집은-결정) 절로 옮기고 뒤집은 근거를 적는다.
- 측정 신호에서 나온 개선 후보의 채택·보류·거부 기록은 이 문서가 아니라
  [`loop-decisions.jsonl`](loop-decisions.jsonl)에 있다. 그 절차는
  [`self-improvement-loop.md`](self-improvement-loop.md)를 따른다.

## 하네스 설계

| 결정 | 이유 | 근거 |
|---|---|---|
| 하네스가 강제하는 것은 작업 순서와 접근 영역 두 가지뿐이다. 출력 형식과 handoff 형식은 agent 가 정한다. | 하네스의 일은 모델의 사고를 대신하는 것이 아니다. 모델이 놓치기 쉬운 되돌릴 수 없는 경계만 붙잡는다. | [`CLAUDE.md`](../../CLAUDE.md)의 "dcness 강제 원칙" 절, [#591](https://github.com/Daeguk-Sun/dcNess/issues/591) |
| hook 자체의 오류나 판정 불가는 작업을 막지 않고 통과시킨다. 통과시킨 사실은 기록으로 남긴다. | hook 의 버그가 사용자의 전체 작업을 과하게 막지 않게 한다. | [`docs/plugin/hooks.md`](../plugin/hooks.md)의 "Layer 1" 절 |
| 형식 위반이나 비용 증가 같은 문제는 차단하지 않고 경고한다. 경고를 차단으로 자동 승격하지 않는다. | 차단은 중대한 위반에만 쓴다. | [`CLAUDE.md`](../../CLAUDE.md)의 "안티패턴" 목록 |
| 모든 agent 에 적용되는 읽기 금지는 두지 않는다. 인프라 경로는 쓰기만 막는다. 읽기를 막는 규칙은 agent 별 목록 하나다. | 읽기는 상태를 바꾸지 않으므로 되돌릴 수 없는 변경을 막지 않는다. 금지 때문에 검증 agent 가 `.claude/` 아래의 실제 증거 대신 간접 증거로 판정했다. | [#1300](https://github.com/Daeguk-Sun/dcNess/issues/1300), [`docs/plugin/hooks.md`](../plugin/hooks.md)의 "file-guard.sh" 절 |
| 중간 단계가 통과한 뒤 메인이 멈춰도 종료 훅은 계속 진행을 요구하지 않는다. 실행은 닫지 않고 열어 둔다. 종료 훅이 막는 것은 마감 검증 순서 위반뿐이다. | 다음 단계가 사용자 확인인 흐름에서 이 요구는 항상 틀렸고 2회 뒤 스스로 풀려 강제력도 없었다. 실행을 바로 닫으면 사용자 답 뒤의 다음 단계 시작이 실패한다. | [#1301](https://github.com/Daeguk-Sun/dcNess/issues/1301), [`docs/plugin/hooks.md`](../plugin/hooks.md)의 "stop-end-run.sh" 절 |
| 새 skill·command·agent·gate 를 추가하려면 기존 수단으로 부족한 이유를 먼저 설명한다. | 사용자에게 보이는 진입점을 작게 유지한다. | [`CLAUDE.md`](../../CLAUDE.md)의 "안티패턴" 5번, [`docs/plugin/positioning.md`](../plugin/positioning.md) |
| 사용자의 승인 한 단어는 그때 묻던 선택만 확정한다. agent 가 설명문에 사실처럼 적은 제품 동작은 사용자 확정으로 세지 않는다. 사용자의 이해를 확인하는 수단은 agent 가 고르고 형식을 강제하지 않는다. | 핵심 동작 정의가 질문 밖에 있으면 사용자가 설계가 끝난 뒤에야 문제를 발견하고 하위 문서 전체를 다시 쓴다. 사용자에게 효과가 있는 것은 형식이 아니라 상황 단위로 풀어 쓴 설명이다. | [`docs/plugin/decision-completeness.md`](../plugin/decision-completeness.md)의 "agent 전제와 사용자 확정" 절, [#1294](https://github.com/Daeguk-Sun/dcNess/issues/1294) |

## 저장소 운영

| 결정 | 이유 | 근거 |
|---|---|---|
| dcNess 저장소는 자기 자신에 `/init-dcness`를 실행하지 않는다. plug-in 규격은 이 저장소에 적용되지 않는다. | plug-in 규격은 외부 활성 프로젝트를 위한 것이다. | [`CLAUDE.md`의 해당 절](../../CLAUDE.md#dcness-자체는-init-dcness-미적용-자기-규격-미얽매임) |
| 기능을 추가하면 그 기능이 사용자 환경에 도달하는 경로를 PR 본문에 적는다. | 이 저장소에만 추가한 기능이 설치한 외부 프로젝트에서 작동하지 않은 사례가 있었다. | [`CLAUDE.md`의 해당 절](../../CLAUDE.md#추가한-기능은-반드시-배포-경로에도-포함) |
| 외부에 배포되는 파일에는 내부 추적 ID 를 본문으로 넣지 않는다. | 외부 사용자에게 내부 추적 표현은 잡음이다. | [`CLAUDE.md`](../../CLAUDE.md)의 "내부 ID 를 외부 배포물에 포함하지 마라" 절 |
| PR 은 squash 하지 않고 일반 merge 로 합친다. | 커밋별 히스토리를 보존한다. | [`CLAUDE.md`](../../CLAUDE.md)의 "커밋 / PR 절차" 절 |
| merge 한 뒤에도 브랜치를 삭제하지 않는다. | 기록 없음 | [`CLAUDE.md`](../../CLAUDE.md)의 "커밋 / PR 절차" 절 |
| 문서의 절을 위치 번호로 가리키지 않는다. 제목 기반 링크로 가리킨다. | 절이 추가되면 번호가 밀려서 참조가 다른 절을 가리킨다. 링크 검사는 번호 참조를 검증하지 못한다. | [`doc-conventions.md`](doc-conventions.md) |

## 릴리즈와 배포

| 결정 | 이유 | 근거 |
|---|---|---|
| 릴리즈는 새 `vMAJOR.MINOR.PATCH` tag 에서만 실행한다. 이미 배포한 version 의 tag 를 옮기거나 다시 쓰지 않는다. | 같은 version 의 배포물이 항상 같은 내용이어야 한다. | [`plugin-release.md`](plugin-release.md), [#1158](https://github.com/Daeguk-Sun/dcNess/issues/1158) |
| `/init-dcness`는 프로젝트에 이미 있는 seed 파일을 덮어쓰지 않는다. | 기록 없음 | [`docs/plugin/init-dcness.md`](../plugin/init-dcness.md)의 배포 표("부재 시만 생성") |

## 검증

| 결정 | 이유 | 근거 |
|---|---|---|
| 행동 eval 의 실패를 뒤이은 재실행 통과로 닫지 않는다. 최초 실패까지 합친 전체 정답률을 보고한다. | 재실행은 불안정 여부를 판별하는 수단이다. 통과한 표본을 고르는 수단이 아니다. | [`evals/README.md`](../../evals/README.md)의 "실패·재실행 처리 규범" 절, [#1125](https://github.com/Daeguk-Sun/dcNess/issues/1125) |
| CI 에서 간헐적으로 실패하는 테스트를 자동 재실행이나 실패 무시로 덮지 않는다. 원인을 판정하고 고친다. | 재실행으로 통과시키면 원인이 가려진다. | [#1265](https://github.com/Daeguk-Sun/dcNess/issues/1265), [PR #1287](https://github.com/Daeguk-Sun/dcNess/pull/1287) |
| 전역 architecture map 은 필요할 때 만드는 리포트다. 저장소에 넣어 두고 drift 를 검사하는 대상이 아니다. | 기록 없음 | [`CLAUDE.md`](../../CLAUDE.md)의 "게이트 요약" 절 doc-sync 항목 |

## 뒤집은 결정

아직 없다.

## 과거 기록

- dcNess 로 옮겨 올 때의 모듈 단위 결정은 [`docs/archive/migration-decisions.md`](../archive/migration-decisions.md)에 있다.
- 릴리즈별 변경 요약은 [`release-notes.md`](release-notes.md)에 있다.
