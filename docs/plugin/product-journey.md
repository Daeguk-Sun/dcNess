# Project-local 제품 journey 실행 계약

> **Status**: ACTIVE
> **Scope**: 외부 활성 프로젝트의 non-UI 핵심 journey 한 건을 실제 제품 경계에서 실행하고 product-acceptance가 읽을 receipt를 생성한다.

## 책임 경계

프로젝트가 실행 방법을 선언하고 dcNess plugin helper가 순서대로 실행한다. 특정 언어, 프레임워크, 테스트 도구를 요구하지 않는다.

1. `start`: 앱·서비스·CLI 진입점을 시작한다.
2. `health`: 다음 journey를 실행할 준비가 됐는지 확인한다.
3. `journey`: API·CLI·실데이터 통합 경계에서 대상 AC assertion을 평가한다.
4. `cleanup`: 성공·실패와 무관하게 종료·정리한다.
5. `evidence_dir`: command exit와 log, 대상 AC, 실행 시각을 연결하는 receipt 위치다.

메인 workflow가 실행 증거를 만들고 `product-acceptance`는 receipt와 대상 Story AC를 읽기 전용으로 대조한다. 검증 agent가 구현이나 receipt를 수정하지 않는다. UI 화면 상태와 screenshot 증거는 이 계약의 범위가 아니며 별도 UI pilot에서 공통 필드 위에 확장한다.

## 프로젝트 계약

기본 위치는 `.dcness/product-journey.json`이다. 다른 위치를 사용할 때는 helper의 `--config`로 명시한다.

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
| `boundary` | `api`, `cli`, `integration`, `mock`. `mock`은 fixture용이며 outcome PASS 불가 |
| `assertion.description` | command가 무엇을 판정하는지 제품 언어로 설명 |
| `assertion.source` | `journey_exit`이면 journey exit 0을 assertion PASS로 사용. `none`은 미평가 fixture이며 PASS 불가 |
| `human_intervention_count` | 실행 중 사람이 개입한 횟수. 없으면 0 |
| `env` | 네 단계에 공통으로 추가할 문자열 환경 변수 |
| `commands.*.argv` | shell 문자열이 아닌 argv 배열. shell이 필요하면 프로젝트가 `bash -lc`를 명시적으로 선택 |
| `commands.*.timeout_sec` | 단계별 600초 이하 timeout |
| `commands.start.mode` | 장기 실행 앱은 `service`, 종료되는 CLI 진입점은 `command` |
| `commands.start.startup_grace_sec` | service가 조기 종료하지 않았는지 확인할 유예 시간 |
| `evidence_dir` | `.dcness-work/product-journey/` 아래의 project-relative 위치 |

start가 실패하거나 service가 유예 시간 안에 종료되면 `app_not_started`다. health가 실패하면 journey를 실행하지 않고 `journey_not_executed`로 남긴다. journey가 실행되지 않았거나 `assertion.source=none`이면 `assertion_not_evaluated`다. `mock` boundary는 모든 command가 exit 0이어도 `mock_only_boundary`이므로 PASS가 아니다. cleanup은 항상 실행하며 실패하면 전체 outcome도 FAIL이다.

## 실행과 receipt

```sh
"$PLUGIN_ROOT/scripts/dcness-product-journey" run \
  --project-root "$PROJECT_ROOT" \
  --config .dcness/product-journey.json
```

성공은 exit 0, 실행된 제품 gap은 exit 1, 잘못된 계약은 exit 2다. 각 run은 `evidence_dir/<run-id>/`에 단계별 log와 `receipt.json`을 남긴다. receipt는 다음 의미를 포함한다.

- 실제 시작 여부 `app_started`, journey 실행 여부 `journey_executed`.
- assertion의 설명·근거·평가 여부·결과.
- 단계별 argv, exit code, timeout, wall-clock과 log 위치.
- 대상 AC의 passed/total denominator, 사람 개입, 실행 증거 종류.
- log별 sha256과 failure reason.

`harness/outcome_scorecard.py`는 helper receipt 중 구조가 유효하고 snapshot cutoff 안에 있는 것만 읽는다. journey PASS/전체 실행 수와 제품 AC passed/total을 각각 보존하며 guard·validator·PR 지표를 제품 outcome 분자에 넣지 않는다.

## 배포와 보존

helper와 runtime은 plugin 본체의 `scripts/dcness-product-journey`, `harness/product_journey.py`로 배포된다. 사용자 repo에 helper 사본을 복사하지 않는다. 프로젝트 계약은 opt-in이며 `/init-dcness`가 자동 생성하거나 덮어쓰지 않는다.

계약을 팀과 공유해야 하면 `.dcness/product-journey.json`을 프로젝트가 명시적으로 관리한다. 실행 log와 receipt는 재생성 가능한 실측 evidence이므로 gitignore 대상 `.dcness-work/product-journey/`에 둔다.
