---
design: optional
story: 2
task_index: 2/3
depends_on: [01-dry-run-row-count]
---

# 02-invalid-row-report

## 사전 준비

- 읽을 문서: `stories.md` (Story 2), `architecture.md`

## 무엇을 만드나

- `contacts import <file>` 이 잘못된 행의 번호와 이유를 출력하고 exit 1 로 끝난다. Story 2 완료 시 명령줄에서 잘못된 행이 보인다.
- 제품 경계: `contacts import` 명령의 표준 출력과 exit code.
- 첫 동작 증거 지점: 이메일이 빈 행에 대해 `row <n>: email is empty` 출력.

## 왜 만드나

- PRD M2 와 사용자 확정 2건(전체 중단, 이메일 규칙). 검사 모듈과 명령 출력 연결을 한 task 로 묶는다.

## Scope

### 수정 허용

- `src/row_validator/`
- `src/import_cli/`
- `tests/row_validator/`
- `tests/import_cli/`
- `tests/fixtures/invalid_rows/`

### 수정 금지

- `src/csv_parser/`
- `src/contact_store/`

## 인터페이스

- 계약/결정 링크:
  - module: row-validator, import-cli (`architecture.md` 모듈 목록)
- owner/entrypoint 요약:
  - owner flow/module: import-cli
  - entrypoint role: `parse(path)` 뒤 `validate(rows)` 호출 → `ValidationReport.errors` 를 행 번호 순으로 출력
  - state owner: 없음(상태를 보관하지 않는다)
  - validation path: `pytest tests/import_cli -k invalid_row`

## 수용 기준

| REQ | 내용 | 검증 명령 | 통과 조건 |
|---|---|---|---|
| REQ-001 (from AC-201) | 이메일이 빈 행에 대해 `row <n>: email is empty` 를 출력하고 exit 1 | `(TEST) pytest tests/import_cli -k invalid_row_empty_email` | green |
| REQ-002 (from AC-202) | 이메일에 `@` 가 없는 행에 대해 `row <n>: email is malformed` 를 출력하고 exit 1 | `(TEST) pytest tests/import_cli -k invalid_row_malformed_email` | green |
| REQ-003 (technical: 검사 단위 경계) | `validate(rows)` 가 `tests/fixtures/invalid_rows/` 의 CSV 파일별로 정해진 `RowError` 목록을 돌려준다 | `(TEST) pytest tests/row_validator -k fixture_cases` | green |

## 주의사항

- 모듈 설계 주의: 이메일 규칙 판정은 row-validator 내부에 숨긴다. 공개 인터페이스는 `validate(rows) -> ValidationReport` 하나로 유지한다.
- 테스트 입력은 테스트 코드 안의 문자열이 아니라 `tests/fixtures/invalid_rows/` 의 CSV 파일로 둔다.
