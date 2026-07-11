```diff
diff --git a/src/messages/retry.py b/src/messages/retry.py
--- a/src/messages/retry.py
+++ b/src/messages/retry.py
@@
-    delay = min(base * attempt, maximum)
+    delay = min(base * max(attempt, 1), maximum)
diff --git a/tests/integration/test_retry.py b/tests/integration/test_retry.py
--- a/tests/integration/test_retry.py
+++ b/tests/integration/test_retry.py
@@
+def test_zero_attempt_uses_first_retry_delay():
+    assert retry_delay(attempt=0) == retry_delay(attempt=1)
```
