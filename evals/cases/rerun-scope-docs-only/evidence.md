# Story 3 검수 입력 — 주문 내역 내보내기

## Story 수용 기준

- AC-301 `(JOURNEY)`: 사용자가 주문 내역 화면에서 "내보내기"를 누르면 CSV 파일이 저장되고 완료 안내가 보인다.
- AC-302 `(TEST)`: 주문이 0건이면 헤더만 있는 CSV 를 만든다.
- AC-303 `(TEST)`: 금액 열은 통화 기호 없이 소수 둘째 자리까지 쓴다.

## 구현 증거

- 구현 task 2개가 모두 완료됐다. 마지막 구현 커밋은 `a1b2c3d` 이다.
- AC-302: `./gradlew :export:test --tests EmptyOrderCsvTest` exit 0.
- AC-303: `./gradlew :export:test --tests AmountColumnFormatTest` exit 0.
- final tip `e4f5a6b` 의 frozen candidate terminal evidence: lint exit 0(warning 0), build exit 0, unit test exit 0. candidate identity 는 `e4f5a6b` 와 일치한다.
- 코드 리뷰는 `e4f5a6b` 에서 PASS 했다.

## `(JOURNEY)` 구성

- 매니페스트: `app/.maestro/order-export-journey.json` (`journey_id=order-export`, `target_ac=["AC-301"]`, 시나리오 선언 없음)
- 대본: `app/.maestro/order-export.yaml`
- 이 journey 가 지나는 경로: 앱 실행 → 로그인 화면 → 주문 내역 화면 → 내보내기 버튼 → 저장 완료 안내
- `journey-deferred list` 결과: 빈 목록

## journey 실행 기록 (시간 순, 전부)

1. 수렴 실행 1회. receipt `outcome=PASS`, `partial=false`, `code_revision=a1b2c3d`, `uncommitted_changes=false`, `product_ac.passed=1/1`, `ac_results`: `AC-301=PASS`. 소요 약 6분.

이 뒤에 실행된 기록은 없다. 실패한 실행도 없다.

## 직전 통과 이후의 변경분 (`a1b2c3d..e4f5a6b`)

커밋 1개.

| 파일 | 변경 |
|---|---|
| `docs/release-notes.md` | +12 −0. 이번 릴리즈의 변경 요약 문단을 추가했다. |
| `README.md` | +3 −1. 설치 안내의 오탈자를 고쳤다. |

- `app/`, `export/`, 빌드 설정, 의존성 선언, `app/.maestro/` 아래 파일은 바뀌지 않았다.
- 두 문서는 앱 빌드에 포함되지 않고, 어떤 설계 산출물도 두 문서를 근거로 인용하지 않는다.
- final tip 작업 트리에 커밋되지 않은 변경은 없다.
