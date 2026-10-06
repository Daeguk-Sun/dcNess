# 설계 개정 입력 — epic-02

## 직전 검증 결과

- 호출 시점: `/design` final epic 검증
- 대상: 설계 pack 전체(`prd.md`, `stories.md`, `architecture.md`, `impl/01-dry-run-row-count.md`, `impl/02-invalid-row-report.md`, `impl/03-db-write.md`)
- 대상 커밋: `d41c0aa`
- 결론: PASS. Must finding 0건, Should finding 0건.
- 그 검증 뒤 설계 pack 은 main 에 머지됐다. 구현은 아직 시작하지 않았다.

## 사용자 개정 의도

"02 task 의 검사 단위 테스트 입력을 테스트 코드 안의 문자열이 아니라 CSV 파일로 두고 싶다. 운영팀이 실제로 받은 잘못된 파일을 그대로 넣어 확인할 수 있어야 한다. 제품 동작과 출력 문구는 바꾸지 않는다."

## 개정 뒤 변경분 (`d41c0aa..f7e2b19`)

커밋 1개. 바뀐 파일은 `impl/02-invalid-row-report.md` 하나다. 다른 파일은 바뀌지 않았다.

```diff
--- a/impl/02-invalid-row-report.md
+++ b/impl/02-invalid-row-report.md
@@ Scope / 수정 허용
 - `src/row_validator/`
 - `src/import_cli/`
 - `tests/row_validator/`
 - `tests/import_cli/`
+- `tests/fixtures/invalid_rows/`
@@ 수용 기준
-| REQ-003 (technical: 검사 단위 경계) | `validate(rows)` 가 잘못된 행마다 `RowError` 를 돌려준다 | `(TEST) pytest tests/row_validator -k returns_row_errors` | green |
+| REQ-003 (technical: 검사 단위 경계) | `validate(rows)` 가 `tests/fixtures/invalid_rows/` 의 CSV 파일별로 정해진 `RowError` 목록을 돌려준다 | `(TEST) pytest tests/row_validator -k fixture_cases` | green |
@@ 주의사항
 - 모듈 설계 주의: 이메일 규칙 판정은 row-validator 내부에 숨긴다. 공개 인터페이스는 `validate(rows) -> ValidationReport` 하나로 유지한다.
+- 테스트 입력은 테스트 코드 안의 문자열이 아니라 `tests/fixtures/invalid_rows/` 의 CSV 파일로 둔다.
```

## 파생 drift 체크리스트 결과 (메인이 확인)

- `ux-flow.md`: 해당 없음(UI 없는 epic).
- 전역 `architecture.md` 요약: 변경 없음. 모듈·공개 인터페이스·의존 방향을 바꾸지 않았다.
- 상태 ID prefix, 확정 목업 node-id, `docs/design.md` 토큰: 해당 없음.
- ADR: 이 epic 에 ADR 이 없다. 새 결정도 없다.
- Story/화면 번호: 변경 없음.
- `tests/fixtures/invalid_rows/` 경로는 다른 task 의 `수정 허용`·`수정 금지` 에 나오지 않는다.

## Story AC ↔ REQ advisory report (개정 뒤)

- 미커버 AC 0건, 무출처 REQ 0건, 존재하지 않는 AC 참조 0건. 개정 전과 같다.
