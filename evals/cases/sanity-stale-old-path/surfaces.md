# Repository surfaces

- `AppModule.kt`: binds `SyncPort` to `SyncCoordinator`
- `AndroidManifest.xml`: still registers `.legacy.SyncService`
- `res/xml/sync_service.xml`: still points at `.legacy.SyncService`
- `LegacySyncServiceTest.kt`: asserts the old retry behavior
- new route dispatches to `SyncCoordinator`
- runtime smoke starts both registrations and logs duplicate sync scheduling
