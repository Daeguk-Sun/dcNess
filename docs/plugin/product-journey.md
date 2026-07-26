# Project-local 제품 journey 실행 계약

> **Status**: ACTIVE
> **Scope**: 외부 활성 프로젝트의 핵심 journey 한 건을 실제 제품 경계에서 실행하고 product-acceptance가 읽을 receipt를 생성한다. UI journey는 같은 실행 계약에 단계별 화면 증거와 요소 bounds 기반 UX 정합성 판정을 더한다.

## 책임 경계

프로젝트가 실행 방법을 선언하고 dcNess plugin helper가 순서대로 실행한다. 특정 언어, 프레임워크, 테스트 도구를 요구하지 않는다.

1. `start`: 앱·서비스·CLI 진입점을 시작한다.
2. `health`: 다음 journey를 실행할 준비가 됐는지 확인한다.
3. `journey`: API·CLI·UI·실데이터 통합 경계에서 대상 AC assertion을 평가한다.
4. `cleanup`: 성공·실패와 무관하게 종료·정리한다.
5. `evidence_dir`: command exit와 log, 대상 AC, 실행 시각을 연결하는 receipt 위치다.

module-architect가 실앱 실행이 필요한 AC를 `(JOURNEY)` REQ로 지정하고 인수 환경과 하네스 배관 경로를 impl task에 선언한다. build-worker는 project-local e2e flow와 journey 매니페스트를 작성한 뒤, 모든 task가 끝난 final tip에서 별도 수렴 호출로 실제 실행·관찰·수정을 끝낸다. `product-acceptance`는 이 수렴 결과를 신뢰해 생략하지 않고 final tip에서 sealed receipt를 직접 생성·판정한다. 고치기 위한 실행은 build-worker, 판정하기 위한 write-zero 실행은 product-acceptance 소유다. UI 경계도 네 command와 같은 assertion 판정을 재사용하며, helper가 브라우저를 직접 자동화하지 않는다. 프로젝트가 소유한 journey command가 화면을 조작하고 screenshot·상태 파일을 남긴다.

## 프로젝트 계약

build-worker가 만드는 매니페스트는 `.dcness/` 밖 owner module/소스 영역(예: `app/.maestro/dcness-journey.json`)에 둔다. `.dcness/`는 sub-agent write 보호 영역이므로 carve-out을 만들지 않는다. helper 실행 시 `--config`로 매니페스트 경로를 반드시 명시한다.

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
  "acceptance_environment": {
    "automation": "automated",
    "requirements": [
      {
        "id": "project-cli-ready",
        "description": "worker 실행 컨텍스트에서 실제 CLI와 fixture 저장소에 도달한다",
        "probe": {
          "argv": ["./bin/app", "doctor"],
          "timeout_sec": 30
        },
        "prepare": {
          "argv": ["./scripts/prepare-acceptance.sh"],
          "timeout_sec": 300
        }
      }
    ]
  },
  "harness_paths": [
    "scripts/assert-export-journey.sh",
    "scripts/cleanup-export-journey.sh"
  ],
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
| `acceptance_environment.automation` | `automated` 또는 `human_verification`. 후자는 `자동 인수 불가, 사람 확인 필요`를 명시하는 값이며 env 선검증·수렴 호출 비발동 |
| `acceptance_environment.requirements` | worker 실행 컨텍스트가 실제로 도달해야 하는 device/emulator+socket, browser/driver, service+writable fixture, provisioned tenant, 특수 seed 권한 같은 요건 목록 |
| `acceptance_environment.requirements[].probe` | worker 실행 컨텍스트에서 요건 충족 여부를 확인하는 argv와 timeout. 판정 주체를 main 환경으로 바꾸지 않는다 |
| `acceptance_environment.requirements[].prepare` | emulator boot, container/service 기동, socket 노출처럼 기계적으로 준비할 수 있을 때 쓰는 선택 argv와 timeout |
| `harness_paths` | flow, seed, runner, manifest, env adapter처럼 수렴 호출이 대조·수정할 project-relative 하네스 배관 경로. write 경계를 기계 강제하는 목록이 아니라 설계·리뷰 handoff 계약 |
| `env` | 네 단계에 공통으로 추가할 문자열 환경 변수 |
| `commands.*.argv` | shell 문자열이 아닌 argv 배열. setup/teardown/상태전이 오케스트레이션이 필요하면 `commands.journey.argv`에서 `bash`와 프로젝트 스크립트 경로를 명시적으로 선택 |
| `commands.*.timeout_sec` | 단계별 600초 이하 timeout |
| `commands.start.mode` | 장기 실행 앱은 `service`, 종료되는 CLI 진입점은 `command` |
| `commands.start.startup_grace_sec` | service가 조기 종료하지 않았는지 확인할 유예 시간 |
| `evidence_dir` | `.dcness-work/product-journey/` 아래의 project-relative 위치 |

새 `(JOURNEY)`는 design/impl-task가 `acceptance_environment`와 `harness_paths`를 먼저 소유하고, build-worker가 같은 값을 project-local 매니페스트에 materialize한다. `automation=automated`이면 `/impl-loop`가 run 진입 직후 worker 실행 컨텍스트에서 probe와 가능한 prepare를 수행하고, 모든 task 완료 뒤 같은 실행 substrate의 fresh build-worker 수렴 호출을 연다. journey 미선언 story와 `automation=human_verification` journey에는 env 선검증·수렴 호출이 비발동이며 기존 `사람 확인 안내`로 남는다.

probe가 확실한 미충족을 보고하고 `prepare`가 없거나 실패 사유상 자동 준비가 불가능할 때만 구현 전에 사용자가 환경 준비 또는 journey 검수 분리를 한 번 선택한다. 도구 부재처럼 검출 자체가 불확실하면 차단하지 않고 구현·수렴으로 진행한다. main에서 보이는 device나 service는 worker 실행 컨텍스트의 도달성 증거를 대신하지 않는다.

사용자가 journey 검수 분리를 선택하면 메인은 해당 `journey_id`를 현재 run의 `journey_deferred` 목록으로 보존한다. 이는 설계가 소유한 `acceptance_environment.automation`을 바꾸거나 매니페스트를 다시 쓰지 않는다. 현재 run에서만 해당 journey를 `human_verification`/follow-up 처분으로 취급하며, 다른 자동 journey의 env 선검증·수렴·sealed 판정은 계속 수행한다.

start가 실패하거나 service가 유예 시간 안에 종료되면 `app_not_started`다. health가 실패하면 journey를 실행하지 않고 `journey_not_executed`로 남긴다. journey가 실행되지 않았거나 `assertion.source=none`이면 `assertion_not_evaluated`다. `mock` boundary는 모든 command가 exit 0이어도 `mock_only_boundary`이므로 PASS가 아니다. cleanup은 항상 실행하며 실패하면 전체 outcome도 FAIL이다.

### `(JOURNEY)` flow 설계 경계

- flow 산출물은 단일 UI yaml에 한정되지 않는다. 시드, 역할 교체, 네트워크 상태 토글처럼 전후 상태를 엮어야 하면 build-worker가 setup/teardown/상태전이 스크립트를 함께 작성하고 journey argv에서 오케스트레이션한다.
- negative 동작 계약은 부재만 기다리지 않고 대응하는 양성 프록시 event를 REQ와 assertion에 명시한다. 양성 프록시가 없으면 자동 PASS를 만들지 않고 `사람 확인 안내`로 분리한다.
- 관찰 창이 sub-second인 상태나 순수 위치·픽셀 판정은 flaky한 `(JOURNEY)`로 강제하지 않고 `사람 확인 안내`로 분리한다.

## UI 증거 확장

`boundary=ui`는 위 project-local 계약에 `ui_evidence.steps`와 아래 [UX 정합성 렌즈](#ux-정합성-렌즈)의 `ux_integrity`를 함께 추가한다. 이 절의 예시는 `ui_evidence` 부분만 떼어 보인 조각이며, `ux_integrity` 없이 실행하면 계약 오류(exit 2)다. 최소 두 단계가 필요하며 `final=true`인 단계들이 `target_ac` 전부를 덮어야 한다. 각 evidence path는 해당 run directory 내부의 상대 경로이고 type은 `screenshot`, `state`, `log` 중 하나다.

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

## UX 정합성 렌즈

요소가 화면에 존재한다는 가시성 assertion만으로는 `boundary=ui`의 REQ를 닫을 수 없다. 요소가 시스템 chrome이나 다른 레이어에 가려 실제로 조작·판독이 불가능해도 "보인다"는 assertion은 그대로 통과하므로, 기능 assertion이 exit 0이어도 사람이 보면 깨진 화면이 제품 outcome PASS가 되는 false-green이 구조적으로 가능하다. 그래서 `boundary=ui` 매니페스트는 `ux_integrity`를 반드시 선언하고, helper가 요소의 실제 bounds를 근거로 겹침·가림을 판정한다. 선언이 없으면 `ui_evidence`와 같은 계약 오류(exit 2)이며, product-acceptance는 이를 실행 불가 gap으로 분리한다.

책임 경계는 기존과 같다. 플랫폼별 화면 hierarchy를 어떤 도구로 dump하는지는 프로젝트 harness가 소유하고, dcNess는 그 결과를 읽어 판정하는 계약과 계약 부재의 gap 판정만 소유한다.

요소 bounds는 한 화면 상태 안에서만 의미가 있으므로 판정 단위는 화면 snapshot이다. 각 snapshot은 `ui_evidence.steps`의 한 단계에 묶이고 자기 layout report를 가진다. 서로 다른 화면의 요소를 한 report에 합치면 남의 화면 요소끼리 가림 판정이 나므로, snapshot끼리 같은 layout report 경로를 공유할 수 없다. 요소가 닫는 AC도 그 단계가 evidence로 내세운 AC 안에서만 고를 수 있고, AC를 실제로 닫는 `final=true` 단계는 자기 snapshot으로 자기 AC를 전부 판정해야 한다. 그렇지 않으면 앞 화면 요소가 뒤 화면의 AC를 대신 닫아, 정작 가려진 최종 화면 판정을 통째로 생략할 수 있다.

```json
{
  "boundary": "ui",
  "target_ac": ["AC-ONBOARD-1", "AC-ONBOARD-2"],
  "ux_integrity": {
    "snapshots": [
      {
        "step_id": "onboarding",
        "layout_report": "onboarding-layout.json",
        "mockup_reference": "docs/design-variants/onboarding.html",
        "elements": [
          {
            "element_id": "permission-banner-cta",
            "target_ac": ["AC-ONBOARD-1"],
            "node_id": "onboarding.permission-cta"
          }
        ]
      },
      {
        "step_id": "result",
        "layout_report": "result-layout.json",
        "elements": [
          {"element_id": "result-confirm-cta", "target_ac": ["AC-ONBOARD-2"]}
        ]
      }
    ]
  }
}
```

| 필드 | 계약 |
|---|---|
| `ux_integrity.snapshots` | 화면 단위 판정 목록. 한 개 이상 필수이며 `final=true`인 각 `ui_evidence` 단계마다 그 단계 자신의 snapshot이 해당 단계의 AC를 전부 판정해야 한다 |
| `ux_integrity.snapshots[].step_id` | 이 snapshot이 판정하는 화면. `ui_evidence.steps`에 선언한 `step_id` 중 하나여야 하고 snapshot 사이에서 유일하다. 그 단계가 evidence로 내세운 AC만 이 snapshot에서 닫을 수 있다 |
| `ux_integrity.snapshots[].layout_report` | journey command가 run directory 안에 생성하는 그 화면의 layout report 상대 경로. snapshot끼리 공유할 수 없다 |
| `ux_integrity.snapshots[].elements` | 그 화면에서 REQ를 닫는 근거가 되는 요소 목록. 한 개 이상 필수 |
| `ux_integrity.snapshots[].elements[].element_id` | layout report의 같은 식별자와 대응하는 요소 id |
| `ux_integrity.snapshots[].elements[].node_id` | 확정 목업의 `data-node-id`. 그 snapshot이 `mockup_reference`를 선언하면 요소마다 필수 |
| `ux_integrity.snapshots[].mockup_reference` | 그 화면의 확정 목업 경로(`docs/design-variants/<screen-id>.html`). 선언하면 receipt에 보존돼 목업 기준 배치 판정의 입력이 된다 |

### layout report 계약

프로젝트 journey command는 `DCNESS_PRODUCT_JOURNEY_RUN_DIR` 아래에 화면마다 다음 형태의 layout report를 생성한다. 좌표계는 viewport 기준 픽셀이며 `safe_area`는 시스템 chrome(status bar, navigation bar, notch 등)이 점유한 inset이다.

```json
{
  "version": 1,
  "viewport": {"width": 1080, "height": 2400},
  "safe_area": {"top": 96, "right": 0, "bottom": 48, "left": 0},
  "elements": [
    {
      "element_id": "permission-banner-cta",
      "bounds": {"x": 40, "y": 400, "width": 1000, "height": 120},
      "z": 0
    },
    {
      "element_id": "modal-scrim",
      "bounds": {"x": 0, "y": 96, "width": 1080, "height": 2256},
      "z": 5
    }
  ]
}
```

`safe_area`의 네 inset과 요소별 `z`는 생략할 수 없고 모든 수치는 유한한 값이어야 한다. 둘 다 판정의 입력 자체이므로, 없는 값을 0으로 가정하거나 `NaN`을 그대로 받아들이면 chrome 침범과 가림이 검출 불가능한 상태가 조용히 PASS로 바뀐다. chrome이 없는 화면은 0을 명시하고, hierarchy dump가 draw order를 제공하지 못하면 그 report로는 판정하지 않는다. 선언하지 않은 요소도 report에 담아야 가림 판정의 상위 레이어로 쓰인다. 같은 `element_id`가 두 번 나오면 어느 요소를 판정할지 모호하므로 report 전체를 무효로 본다.

### 판정 규칙

helper는 snapshot마다 자기 layout report만 읽고, 선언한 요소마다 두 가지를 bounds에서 계산한다.

- **`ux_integrity_chrome_overlap`** — 요소 bounds가 viewport ∩ safe area 안에 완전히 들어가지 않는다. 시스템 chrome 침범과 viewport 밖 잘림을 함께 잡는다.
- **`ux_integrity_occluded`** — 요소 중심점을 같은 화면에서 `z`가 더 큰 요소가 덮는다. 조작·판독의 대표 지점이 상위 레이어에 막힌 상태다. 단, 대상 요소 bounds 안에 완전히 들어가는 요소는 그 요소의 구성 부분(버튼 안의 label·icon 등)으로 보고 가림 후보에서 제외한다. 이 제외가 없으면 자식 노드를 별도로 dump하는 흔한 hierarchy에서 정상 버튼이 전부 실패한다.

layout report가 없거나 비었거나 run directory 밖 symlink면 `ux_integrity_report_missing`, 위 schema로 읽히지 않으면 `ux_integrity_report_invalid`, 선언한 요소가 그 화면 report에 없으면 `ux_integrity_element_missing`이다. 어느 하나라도 발생하면 journey exit이 0이어도 outcome은 FAIL이며, receipt에는 snapshot별로 요소 bounds, `within_safe_area`, `occluded_by`, layout report의 SHA-256이 남는다. 사람 확인으로 미루지 않고 journey 실행 경로에서 판정한다.

receipt에 적힌 판정값은 근거를 대신하지 않는다. scorecard가 receipt를 읽을 때 무엇을 판정해야 했는지는 receipt가 아니라 tracked 매니페스트에서 다시 읽고(`declaration_sha256`로 대조), 그 선언과 해시가 일치하는 layout report로 판정을 다시 계산해 기록값과 대조한다. 그래서 `occluded_by`만 고쳐 쓴 receipt, 뒤 화면 snapshot을 지우고 그 AC를 앞 요소로 옮긴 receipt, 가려진 요소를 같은 report 안의 멀쩡한 다른 요소로 바꿔치기한 receipt가 모두 구조 무효로 버려진다. 매니페스트의 UX 선언을 바꾸면 그 이전 receipt는 다른 계약의 산물이므로 더 이상 집계되지 않는다.

관찰 창이 sub-second인 상태나 픽셀 단위 시각 회귀는 여전히 이 렌즈의 대상이 아니다. 이 렌즈는 스크린샷 diff가 아니라 요소 bounds의 겹침·가림만 판정한다.

### 확정 목업과의 연결

확정 목업이 있는 화면은 impl task의 `디자인 참조` 절이 진본이다. 그 절의 확정 목업 경로와 핵심 `data-node-id` 매핑을 build-worker가 해당 화면 snapshot의 `mockup_reference`와 요소별 `node_id`로 materialize하고, helper가 그대로 receipt에 보존한다. product-acceptance는 이 링크로 목업 기준 배치와 실제 bounds를 같은 요소 단위에서 대조하며, 목업 없이 진행하기로 한 화면은 `mockup_reference`를 생략해 그 사실이 receipt에 드러나게 한다.

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
- UI journey이면 UX 정합성 렌즈의 화면 snapshot별 layout report path·존재 여부·SHA-256, 확정 목업 링크, 요소별 bounds·`within_safe_area`·`occluded_by`.
- 대상 AC의 passed/total denominator, 사람 개입, 실행 증거 종류.
- log별 sha256과 failure reason.

repository operations의 `harness/outcome_scorecard.py`는 helper receipt 중 구조가 유효하고 snapshot cutoff 안에 있는 것만 읽는다. scorecard 구현은 release artifact에 포함되지 않으며 plug-in runtime이 이를 import하지 않는다. journey PASS/전체 실행 수와 제품 AC passed/total을 각각 보존하며 guard·validator·PR 지표를 제품 outcome 분자에 넣지 않는다.

## 배포와 보존

helper와 runtime은 plugin 본체의 `scripts/dcness-product-journey`, `harness/product_journey.py`로 배포된다. 사용자 repo에 helper 사본을 복사하지 않는다. 프로젝트 계약은 opt-in이며 `/init-dcness`가 자동 생성하거나 덮어쓰지 않는다.

계약을 팀과 공유해야 하면 owner module/소스 영역의 매니페스트와 e2e flow를 프로젝트가 명시적으로 관리한다. plugin에 포함된 build-worker가 활성 프로젝트의 해당 영역에 산출물을 만들기 때문에 신규 `/init-dcness` deploy 스텝은 필요 없다. 실행 log와 receipt는 재생성 가능한 실측 evidence이므로 gitignore 대상 `.dcness-work/product-journey/`에 둔다.
