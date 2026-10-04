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
| REQ-301 | Story AC | 로그인 후 최근 읽은 책 섹션 | `(from AC-301)` | `(JOURNEY) app/.maestro/dcness-journey.json` 시나리오 `login-home` | 전체 시나리오 실행 receipt 의 `ac_results["AC-301"]=PASS`. 시작 상태: 앱 데이터 초기화 후 테스트 계정으로 로그인 화면부터 시작 |
| REQ-302 | Story AC | 표지 → 상세 이동 | `(from AC-302)` | `(JOURNEY) app/.maestro/dcness-journey.json` 시나리오 `home-detail` | `ac_results["AC-302"]=PASS`. 시작 상태: 시나리오가 seed 책 1권과 로그인 토큰을 직접 주입하고 홈에서 시작 |
| REQ-303 | Story AC | 서재에 담기 | `(from AC-303)` | `(JOURNEY) app/.maestro/dcness-journey.json` 시나리오 `shelf-add` | `ac_results["AC-303"]=PASS`. 시작 상태: seed 책 1권, 빈 서재, 로그인 토큰 주입 후 그 책 상세 딥링크로 시작 |
| REQ-304 | Story AC | 밀어서 삭제 | `(from AC-304)` | `(JOURNEY) app/.maestro/dcness-journey.json` 시나리오 `shelf-delete` | `ac_results["AC-304"]=PASS`. 시작 상태: 서재에 책 1권이 담긴 상태를 seed로 만들고 서재 탭에서 시작 |
| REQ-TECH-301 | 기술 REQ | 서재 저장소 단위 테스트 | `(technical: 저장소 경계 계약)` | `(TEST) ./gradlew :app:testDebugUnitTest` | exit 0 |

journey 선언:

- `acceptance_environment.automation: automated`
- `requirements[0].probe`: `adb shell getprop sys.boot_completed` (timeout 10초), `prepare`: `scripts/journey/boot-emulator.sh` (timeout 300초)
- `harness_paths`: `app/.maestro/login-home.yaml`, `app/.maestro/home-detail.yaml`, `app/.maestro/shelf-add.yaml`, `app/.maestro/shelf-delete.yaml`, `scripts/journey/seed.sh`, `app/.maestro/dcness-journey.json`
- 매니페스트 하나에 `start`·`health`·`cleanup`과 시나리오 4개(`login-home`, `home-detail`, `shelf-add`, `shelf-delete`)를 선언한다. `commands.journey`는 쓰지 않는다.
- `commands.start`: debug APK 빌드·설치·실행 (`scripts/journey/install-and-launch.sh`, timeout 300초). 한 번만 실행된다.
- 각 시나리오 `timeout_sec`: 300초. 시나리오마다 `scripts/journey/seed.sh <scenario>`로 시작 상태를 만든 뒤 자기 대본을 실행한다.
- `commands.cleanup`: 앱 데이터 초기화 (`scripts/journey/clear-app.sh`, timeout 60초)
- `boundary: ui`. 시나리오마다 시작 화면과 최종 화면 두 `ui_evidence` 단계를 두고, 각 단계에 그 화면을 남기는 시나리오의 `scenario_id`를 적는다. 최종 화면 단계마다 `ux_integrity` snapshot을 선언한다. 판정 요소: `login-home`은 "최근 읽은 책" 섹션 제목, `home-detail`은 상세 제목·저자, `shelf-add`는 서재 목록의 새 항목, `shelf-delete`는 삭제 확인 뒤 빈 목록 안내. 각 대본은 화면마다 hierarchy dump 도구로 `safe_area`와 요소 `z`를 담은 layout report를 남긴다.
- 확정 목업 없음: 이 epic은 기존 화면 컴포넌트를 재사용하기로 한 decision이 머지돼 있어 `mockup_reference`를 생략한다.
