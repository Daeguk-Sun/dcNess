# code-validator finding 예시

이 문서는 예시다. 실제 판단은 `code-validator-agent.md`의 판단 축을 따른다.

## 스펙 충실도

- 계획한 함수 signature와 구현 signature가 다름
- 계획한 파일이 생성되지 않음
- error mode가 throw에서 silent return으로 바뀜

## 범위 통제

- impl Scope 밖 파일이 수정됨
- bugfix가 unrelated refactor를 포함함

## 의존 계약

- wrapper를 거치기로 했는데 외부 SDK를 직접 import함
- architecture에 없는 모듈 내부 파일을 import함
- DB schema 변경이 migration 없이 코드에만 반영됨

## 구현 위험

- cleanup 없는 interval 또는 event listener
- 새 `as any`나 type ignore
- async 완료 후 unmounted state update
- 민감 값 log
