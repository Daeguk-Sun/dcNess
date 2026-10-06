---
design: optional
story: 1
task_index: 1/3
depends_on: []
---

# 01-dry-run-row-count

## 사전 준비

- 읽을 문서: `stories.md` (Story 1), `architecture.md`

## 무엇을 만드나

- `contacts import <file> --dry-run` 이 CSV 파일을 읽고 `rows: N` 을 출력한다. Story 1 완료 시 명령줄에서 행 수가 보인다.
- 제품 경계: `contacts import` 명령의 표준 출력과 exit code.
- 첫 동작 증거 지점: 올바른 파일에 대해 `rows: N` 출력.

## 왜 만드나

- PRD M1. 파서와 명령 진입점을 한 task 로 묶어 첫 Story 에서 명령줄 동작을 낸다.

## Scope

### 수정 허용

- `src/csv_parser/`
- `src/import_cli/`
- `tests/csv_parser/`
- `tests/import_cli/`

### 수정 금지

- `src/row_validator/`
- `src/contact_store/`

## 인터페이스

- 계약/결정 링크:
  - module: csv-parser, import-cli (`architecture.md` 모듈 목록)
- owner/entrypoint 요약:
  - owner flow/module: import-cli
  - entrypoint role: `contacts import` 인자 해석 → `parse(path)` 호출 → 출력
  - state owner: 없음(상태를 보관하지 않는다)
  - validation path: `pytest tests/import_cli -k dry_run`

## 수용 기준

| REQ | 내용 | 검증 명령 | 통과 조건 |
|---|---|---|---|
| REQ-001 (from AC-101) | 올바른 CSV 에 대해 `--dry-run` 이 `rows: N` 을 출력하고 exit 0 | `(TEST) pytest tests/import_cli -k dry_run_prints_row_count` | green |
| REQ-002 (technical: 파서 단위 경계) | `parse(path)` 가 헤더를 제외한 행 목록을 돌려준다 | `(TEST) pytest tests/csv_parser -k parse_returns_rows` | green |

## 주의사항

- 모듈 설계 주의: 파일 인코딩 처리와 구분자 처리는 csv-parser 내부에 숨긴다.
