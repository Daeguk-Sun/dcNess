> 룰 SSOT: [`docs/plugin/git-spec.md` PR 본문](../docs/plugin/git-spec.md#pr-본문) (외부 활성 프로젝트 공통).
> 본 template = dcness self 전용 — `## 배포 경로 검증` 섹션이 dcness self 작업용으로 추가됨 ([`CLAUDE.md` 추가한 기능은 반드시 배포 경로에도 포함](../CLAUDE.md#추가한-기능은-반드시-배포-경로에도-포함)).

## 관련 이슈 번호

<!-- 트레일러 룰 (git-spec 의 PR 트레일러 기본 룰):
     - 단일 story → Closes #story (epic 마지막이면 Closes #epic 동봉)
     - story branch stack PR → 생성 시 직전 story branch base, merge 시 main 리타겟 후 Closes #story
     - QA PR → tracked 보정이 있으면 Part of #epic, epic close를 발동하면 Closes #epic
     - issue 없는 infra/follow-up → Document-Exception-PR-Close: <사유> -->
Part of #N

## 배경 및 문제

<!-- WHY: 왜 이 PR 이 필요한가. 가능하면 히스토리 포함 -->
-

## 원인 (해당 시)

<!-- 버그픽스 / RCA 케이스만 작성. 단순 feature 추가는 생략 또는 `-` -->
-

## 작업내용

<!-- WHAT: 하위 commit 들 제목·내용 종합 -->
-

## 결정 근거

<!-- 검토한 대안, 채택 이유. 단순 변경이면 `-` -->
-

## 배포 경로 검증 (plug-in 영향 시)

<!-- dcness self 룰 (CLAUDE.md 의 배포 경로 검증). agents/** / commands/** / hooks/** / init-dcness 복사 파일 / docs/plugin SSOT 변경 시 의무.
     해당 없음 시 "N/A — dcness self 운영 작업" -->
-

## 신규 surface justification (새 public skill/command/agent/gate 추가 시만)

<!-- 운영 원칙: 사용자-facing surface 는 작게 유지가 기본 (positioning.md 신규 surface justification + CLAUDE.md 안티패턴 5).
     새 public 발화를 늘리는 PR 에서만 작성. surface 변화 없으면 "N/A".
     세 질문에 답: (1) 기존 risk router lane 으로 흡수 안 되나? (2) 기존 validator/reviewer 로 검증 안 되나? (3) 기존 agent 내부 단계로 못 두고 새 public 발화가 꼭 필요한가? -->
-

## Test Plan

<!-- 하위 commit Test Plan 종합. 머지 직전 메인이 종합 갱신 -->
- [ ] 관련 테스트 추가/갱신/전체 통과
- [ ] 회귀 검증

## 참고

-
