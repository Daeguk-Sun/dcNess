# Spec Delivery Reference

`/spec` 산출물을 PR 로 머지하고, 필요 시 issue 를 등록한 뒤 `/design` 을 권고할 때 쓰는 참고 자료다. 실행 순서는 [`SKILL.md`](SKILL.md), 분기는 [`spec-routing.md`](spec-routing.md) 가 진본이다.

## branch + PR

```bash
git checkout -b docs/<slug> main
git add docs/prd.md docs/index.md docs/epics/epic-NN-<slug>/stories.md
# preflight 를 실행했다면: git add docs/tech-review.md
git commit -m "[docs] PRD 신규 / 변경 요약"
git push -u origin docs/<slug>
gh pr create --base main --title "..." --body "..."
bash "$PLUGIN_ROOT/scripts/pr-finalize.sh" <PR_NUMBER>
```

PRD/stories.md delivery branch는 항상 `main`에서 만든다. 후속 다중 story 구현의 branch stack은 `/impl-loop`가 별도로 구성하며 spec 산출물에 base marker를 남기지 않는다.

## 이슈 등록

PR 머지 완료 후 사용자가 Y 를 선택하면 메인이 자동화 스크립트를 호출한다.

이슈 생성 전에 Issue Brief 본문과 IssueType label 을 검증한다. 선택적 Project 좌표 해석, field/option bootstrap, 등록 skip/backfill 정책은 [`docs/plugin/issue-lifecycle.md#issuelabel-status-lifecycle`](../../docs/plugin/issue-lifecycle.md#issuelabel-status-lifecycle) 를 따른다. 어떤 경우에도 Project 상태는 이슈 생성을 막지 않는다.

```bash
bash "$PLUGIN_ROOT/scripts/create_epic_story_issues.sh" docs/epics/epic-NN-<slug>/stories.md --project <number> --owner <owner>
```

스크립트 동작:

1. stories.md parse — epic + Story N 추출
2. milestone number 조회
3. epic issue 생성 → stories.md 에 번호 기록
4. story issue N개 생성 → stories.md 에 번호와 하단 표 기록
5. sub-issue API 호출
6. 선택적 GitHub Project backfill — epic(`Status=Todo`, `IssueType=epic`, `Priority=major`) / story(`Status=Todo`, `IssueType=story`, `Priority=major`). 좌표·backfill 정책은 [`docs/plugin/issue-lifecycle.md#issuelabel-status-lifecycle`](../../docs/plugin/issue-lifecycle.md#issuelabel-status-lifecycle) 포인터를 따른다
7. 결과 prose 출력

스크립트 실패 시 메인이 사용자에게 보고하고 [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#sub-issue-연결-epic-story-gh-api-메커니즘)에 따라 수동 처리한다. 보드 등록이 partial 이면 어떤 issue 가 미반영인지 보고하고 보드/field 셋업 후 재실행으로 backfill 한다. 이슈 등록 후 stories.md 변경분은 별도 commit + PR 또는 사용자 자율이다.
