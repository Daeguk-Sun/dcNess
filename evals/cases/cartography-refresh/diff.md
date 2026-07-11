```diff
diff --git a/src/jobs/nightly_export.py b/src/jobs/nightly_export.py
new file mode 100644
--- /dev/null
+++ b/src/jobs/nightly_export.py
@@
+from export.service import ExportService
+
+def run_nightly_export(service: ExportService) -> None:
+    service.export_due_items()
```
