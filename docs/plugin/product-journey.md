# Project-local 제품 journey 실행 계약

> **Status**: ACTIVE
> **Scope**: 외부 활성 프로젝트의 핵심 journey 한 건을 실제 제품 경계에서 실행하고 product-acceptance가 읽을 receipt를 생성한다. UI journey는 같은 실행 계약에 단계별 화면 증거만 선택적으로 추가한다.

## 책임 경계

프로젝트가 실행 방법을 선언하고 dcNess plugin helper가 순서대로 실행한다. 특정 언어, 프레임워크, 테스트 도구를 요구하지 않는다.

1. `start`: 앱·서비스·CLI 진입점을 시작한다.
2. `health`: 다음 journey를 실행할 준비가 됐는지 확인한다.
3. `journey`: API·CLI·UI·실데이터 통합 경계에서 대상 AC assertion을 평가한다.
4. `cleanup`: 성공·실패와 무관하게 종료·정리한다.
5. `evidence_dir`: command exit와 log, 대상 AC, 실행 시각을 연결하는 receipt 위치다.

module-architect가 실앱 실행이 필요한 AC를 `(JOURNEY)` REQ로 지정하고, build-worker가 project-local e2e flow와 journey 매니페스트를 작성한다. `product-acceptance`는 receipt가 없으면 tip에서 helper를 실행하고, 생성된 receipt와 대상 Story AC를 판정한다. 검증 agent는 tracked 구현·설계 소스나 receipt를 수정하지 않는다. UI 경계도 네 command와 같은 assertion 판정을 재사용하며, helper가 브라우저를 직접 자동화하지 않는다. 프로젝트가 소유한 journey command가 화면을 조작하고 screenshot·상태 파일을 남긴다.

## 프로젝트 계약

build-worker가 만드는 새 매니페스트는 `.dcness/` 밖 owner module/소스 영역(예: `app/.maestro/dcness-journey.json`)에 둔다. `.dcness/`는 sub-agent write 보호 영역이므로 carve-out을 만들지 않는다. 이 lifecycle에서는 helper의 `--config`로 매니페스트 경로를 명시한다. helper의 기존 기본 경로 지원은 수동으로 관리 중인 legacy 계약 호환용이며, 새 build-worker 산출물 위치가 아니다.

```json
{
  "version": 1,
  "journey_id": "account-export-cli",
  "target_ac": ["AC-EXPORT-1"],
  "boundary": "cli",
  "assertion": {
    "description": "export 명령이 실제 저장소에서 대상 파일을 생성하고 내용을 검증한다",
    "source": "journey_exit"
  },
  "human_intervention_count": 0,
  "env": {
    "APP_ENV": "acceptance"
  },
  "commands": {
    "start": {
      "argv": ["./bin/app", "--version"],
      "mode": "command",
      "timeout_sec": 30
    },
    "health": {
      "argv": ["./bin/app", "doctor"],
      "timeout_sec": 30
    },
    "journey": {
      "argv": ["./scripts/assert-export-journey.sh"],
      "timeout_sec": 120
    },
    "cleanup": {
      "argv": ["./scripts/cleanup-export-journey.sh"],
      "timeout_sec": 30
    }
  },
  "evidence_dir": ".dcness-work/product-journey"
}
```

### 필드 의미

| 필드 | 계약 |
|---|---|
| `journey_id` | 소문자·숫자·`.`·`_`·`-`로 된 안정 식별자 |
| `target_ac` | journey assertion이 대조할 Story AC 식별자. 한 개 이상 필수 |
| `boundary` | `api`, `cli`, `integration`, `ui`, `mock`. `mock`은 fixture용이며 outcome PASS 불가 |
| `assertion.description` | command가 무엇을 판정하는지 제품 언어로 설명 |
| `assertion.source` | `journey_exit`이면 journey exit 0을 assertion PASS로 사용. `none`은 미평가 fixture이며 PASS 불가 |
| `human_intervention_count` | 실행 중 사람이 개입한 횟수. 없으면 0 |
| `env` | 네 단계에 공통으로 추가할 문자열 환경 변수 |
| `commands.*.argv` | shell 문자열이 아닌 argv 배열. setup/teardown/상태전이 오케스트레이션이 필요하면 `commands.journey.argv`에서 `bash`와 프로젝트 스크립트 경로를 명시적으로 선택 |
| `commands.*.timeout_sec` | 단계별 600초 이하 timeout |
| `commands.start.mode` | 장기 실행 앱은 `service`, 종료되는 CLI 진입점은 `command` |
| `commands.start.startup_grace_sec` | service가 조기 종료하지 않았는지 확인할 유예 시간 |
| `evidence_dir` | `.dcness-work/product-journey/` 아래의 project-relative 위치 |

start가 실패하거나 service가 유예 시간 안에 종료되면 `app_not_started`다. health가 실패하면 journey를 실행하지 않고 `journey_not_executed`로 남긴다. journey가 실행되지 않았거나 `assertion.source=none`이면 `assertion_not_evaluated`다. `mock` boundary는 모든 command가 exit 0이어도 `mock_only_boundary`이므로 PASS가 아니다. cleanup은 항상 실행하며 실패하면 전체 outcome도 FAIL이다.

### `(JOURNEY)` flow 설계 경계

- flow 산출물은 단일 UI yaml에 한정되지 않는다. 시드, 역할 교체, 네트워크 상태 토글처럼 전후 상태를 엮어야 하면 build-worker가 setup/teardown/상태전이 스크립트를 함께 작성하고 journey argv에서 오케스트레이션한다.
- negative 동작 계약은 부재만 기다리지 않고 대응하는 양성 프록시 event를 REQ와 assertion에 명시한다. 양성 프록시가 없으면 자동 PASS를 만들지 않고 `사람 확인 안내`로 분리한다.
- 관찰 창이 sub-second인 상태나 순수 위치·픽셀 판정은 flaky한 `(JOURNEY)`로 강제하지 않고 `사람 확인 안내`로 분리한다.

## UI 증거 확장

`boundary=ui`는 위 project-local 계약을 바꾸지 않고 `ui_evidence.steps`만 추가한다. 최소 두 단계가 필요하며 `final=true`인 단계들이 `target_ac` 전부를 덮어야 한다. 각 evidence path는 해당 run directory 내부의 상대 경로이고 type은 `screenshot`, `state`, `log` 중 하나다.

```json
{
  "boundary": "ui",
  "target_ac": ["AC-ONBOARD-1"],
  "ui_evidence": {
    "steps": [
      {
        "step_id": "onboarding",
        "description": "생년월일과 동의를 입력한 화면",
        "target_ac": ["AC-ONBOARD-1"],
        "final": false,
        "evidence": [
          {"path": "onboarding.png", "type": "screenshot"}
        ]
      },
      {
        "step_id": "result",
        "description": "제출 뒤 제품 AC를 판정하는 최종 화면",
        "target_ac": ["AC-ONBOARD-1"],
        "final": true,
        "evidence": [
          {"path": "result.png", "type": "screenshot"},
          {"path": "browser-assertions.log", "type": "log"}
        ]
      }
    ]
  }
}
```

helper는 command 환경에 `DCNESS_PRODUCT_JOURNEY_RUN_DIR` 절대경로를 주입한다. 프로젝트 journey command는 이 위치에 선언한 파일을 생성한다. receipt에는 project-relative path, 존재 여부, SHA-256을 단계별로 기록한다. 파일이 없거나 비어 있거나 run directory 밖 symlink면 `ui_evidence_missing`으로 FAIL한다. screenshot 파일 자체가 assertion을 대신하지 않으며, `journey_exit=0`이 단계별 화면 assertion 평가를 증명해야 한다.

이는 UI 전용 실행기나 범용 E2E 플랫폼이 아니다. 기존 Playwright, AppTest, XCUITest 같은 project-local 도구 또는 수동으로 보존된 자동화 driver를 journey command가 선택하고, dcNess helper는 실행 순서·receipt·무결성만 맡는다.

## 실행과 receipt

```sh
"$PLUGIN_ROOT/scripts/dcness-product-journey" run \
  --project-root "$PROJECT_ROOT" \
  --config app/.maestro/dcness-journey.json
```

성공은 exit 0, 실행된 제품 gap은 exit 1, 잘못된 계약은 exit 2다. 각 run은 `evidence_dir/<run-id>/`에 단계별 log와 `receipt.json`을 남긴다. receipt는 다음 의미를 포함한다.

- 실제 시작 여부 `app_started`, journey 실행 여부 `journey_executed`.
- assertion의 설명·근거·평가 여부·결과.
- 단계별 argv, exit code, timeout, wall-clock과 log 위치.
- UI journey이면 핵심 단계 설명·대상 AC·최종 단계 여부·screenshot/state/log path와 SHA-256.
- 대상 AC의 passed/total denominator, 사람 개입, 실행 증거 종류.
- log별 sha256과 failure reason.

`harness/outcome_scorecard.py`는 helper receipt 중 구조가 유효하고 snapshot cutoff 안에 있는 것만 읽는다. journey PASS/전체 실행 수와 제품 AC passed/total을 각각 보존하며 guard·validator·PR 지표를 제품 outcome 분자에 넣지 않는다.

## 배포와 보존

helper와 runtime은 plugin 본체의 `scripts/dcness-product-journey`, `harness/product_journey.py`로 배포된다. 사용자 repo에 helper 사본을 복사하지 않는다. 프로젝트 계약은 opt-in이며 `/init-dcness`가 자동 생성하거나 덮어쓰지 않는다.

계약을 팀과 공유해야 하면 owner module/소스 영역의 매니페스트와 e2e flow를 프로젝트가 명시적으로 관리한다. plugin에 포함된 build-worker가 활성 프로젝트의 해당 영역에 산출물을 만들기 때문에 신규 `/init-dcness` deploy 스텝은 필요 없다. 실행 log와 receipt는 재생성 가능한 실측 evidence이므로 gitignore 대상 `.dcness-work/product-journey/`에 둔다.
