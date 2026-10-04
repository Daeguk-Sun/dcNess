# 설계 산출물 발췌 — epic-02-library / story-03-browse

외부 활성 프로젝트(Android 앱)의 epic 설계 pack 중 검토 대상 부분만 옮겼다. epic architecture, decisions, 확정 목업은 이 story 범위에서 변경이 없고 이미 머지됐다.

## stories.md — Story 3: 서재 둘러보기

- AC-301: 처음 설치한 사용자가 로그인하면 홈 화면에 "최근 읽은 책" 섹션이 보인다.
- AC-302: 홈에서 책 표지를 누르면 책 상세 화면으로 이동하고 제목·저자가 보인다.
- AC-303: 상세 화면에서 "서재에 담기"를 누르면 서재 탭 목록에 그 책이 추가된다.
- AC-304: 서재 탭에서 책을 왼쪽으로 밀면 삭제 확인 후 목록에서 사라진다.

## impl/03-03-browse-journey.md (Story 3 마지막 task, task_index: 3/3)

### 수정 허용

- `app/src/main/java/com/example/library/browse/`
- `app/src/test/java/com/example/library/browse/`
- `app/.maestro/`
- `scripts/journey/`

### 수용 기준

| REQ | 유형 | 내용 | 출처 | 검증 명령 | 통과 조건 |
|---|---|---|---|---|---|
| REQ-301 | Story AC | 로그인 후 최근 읽은 책 섹션 | `(from AC-301)` | `(JOURNEY) app/.maestro/dcness-journey.json` | receipt outcome=PASS, 대상 AC 전부 덮음 |
| REQ-302 | Story AC | 표지 → 상세 이동 | `(from AC-302)` | `(JOURNEY) app/.maestro/dcness-journey.json` | 위와 같음 |
| REQ-303 | Story AC | 서재에 담기 | `(from AC-303)` | `(JOURNEY) app/.maestro/dcness-journey.json` | 위와 같음 |
| REQ-304 | Story AC | 밀어서 삭제 | `(from AC-304)` | `(JOURNEY) app/.maestro/dcness-journey.json` | 위와 같음 |
| REQ-TECH-301 | 기술 REQ | 서재 저장소 단위 테스트 | `(technical: 저장소 경계 계약)` | `(TEST) ./gradlew :app:testDebugUnitTest` | exit 0 |

journey 선언:

- `acceptance_environment.automation: automated`
- `requirements[0].probe`: `adb shell getprop sys.boot_completed` (timeout 10초), `prepare`: `scripts/journey/boot-emulator.sh` (timeout 300초)
- `harness_paths`: `app/.maestro/login.yaml`, `app/.maestro/home.yaml`, `app/.maestro/detail.yaml`, `app/.maestro/shelf-add.yaml`, `app/.maestro/shelf-delete.yaml`, `scripts/journey/run-all-flows.sh`, `app/.maestro/dcness-journey.json`
- `commands.start`: debug APK 빌드·설치·실행 (`scripts/journey/install-and-launch.sh`, timeout 300초)
- `commands.journey`: `bash scripts/journey/run-all-flows.sh` (timeout 1800초). 이 스크립트가 login → home → detail → shelf-add → shelf-delete 대본 5개를 차례로 실행하고, 하나라도 실패하면 exit 1로 끝낸다.
- `commands.cleanup`: 앱 데이터 초기화 (`scripts/journey/clear-app.sh`, timeout 60초)
- `boundary: ui`. 대본마다 최종 화면 `ui_evidence` 단계와 `ux_integrity` snapshot을 선언한다. 판정 요소: home은 "최근 읽은 책" 섹션 제목, detail은 상세 제목·저자, shelf-add는 서재 목록의 새 항목, shelf-delete는 삭제 확인 뒤 빈 목록 안내. 각 대본은 화면마다 hierarchy dump 도구로 `safe_area`와 요소 `z`를 담은 layout report를 남긴다.
- 확정 목업 없음: 이 epic은 기존 화면 컴포넌트를 재사용하기로 한 decision이 머지돼 있어 `mockup_reference`를 생략한다.
- 대본들은 앞 대본이 끝난 화면과 로그인 상태를 이어받아 진행한다. 예를 들어 detail 대본은 home 대본이 연 홈 화면에서 시작한다.

참고 실측: 같은 프로젝트의 이전 story에서 대본 9개를 한 스크립트로 묶은 journey가 556~579초 걸렸다. 수렴 중 대본 하나를 고칠 때마다 전체를 다시 실행했다.
