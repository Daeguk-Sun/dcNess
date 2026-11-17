# Story 2 마감 — 통화 기록 목록 화면

외부 활성 프로젝트는 개인 개발자가 만드는 Android 전화 앱이다. Story 2 의 모든 task 구현이 끝나 `/impl-loop` 마감 시퀀스에 들어왔다. 메인이 product-acceptance 에 넘긴 입력은 아래와 같다.

## Story AC

- AC-2-1: 통화 기록 탭을 열면 통화 기록이 날짜별로 묶여 최근 순으로 보인다.
- AC-2-2: 각 행은 상대(이름 또는 번호), 통화 종류와 통화 시간, 시각을 보여준다.
- AC-2-3: 통화 종류(발신 연결, 발신 미연결, 수신, 부재중, 거절)는 확정 목업의 표시 규칙을 따른다.

## 확정 목업

- `mockup-call-log.html` — 이 Story 의 확정 목업. 프레임 5개(발신 연결, 발신 미연결, 수신, 부재중, 주소록에 없는 번호)

## 구현 화면 증거

- `screen-call-log.png` — Android 에뮬레이터(360dp 폭)에서 앱을 실행해 통화 기록 탭을 연 화면의 스크린샷
- journey receipt 요약: `app_started=true`, `journey_executed=true`, assertion 3개 모두 `evaluated=true`·`passed=true`, `ux_integrity` 모든 요소 `within_safe_area=true`·`occluded_by=[]`, outcome PASS

## 검수 시드

- `seed.md` — journey 실행 전에 에뮬레이터 통화 기록 DB 에 넣은 테스트 데이터

## 사용자 결정

- 2026-11-12: 하위 탭(전체/부재중)은 목업의 왼쪽 정렬 짧은 탭 대신 화면 폭을 반씩 나누는 배치로 간다. 사용자가 구현 화면을 보고 직접 승인함.

## 기타 증거

- lint·build·unit test 모두 통과 (same-tree terminal evidence, frozen candidate identity 일치)
- build-worker 자체 보고: "목업과 레이아웃 계층·node-id 모두 일치, 구조 정합 확인"
