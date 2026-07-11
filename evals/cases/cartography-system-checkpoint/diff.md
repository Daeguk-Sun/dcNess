```diff
diff --git a/src/api/messages.py b/src/api/messages.py
deleted file mode 100644
--- a/src/api/messages.py
+++ /dev/null
@@
-def post_message(payload):
-    return IngestGateway().accept(payload)
diff --git a/src/stream/ingress.py b/src/stream/ingress.py
new file mode 100644
--- /dev/null
+++ b/src/stream/ingress.py
@@
+class StreamIngress:
+    def accept(self, event): ...
```
