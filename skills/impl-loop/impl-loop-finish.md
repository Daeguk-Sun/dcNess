# `/impl-loop` completed 이후 마감

이 문서는 모든 target task가 local commit으로 completed 된 뒤에만 읽는다. worker 시작 preflight가 아니다.

## merge candidate와 review 입력

- 단일 story는 story branch vs main, 다중 story는 최종 stack tip vs main을 merge candidate로 고정한다.
- task별 commit, 검증 명령, phase prose, build-worker Cartography impact, affected Root Cartography, 관련 epic/decision, target GitHub issue AC snapshot을 수집한다.
- review 대상이 commit이면 commit id와 변경 파일 목록을 선행한다. uncommitted diff일 때만 diff 파일을 쓴다.
- [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md)는 validator/acceptance 호출 직전에만 읽는다.

## Story PR / integrated review / merge

마감 순서는 다음과 같다.

1. 자동 journey가 있으면 final tip에서 fresh context `JOURNEY_CONVERGENCE`
2. Epic close이면 `impl-validator:CODEBASE_SANITY`
3. merge candidate `impl-validator` 통합 review
4. 필요하면 `module-architect:CARTOGRAPHY_REFRESH`와 impl-validator 재검증
5. `product-acceptance`
6. target GitHub issue AC close audit
7. tree-preserving 커밋 consolidate
8. 최초 PR 생성
9. 별도 merge gate

`JOURNEY_CONVERGENCE → impl-validator:CODEBASE_SANITY → product-acceptance → target GitHub issue AC close audit → 커밋 consolidate → PR 생성` 순서를 바꾸지 않는다. 최종 tree가 불변이면 review/acceptance 증거를 유지하고, 의미 단위 commit이 이미 clean하면 consolidate는 no-op이다. 최초 PR은 이 순서가 끝난 뒤에만 만든다.

### journey

- `journey_deferred`가 아닌 자동 journey만 `JOURNEY_CONVERGENCE`를 실행한다.
- 첫 실행 PASS면 끝내고, 실패하면 실행 → 관찰 → 배관 수정 → 재실행한다.
- story-local production 수정은 해당 story branch에 commit하고 downstream branch를 restack한다.
- 다중 story의 cross-cutting production 수정과 tracked flow/manifest 보정은 QA branch가 소유한다.
- `journey_deferred`는 수렴·sealed journey 실행 비발동이며 종료 조건의 수렴 PASS Must 비대상이다. 해당 issue에 `Closes`를 붙이지 않는다.
- 같은 실패 서명이 수정 뒤 반복되는 무진행은 3회, 전체 iteration은 12회가 상한이다. device 유실·재부팅은 1회만 자동 재준비한다.
- 서로 다른 실패가 이전 실패를 고친 뒤 순차 노출되면 무진행으로 세지 않는다. 전체 iteration 12회가 실패 서명과 별개인 실질 runaway 가드다.
- 상한 소진 시 커밋을 보존하고 `수렴 재개 / production만 착지하고 journey 분리 / run 폐기` 중 사용자 처분을 받는다. production만 착지하면 human verification/follow-up으로 남기고 issue를 닫지 않는다.

### CODEBASE_SANITY

Epic당 최종 clean candidate 1회만 affected dependency cone을 `impl-validator:CODEBASE_SANITY`로 감사한다. 모든 Story/PR마다 반복하지 않는다.

- code revision/tree identity와 실제 lint/build/test/typecheck 명령·exit·warning을 기록한다.
- coverage 도구가 없으면 `UNKNOWN`으로 기록한다.
- dead code, stale registration, duplicate/example/scaffold, suppression/deprecation, convention drift를 분류한다.
- receipt는 primary worktree의 `.dcness-work/codebase-sanity/`에 보존한다.
- receipt 경로는 `dcness-helper sanity-receipt-dir --project-root "$PROJECT_ROOT"`로 계산한다.
- finding은 build-worker rework로 수정하고 journey convergence와 Sanity부터 재진입한다.

코드가 바뀌면 기존 Sanity와 merge review 증거는 stale이다. Cartography 문서만 bounded refresh되고 code tree가 같으면 Sanity receipt는 유지할 수 있으나 merge review는 갱신 Root로 다시 수행한다.

### 격리 review

구현 provider의 반대 진영을 기본 review provider로 resolve한다. validator는 read-only다. MUST FIX가 있으면 최대 3회 root-cause 수정하고 관련 gate를 재실행한다. build-worker rework가 코드나 harness를 바꾸면 필요한 earlier evidence부터 다시 수집한다.

`impl-validator review 출력은 merge candidate 경계에서 1회`가 기본이다. 모든 task마다 full review를 반복하지 않는다.

## Cartography freshness

build-worker Cartography impact와 affected Root Cartography를 merge candidate 및 관련 epic/decision과 대조한다.

- 영향 없음/일치: 계속한다.
- capability 상태 drift 또는 route/state/as-built edge stale: `begin-step module-architect CARTOGRAPHY_REFRESH`로 bounded producer를 열고 `end-step module-architect CARTOGRAPHY_REFRESH --prose-file <path>`로 기록한 뒤 같은 diff+갱신 Root를 impl-validator 재검증한다.
- system boundary/global decision 변경: `/design --revise` 또는 system checkpoint로 보낸다.

durable impact handoff만으로 freshness가 해소되지는 않는다. canonical Root refresh와 impl-validator 재검증 없이 최종 clean으로 보고하지 않는다.
local-only/ignored Root는 code PR에 강제 포함하지 않고 canonical local Root에서 갱신한다.

## product acceptance

story/epic 마감마다 read-only `product-acceptance`를 수행한다. product-acceptance는 외부 상태 변경(`gh` issue/PR mutation, push, merge)을 하지 않는다. UI면 확정 목업 경로, 구현 화면 스크린샷, 화면 증거를 포함해 화면 증거 부재와 목업 불일치를 판정한다. 자동 journey는 final tip에서 `dcness-product-journey`를 다시 실행한 sealed receipt로 판정한다. mock-only, app-not-started, assertion 미평가, UI evidence 누락은 PASS가 아니다.

impl-validator는 계획 대비 구현 정합과 merge candidate diff 위험을 맡는다. 여러 PR이 합쳐진 story 동작과 여러 story가 합쳐진 epic 동작의 사용자 관찰 가능 동작은 마감 product-acceptance가 맡는다.

acceptance gap 수정으로 code가 바뀌면 convergence/Sanity/review 증거를 stale 처리하고 다시 진입한다. route-only Cartography stale이면 refresh → impl-validator 재검증 → acceptance 재검수 순서로 닫는다.

auto-fixable gap은 PRD/Story AC 미충족, 검수 증거 부족, smoke 실패, mock-only green/동작 증거 부족, 화면 증거 부재, 구현으로 닫히는 목업 불일치, 사용자 동선 부적합/내부 계약 노출이다. 설계 결함, 범위 재정의, 사용자/UX 선택, 보안·권한·데이터 위험은 비자동 gap으로 사용자에게 넘긴다.

## 마감 복구 한도

| 경로 | 한도 | 초과 시 |
|---|---|---|
| Codebase Sanity `FAIL` → build-worker rework → 재감사 | 3 | 사용자 위임 |
| impl-validator `FAIL` → root-cause 수정 → 재리뷰 | 3 | 사용자 위임 |
| product-acceptance auto-fixable gap → rework → 재검수 | 3 | 사용자 위임 |

같은 영역 finding이 반복되면 줄 단위 점 패치가 아니라 root cause를 재검토한다. 비자동 acceptance gap, 설계·AC 충돌, `ESCALATE`는 사용자에게 넘긴다.

## target GitHub issue AC close audit

진입 때 보관한 snapshot을 구현·명령·validator·acceptance 증거와 대조한다. 자동 판정 가능한 typed 항목만 충족 증거가 있을 때 체크하고, issue body write는 close 경계에서 issue별 한 번만 수행한다.

```bash
node "$PLUGIN_ROOT/scripts/check_issue_body.mjs" \
  --body-file <issue-body.md> \
  --acceptance-only \
  --require-complete
```

미충족·미체크 typed AC, acceptance FAIL, Cartography freshness 미해소가 있으면 최초 PR이나 merge를 금지한다. 사람 판정은 체크하지 않고 `human verification 대기`로 보고한다.

## PR stack과 merge

- commit 경계에서 [`git-spec.md`](../../docs/plugin/git-spec.md)를 읽고 의미 단위를 맞춘다. hook을 우회하지 않는다.
- `action=story-pr`마다 봉인한 story branch/base를 그대로 사용한다.
- 단일 story는 PR 1개다. 다중 story는 story PR stack과 실제 tracked cross-cutting fix가 있을 때만 QA PR을 만든다.
- PR body에는 story별 `Closes`, 필요한 epic close trailer, 검증, 배포 경로를 기록한다.
- 사람 확인이 남으면 최초 PR 생성 뒤 `human verification 대기`로 멈추고 별도 merge gate로 보존한다. 이 대기는 blocked가 아니다.
- 사용자가 유일한 merge gate다. 자동 merge 금지다.
- 승인 뒤 story 순서대로 base를 main으로 리타겟하고 최신 main 위로 rebase한다. tree가 바뀌면 review/acceptance/AC audit을 다시 수행한다.
- 각 PR의 review·acceptance·AC audit과 사용자 승인이 확인된 뒤에만 `$PLUGIN_ROOT/scripts/pr-finalize.sh`를 호출한다.

## 종료

처리 N/N, task commit, story/QA PR URL, final tip, review round, acceptance, Cartography freshness, target issue AC close audit, human verification 잔여를 보고한다. phase prose 3개·commit·state mark·필수 review/acceptance/audit 중 하나라도 없으면 clean으로 보고하지 않는다.

PR/merge handoff 전에는 story worktree를 유지한다. 종료 시점에만 [`loop-procedure.md` worktree 분기](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정)를 읽고, 커밋 흡수와 clean 상태가 모두 증명된 worktree만 `ExitWorktree(action="remove")`하며 dirty/unmerged worktree는 `ExitWorktree(action="keep")`한다.

완료 뒤 별도 자율 작업으로 이어갈 때만 `dcness-helper post-task-begin --reason <사유>`를 호출해 task ROI와 분리한다. 이 #472 marker는 worker 시작 preflight가 아니다.
