```diff
diff --git a/src/export/entrypoint.py b/src/export/entrypoint.py
new file mode 100644
--- /dev/null
+++ b/src/export/entrypoint.py
@@
+def export_attachment(service: ExportService, attachment_id: str, output: Path) -> Path:
+    return service.export_attachment(attachment_id, output)
diff --git a/src/cli.py b/src/cli.py
--- a/src/cli.py
+++ b/src/cli.py
@@
+    export_parser = subcommands.add_parser("export")
+    export_parser.set_defaults(handler=run_export)
diff --git a/tests/integration/test_export_cli.py b/tests/integration/test_export_cli.py
new file mode 100644
--- /dev/null
+++ b/tests/integration/test_export_cli.py
@@
+def test_export_cli_writes_real_attachment(tmp_path, fixture_store):
+    result = run_cli(["export", "attachment-1", "--out", str(tmp_path)], store=fixture_store)
+    assert result.exit_code == 0
+    assert (tmp_path / "attachment-1.bin").read_bytes() == b"attachment-bytes"
```
