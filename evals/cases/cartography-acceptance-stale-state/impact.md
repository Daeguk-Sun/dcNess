# Implementation Cartography impact

- runtime entrypoint: `src/export/entrypoint.py` landed
- owner: ExportService 유지
- dependency edge: CLI → export entrypoint → ExportService 추가
- public surface: documented CLI command 추가
- state before/after: attachment export planned → landed
- evidence: integration test와 CLI smoke
- related epic/decision: epic-21 / ADR-0021
