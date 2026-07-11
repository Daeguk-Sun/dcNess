# Product evidence

- PR #210은 `src/export/entrypoint.py`에서 ExportService를 호출한다.
- `tests/integration/test_attachment_export.py`는 실제 attachment fixture를 entrypoint로 export하고 생성 파일의 bytes를 검증한다.
- CLI smoke `app export attachment-1 --out /tmp/export`가 exit 0이고 `/tmp/export/attachment-1.bin`을 생성했다.
- system boundary, owner, ADR-0021은 바뀌지 않았다.
