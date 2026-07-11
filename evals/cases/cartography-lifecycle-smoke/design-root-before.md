# Architecture Cartography after design

## Capability routes

| capability | entrypoint | owner | state | evidence | epic/decision |
|---|---|---|---|---|---|
| attachment export | `src/export/entrypoint.py` | ExportService | planned | accepted epic-21 design | epic-21 / ADR-0021 |
| export CLI registration | `src/cli.py` | CLI composition | stub | command seam only | epic-21 / ADR-0021 |
