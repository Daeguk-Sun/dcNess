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
diff --git a/tests/integration/test_nightly_export.py b/tests/integration/test_nightly_export.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_nightly_export.py
@@
+def test_scheduler_callback_reaches_real_export_service(tmp_path):
+    service = ExportService(output_dir=tmp_path)
+    service.add_due_item("message-1")
+
+    run_nightly_export(service)
+
+    assert (tmp_path / "message-1.json").is_file()
```
