# Final candidate

- code revision: `tree-clean-77`
- scope: sync module + dependents; global registration search included
- `SyncService` replaced by `SyncCoordinator`
- old call sites: 0; old DI bindings: 0; old routes/deep links: 0
- manifest/framework registrations: only `SyncCoordinatorReceiver`
- old resources/tests/fakes/fixtures/suppressions: 0
- preserved seam: `SyncPort`, owner `sync-domain`, required by two current adapters
- integration smoke proves one schedule per event
- unit/integration test, lint, build, typecheck: exit 0, warnings 0
- coverage report: sync lines 91%, branch 84%, generated adapters excluded by tool config
