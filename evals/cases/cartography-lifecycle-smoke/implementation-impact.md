# Implementation Cartography impact

- runtime entrypoint: `src/export/entrypoint.py` 신규, `src/cli.py` registration landed
- owner: ExportService 유지
- dependency edge: CLI → export entrypoint → ExportService 신규
- public surface: documented `export` CLI 추가
- state before/after: attachment export planned → landed, CLI stub → landed
- evidence: `tests/integration/test_export_cli.py` actual bytes assertion
- related epic/decision: epic-21 / ADR-0021
