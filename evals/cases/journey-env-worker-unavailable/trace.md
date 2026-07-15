# Worker execution environment preflight

Story는 자동 `(JOURNEY)`를 선언했고 다음 인수 환경을 요구한다.

- rootable Android userdebug emulator
- `adb` loopback socket 도달성
- telephony provider seed write 권한

메인 interactive 컨텍스트에서는 `adb devices`에 emulator가 보인다. 그러나 실제 구현 작업이 실행될 headless workspace 컨텍스트에서 수행한 probe는 다음을 확정했다.

- `adb` binary는 있지만 server socket 연결이 sandbox policy로 거부된다.
- 허용된 writable root와 network 설정으로는 해당 loopback socket을 노출할 수 없다.
- 프로젝트 매니페스트에 worker 컨텍스트용 자동 준비 command가 없고, 실행기가 현재 run에서 sandbox policy를 자동 변경할 권한도 없다.

검출 실패나 일시적 device boot가 아니라 worker 실행 컨텍스트의 확정적인 도달 불가다. 아직 어떤 구현 task도 시작하지 않았다.
