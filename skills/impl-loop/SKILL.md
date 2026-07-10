---
name: impl-loop
description: Story/공통 impl task 파일(SDD 설계도)을 받아 단일 build-worker headless runner 로 구현한다. task 1개(single) 또는 여러 개(chain/story/epic) 를 처리하며, build-worker 가 task 별 로컬 커밋까지 소유하고, 모든 대상 task 구현 후 merge candidate diff 를 impl-validator 가 1회 통합 리뷰한다. push/PR/merge 는 메인만 수행한다. 사용자가 "/impl-loop <task>", "이 deep task 구현", "전부 구현", "task 다 돌려", "epic 전체 구현", "끝까지 구현", "/design 후 자동"처럼 impl task 경로/목록/story/epic 을 명시할 때 사용한다. 일반 구현·버그픽스·한 줄 수정은 기본 진입점 `/impl`.
---

# Impl Loop Skill — story/epic build-worker runner

> 본 스킬 = `/design` 이 만든 SDD story/epic 설계도(`docs/epics/**/impl/NN-*.md`)를 단일 구현 엔진 `build-worker` headless runner 로 처리한다. 일반 구현 요청은 [`/impl`](../impl/SKILL.md) 이 맡는다.

> 🔴 **분기 규칙 SSOT** — build-worker 결론 → 다음 호출 / retry 한도 / acceptance gap 처리는 [`impl-loop-routing.md`](impl-loop-routing.md) 가 본 skill 의 단일 진본. 본 파일은 진행 절차만 담는다.

## Loop

- **loop**: `impl-task-loop` (UI 감지 시 `impl-ui-design-loop`)
- **entry_point**: `impl`
- **implementation**: `build-worker` 하나. `build-worker` 는 test + impl + self-validate + task local commit 을 수행한다.
- **review**: 모든 대상 task 가 completed 된 뒤 merge candidate diff 를 대상으로 `impl-validator` 1회 통합 리뷰.
- **main-owned**: push / PR 생성 / PR merge / issue mutation 은 메인 전담.
- **state**: `dcness-story-runner` 가 task 순서와 task commit 상태만 저장하고 story PR/run 종결은 task 에서 계산한다.
- **분기 규칙**: [`impl-loop-routing.md`](impl-loop-routing.md)

UI expected_steps 의 `canvas-design` 은 진행 뷰용 main-owned checkpoint 이며 helper begin/end-step 비대상이다. draft 가 필요할 때 ledger 에 기록되는 실제 Agent step 은 `begin-step designer` 다.

## Inputs

- deep task 경로 (필수): 단일 task, task list, glob, 또는 epic impl 디렉터리.
- 이슈 번호 (있으면): parent epic/story 본문과 target GitHub issue AC read 에 사용한다.
- 선택 `--retry-limit N`: task 당 자동 재시도 한도. 기본 3.
- 선택 `--no-acceptance`: story/epic 마감 acceptance 비활성. 미지정 시 기본 ON.

## 비대상

- 일반 구현 / 버그픽스 / 한 줄 수정 / 설계 문서 없는 작은 구현 → `/impl`
- spec / design 단계 → `/spec` (PRD) 또는 `/design` (설계)
- deep task 부재 → 기본 진입점 `/impl`

## UI 작업 시 canvas-design 선두

UI 작업이면 구현 전 **UI 기준 확보 분기**를 먼저 본다. 내부 [`canvas-design`](../canvas-design/SKILL.md) 은 main-owned checkpoint 이며 helper begin/end-step 비대상이다. 기준 있음 / 신규 시각 구조 + 기준 없음 / 시각 구조 불변을 판정하고, 필요한 경우 `begin-step designer` 로 designer Agent 를 호출해 draft 생성 → 사용자 PICK → 확정본 승격 → `docs/design-variants/canvas.html` frame 등록을 수행한다.

반환값은 `docs/design-variants/<screen-id>.html` 확정 목업 경로와 핵심 node-id 매핑이다. `build-worker` 는 그 경로를 디자인 정합 기준으로 읽고, 레이아웃 계층·상태·토큰·의도적 차이를 보고한다. 사용자 PICK 은 draft 생성 시 canvas-design 내부 조건부 절차이며 chain sub-step 으로 세지 않는다.

## 워크트리와 base

진입 시 worktree 격리를 기본으로 사용한다. 자세한 mechanics 는 [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정)를 따른다.

### Base ref 분기

통합 브랜치 모드는 [`loop-procedure.md` base-ref 분기](../../docs/plugin/loop-procedure.md#base-ref-분기-통합-브랜치-모드-424) 와 [`git-spec.md#git-절차`](../../docs/plugin/git-spec.md#git-절차)가 SSOT 다. epic 단위 `stories.md` 상단 `**Base Branch:** feature/<slug>` 마커가 있으면 outer worktree base ref 와 PR base 를 그 branch 로 맞춘다.

## Pre-flight

1. `docs/epics/**/stories.md` 상단의 `**GitHub Epic Issue:** [#N]` 또는 `미등록 (사유: …)` 를 확인한다. 없으면 STOP.
2. parent epic/story issue 본문을 진입 preflight 에서 한 번 read 하고 target GitHub issue AC snapshot 을 만든다. task 자체는 GitHub issue 가 아니라 impl 파일 + task commit 으로 추적한다. snapshot 은 task/story 진행 전체에서 재사용하며 반복 issue 조회를 추가하지 않는다. 검증 주체가 없는 legacy AC 는 `[command]`/`[agent-read]` 로 분류하고, 일반론 AC 는 snapshot 에서 구체화해 구현 계약으로 쓴다. body 반영은 close 경계의 1회 write 에 포함하며, 사용자 판단 없이는 구체화할 수 없으면 추측하지 않는다.
3. task 가 이미 머지됐는지 `git log --grep <task-slug>` 와 task tail 로 확인한다.
4. `begin-run impl --design-doc <task impl 문서>` 로 설계 문서를 기록한다. 이 값은 build-worker gate, boundary pre-flight, impl-validator review 근거다.
5. `boundary-suggestions --impl-plan <task>` 로 `### 수정 허용` 경로가 `ALLOW_MATRIX ∪ .dcness/boundary.json` 으로 커버되는지 확인한다. 미커버 경로는 사람 승인 후 boundary override 가 필요하다.
6. generated TDD hook 상태를 확인한다. 플랫폼 또는 project-local 계약이 있는데 hook 이 없거나 linked worktree/headless 재사용에 필요한 생성 파일이 커밋되지 않았으면 구현 step 시작을 STOP 한다.

## TaskCreate / TaskUpdate

본 skill 의 모든 step 은 Claude Code 의 **TaskCreate / TaskUpdate 호출과 한 묶음**이다. 자율 skip 금지.

WHY: dcness helper `begin-step` / `end-step` 은 run state 파일만 갱신하고, TaskCreate / TaskUpdate 는 사용자가 직접 보는 진행 표시다. 둘은 중복이 아니라 보완 관계다.

**중대 차단 안티패턴**: "begin-step 으로 트래킹 충분하다 자율 판단해서 TaskCreate skip" — 사용자 진행 상태가 보이지 않아 회귀한다.

호출 시점:

- 진입 직후 task list 생성.
- 각 step 전환 때 `TaskUpdate(status=in_progress | completed)`.
- 종료 직전 헤더와 sub-step 전부 completed.

retry 시 기존 sub-step 을 재활용하고 신규 TaskCreate 를 만들지 않는다.

## Sub-agent prompt 작성 checkpoint (#780)

`build-worker` / `impl-validator` / `product-acceptance` 호출 전, `begin-step` stdout 의 `[PROMPT_SLOT_CHECK]` 를 prompt 작성 전에 읽는다. prompt 는 [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md) 3슬롯을 사용한다.

- **대상 + 읽을 진본**: impl 파일 경로, preflight 에서 확보한 parent epic/story target GitHub issue AC snapshot, 검토 대상 diff 같은 SSOT 포인터만 둔다.
- **worktree**: worktree 활성 시 worktree 절대경로를 넣는다.
- **이 호출 특유**: 재호출 finding, wave-plan 신호, 검증 대행 결과처럼 진본에 아직 없는 신호만 둔다.
- agent 본업의 구현 방식, 테스트 assert 방식, 알고리즘 같은 방법 처방은 prompt 에 넣지 않는다.

## impl 파일 사전 read 의무 (MUST — module-architect 7 원칙 + cost-aware #436)

진입 시 `build-worker` 가 impl 파일의 `## 사전 준비` 섹션을 따라 다음 파일을 read 한다. **통째 read 금지** — `CLAUDE.md` 의 cost-aware 행동 (#402) 과 맞춘다. 200 line 초과 doc 은 grep + offset/limit 부분 read 를 사용한다.

| 항목 | read 범위 |
|---|---|
| `docs/architecture.md` | 200 line 초과 시 본 task 관련 섹션만 grep + offset read. 100 line 이하면 통째 OK |
| `docs/decisions/` | 본 task 영향 decision 만 read. 부재 시 silent skip |
| `docs/prd.md` | 본 task 의 Story 항목 섹션만. 통째 read 금지 |
| 의존 task 머지 PR | `gh pr view <num> --json body --jq '.body' | head -20` |
| 형제 PR 환기 | `gh pr list --search "[epic<N>]" --state merged --limit 10 --json title,url` |
| 의존 모듈 (수정 X 영역) | grep + 시그니처만 read. 예: `grep "^export" path/to/file.ts | head -10` |
| 의존 모듈 (수정 영역) | 통째 read OK |

메인 직접 read 는 **진입 분기 판단 최소**만 수행한다. 메인이 통째 read 하지 말 것. agent prompt 에 경로를 넣으면 build-worker 가 위 룰로 자체 read 한다.

## build-worker 실행

1. `dcness-helper prev-tasks-reset` 은 chain 첫 task 또는 single 모드에서 `begin-step build-worker` 전에 1회 호출한다. chain 2번째+ task 는 직전 task 산출이 `[PREVIOUS_TASKS]` 로 들어가므로 reset 하지 않는다.
2. `begin-step build-worker` 로 step 을 열고 implementation provider 를 resolve 한다. 기본 provider 는 `headless-chain` 이다.
3. `dcness-implementation-chain build-worker --provider <provider> --prompt-file <file>` 를 실행한다. prompt 에는 target GitHub issue AC snapshot 을 진본 포인터로 포함한다. 성공 경로는 마지막 응답 저장과 `end-step build-worker` 까지 수행한다.
4. build-worker 는 test → impl → self-validate 를 한 task 안에서 수행하고, gates 가 green 이면 로컬 task commit 을 만든다.
5. task local commit 은 [`git-spec.md#의미-단위-커밋-분할`](../../docs/plugin/git-spec.md#의미-단위-커밋-분할)을 따른다. build-worker 는 한 task 안에서도 독립 검토 가능한 의미 단위로 쪼개되, 각 커밋은 hook 을 통과할 수 있는 일관 상태여야 한다.
6. build-worker 는 `git status`, `git diff`, `git diff --check`, `git add`, `git commit`, `git rev-parse HEAD` 만 사용할 수 있다. `git push`, `gh pr create`, `gh pr merge`, `gh issue` mutation 은 금지다.
7. build-worker report 에 commit sha, 검증 명령, clean status 가 없으면 task clean 으로 보지 않는다.

provider wrapper:

```bash
PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"

PROVIDER="${DCNESS_IMPLEMENTATION_PROVIDER:-headless-chain}"
PROMPT_FILE="<prompt-file>"
"$PLUGIN_ROOT/scripts/dcness-implementation-chain" build-worker --provider "$PROVIDER" --prompt-file "$PROMPT_FILE"
```

phase prose:

- build-worker 는 `build-test.md`, `build-impl.md`, `build-validate.md` phase prose 를 남긴다.
- `build-{test,impl,validate}.md` 3개 실존 확인은 false-clean 방지 닻이다.
- phase prose 부재 또는 worker/validator 흔적 없이 clean 표기 = false-clean → blocked.

검증 대행:

- build-worker 가 환경 제약으로 검증 명령을 실행하지 못해 `VALIDATION_BLOCKED` 를 보고하면, 메인이 같은 worktree cwd 에서 worker 가 남긴 명령을 직접 실행한다.
- 검증 미실행 상태로 commit/push/PR 진행 금지.

## story/epic runner task 단일 상태 (#1019, #1041)

`/impl-loop` 은 story/epic 진행을 자연어로 암기하지 않는다. 진입 직후 `dcness-story-runner plan/init` 이 impl task 목록을 path 순으로 정렬한다. 정렬 결과에서 같은 frontmatter `story` 값(숫자 story 와 `공통` 모두)이 둘 이상의 비연속 block 으로 재등장하면 `plan/init` 은 관련 task 경로를 보고하고 fail-fast 한다. `init` 은 이 검증을 기존 state 의 아카이브·교체보다 먼저 수행해 실패 시 state 를 변경하지 않는다. story 간 의존성을 표현할 수 있는 path 순서를 runner 가 임의로 재정렬하지 않으며, 각 story 가 한 연속 block 인 입력은 기존 순서를 그대로 보존한다. state file 에는 각 task 의 `pending / running / completed / error / blocked` 와 `attempts / commit / provider / note` 만 저장한다. story/run status 와 PR 번호는 저장하지 않는다.

실행 단위는 **task commit** 과 **story sub-PR** 이다. build-worker 가 각 task local commit 을 만든 뒤 `dcness-story-runner mark --status completed --commit <sha>` 로 state 를 갱신한다. `error` / `blocked` 는 서로 다른 task 상태로 기록하고 `--note <사유>` 를 반드시 남긴다.

`next-action` 의 파생 결과만 다음 행동을 정한다.

- `action=task`: 미완 task 를 build-worker 로 실행한다.
- `action=story-pr`: 직전 story 의 task commit 이 모두 완료됐다. 응답의 `story` 로 story sub-PR 을 만들고, `next_task` 는 그 PR 반영 뒤 시작할 task 다.
- `action=done`: 모든 task commit 이 완료됐다. `final_story` 로 마지막 story PR 을 만든 뒤 invocation 전체 merge candidate 를 리뷰한다.
- `action=error` / `action=blocked`: 해당 task 의 note 를 근거로 retry 또는 사용자 위임한다.

task 가 모두 completed 면 run 은 PR 생성·머지 여부와 무관하게 종결된 것이다. 다음 `init` 은 기존 state 를 `story-run.completed-<UTC>.json` 으로 자동 보관하고 `--force` 없이 새 run 을 시작한다.

```bash
"$PLUGIN_ROOT/scripts/dcness-story-runner" plan <impl-glob-or-dir>
"$PLUGIN_ROOT/scripts/dcness-story-runner" init --state .dcness-work/story-run.json <impl-glob-or-dir>
"$PLUGIN_ROOT/scripts/dcness-story-runner" mark --state .dcness-work/story-run.json --task <id> --status completed --commit <sha>
"$PLUGIN_ROOT/scripts/dcness-story-runner" next-action --state .dcness-work/story-run.json
```

완료 state 는 `story-run.completed-<UTC>.json` 으로 보관한다. 이 state file 은 직렬 chain driver 전용이며, 메인이 path glob 를 다시 정렬하거나 frontmatter 를 재해석하지 않는다.

story PR 경계:

- 단일 story run: `final_story` PR 1개, base=`main`. review/acceptance 뒤 사람 merge 결정을 기다린다.
- 다중 story/epic run: story 별 branch 와 sub-PR 의 base는 `stories.md`의 통합 브랜치다. `action=story-pr`마다 메인이 sub-PR을 만들고 통합 브랜치로 즉시 머지한다. 다음 story branch는 **갱신된 통합 브랜치에서 재분기**한다.
- 마지막 `action=done`: 마지막 story sub-PR까지 통합한 뒤 통합→main PR 1개를 만든다. 사람 머지 게이트는 이 PR 한 곳이다. epic을 단일 구현 PR로 묶지 않는다.

dry preview echo:

```text
전체: K task commit · S story sub-PR · 다중 story 면 통합→main PR 1개
acceptance 경계: story #<M>…#<N> · epic #<E>   ← 머지 전 검수 대상 (기본 ON, --no-acceptance 시 생략)
```

issue close 가 실제 발동되는 story PR 또는 epic 마감 PR 을 포함한 chain 은 task 수와 무관하게 계획 표 echo + `진행할까요? (Y/n)` 1회 확인 후 진입한다. 확인 응답 전에는 task1 또는 마감 PR 머지로 진입하지 않는다. 통합 브랜치 sub-PR(base ≠ default) 의 `Closes` 는 그 시점에 실제 close 를 발동하지 않으므로 sub-PR chain 진입 확인 기준에서는 제외하고, 마지막 main 머지 PR 직전에 1회 확인한다. yolo 모드에서는 생략한다.

## Story PR / integrated review / merge

story 의 target task 가 completed 될 때마다 메인이 story PR 을 만든다. 다중 story run 은 story sub-PR 을 통합 브랜치에 누적하되, `impl-validator review 출력은 merge candidate 경계에서 1회`만 수행한다. 단일 story 는 열린 story→main PR diff 를, 다중 story/epic 은 모든 sub-PR 이 반영된 통합→main diff 를 넘긴다.

정상 순서:

1. 한 story 의 build-worker task commit 들과 `git status --porcelain` clean 을 확인한다.
2. `scripts/pr-create.sh` 또는 repo git-spec 절차로 story PR 을 만든다.
3. 다중 story/epic 이면 story sub-PR 을 통합 브랜치로 머지하고 remote 통합 ref 를 갱신한 뒤, 다음 story branch 를 그 ref 에서 새로 만든다. 단일 story PR 은 열린 채 유지한다.
4. 모든 story PR 경계를 처리한 뒤 다중 story/epic 은 통합→main PR 을 만든다.
5. `begin-step impl-validator` → build-worker provider 의 반대편으로 review provider 를 resolve 하고, `impl-validator` 가 merged diff 를 plan ∪ target GitHub issue AC 기준으로 1회 리뷰한다.
6. `PASS` 후 `STORY_ACCEPTANCE` × N, epic close 시 `EPIC_ACCEPTANCE` 를 수행한다.
7. 단일 story→main 또는 통합→main PR 은 사용자 merge 결정이 필요한 repo 에서 멈춘다.

close 를 발동하는 최종 PR 은 CI green, product-acceptance 와 impl-validator PASS 만으로 clean 이 아니다. 이 최종 증거가 확정된 뒤 메인이 `Closes` 대상 story/epic issue 각각의 target GitHub issue AC 전항목 증거를 대조하고 자동 판정 가능한 체크박스를 모두 check 한 뒤, 이슈 본문 write 를 issue 별 close 경계에서 한 번 수행한다. 진행 중 task/story 경계에서는 issue mutation 이나 재조회를 추가하지 않는다. 각 최종 body 는 다음 감사가 PASS 해야 한다.

```bash
node scripts/check_issue_body.mjs \
  --body-file <issue-body.md> \
  --acceptance-only \
  --require-complete
```

미충족·미체크 target GitHub issue AC 가 하나라도 있으면 clean 마감과 merge 를 금지한다. 기존 이슈 체크박스에 사람 판정 항목이 남아 있으면 agent 는 자동 항목만 충족·체크하고 잔여 human verification 목록을 보고 정지한다. 이는 자동 구현 실패인 `blocked` 가 아니라 `human verification 대기`다.

`impl-validator FAIL` 이면 메인이 root cause 를 고친 뒤 새 commit 을 PR branch 에 append 하거나, 이미 머지된 뒤라면 fix PR 을 만든다. 단일 story PR 은 해당 PR branch 에 append 한다. story PR 이 2개 이상인 run 에서 FAIL 보정이 필요하면 downstream rebase 없이 통합 fix PR 1개를 만든다. 같은 finding 을 줄 단위 점 패치로 반복하지 않는다. cycle 한도는 routing 문서가 소유한다.

review provider resolve:

```bash
IMPLEMENTATION_PROVIDER="${DCNESS_IMPLEMENTATION_PROVIDER:-headless-chain}"
REVIEW_PROVIDER=$("$HELPER" routing resolve impl-validator --implementation-provider "$IMPLEMENTATION_PROVIDER")
```

`routing.json` 에 `impl-validator` 가 명시되어 있으면 그 값이 우선한다. 명시값이 없으면 headless-chain/codex-first build-worker 의 리뷰는 Claude, claude-headless/claude build-worker 의 리뷰는 Codex 가능 시 Codex·불가 시 Claude 다.

## 마감 acceptance

story/epic 마감마다 제품 검수(`product-acceptance`)를 끼워 **PASS 후에만 마감 PR 을 머지**한다. 기본 ON — `--no-acceptance` 또는 "검수 없이" 발화 시에만 생략한다.

최종 main 대상 PR 이 여러 story 를 닫으면 `product-acceptance:STORY_ACCEPTANCE` 를 story × N 으로 수행한 뒤, epic close 가 실제 발동되면 `product-acceptance:EPIC_ACCEPTANCE` 를 1회 수행한다. gap 수정 commit 이 생기면 이전 STORY PASS 는 stale 이므로 STORY_ACCEPTANCE 부터 다시 돌린다.

product-acceptance 는 read-only 라 `gh` 호출 불가다. PR 목록·검증 결과·동작 증거·UI 목업 정합 증거는 메인이 prompt 에 직접 담는다. UI task 는 확정 목업 경로, 구현 화면 스크린샷, 화면 증거를 함께 넣어 목업 불일치와 화면 증거 부재를 판정할 수 있게 한다. 핵심 AC 증거가 mock-only green 이거나 대상 사용자에게 부적합한 입력/진행 동선이면 gap 이다.

호출:

```text
begin-step product-acceptance STORY_ACCEPTANCE
end-step product-acceptance STORY_ACCEPTANCE --prose-file <file>
begin-step product-acceptance EPIC_ACCEPTANCE
end-step product-acceptance EPIC_ACCEPTANCE --prose-file <file>
```

`PASS` → target GitHub issue AC close audit 로 진행한다. `FAIL` → auto-fixable gap 은 build-worker rework 로 수정하고 impl-validator 재리뷰 후 재검수한다. `ESCALATE` → 사용자 위임. acceptance FAIL 또는 AC close audit 미해소 상태로 `pr-finalize.sh` 강행 금지.

## 진행 뷰 task 리스트

진행 뷰는 [`harness/chain_view.py`](../../harness/chain_view.py) helper 가 산출한다. 입력은 task list JSON `{tasks:[{name, engine:"build-worker", closes?}], current}` 이며, UI task 는 `engine:"ui-build-worker"` 로 표현한다. 그 외 변종은 `substeps:[...]` 명시 라벨을 사용한다. 구현 주체 enum 을 늘리지 않는다.

sub-step:

- 기본 task: `build-worker` → `impl-validator`
- UI task: `canvas-design` → `build-worker` → `impl-validator`
- story close: `product-acceptance`
- epic close: `product-acceptance:STORY` → `product-acceptance:EPIC`

완료 task 는 한 줄, 현재 task 만 sub-step 펼침, 예정 task 는 대기 줄이다. 총 task 수 기준 redraw strategy 는 ≤10 full / 11~20 partial / >20 minimal 이다.

## review 출력 재정의 (#446)

chain 안에서는 매 task 전수 review.md 출력을 하지 않는다. 메인 컨텍스트 출력 = 5줄 요약이며 자유 형식 단축 금지.

```text
[task<i> · <slug>] <clean|error|blocked>
build-worker: N tests RED→GREEN · M files +X -Y · validate PASS|FAIL · commit <sha>
finding: <PASS 시 "없음" / FAIL·NICE TO HAVE 시 1-2 문장>
PR <#NNN> merged · closes #<MMM>
next: <다음 task slug 진입 | story-pr | integrated-review | 정지 사유>
```

close 발동 PR 은 acceptance 줄을 `PR <#NNN> merged` 앞에 추가한다. 디스크의 `<run_dir>/review.md` 는 원본 그대로 저장한다.

## 종료 조건

전체 완료 후 메인은 처리 N/N, task commit sha, story sub-PR URL, 최종 main 대상 PR URL, impl-validator round, acceptance 결과, target GitHub issue AC close audit 결과를 보고한다. clean 판정 전에는 다음 흔적을 확인한다.

- build-worker phase prose 3개.
- build-worker local commit sha.
- `dcness-story-runner` state mark.
- merge candidate impl-validator PASS.
- 필요한 product-acceptance PASS.
- target issue 가 있으면 자동 판정 가능한 AC 전항목 충족·체크 + `require-complete` PASS.

이 중 하나라도 없는데 clean 이라고 쓰면 false-clean → blocked.

전체 완료 보고 뒤 메인이 이슈 등록, cleanup, 측정 같은 자율 작업으로 이어갈 때는 진입 전 `dcness-helper post-task-begin --reason "<사유>"` 를 호출한다. 이 marker 는 task ROI 측정 분리를 위한 #472 계약이다.

## 안티패턴

- task N 개를 한 build-worker 호출에 묶어 한 번에 처리.
- task commit/mark 전 다음 task 진입.
- build-worker 가 push / PR 생성 / merge / issue mutation 수행.
- story sub-PR 을 건너뛰고 epic 구현을 단일 PR 로 묶기.
- 모든 구현 뒤 impl-validator 통합 리뷰 없이 최종 main 대상 PR 을 머지하기.
- story/epic close 발동 PR 에서 acceptance 생략 또는 FAIL 미해소 상태로 `$PLUGIN_ROOT/scripts/pr-finalize.sh` 강행.
- TaskCreate / TaskUpdate skip.
- chain 전체 완료 후 자율 작업 (이슈 등록 / cleanup / 분석) 진입 시 `post-task-begin` marker 누락.

## 참조

- 분기 규칙: [`impl-loop-routing.md`](impl-loop-routing.md)
- 기본 구현 진입점: [`/impl`](../impl/SKILL.md)
- loop mechanics: [`loop-procedure.md`](../../docs/plugin/loop-procedure.md)
- branch / commit / PR: [`git-spec.md`](../../docs/plugin/git-spec.md)
- build-worker: [`build-worker.md`](../../agents/build-worker.md)
- impl-validator: [`impl-validator.md`](../../agents/impl-validator.md)
- product acceptance: [`/acceptance`](../acceptance/SKILL.md)
