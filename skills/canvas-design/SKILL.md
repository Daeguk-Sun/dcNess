---
name: canvas-design
description: 내부 UI 기준 확보 wrapper. draft 후보 생성, 사용자 PICK, 확정본 승격, 보드·진입점 재생성을 한 경로로 수행한다. 공개 진입점이 아니며 /ux, /impl, /impl-loop 내부에서 호출된다.
---

# canvas-design

> 공개 진입점이 아니다. 외부 workflow는 `/spec → /design → /impl → /acceptance`를 유지한다.

## 목적

UI 기준을 `docs/design-variants/`에 남긴다. 사람은 후보를 PICK하고 생성 결과를 검수한다. 화면·전이·여정의 값과 보드 배치는 agent 산출물과 생성기가 소유한다.

산출물 계약의 진본은 [`docs/plugin/design-variants.md`](../../docs/plugin/design-variants.md)다. 이 스킬은 계약을 반복하지 않고 실행 순서와 권한만 소유한다.

## 입력

- 대상 화면 ID와 관련 ux-flow
- 기준 소스: `existing-confirmed` / `user-provided` / `new-draft` / `skip`
- 관련 issue·impl task·design.md

## 실행

1. `templates/design-variants/` seed가 없을 때만 복사한다. 기존 파일은 보존하고, 엔진 차이는 경고한다.
2. 기존 확정본·사용자 기준·신규 draft·skip 중 경로를 정한다.
3. draft가 필요하면 foreground designer를 호출한다. designer는 `drafts/`에 확정본과 같은 형식의 후보만 만든다.
4. 후보를 사용자에게 제시해 PICK을 받는다. NG면 다시 만들고, OK면 선택본을 같은 이름의 `screens/<screen-id>.html`로 이동한다.
5. 같은 화면의 탈락 후보만 제거한다. 다른 화면 후보는 보존한다.
6. plugin 소유 생성기 3종을 실행해 저니 보드, 변형 전수 보드, 두 진입점을 갱신한다. 이어서 세 생성기의 `--check`를 모두 통과시킨다.
7. 확정본 경로, 보드 경로, 핵심 node-id, 의도적 차이를 호출자에게 반환한다.

사용자 PICK 대기 중에는 결론을 내리지 않는다.

## 결론

- `PASS` — 필요한 PICK·승격·재생성·검사가 끝났다.
- `ESCALATE` — 기준 충돌, seed 실패, 화면 ID 충돌, 사용자 중단처럼 임의 진행할 수 없다.

마지막 단락에 결론 enum 하나를 명시한다.

## 권한

- designer: `docs/design-variants/drafts/`만 write
- 메인: PICK, 순수 이동, 후보 정리, 생성기 실행
- 생성기: 보드·두 진입점 전량과 프로젝트 포인터 한 줄 소유
- 프로젝트: `_lib/` 수정 금지

`canvas-design`은 helper begin/end-step 비대상 main-owned checkpoint다. designer Agent의 spawn/완료만 SubagentStart/PostToolUse lifecycle hook이 기록한다.

## 호출자

`/ux`, `/impl`, `/impl-loop`는 승격 절차를 복제하지 않고 이 스킬을 호출한다. `design: required` impl task에는 반환된 확정본과 node-id 매핑을 기록한다.
