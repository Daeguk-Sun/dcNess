# Story 2 검수 입력 — 장바구니 수량 변경과 프로필 이름 수정

## Story 수용 기준

- AC-201 `(JOURNEY)`: 사용자가 장바구니 화면에서 수량을 바꾸면 합계가 바로 바뀐다.
- AC-202 `(JOURNEY)`: 사용자가 장바구니 화면에서 "결제"를 누르면 결제 화면에 같은 합계가 보인다.
- AC-203 `(JOURNEY)`: 사용자가 프로필 수정 화면에서 이름을 바꾸고 저장하면 설정 화면에 새 이름이 보인다.
- AC-204 `(TEST)`: 수량은 1 미만으로 내려가지 않는다.

## 구현 증거

- 구현 task 3개가 모두 완료됐다.
- AC-204: `./gradlew :cart:test --tests QuantityLowerBoundTest` 가 final tip 에서 exit 0.
- final tip `7c8d9e0` 의 frozen candidate terminal evidence: lint exit 0(warning 0), build exit 0, unit test exit 0. candidate identity 는 `7c8d9e0` 와 일치한다.
- 코드 리뷰는 `7c8d9e0` 에서 PASS 했다.

## `(JOURNEY)` 구성

journey 는 2개이고 매니페스트가 서로 다르다. 두 매니페스트 모두 시나리오 선언이 없다.

| journey_id | 매니페스트 | 대본 | 담당 AC | 지나는 경로 |
|---|---|---|---|---|
| `cart-checkout` | `app/.maestro/cart-checkout-journey.json` | `app/.maestro/cart-checkout.yaml` | AC-201, AC-202 | 앱 실행 → 상품 목록 화면 → 장바구니 화면(`CartScreen`) → 결제 화면 |
| `profile-edit` | `app/.maestro/profile-edit-journey.json` | `app/.maestro/profile-edit.yaml` | AC-203 | 앱 실행 → 설정 화면 → 프로필 수정 화면(`ProfileEditScreen`) → 설정 화면 |

- 두 journey 는 앱 실행 단계 외에 같은 화면, 같은 상태 보관 객체, 같은 저장소를 지나지 않는다. 장바구니 기능은 `cart` 모듈에, 프로필 기능은 `profile` 모듈에 있고 두 모듈은 서로 의존하지 않는다.
- `journey-deferred list` 결과: 빈 목록

## journey 실행 기록 (시간 순, 전부)

1. `cart-checkout` 수렴 실행. receipt `outcome=PASS`, `partial=false`, `code_revision=5a6b7c8`, `uncommitted_changes=false`, `ac_results`: `AC-201=PASS`, `AC-202=PASS`. 소요 약 7분.
2. `profile-edit` 수렴 실행. receipt `outcome=PASS`, `partial=false`, `code_revision=5a6b7c8`, `uncommitted_changes=false`, `ac_results`: `AC-203=PASS`. 소요 약 4분.

이 뒤에 실행된 기록은 없다. 실패한 실행도 없다.

## 직전 통과 이후의 변경분 (`5a6b7c8..7c8d9e0`)

커밋 1개. 코드 리뷰 지적을 반영한 수정이다.

| 파일 | 변경 |
|---|---|
| `cart/src/main/java/com/example/cart/ui/CartScreen.kt` | +41 −18. 수량 증가·감소 버튼의 배치를 바꾸고, 수량이 바뀔 때 합계를 다시 계산하는 호출 위치를 버튼 핸들러에서 상태 보관 객체로 옮겼다. |
| `cart/src/main/java/com/example/cart/ui/CartViewModel.kt` | +22 −9. 합계 재계산 함수를 추가했다. |
| `cart/src/test/java/com/example/cart/ui/CartViewModelTest.kt` | +30 −0. 합계 재계산 단위 테스트를 추가했다. |

- `profile` 모듈, 앱 실행 진입점, 빌드 설정, 의존성 선언, `app/.maestro/` 아래 파일은 바뀌지 않았다.
- final tip 작업 트리에 커밋되지 않은 변경은 없다.
