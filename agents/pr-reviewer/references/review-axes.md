# pr-reviewer review axes

이 문서는 리뷰 힌트다. 고정 검토표가 아니며, 변경 맥락에 맞게 축을 선택한다.

## 유지보수성

- 같은 개념이 여러 이름으로 표현되는가
- 함수가 하나의 책임으로 읽히는가
- 분기와 조기 반환이 이해 가능한가

## 단순성

- 요구에 없는 추상화가 생겼는가
- 설정, flag, layer가 실제 변경 이유 없이 추가됐는가

## 중복

- 같은 의도가 여러 곳에 반복되는가
- 테스트나 fixture의 반복이 의미 있는지 단순 복사인지 구분되는가

## 운영 위험

- debug log, 임시 mock, 하드코딩 환경값이 남았는가
- 실패 상태가 사용자나 운영자에게 관찰 가능한가

## 명백한 보안 위험

- 사용자 입력이 query, command, HTML, URL에 검증 없이 들어가는가
- secret, token, 개인정보가 저장소나 log에 노출되는가
- postMessage, CORS, deeplink 같은 trust boundary가 열려 있는가

## 흐름 누적

- 이번 diff가 이미 여러 제품 흐름을 떠안은 파일에 또 다른 흐름을 append하는가
- 새 능력이 별도 모듈이 아니라 기존 대형 파일에 흡수되는가
- 기준은 [`module-design-principles.md` 단일 파일 다중 흐름 누적](../../_shared/module-design-principles.md#단일-파일-다중-흐름-누적) 절이다. footprint 밖 기존 누적은 MUST FIX가 아니라 후속 권고로 둔다

## Agent Operability

- 이번 diff가 다음 agent 의 edit target 을 안정적으로 찾기 어렵게 만드는가
- entrypoint 에 render/helper/session state key 를 append 해 state owner 를 흐리게 만드는가
- owner module 없이 새 mode/screen/panel/flow 를 기존 entrypoint 에 흡수하는가
- validation path 가 owner flow/module 근처에 남지 않고 수동 탐색에 의존하는가
- 수정 허용 범위가 overly broad entrypoint touch 로 열려 있어 무관한 흐름까지 편집하게 만드는가
- entrypoint 파일 자체는 owner module 로 인정하지 않는다. 함수명 prefix 또는 같은 파일 위치는 searchability 보조 신호일 뿐 owner 분리 증거가 아니다
- manual-only validation 은 owner 근처 validation path 가 아니다
- 기준은 [`module-design-principles.md` Agent Operability](../../_shared/module-design-principles.md#agent-operability) 절이다. 파일 크기나 UI 변경 자체가 아니라 edit target, state owner, validation path 악화를 본다
- severity: owner module 없이 새 flow 를 entrypoint 에 append 하면서 render/helper/session/global state 를 흡수하고 owner 근처 validation path 를 남기지 않는 조합은 NICE TO HAVE 가 아니라 MUST FIX 로 승격한다. owner module + dispatch-only entrypoint + owner 근처 validation path 구조나 파일 크기·footprint 밖 기존 누적은 승격 대상이 아니다
