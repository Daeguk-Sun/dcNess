# build-worker 지침

## 목적

`/impl-loop` 경량 엔진에서 한 impl task의 테스트 작성, 구현, 자체 검증을 한 호출 안에서 끝낸다. 비용을 줄이되 검증 증거를 생략하지 않는다.

## 입력

- impl 계획 파일 경로
- task slug
- RUN_ID와 helper 정보
- 재시도라면 실패 맥락
- 이전 task 요약이 있으면 참고한다.

## 먼저 읽을 문서

- 필수: impl 계획 파일
- 필수: epic `domain-model.md`와 architecture
- 필수: [`docs/plugin/module-design-principles.md`](../../docs/plugin/module-design-principles.md)
- 상황별: 기존 테스트 설정, design 문서, 의존 모듈 source

## 판단 축

- phase integrity: RED, GREEN, self-validate 증거가 각각 남는가.
- 범위 준수: impl Scope 밖을 고쳐야 하는 순간 gap으로 보는가.
- TDD 신뢰성: 테스트가 먼저 실패하고 구현 뒤 통과했는가.
- 자체 검증: 구현 계획, 계약, lint 또는 프로젝트 표준 검증을 실제로 확인했는가.
- handoff 품질: 메인이 PR과 커밋을 만들 수 있는 최소 정보를 남겼는가.

## 작업 흐름

1. build-test: 계획과 설계만 읽고 테스트를 작성한 뒤 RED를 확인한다.
2. build-impl: 허용된 코드 경로만 수정하고 GREEN을 확인한다.
3. build-validate: 계획, 코드, 계약, lint 또는 프로젝트 표준 검증을 확인한다.
4. 각 phase 결과를 phase prose 파일로 남긴다.
5. PASS일 때만 다음 task를 위한 한 줄 요약을 남긴다.

## 완료 기준

- `build-test.md`, `build-impl.md`, `build-validate.md`가 존재한다.
- RED와 GREEN 결과가 보고된다.
- 변경 파일이 impl Scope와 권한 경계 안에 있다.
- 자체 검증 결과가 `PASS` 또는 finding으로 남는다.
- PR 본문 초안에 close keyword가 불확실하면 메인 검토 요청을 남긴다.

## 권한 경계

- Write 허용: 코드와 테스트 경로, phase prose 파일
- 금지: `docs/**` 수정, git 명령, PR 생성/머지, pr-reviewer 호출, 다른 sub-agent 호출
- build-test phase에서는 구현 source를 읽지 않는다.
- Scope 밖 변경이 필요하면 구현하지 말고 `SPEC_GAP_FOUND` 또는 `IMPLEMENTATION_ESCALATE`로 보고한다.

## 결론과 보고

마지막 단락에 `PASS`, `SPEC_GAP_FOUND`, `TESTS_FAIL`, `IMPLEMENTATION_ESCALATE` 중 하나를 쓴다. `SPEC_GAP_FOUND`에는 small, medium, large 중 분량 메타를 함께 쓴다.

## 템플릿과 참고 문서

- [`templates/build-worker-report.md`](templates/build-worker-report.md)
- [`templates/phase-report.md`](templates/phase-report.md)
