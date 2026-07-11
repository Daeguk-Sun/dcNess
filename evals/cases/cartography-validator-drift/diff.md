```diff
diff --git a/app/src/main/kotlin/example/App.kt b/app/src/main/kotlin/example/App.kt
--- a/app/src/main/kotlin/example/App.kt
+++ b/app/src/main/kotlin/example/App.kt
@@
+import example.data.MessageObserver
 class App : Application() {
+  private val observer = MessageObserver()
   override fun onCreate() {
     super.onCreate()
+    observer.start()
   }
+  override fun onTerminate() {
+    observer.stop()
+    super.onTerminate()
+  }
 }
diff --git a/app/src/test/kotlin/example/AppObserverIntegrationTest.kt b/app/src/test/kotlin/example/AppObserverIntegrationTest.kt
new file mode 100644
--- /dev/null
+++ b/app/src/test/kotlin/example/AppObserverIntegrationTest.kt
@@
+class AppObserverIntegrationTest {
+  @Test fun applicationLifecycleStartsAndStopsObserver() {
+    val observer = RecordingMessageObserver()
+    val app = App(observer)
+
+    app.onCreate()
+    assertTrue(observer.started)
+    app.onTerminate()
+    assertTrue(observer.stopped)
+  }
+}
```
