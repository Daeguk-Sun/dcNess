# Invocation A — route-only refresh

- affected Root Cartography 좌표: `Capability 상태 / attachment export`, `As-built routes / CLI export`
- merge candidate diff: `src/cli/export.ts` now dispatches to `src/export/ExportService.ts`; no module owner, storage policy, public boundary, or global decision changed.
- implementation Cartography impact: attachment export `planned → landed`; new CLI export → ExportService edge; related epic-21 and decision 0021.
- state evidence: `tests/integration/export.test.ts` PASS and `message-hub export attachment-1 --out /tmp/export` exit 0 with byte-for-byte result.
- docs policy: `docs/architecture.md` is canonical local-only/ignored private documentation and must not be added to the code PR.
- unchanged sentinels: message search, scheduler cleanup, and Global decisions must remain byte-for-byte unchanged.
