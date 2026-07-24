# Root Cartography before final sync

## Capability 상태

| Capability | 상태 | Runtime entrypoint | Evidence |
|---|---|---|---|
| attachment export | planned | `src/cli/export.ts` | epic-21 |
| message search | landed | `src/cli/search.ts` | `tests/integration/search.test.ts` |

## As-built routes

- CLI search → `src/cli/search.ts` → `src/search/SearchService.ts`
- scheduler cleanup → `src/jobs/cleanup.ts` → `src/storage/MessageStore.ts`

## Global decisions

- attachment storage remains the existing byte-store policy in `docs/decisions/0021-attachment-storage.md`.
