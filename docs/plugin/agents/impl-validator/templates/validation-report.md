# impl-validator report template

이 문서는 schema 가 아니라 보고 재료 예시다. 실제 출력은 자유 prose 로 작성한다.

## PASS

- 검증 범위: merge candidate diff / 변경 파일 / 계획 파일 유무 / 테스트 증거
- 다중 story/epic이면 stack tip vs main diff를 봤는지 명시
- 남은 NICE TO HAVE 가 있으면 blocker 가 아님을 명시

마지막 단락: `PASS`

`CODEBASE_SANITY` mode라면 merge diff 목록 대신 code revision/tree identity, repo 또는 affected dependency cone scope, 명령·exit/warning, coverage 값 또는 `UNKNOWN` 근거, dead-code 후보별 분류, 남은 warning/unknown을 자유 prose로 남긴다. 이 항목들도 고정 schema가 아니다.

## FAIL

- `[spec-gap]` path:line — 깨진 계획/계약, 영향, 필요한 재진입 방향
- `[quality-gap]` path:line — merge blocker, 영향, 필요한 polish 방향

마지막 단락: `FAIL`

## ESCALATE

- 판단 불가 이유: 누락 입력 / 권한 밖 정보 / stack tip vs main diff 부재 / spec 부재가 하드스톱인 이유
- 메인 오케스트레이터 판단점

마지막 단락: `ESCALATE`
