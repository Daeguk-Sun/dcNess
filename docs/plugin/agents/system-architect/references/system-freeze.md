# System Checkpoint 참고

system-architect 는 `/design` 기본 상설 stage 가 아니다. 예외는 두 가지다. 첫째, greenfield 첫 설계에서 모듈 topology 가 전혀 없을 때 module-architect 앞에 1회 THIN_BOOTSTRAP 으로 큰 모듈 경계만 얇게 나눈다. 둘째, 기존 모듈 경계, 도메인 불변조건, 저장 정책, public API boundary, 전역 decision 처럼 system-level 결정을 바꾸는 신호가 있을 때만 opt-in CHECKPOINT 로 호출한다.

THIN_BOOTSTRAP 은 system 재진입이 아니다. bootstrap 뒤에 별도 architecture-validator 를 끼우지 않고 module-architect(epic-batch)로 바로 간다.

## system 재진입 사유

`SYSTEM_BOUNDARY`에 해당할 때만 system-architect 재진입을 기본값으로 둔다.

- 도메인 invariant가 바뀜
- use case ownership이 바뀜
- port consumer가 바뀜
- 저장 정책이 바뀜
- `docs/decisions/` 수준의 전역 결정이 틀림
- 기존 모듈 경계 또는 public API boundary 가 바뀜

## system 재진입이 아닌 것

다음은 module-architect 보강 또는 validator Should finding 으로 처리한다.

- ux-flow 또는 stories prose 가 module responsibility / decision 과 표현만 다름
- impl task 의 Agent Workability, scope, acceptance criteria 보강
- 전역 architecture 요약 리포트가 생성되지 않음

## checkpoint 이후 허용되는 append

새 epic 을 설계할 때 다음은 system 재설계가 아니라 module-architect epic-batch 에서 처리 가능한 append 다.

- epic `architecture.md` 모듈 목록에 새 owner module 행 추가
- 새 `docs/decisions/NNNN-slug.md` 링크 추가
- affected module docs 에 validation path delta 추가
- impl task 의 module/decision 참조 보강

기존 accepted decision 자체를 바꾸거나 전역 invariant 를 바꾸면 append 가 아니라 `SYSTEM_BOUNDARY` 로 본다.
