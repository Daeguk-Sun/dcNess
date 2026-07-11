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
```
