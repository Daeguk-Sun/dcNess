# Spec Delivery Reference

`/spec` 산출물을 PR 로 머지하고, 필요 시 issue 를 등록한 뒤 `/design` 을 권고할 때 쓰는 참고 자료다. 실행 순서는 [`SKILL.md`](SKILL.md), 분기는 [`spec-routing.md`](spec-routing.md) 가 진본이다.

## 일반 branch + PR

```bash
git checkout -b docs/<slug> main
git add docs/prd.md docs/epics/epic-NN-<slug>/stories.md
# preflight 를 실행했다면: git add docs/tech-review.md
git commit -m "[docs] PRD 신규 / 변경 요약"
git push -u origin docs/<slug>
gh pr create --base main --title "..." --body "..."
bash "$PLUGIN_ROOT/scripts/pr-finalize.sh" <PR_NUMBER>
```

## 통합 브랜치 branch + PR

```bash
git checkout -b feature/<slug> main
git push -u origin feature/<slug>
git checkout -b docs/<slug>_prd feature/<slug>
git add docs/prd.md docs/epics/epic-NN-<slug>/stories.md
# preflight 를 실행했다면: git add docs/tech-review.md
git commit -m "[docs] PRD 신규 / 변경 요약"
git push -u origin docs/<slug>_prd
gh pr create --base feature/<slug> --title "[docs] ..." \
  --body "... \nDocument-Exception-PR-Close: PRD/stories.md 머지 — 이슈 없음"
bash "$PLUGIN_ROOT/scripts/pr-finalize.sh" <PR_NUMBER>
```

`Document-Exception-PR-Close` 마커는 PRD sub-PR 이 이슈 등록 전 단계라 별도 추적 이슈를 만들지 않기 위한 예외다.

## 이슈 등록

PR 머지 완료 후 사용자가 Y 를 선택하면 메인이 자동화 스크립트를 호출한다.

이슈 생성 전에 보드(Project) 상태를 점검한다. 좌표(owner/number)는 `gh variable get DCNESS_PROJECT_NUMBER` 로 조회하거나 `--project`/`--owner` 로 넘긴다. 보드나 field/option 이 없거나 불완전하면 사용자에게 "지금 보드를 만들/채울까요?" 를 물어보고, 동의하면 `github_project_lifecycle.mjs bootstrap --apply` (보드 자체가 없으면 `gh project create` + `gh project link` 를 먼저) 로 셋업한 뒤 좌표를 `gh variable set` 으로 저장한다. 거부하면 보드 없이 진행한다. 어떤 경우에도 이슈 생성은 막지 않는다.

```bash
bash "$PLUGIN_ROOT/scripts/create_epic_story_issues.sh" docs/epics/epic-NN-<slug>/stories.md --project <number> --owner <owner>
```

스크립트 동작:

1. stories.md parse — epic + Story N 추출
2. milestone number 조회
3. epic issue 생성 → stories.md 에 번호 기록
4. story issue N개 생성 → stories.md 에 번호와 하단 표 기록
5. sub-issue API 호출
6. GitHub Project 보드 등록 — epic(`Status=Todo`, `IssueType=epic`, `Priority=major`) / story(`Status=Todo`, `IssueType=story`, `Priority=major`). 좌표 없으면 등록 skip + 경고(이슈는 생성됨). 멱등 재실행 시 이슈 생성은 skip 하고 보드 등록만 backfill
7. 결과 prose 출력

스크립트 실패 시 메인이 사용자에게 보고하고 [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#sub-issue-연결-epic-story-gh-api-메커니즘)에 따라 수동 처리한다. 보드 등록이 partial 이면 어떤 issue 가 미반영인지 보고하고 보드/field 셋업 후 재실행으로 backfill 한다. 이슈 등록 후 stories.md 변경분은 별도 commit + PR 또는 사용자 자율이다.
