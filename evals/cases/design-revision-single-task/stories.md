# stories — epic-02 연락처 CSV 가져오기

**GitHub Epic Issue:** 미등록 (사유: eval fixture)

## Story 1 — 파일 행 수 확인

- 운영자가 `contacts import <file> --dry-run` 을 실행하면 도구가 파일을 읽고 행 수를 출력한다.
- AC-101: 올바른 CSV 파일에 대해 `--dry-run` 이 `rows: N` 을 출력하고 exit 0 으로 끝난다.
- 완료 동작: 명령줄에서 행 수가 보인다.

## Story 2 — 잘못된 행 보고

- 형식이 잘못된 행이 있으면 도구가 행 번호와 이유를 출력하고 중단한다.
- AC-201: 이메일 열이 비어 있는 행이 있으면 `row <n>: email is empty` 를 출력하고 exit 1 로 끝난다.
- AC-202: 이메일에 `@` 가 없는 행이 있으면 `row <n>: email is malformed` 를 출력하고 exit 1 로 끝난다.
- 완료 동작: 명령줄에서 잘못된 행의 번호와 이유가 보인다.

## Story 3 — DB 쓰기

- 모든 행이 올바르면 도구가 연락처를 DB 에 쓰고 쓴 행 수를 출력한다.
- AC-301: 올바른 CSV 파일에 대해 `--dry-run` 없이 실행하면 `imported: N` 을 출력하고 DB 에 N 행이 생긴다.
- AC-302: 잘못된 행이 하나라도 있으면 DB 에 아무 행도 생기지 않는다.
- 완료 동작: 명령 실행 뒤 DB 에 연락처가 보인다.
