# Architecture Cartography after bounded refresh

## Capability routes

| capability | entrypoint | owner | state | evidence | epic/decision |
|---|---|---|---|---|---|
| attachment export | `src/export/entrypoint.py` | ExportService | landed | `tests/integration/test_export_cli.py` + CLI smoke | epic-21 / ADR-0021 |
| export CLI registration | `src/cli.py` | CLI composition | landed | CLI integration test | epic-21 / ADR-0021 |

## Dependency graph

- CLI → export entrypoint → ExportService

Bounded refresh는 위 affected 좌표만 갱신했으며 system topology, storage policy, ADR-0021은 바꾸지 않았다.
