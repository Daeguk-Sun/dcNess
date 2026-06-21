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
