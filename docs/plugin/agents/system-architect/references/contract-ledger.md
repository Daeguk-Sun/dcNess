# Legacy Contract Ledger 참고

Contract Ledger는 과거 `/design` 이 cross-task public contract 전문을 모으던 구양식 산출물이다. 신규 `/design` 산출물은 Ledger row key 를 만들지 않는다. 계약 의미는 epic `architecture.md` 의 `## 모듈 목록` 책임/공개 인터페이스/검증 경로 한 줄과 `docs/decisions/NNNN-slug.md` 에 둔다.

## 구양식 읽기 기준

| 열 | 의미 |
|---|---|
| contract | 과거 stable row key |
| owner | 계약의 진본을 소유하는 모듈 또는 use case |
| producer | 값을 만들거나 상태를 바꾸는 쪽 |
| consumer | 계약을 읽거나 호출하는 쪽 |
| invariant | 반드시 지켜야 하는 조건 |
| ordering | 호출 순서, 생성 순서, 한 번만 계산 같은 시간 조건 |
| error mode | 실패를 표현하는 방식 |
| config | 환경값, feature flag, 외부 설정 |
| forbidden alternative | drift를 만들 수 있어 금지하는 대안 |
| refs | decision, architecture, 추후 impl 문서 같은 근거 |

## 신규 작성 기준

- caller가 올바르게 쓰기 위해 알아야 하는 의미를 module responsibility 와 decision 문서로 옮긴다.
- private helper 이름이나 내부 loop 흐름은 쓰지 않는다.
- impl 문서, validator finding, prompt 에 invariant/ordering/error mode/config/forbidden alternative 사본을 만들지 않는다. 필요한 곳은 module id 와 decision id/link 를 가리킨다.
- task 내부 한정 private interface 는 사본 문제가 없으므로 impl 문서의 `## 인터페이스` 에 남길 수 있다.
- architecture-validator는 구양식 Ledger/References 의 존재만으로 FAIL 하지 않는다. 이번 변경이 실제 계약 의미를 수정할 때 stale 사본이 되는지만 Should finding 으로 보고한다.
