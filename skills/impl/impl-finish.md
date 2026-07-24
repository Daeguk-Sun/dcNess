# `/impl` GREEN 이후 마감

이 문서는 관련 lint/build/test/typecheck/compile이 GREEN이 된 뒤에만 읽는다. 구현 착수 전에 읽는 preflight가 아니다.

## 완료 증거

- 테스트 가능한 변경은 RED→GREEN 실행 기록을 남긴다. docs-only·단순 설정은 TDD skip 사유를 남긴다.
- 핵심 AC는 성격에 맞는 compile, 통합테스트, API/CLI smoke, 실제 앱 진입점 또는 UI 증거로 확인한다. mock-only green만으로 닫지 않는다.
- 변경 파일이 scope와 hard boundary 안인지 확인한다.
- runtime entrypoint, capability/state owner, dependency edge, public surface, 상태 before/after, 관련 epic/decision 변화 여부를 Cartography impact 자유 prose로 정리한다. 영향이 없으면 대조한 Root 좌표와 함께 `영향 없음`을 적는다.
- 대상 GitHub issue가 있으면 진입 때 보관한 typed AC snapshot을 구현·명령·agent-read 증거와 대응시킨다.

## Cartography freshness와 candidate freeze

GREEN 뒤 final mutation owner인 메인 오케스트레이터가 merge candidate diff, Cartography impact, affected Root Cartography, 관련 epic/decision을 먼저 대조한다.

- 영향 없음 또는 Root와 일치: no-op을 기록한다.
- system boundary는 유지되지만 route/state/as-built edge가 stale: final mutation owner가 affected Root만 한 번 bounded sync한다. tracked 문서면 같은 branch에 commit한다.
- system boundary/global decision 변경: route-only patch로 흡수하지 않고 `/design --revise` 또는 system checkpoint를 사용자에게 제시한다.

읽기 전용 validator와 headless build worker는 Cartography 문서를 직접 수정하지 않는다. 별도 module-architect 회귀 없이 final mutation owner가 정상 마감 sync를 소유한다. local-only/ignored Root는 code PR에 강제 포함하지 않되 canonical local Root를 갱신한다. durable impact handoff만으로 freshness가 해소되지는 않는다.

Cartography sync/no-op과 의미 단위 commit이 끝나고 tracked tree가 clean할 때 HEAD와 `HEAD^{tree}`를 candidate identity로 freeze한다.

## 격리 holistic `impl-validator`

1. 검토 대상이 commit이면 commit id와 변경 파일 목록을 전달한다. uncommitted diff일 때만 diff 파일을 사용한다.
2. [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md)를 이 호출 직전에 읽는다.
3. prompt에는 target/읽을 진본, review 대상, Cartography impact, affected Root 좌표, 관련 epic/decision, 진본에 없는 현재 finding만 넣는다. 구현 방법을 처방하거나 과거 대화 전체를 넣지 않는다.
4. terminal receipt의 실제 구현 provider로 `dcness-helper routing resolve impl-validator --actual-implementation-provider <provider> --explain`을 한 번 호출한다. Codex면 `dcness-codex-validator impl-validator`, 그 밖에는 mode 없는 foreground `impl-validator`를 사용한다.
5. validator는 read-only다. 수정은 최초에 선택한 구현 owner가 한다. headless owner라면 새 slim rework prompt로 implementation chain에 `--direct-run --rework --resume-provider <actual-provider>`를 주어 동일 provider·동일 workspace에서 고친다.

validator는 base부터 frozen tip까지 전체 diff를 한 번에 보는 holistic reviewer다. fixed task/commit fan-out을 만들지 않고 실제 unresolved high-risk 또는 넓은 context가 있을 때만 같은 reviewer가 selective extra investigation을 한다.

MUST FIX가 있으면 최대 3회 root-cause 수정 루프를 돈다. 같은 계열 결함과 삭제된 로직의 잔여 호출·문서·테스트도 함께 찾고, 매 round마다 관련 gate와 Cartography sync를 다시 수행해 새 candidate를 freeze한 뒤 재검증한다. 구현 owner를 중간에 바꾸지 않는다. MUST FIX가 없으면 NICE TO HAVE를 merge blocker로 승격하지 않는다.

## commit·PR·CI

- [`git-spec.md`](../../docs/plugin/git-spec.md)를 이 commit 경계에서 처음 읽고 branch/commit/PR 이름과 의미 단위 분할을 맞춘다.
- hook을 우회하지 않는다. 각 commit은 독립적으로 green이어야 한다.
- PR body는 저장소 template, 관련 issue trailer, 배경/문제, 원인, 작업내용, 결정 근거, Test Plan을 채운다.
- dcNess 배포물 변경이면 외부 활성 프로젝트에 도달하는 배포 경로를 적는다.
- PR 생성 후 CI를 확인하고 red면 원인을 수정해 다시 검증한다.

## target GitHub issue AC close audit

PR이 target issue close를 발동하기 직전에만 다음을 수행한다.

1. 진입 때 보관한 AC snapshot과 최종 구현·명령·validator 증거를 전수 대조한다.
2. 자동 판정 가능한 `[command]`/`[agent-read]` 항목만 충족 증거가 있을 때 체크한다.
3. issue body write는 이 close 경계에서 한 번만 수행한다.
4. `scripts/check_issue_body.mjs`가 있으면 같은 body를 다음처럼 감사한다.

```bash
node "$PLUGIN_ROOT/scripts/check_issue_body.mjs" \
  --body-file <issue-body.md> \
  --acceptance-only \
  --require-complete
```

미충족·미체크 typed AC가 하나라도 있으면 clean 마감이나 `Closes` merge를 금지한다. 사람 판정 항목은 agent가 체크하지 않고 `human verification 대기`로 보고하며, 이 대기 자체는 `blocked`로 분류하지 않는다.

## 종료

helper 기반 run이면 대표 workflow 종료 시 `dcness-helper end-run`을 호출한다. 최종 보고에는 구현 경로, review provider, 변경 요약, 검증 명령과 종료코드, review round 수, PR URL, AC close audit 결과, 남은 위험 또는 사람 확인을 포함한다.
구현·검증·candidate freeze·필수 review·AC audit 중 하나라도 증거가 없으면 clean으로 보고하지 않는다.

PR/merge handoff가 끝나기 전에는 worktree를 유지한다. 종료 시점에만 [`loop-procedure.md` worktree 분기](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정)를 읽고, 커밋 흡수와 clean 상태가 모두 증명되면 remove를 검토하며 dirty/unmerged 상태는 keep한다.

완료 뒤 별도 자율 작업으로 이어갈 때만 `dcness-helper post-task-begin --reason <사유>`를 호출해 task ROI와 분리한다. 이 #472 marker는 구현 착수 preflight가 아니다.
