# epic-02 architecture (최소형)

## 모듈 목록

| module | 책임 | 공개 인터페이스 |
|---|---|---|
| csv-parser | CSV 파일을 행 목록으로 읽는다 | `parse(path) -> Rows` |
| row-validator | 행 목록을 검사해 잘못된 행의 번호와 이유를 모은다 | `validate(rows) -> ValidationReport` (`ValidationReport.errors: list[RowError]`, `RowError(row_number, reason)`) |
| contact-store | 연락처를 DB 에 한 트랜잭션으로 쓴다 | `write_all(rows) -> int` |
| import-cli | `contacts import` 명령. 인자를 읽고 위 모듈을 순서대로 호출해 결과를 출력한다 | `contacts import <file> [--dry-run]` |

의존 차단: 모듈별 public 패키지만 노출한다. DI 는 생성자 주입이다.

## 의존 그래프

import-cli → csv-parser, row-validator, contact-store. 세 모듈은 서로 의존하지 않는다.

## Story -> 모듈 매핑

- Story 1: csv-parser + import-cli — 첫 제품 경계 동작: `--dry-run` 이 행 수를 출력한다.
- Story 2: row-validator + import-cli — 잘못된 행의 번호와 이유를 출력하고 exit 1.
- Story 3: contact-store + import-cli — 검사를 통과한 행을 DB 에 쓴다.

구현 순서는 Story 1 → 2 → 3 이다. 매 Story 가 명령줄에서 확인 가능한 동작을 낸다.

## Domain Model

- 생략 판단: 엔티티 1개(연락처 행), 규칙은 PRD 의 사용자 확정 2건으로 충분하다. 낮은 도메인 복잡도로 domain-model.md 를 생략한다.
