# Epic acceptance evidence

- integration: `test_export_cli_writes_real_attachment` PASS
- smoke: `message-hub export attachment-1 --out /tmp/export` exit 0
- result: `/tmp/export/attachment-1.bin` bytes가 fixture attachment와 일치
- refreshed Root: attachment export와 CLI registration 모두 landed이며 실제 코드 경로와 evidence를 가리킴
- prerequisite: bounded refresh 뒤 같은 merge candidate diff와 갱신 Root에 대한 impl-validator 재검증 PASS
