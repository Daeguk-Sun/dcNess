# Runtime wiring

`AndroidManifest.xml`:

```xml
<receiver android:name=".ExportReceiver" android:exported="false">
  <intent-filter><action android:name="com.example.ACTION_EXPORT" /></intent-filter>
</receiver>
```

Instrumentation smoke evidence: broadcasting `ACTION_EXPORT` writes one encrypted attachment and passes.
