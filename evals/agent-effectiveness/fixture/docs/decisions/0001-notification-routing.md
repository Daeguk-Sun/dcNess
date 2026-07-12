# Decision 0001: notification routing

`src/notifications/dispatcher.py` owns notification dispatch. The application calls
that owner from `src/app.py`. `src/extension_port.py` remains an intentional seam for
the planned provider extension and must not be classified as stale code.
