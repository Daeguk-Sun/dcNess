# Build impact

- runtime entrypoint: `src/jobs/nightly_export.py` 신규
- capability/state owner: 기존 ExportService 유지
- dependency edge: Scheduler → nightly_export → ExportService 신규
- public surface: 내부 scheduler callback 추가, 기존 외부 API 변화 없음
- state before/after: nightly export route `planned → landed`
- evidence: `tests/integration/test_nightly_export.py`가 scheduler callback에서 실제 ExportService 호출을 검증
- related epic/decision: epic-21 export, ADR-0021
