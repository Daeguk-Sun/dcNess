# Architecture Cartography

| Capability | Runtime entrypoint | Owner | Decision | Status |
|---|---|---|---|---|
| notification dispatch | `src/app.py` | `src/notifications/dispatcher.py` | `docs/decisions/0001-notification-routing.md` | landed |

`legacy/notification_router.py` is replaced and is not runtime-reachable.
