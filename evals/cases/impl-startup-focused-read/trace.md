# Implementation startup trace

외부 활성 프로젝트의 `/impl` 실행 기록을 구조만 남겨 옮겼다. 각 상황은 독립된 run이다. 모든 run에서 제품 의미는 하나이고 새 권한은 필요 없다.

## A. exact pointer가 있는 main-direct 작업

issue 본문이 수정 대상 `app/src/main/java/com/example/send/SendQueue.kt`와 기존 테스트 `app/src/test/java/com/example/send/SendQueueTest.kt`를 정확히 적었다. 메인은 main-direct를 고르고 worktree에 진입했다.

그 뒤 첫 edit 전까지 메인은 다음 순서로 실행했다.

1. `grep -rn SendQueue app/src/main`
2. `grep -rn SendQueue app/src/test`
3. `sed -n 1,80p .../SendQueue.kt`
4. `sed -n 80,200p .../SendQueue.kt`
5. `grep -rn "retry" app/src/main/java/com/example/send`
6. `cat .../SendRetryPolicy.kt`
7. `sed -n 1,120p .../SendQueueTest.kt`
8. `grep -rn "FakeClock" app/src/test`
9. Read `.../SendQueue.kt`
10. Read `.../SendQueueTest.kt`

worktree 진입부터 첫 RED test edit까지 140초가 걸렸다.

## B. RED 전 이름 규칙 확인

다른 run에서 메인은 worktree 진입 직후, 첫 테스트를 쓰기 전에 브랜치·커밋 이름 규칙 검사 스크립트를 실행하고 이름 규칙 문서를 읽었다. 이 저장소는 commit 시점에 같은 이름 규칙을 검사하는 git hook이 설치돼 있다.

## C. headless 작업의 worker prompt

여러 계층과 migration을 함께 바꾸는 작업이라 메인은 headless를 골랐다. worktree 진입 뒤 메인은 206줄짜리 worker prompt 파일을 작성했고, 작성에만 85초가 걸렸다. prompt에는 다음 내용이 들어 있었다.

- 대상 issue와 목표 한 단락
- 사용자가 확정한 설계 결정 4개
- issue의 acceptance criteria 원문
- 수정할 exact pointer와 수정 허용 경로
- 검증 명령
- worker 작업 절차 재서술: 실패 테스트 먼저 작성, phase별 보고, 커밋 분할 판정 방법
- 메인이 고른 권장 클래스 설계와 함수 signature 초안
- 저장소에 이미 있는 `docs/design.md`의 색·spacing 토큰 표 전체 복사

이 프로젝트의 지침 파일은 worktree에 있고, 이번 run의 worker provider는 그 파일을 자동으로 읽는다.

## D. 지침 파일을 읽지 못하는 worker

다른 headless run에서 프로젝트 지침 파일은 git에서 제외된 로컬 전용 파일이다. 이번 worker provider는 그 파일을 자동으로 읽지 않는다. 메인은 worker prompt에 대상, 확정 결정, acceptance criteria, exact pointer, 검증 명령과 함께 "다른 계정용 GitHub token 사용 규칙"과 "클라이언트 repo에 커밋하면 안 되는 경로 목록" 두 가지 프로젝트 규칙을 다섯 줄로 요약했다. 작성에는 20초가 걸렸다.
