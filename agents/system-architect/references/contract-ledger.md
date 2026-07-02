# Contract Ledger 참고

Contract Ledger는 구현 세부가 아니라 public contract의 의미를 고정하는 원장이다. signature만 적으면 shallow contract다. cross-task 계약 전문은 이 원장에만 두고, impl/compact plan 산출물에는 행 키 포인터만 남긴다.

## 계약에 담을 의미

| 열 | 의미 |
|---|---|
| contract | stable row key. 구현 파일보다 오래 갈 수 있는 짧은 이름이며, 발급 후 재사용·의미 변경 금지 |
| owner | 계약의 진본을 소유하는 모듈 또는 use case |
| producer | 값을 만들거나 상태를 바꾸는 쪽 |
| consumer | 계약을 읽거나 호출하는 쪽 |
| invariant | 반드시 지켜야 하는 조건 |
| ordering | 호출 순서, 생성 순서, 한 번만 계산 같은 시간 조건 |
| error mode | 실패를 표현하는 방식 |
| config | 환경값, feature flag, 외부 설정 |
| forbidden alternative | drift를 만들 수 있어 금지하는 대안 |
| refs | decision, architecture, 추후 impl 문서 같은 근거 |

## 작성 기준

- caller가 올바르게 쓰기 위해 알아야 하는 의미를 적는다.
- private helper 이름이나 내부 loop 흐름은 쓰지 않는다.
- module-architect가 public contract를 바꾸면 원장을 갱신하고 impl/compact plan 에는 갱신한 행 키만 남긴다.
- impl/compact plan, validator finding, prompt 에 invariant/ordering/error mode/config/forbidden alternative 사본을 만들지 않는다. 필요한 곳은 행 키와 원장 경로를 가리킨다.
- task 내부 한정 private interface 는 사본 문제가 없으므로 impl 문서의 `## 인터페이스` 에 남길 수 있다.
- architecture-validator는 이 원장을 기준으로 stale 사본을 찾고, 신규 산출물의 사본은 행 키 참조로 바꾸게 한다.
