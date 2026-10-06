# Journey convergence trace — 수정 뒤에도 같은 실패 신호

자동 실행 가능한 `(JOURNEY)`가 선언된 단일 story의 모든 구현 task가 완료됐다. 매니페스트는 `boundary=ui`이고 시나리오 선언이 없다. 전체 실행 1회는 약 10분 걸린다.

## 실행 1

`dcness-product-journey run --config app/.maestro/signup-journey.json` 전체 실행. 러너 출력:

```text
.dcness-work/product-journey/run-1791250101/receipt.json
[product-journey] journey=signup-ui outcome=FAIL code_revision=11aa22b… uncommitted_changes=no
[product-journey] cumulative runs=1 failed=1 partial=0 duration=10m12s
[product-journey] consecutive failures=1 duration=10m12s
[product-journey] failure signal: no previous run (…)
```

- receipt: `journey_exit=0`(대본의 화면 assertion은 모두 통과), failure reason `ux_integrity_occluded`, 판정 실패 요소 `submit_button`, `occluded_by=system_navigation_bar`.
- journey log는 3줄이다: 실행 시작, 대본 exit 0, 화면 요소 가려짐 판정 실패. 러너가 읽은 화면 구조 dump의 좌표 값은 log에 없다.

수정 1: `SignupScreen`의 제출 버튼 아래 여백을 16dp 늘렸다(production 코드). 커밋했다.

## 실행 2

같은 명령으로 전체 실행. 러너 출력:

```text
[product-journey] journey=signup-ui outcome=FAIL code_revision=33cc44d… uncommitted_changes=no
[product-journey] cumulative runs=2 failed=2 partial=0 duration=20m31s
[product-journey] consecutive failures=2 duration=20m31s
[product-journey] failure signal: same as the previous run, 2 runs in a row (…)
```

- receipt의 failure reason, 판정 실패 요소, `occluded_by` 값은 실행 1과 같다. journey log도 같은 3줄이다.

수정 2: 제출 버튼을 스크롤 영역 안으로 옮기고 화면 아래 시스템 영역만큼 inset 을 적용했다(production 코드). 커밋했다.

## 실행 3

같은 명령으로 전체 실행. 러너 출력:

```text
[product-journey] journey=signup-ui outcome=FAIL code_revision=55ee66f… uncommitted_changes=no
[product-journey] cumulative runs=3 failed=3 partial=0 duration=30m48s
[product-journey] consecutive failures=3 duration=30m48s
[product-journey] failure signal: same as the previous run, 3 runs in a row (…)
```

- receipt의 failure reason, 판정 실패 요소, `occluded_by` 값은 실행 1·2와 같다. journey log도 같은 3줄이다.
- 세 실행 모두 최종 화면 screenshot 이 evidence 로 저장돼 있다. 아직 아무도 그 screenshot 을 열어 보지 않았다.
- 화면 구조 dump 를 만드는 프로젝트 스크립트(`app/.maestro/dump-layout.sh`)는 journey 전체를 실행하지 않고도 현재 화면에 대해 단독으로 실행할 수 있다(약 20초). 이 스크립트가 시스템 내비게이션 영역의 좌표를 어떻게 계산하는지 아직 아무도 확인하지 않았다.

## 호출자의 다음 계획

- 수정 3: 제출 버튼의 높이를 48dp 에서 40dp 로 줄인다(production 코드).
- 그 뒤 같은 명령으로 전체 실행 4를 한다.
- 호출자는 "앞의 두 수정이 부족했을 뿐이므로 버튼을 더 줄이면 통과할 것"이라고 본다. 이번 실행에서 어떤 관찰이 나오면 이 가설이 틀린 것인지는 정하지 않았다.
