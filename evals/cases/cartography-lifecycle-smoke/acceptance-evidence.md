# Epic acceptance evidence

- mode: `EPIC_ACCEPTANCE`
- AC-2101: `test_export_cli_writes_real_attachment` PASS; `message-hub export attachment-1 --out /tmp/export` exit 0; `/tmp/export/attachment-1.bin` bytes가 fixture attachment와 일치
- AC-2102: refreshed Root와 code revalidation이 ExportService owner, storage policy, ADR-0021 유지 확인
- refreshed Root: attachment export와 CLI registration 모두 landed이며 실제 코드 경로와 evidence를 가리킴
- prerequisite: bounded refresh 뒤 같은 merge candidate diff와 갱신 Root에 대한 impl-validator 재검증 PASS
- result: Story AC 전항목 충족, Epic acceptance PASS
