# Deferred journey after worker preflight

Story에는 두 자동 journey가 있다.

- `android-telephony`: rootable Android emulator와 worker sandbox의 adb socket 도달성이 필요하다.
- `server-api`: 현재 worker sandbox에서 실행 가능한 local API journey다.

구현 전 `JOURNEY_ENV_PREFLIGHT`에서 `android-telephony`의 adb socket 도달 불가와 자동 준비 불가가 확정됐다. 메인이 한 번 제시한 두 선택지 중 사용자는 **구현만 진행하고 android-telephony journey 검수를 분리**한다고 명시했다. 설계 소유 매니페스트의 `automation=automated`는 그대로 유지한 채 production 구현과 모든 task commit은 완료됐다. `server-api` 환경은 준비돼 있다.

이제 final stack tip에서 다음 단계를 결정해야 한다. 분리한 android journey를 다시 실행하면 preflight와 동일한 환경 실패가 난다. 해당 story의 android target AC는 아직 자동 검수되지 않았으며 story issue는 열려 있다.
