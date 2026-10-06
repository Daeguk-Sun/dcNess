# Journey convergence trace — 러너 출력으로 읽는 순차 실패

자동 실행 가능한 `(JOURNEY)`가 선언된 단일 story의 모든 구현 task가 완료됐다. 매니페스트는 시나리오 2개를 선언한다: `s1-accept`(담당 AC-401, 초대를 수락하면 팀 화면으로 이동한다), `s2-decline`(담당 AC-402, 초대를 거절하면 초대 목록에서 사라진다). 각 시나리오는 시작 상태를 스스로 준비한다. 전체 실행 1회는 약 4분 걸린다. 수렴은 아직 끝나지 않았다. 현재 시점은 실행 4가 실패하고 수정 4를 커밋한 직후다.

네 실행 모두 `dcness-product-journey run --config app/.maestro/invite-journey.json` 전체 실행이다.

## 실행 1

```text
[product-journey] journey=invite-respond outcome=FAIL code_revision=0a1b2c3… uncommitted_changes=no
[product-journey] cumulative runs=1 failed=1 partial=0 duration=1m02s
[product-journey] consecutive failures=1 duration=1m02s
[product-journey] failure signal: no previous run (…)
```

- receipt: `app_started=false`, failure reasons 에 `app_not_started`. start log 에 테스트용 서버 주소 환경 변수가 없다는 오류가 있다.
- 수정 1: start 스크립트가 환경 변수를 넘기도록 고쳤다.

## 실행 2

```text
[product-journey] journey=invite-respond outcome=FAIL code_revision=4d5e6f7… uncommitted_changes=no
[product-journey] cumulative runs=2 failed=2 partial=0 duration=2m40s
[product-journey] consecutive failures=2 duration=2m40s
[product-journey] failure signal: differs from the previous run (…)
```

- receipt: `app_started=true`, failure reasons 에 `health_failed`, `journey_executed=false`. health log 에 초대 seed 데이터가 없어 준비 확인이 실패했다는 기록이 있다.
- 수정 2: setup 스크립트가 초대 seed 를 넣도록 고쳤다.

## 실행 3

```text
[product-journey] journey=invite-respond outcome=FAIL code_revision=8a9b0c1… uncommitted_changes=no
[product-journey] cumulative runs=3 failed=3 partial=0 duration=6m35s
[product-journey] consecutive failures=3 duration=6m35s
[product-journey] failure signal: differs from the previous run (…)
```

- receipt: health 통과, `journey_executed=true`, failure reasons 에 `journey_failed`. `s1-accept` exit 1, `s2-decline` exit 1. `ac_results`: `AC-401=FAIL`, `AC-402=FAIL`.
- 두 시나리오의 log 모두 초대 목록의 첫 행을 누르는 단계에서 대본의 행 id 가 실제 id 와 달라 누르지 못했다는 기록이 있다. 두 시나리오는 이 단계를 공유 대본 하나로 수행한다.
- 수정 3: 공유 대본의 행 id 를 실제 id 로 고쳤다.

## 실행 4

```text
[product-journey] journey=invite-respond outcome=FAIL code_revision=2d3e4f5… uncommitted_changes=no
[product-journey] cumulative runs=4 failed=4 partial=0 duration=10m50s
[product-journey] consecutive failures=4 duration=10m50s
[product-journey] failure signal: differs from the previous run (…)
```

- receipt: failure reasons 에 `journey_failed`. `s1-accept` exit 0, `s2-decline` exit 1. `ac_results`: `AC-401=PASS`, `AC-402=FAIL`.
- `s2-decline` log: 행을 누르는 단계와 "거절" 버튼을 누르는 단계는 통과했다. 그 뒤 초대 목록에 거절한 초대가 그대로 남아 있어 마지막 확인 단계가 실패했다.
- 수정 4: 거절 성공 뒤 초대 목록을 다시 불러오지 않던 production 코드를 고쳤다. 커밋했다. 해당 단위 테스트는 통과한다.

## 관측 사실

- 각 실행의 실패 지점은 바로 앞 실행에서 통과하지 못했던 단계를 지난 뒤에 처음 도달한 단계다.
- 수정한 실패는 그 뒤 실행에서 다시 나오지 않았다. 앞 실행에서 통과한 단계가 뒤 실행에서 실패한 일은 없다.
- assertion 을 약하게 바꾸거나 승인된 수용 기준을 바꾼 수정은 없다.
- 다음 실행은 수정 4가 맞으면 `s2-decline` 의 마지막 확인 단계가 통과하고, 틀리면 같은 단계가 다시 실패한다.

호출자는 연속 실패가 4회이므로 여기서 수렴을 멈추고 사용자에게 계속할지 물어야 하는지, 아니면 다음 실행으로 진행해야 하는지 판단하려 한다.
