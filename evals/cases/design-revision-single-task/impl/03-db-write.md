---
design: optional
story: 3
task_index: 3/3
depends_on: [02-invalid-row-report]
---

# 03-db-write

## 사전 준비

- 읽을 문서: `stories.md` (Story 3), `architecture.md`

## 무엇을 만드나

- `contacts import <file>` 이 검사를 통과한 행을 DB 에 쓰고 `imported: N` 을 출력한다. Story 3 완료 시 DB 에 연락처가 보인다.
- 제품 경계: `contacts import` 명령의 표준 출력, exit code, DB 의 연락처 행.
- 첫 동작 증거 지점: 올바른 파일에 대해 `imported: N` 출력과 DB N 행.

## 왜 만드나

- PRD M3 와 사용자 확정(잘못된 행이 하나라도 있으면 전체 중단). 이 task 는 02 가 만든 `ValidationReport.errors` 가 비어 있을 때만 `write_all(rows)` 을 호출한다.

## Scope

### 수정 허용

- `src/contact_store/`
- `src/import_cli/`
- `tests/contact_store/`
- `tests/import_cli/`

### 수정 금지

- `src/csv_parser/`
- `src/row_validator/`

## 인터페이스

- 계약/결정 링크:
  - module: contact-store, import-cli (`architecture.md` 모듈 목록)
- owner/entrypoint 요약:
  - owner flow/module: import-cli
  - entrypoint role: `validate(rows)` 결과의 `errors` 가 비어 있으면 `write_all(rows)` 호출 → 출력
  - state owner: contact-store (DB 의 연락처 행)
  - validation path: `pytest tests/import_cli -k db_write`

## 수용 기준

| REQ | 내용 | 검증 명령 | 통과 조건 |
|---|---|---|---|
| REQ-001 (from AC-301) | 올바른 CSV 에 대해 `imported: N` 을 출력하고 DB 에 N 행이 생긴다 | `(TEST) pytest tests/import_cli -k db_write_imports_all_rows` | green |
| REQ-002 (from AC-302) | 잘못된 행이 하나라도 있으면 DB 에 아무 행도 생기지 않는다 | `(TEST) pytest tests/import_cli -k db_write_aborts_on_invalid_row` | green |
| REQ-003 (technical: 저장 단위 경계) | `write_all(rows)` 이 한 트랜잭션으로 쓰고 쓴 행 수를 돌려준다 | `(TEST) pytest tests/contact_store -k write_all_single_transaction` | green |

## 주의사항

- 모듈 설계 주의: 트랜잭션 처리는 contact-store 내부에 숨긴다.
