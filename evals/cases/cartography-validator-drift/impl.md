# Message observer lifecycle wiring

`App.kt`가 기존 `MessageObserver`를 시작·종료 lifecycle에 연결한다. owner는 data module에 남고 app-root는 composition wiring만 소유한다. integration test로 observer start/stop을 검증한다.
