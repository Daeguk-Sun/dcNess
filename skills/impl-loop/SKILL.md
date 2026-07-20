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
- **review**: 모든 대상 task 와 `journey_deferred`가 아닌 자동 `(JOURNEY)` 수렴이 completed 된 뒤 merge candidate diff 를 대상으로 `impl-validator` 1회 통합 리뷰. Epic close를 발동하는 최종 candidate만 그 앞에서 `impl-validator:CODEBASE_SANITY`를 1회 수행한다.
- **main-owned**: push / PR 생성 / PR merge / issue mutation 은 메인 전담. 최초 PR은 acceptance·AC close audit·tree-preserving consolidate 뒤에만 만든다.
- **state**: `dcness-story-runner` 가 task 순서와 task commit 상태만 저장하고 story PR/run 종결은 task 에서 계산한다.
- **분기 규칙**: [`impl-loop-routing.md`](impl-loop-routing.md)

UI expected_steps 의 `canvas-design` 은 진행 뷰용 main-owned checkpoint 이며 helper begin/end-step 비대상이다. draft가 필요할 때 ledger에 기록되는 실제 mode 없는 foreground designer step은 lifecycle hook이 소유한다.

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

UI 작업이면 구현 전 **UI 기준 확보 분기**를 먼저 본다. 내부 [`canvas-design`](../canvas-design/SKILL.md) 은 main-owned checkpoint 이며 helper begin/end-step 비대상이다. 기준 있음 / 신규 시각 구조 + 기준 없음 / 시각 구조 불변을 판정하고, 필요한 경우 mode 없는 foreground designer Agent를 lifecycle hook 경로로 호출해 draft 생성 → 사용자 PICK → 확정본 승격 → `docs/design-variants/canvas.html` frame 등록을 수행한다.

반환값은 `docs/design-variants/<screen-id>.html` 확정 목업 경로와 핵심 node-id 매핑이다. `build-worker` 는 그 경로를 디자인 정합 기준으로 읽고, 레이아웃 계층·상태·토큰·의도적 차이를 보고한다. 사용자 PICK 은 draft 생성 시 canvas-design 내부 조건부 절차이며 chain sub-step 으로 세지 않는다.

## 워크트리와 story stack

진입 시 worktree 격리를 기본으로 사용한다. 자세한 mechanics 는 [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정)를 따른다.

### Story branch base

단일 story worktree는 `main`에서 시작한다. 다중 story는 첫 story를 `main`, 다음 story를 직전 story 브랜치에서 재분기한다. PR 생성 시 stack base를 유지하고 merge 승인 시점에만 main으로 리타겟·리베이스한다. mechanics는 [`loop-procedure.md` story 브랜치 스택](../../docs/plugin/loop-procedure.md#story-브랜치-스택), naming/trailer는 [`git-spec.md` story 브랜치 스택](../../docs/plugin/git-spec.md#story-브랜치-스택)이 진본이다.

## Pre-flight

1. `docs/epics/**/stories.md` 상단의 `**GitHub Epic Issue:** [#N]` 또는 `미등록 (사유: …)` 를 확인한다. 없으면 STOP.
2. parent epic/story issue 본문을 진입 preflight 에서 한 번 read 하고 target GitHub issue AC snapshot 을 만든다. task 자체는 GitHub issue 가 아니라 impl 파일 + task commit 으로 추적한다. snapshot 은 task/story 진행 전체에서 재사용하며 반복 issue 조회를 추가하지 않는다. AC가 없거나 검증 주체가 미기재됐으면 close 전에 현행 typed AC로 갱신하고, agent가 의미를 임의 추론해 체크·재분류하지 않는다. 현행 typed 일반론 AC 는 snapshot 에서 구체화해 구현 계약으로 쓰되 사용자 판단 없이는 구체화하지 않는다.
3. task 가 이미 머지됐는지 `git log --grep <task-slug>` 와 task tail 로 확인한다.
4. `begin-run impl --design-doc <task impl 문서>` 로 설계 문서를 기록한다. 이 값은 build-worker gate, boundary pre-flight, impl-validator review 근거다.
5. `boundary-suggestions --impl-plan <task>` 로 `### 수정 허용` 경로가 `ALLOW_MATRIX ∪ .dcness/boundary.json` 으로 커버되는지 확인한다. 미커버 경로는 사람 승인 후 boundary override 가 필요하다.
6. generated TDD hook 상태를 확인한다. 플랫폼 또는 project-local 계약이 있는데 hook 이 없거나 linked worktree/headless 재사용에 필요한 생성 파일이 커밋되지 않았으면 구현 step 시작을 STOP 한다.
7. task 목록에서 `(JOURNEY)` 선언과 `acceptance_environment`를 수집한다. journey 미선언 run과 `automation=human_verification`만 있는 run은 추가 호출 없이 no-op이다. 자동 journey가 있으면 구현 전에 `begin-step build-worker JOURNEY_ENV_PREFLIGHT`를 열어 실제 worker 실행 컨텍스트에서 probe·자동 준비를 1회 수행한다. 준비 완료 또는 검출 불확실은 `PASS`로 task 구현에 진행하고, 확실한 미충족 + 자동 준비 불가만 사용자에게 환경 먼저 준비 / 구현만 진행하고 journey 검수 분리 중 하나를 1회 확인한다. 분리를 선택하면 해당 `journey_id`를 현재 run의 `journey_deferred` 목록으로 진행 뷰와 이후 모든 build-worker·impl-validator·product-acceptance prompt에 보존한다. 해당 journey는 수렴·sealed acceptance·종료 조건의 수렴 PASS Must 비대상이며 human verification/follow-up으로 남고, 그 AC가 속한 story/epic issue는 닫지 않으며 PR body에 `Closes`를 붙이지 않는다. 다른 자동 journey는 정상 진행한다.

## TaskCreate / TaskUpdate

본 skill 의 모든 step 은 Claude Code 의 **TaskCreate / TaskUpdate 호출과 한 묶음**이다. 자율 skip 금지.

WHY: lifecycle hook/helper는 run state를, TaskCreate/TaskUpdate는 사용자가 직접 보는 진행 표시를 소유한다. 둘은 중복이 아니라 보완 관계다.

**중대 차단 안티패턴**: "begin-step 으로 트래킹 충분하다 자율 판단해서 TaskCreate skip" — 사용자 진행 상태가 보이지 않아 회귀한다.

호출 시점:

- 진입 직후 task list 생성.
- 각 step 전환 때 `TaskUpdate(status=in_progress | completed)`. `in_progress`와 mode 없는 foreground Claude Agent 호출이 서로 결과 의존성이 없으면 같은 assistant turn의 독립 tool batch로 발행한다.
- 종료 직전 헤더와 sub-step 전부 completed.

retry 시 기존 sub-step 을 재활용하고 신규 TaskCreate 를 만들지 않는다.

## Sub-agent prompt 작성 checkpoint (#780)

`build-worker` / `impl-validator` / `product-acceptance` 호출 전, Agent tool input을 쓰기 전에 [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md)를 직접 읽고 3슬롯을 점검한다. 정적 원칙은 `begin-step` stdout relay가 아니다. foreground Claude Agent의 worktree와 `[PREVIOUS_TASKS]`는 SubagentStart hook이, headless build-worker는 wrapper가 첫 prompt에 직접 넣는다.

- **대상 + 읽을 진본**: impl 파일 경로, preflight 에서 확보한 parent epic/story target GitHub issue AC snapshot, merge candidate diff, build-worker Cartography impact 자유 prose, affected Root Cartography 좌표, 관련 epic/decision 같은 SSOT 포인터만 둔다.
- **리뷰 대상 전달 우선순위**: build-worker task 결과처럼 검토 대상이 커밋으로 존재하면 커밋 id와 변경 파일 목록을 선행 전달하고, validator가 `git show` / `git diff` / `git log`로 커밋 진본을 직접 펼치게 한다. 호출자는 별도 diff 파일을 덤프하지 않는다. 커밋이 없는 uncommitted local diff일 때만 diff 파일 전달을 폴백으로 사용한다.
- **worktree**: foreground Claude Agent는 SubagentStart hook, headless는 wrapper가 worktree 절대경로를 동적으로 넣는다. 메인은 Bash stdout을 prompt로 재전달하지 않는다.
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

1. `journey_deferred`가 아닌 자동 `(JOURNEY)`가 있으면 task loop보다 먼저 같은 provider·sandbox 설정의 `JOURNEY_ENV_PREFLIGHT` mode를 호출한다. 이 호출은 tracked write/commit 없이 worker 실행 컨텍스트의 runtime 도달성을 판정한다. main host probe나 product-acceptance 실행으로 대행하지 않는다.
2. `dcness-helper prev-tasks-reset` 은 chain 첫 task 또는 single 모드에서 build-worker 호출 전에 1회 실행한다. chain 2번째+ task 는 직전 task 산출을 hook/wrapper가 `[PREVIOUS_TASKS]`로 직접 넣으므로 reset하지 않는다.
3. implementation provider를 먼저 resolve한다. 기본 provider는 `headless-chain`이다. headless provider면 wrapper 소유권을 위해 `begin-step build-worker`로 열고, mode 없는 foreground Claude Agent면 명시적 begin/end-step 없이 lifecycle hook에 맡긴다. modeful Claude Agent는 `begin-step build-worker <MODE>`를 유지한다.
4. `dcness-implementation-chain build-worker --provider <provider> --prompt-file <file>` 를 실행한다. prompt 에는 target GitHub issue AC snapshot 을 진본 포인터로 포함한다. 성공 경로는 마지막 응답 저장과 `end-step build-worker` 까지 수행한다.
5. build-worker 는 test → impl → self-validate 를 한 task 안에서 수행하고, gates 가 green 이면 로컬 task commit 을 만든다.
   - `task_index: total/total` 인 Story 마지막 task 는 impl 문서의 종합 검증 REQ 로 해당 Story AC 전항목을 다시 실행·관찰한다. 앞 task 의 PASS 를 대신 재사용하지 않는다. 마지막 task 에 전수 검증 REQ 가 없으면 구현 완료로 간주하지 않고 `SPEC_GAP_FOUND` 로 설계 보강을 요청한다.
6. task local commit 은 [`git-spec.md#의미-단위-커밋-분할`](../../docs/plugin/git-spec.md#의미-단위-커밋-분할)을 따른다. build-worker 는 한 task 안에서도 독립 검토 가능한 의미 단위로 쪼개되, 각 커밋은 hook 을 통과할 수 있는 일관 상태여야 한다.
7. build-worker 는 `git status`, `git diff`, `git diff --check`, `git add`, `git commit`, `git rev-parse HEAD` 만 사용할 수 있다. `git push`, `gh pr create`, `gh pr merge`, `gh issue` mutation 은 금지다.
8. build-worker report 에 commit sha, 검증 명령, clean status 가 없으면 task clean 으로 보지 않는다.

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

최초 resolve한 plugin root/helper 절대경로를 이후 독립 Bash 호출에 literal로 넣는다. 위 변수는 한 Bash 프로세스 안의 예시일 뿐 호출 간 지속 상태가 아니다.

phase prose:

- build-worker 는 `build-test.md`, `build-impl.md`, `build-validate.md` phase prose 를 남긴다.
- 이 세 파일은 worker 내부 phase 증거이며 outer Agent lifecycle receipt가 아니다. phase별 outer begin/end-step을 추가하거나 phase 파일을 outer completion으로 중복 append하지 않는다.
- `build-{test,impl,validate}.md` 3개 실존 확인은 false-clean 방지 닻이다.
- phase prose 부재 또는 worker/validator 흔적 없이 clean 표기 = false-clean → blocked.

검증 대행:

- build-worker 가 `VALIDATION_BLOCKED` 를 보고하면 먼저 같은 run ledger의 최신 `codex_sandbox_permission_required` event가 가리키는 `codex-sandbox-permission-*.json` receipt와 `permission_required` 상태를 확인한다. 이 receipt는 Codex wrapper가 자유 prose와 raw log의 좁은 sandbox signature를 함께 읽어 생성하며 agent 출력 JSON/marker가 아니다.
- permission receipt가 없으면 기존 경로대로 메인이 같은 worktree cwd에서 worker가 남긴 검증 명령을 직접 실행한다. assertion/compile/test 실패, 일반 `Permission denied`, Codex CLI/auth/timeout 실패에는 receipt가 생기지 않는다.
- `permission_required`이면 메인은 사용자에게 승인 전에 다음 사실을 한 번 설명한다: 필요한 capability, `network_access`가 loopback 전용이 아니라 Codex workspace-write의 **outbound network** 전체 허용이라는 범위, 제안 writable root 절대경로와 로그 근거, `workspace-write` 유지, `danger-full-access` 미사용. 선택지는 **이번 실행에만 허용 / 이 프로젝트에 저장 / 거부** 세 가지다.
- 사용자가 선택하면 `"$PLUGIN_ROOT/scripts/dcness-codex-permission" retry --receipt <receipt> --decision once|project|deny --prompt-file "$PROMPT_FILE" --project-root "$PROJECT_ROOT" --helper "$HELPER"`를 실행한다. `once`는 승인 env를 해당 Codex worker 프로세스에만 전달하고 설정 파일을 쓰지 않는다. `project`는 기존 최상위/`env` 키를 보존해 `.claude/settings.local.json`에 승인한 키만 병합하고 현재 재시도에도 같은 env를 명시적으로 전달한다.
- permission retry는 provider chain이 아니라 Codex build-worker를 직접 `-s workspace-write`로 한 번만 재호출한다. malformed settings, 사용자 `deny`, 안전한 root 추론 실패, 승인 후 같은 거부 반복은 설정·권한을 더 바꾸지 않고 `VALIDATION_BLOCKED`를 유지한다. 이 상태에서 host 직접 검증, 다른 provider, `danger-full-access`로 우회하지 않고 증거와 남은 선택지를 사용자에게 보고한다.
- 검증 미실행 상태로 commit/push/PR 진행 금지.

## story/epic runner task 단일 상태 (#1019, #1041)

`/impl-loop` 은 story/epic 진행을 자연어로 암기하지 않는다. 진입 직후 `dcness-story-runner plan/init` 이 impl task 목록을 path 순으로 정렬한다. 정렬 결과에서 같은 frontmatter `story` 값(숫자 story 와 `공통` 모두)이 둘 이상의 비연속 block 으로 재등장하면 `plan/init` 은 관련 task 경로를 보고하고 fail-fast 한다. `init` 은 이 검증을 기존 state 의 아카이브·교체보다 먼저 수행해 실패 시 state 를 변경하지 않는다. story 간 의존성을 표현할 수 있는 path 순서를 runner 가 임의로 재정렬하지 않으며, 각 story 가 한 연속 block 인 입력은 기존 순서를 그대로 보존한다. state file 에는 각 task 의 `pending / running / completed / error / blocked` 와 `attempts / commit / provider / note` 만 저장한다. story/run status 와 PR 번호는 저장하지 않는다.

실행 단위는 **task commit** 과 **story PR** 이다. build-worker가 각 task local commit을 만든 뒤 mark 성공에만 next-action을 실행하는 한 Bash 호출로 `dcness-story-runner mark ... && dcness-story-runner next-action ...`을 묶는다. `&&` 계약 때문에 mark 실패 시 next-action은 실행되지 않는다. `error` / `blocked` 는 서로 다른 task 상태로 기록하고 `--note <사유>` 를 반드시 남긴다.

`next-action` 의 파생 결과만 다음 행동을 정한다.

- `action=task`: 미완 task 를 build-worker 로 실행한다.
- `action=story-pr`: 직전 story 의 task commit 이 모두 완료됐다. 응답의 `story`와 `pr_base`로 PR base 메타와 story branch tip을 봉인하되 원격 PR은 아직 만들지 않는다. `next_branch_base`가 가리키는 직전 story 브랜치에서 재분기한 뒤 `next_task`를 시작한다.
- `action=done`: 모든 task commit 이 완료됐다. `final_story`와 `pr_base`의 마지막 story branch tip을 봉인하고 `stack_tip` vs main merge candidate를 확정한다. `journey_deferred`를 제외한 수렴 대상만 다음 호출로 보내며, 최초 PR cut은 필요한 수렴·review·acceptance·AC audit·consolidate 뒤다.
- `action=error` / `action=blocked`: 해당 task 의 note 를 근거로 retry 또는 사용자 위임한다.

task 가 모두 completed 면 run 은 PR 생성·머지 여부와 무관하게 종결된 것이다. 다음 `init` 은 기존 state 를 `story-run.completed-<UTC>.json` 으로 자동 보관하고 `--force` 없이 새 run 을 시작한다.

```bash
"<PLUGIN_ROOT_ABS>/scripts/dcness-story-runner" plan <impl-glob-or-dir>
"<PLUGIN_ROOT_ABS>/scripts/dcness-story-runner" init --state .dcness-work/story-run.json <impl-glob-or-dir>
"<PLUGIN_ROOT_ABS>/scripts/dcness-story-runner" mark --state .dcness-work/story-run.json --task <id> --status completed --commit <sha> && \
  "<PLUGIN_ROOT_ABS>/scripts/dcness-story-runner" next-action --state .dcness-work/story-run.json
```

`<PLUGIN_ROOT_ABS>`는 진입 시 최초 resolve한 literal 절대경로다. `$PLUGIN_ROOT` shell 변수가 독립 Bash tool 호출 사이에 지속된다고 가정하지 않는다. `dcness-helper`의 self-location은 이미 발견된 executable 내부 root 해소일 뿐 executable 발견 경로가 아니다.

완료 state 는 `story-run.completed-<UTC>.json` 으로 보관한다. 이 state file 은 직렬 chain driver 전용이며, 메인이 path glob 를 다시 정렬하거나 frontmatter 를 재해석하지 않는다.

story branch / PR 경계:

- 단일 story run: `final_story` branch 1개를 base=`main`으로 봉인한다. review/acceptance/AC audit/consolidate 뒤 PR 1개를 처음 만든다.
- 다중 story/epic run: story branch를 `story1(base=main) → story2(base=story1) → …`로 쌓는다. `action=story-pr`마다 현재 tip과 base를 봉인하고 다음 branch는 **직전 story 브랜치에서 재분기**한다. 원격 story PR은 아직 만들지 않는다.
- 마지막 `action=done`: `stack_tip` vs main을 최종 candidate로 삼는다. tracked cross-cutting 보정이 생기면 stack tip 기반 QA branch가 흡수하고, 변경이 없으면 빈 QA branch/PR을 만들지 않는다. 모든 PR은 clean cut 경계에서 한 번에 만든다.
- loop의 자동 merge 금지: 사용자가 유일한 merge gate다. 승인 전 `$PLUGIN_ROOT/scripts/pr-finalize.sh` 호출은 금지한다.

dry preview echo:

```text
전체: K task commit · S story PR · tracked 마감 보정이 있으면 QA PR 1개
stack: story1(base=main) → story2(base=story1) → … → QA(조건부)
acceptance 경계: story #<M>…#<N> · epic #<E>   ← 각 main 리타겟/merge 전 검수 대상 (기본 ON, --no-acceptance 시 생략)
```

issue close 가 실제 발동되는 story PR 또는 epic 마감 PR 을 포함한 chain 은 task 수와 무관하게 계획 표 echo + `진행할까요? (Y/n)` 1회 확인 후 진입한다. 확인 응답 전에는 task1 또는 story PR merge 준비로 진입하지 않는다. 구현 완료 뒤 각 story PR 의 main 리타겟 직전에 1회 확인한다. yolo 모드에서는 생략한다.

## Story PR / integrated review / merge

story 의 target task 가 completed 될 때마다 메인은 story branch tip과 base만 봉인한다. 다중 story run 은 local branch stack을 먼저 완성하고, `impl-validator review 출력은 merge candidate 경계에서 1회`만 수행한다. 단일 story는 story→main candidate diff, 다중 story/epic은 **스택 tip vs main** diff를 넘긴다. QA branch가 있으면 그 branch가 stack tip이다. 모든 Story/PR마다 full-repo semantic audit을 강제하지 않으며, repo-wide Codebase Sanity cadence는 Epic당 최종 clean candidate 1회가 기본이다.

정상 순서:

1. 한 story 의 build-worker task commit 들과 `git status --porcelain` clean 을 확인한다. runner의 `pr_base`와 story branch tip을 기록한 뒤, 다중 story/epic이면 `next_branch_base`가 가리키는 직전 story branch에서 다음 story branch를 만든다. 자동 merge 금지다.
2. 모든 target task가 completed 되면 `journey_deferred`가 아닌 자동 `(JOURNEY)`가 있는 final stack tip에서 `begin-step build-worker JOURNEY_CONVERGENCE`로 fresh context 수렴 호출을 연다. 첫 실행 PASS면 1회로 끝내고, 실패하면 실행·관찰·배관 수정·재실행을 수행한다. 단일 story tracked 수정은 해당 story branch에 둔다. N-story 수렴의 story-local production 수정은 해당 story branch에 commit하고 downstream branch를 restack하며, cross-cutting production 수정과 tracked flow/manifest 보정은 QA branch에 둔다.
3. 수렴 호출이 발동했다면 `JOURNEY_CONVERGENCE` PASS 뒤, 수렴 대상이 없어 비발동했다면 바로 final tip에서 통합 test/E2E 증거를 확정한다. 수렴이 production code를 바꾸면 재현 테스트 RED→GREEN과 의미 단위 commit이 있어야 한다. 설계·AC 충돌, 수렴 한도 초과는 분기 규칙대로 중단한다.
4. Epic close를 발동할 최종 stack tip에서 메인이 repo의 실제 test/lint/build/typecheck/coverage 명령을 발견·실행하고 code revision 또는 tree identity, 명령별 exit code, warning, coverage 도구·리포트 유무를 수집한다. coverage 도구가 없으면 `UNKNOWN`이며 test count로 추정하지 않는다. 작은 단일-module repo는 전체 repo, 큰 repo는 affected module과 affected dependency cone을 semantic scope로 잡고 cheap global signals를 함께 남긴다.
5. `begin-step impl-validator CODEBASE_SANITY`로 `impl-validator:CODEBASE_SANITY`를 연다. 같은 read-only impl-validator에 final merge candidate, task별 build-worker 보고, 수렴 증거, 수집한 기계적 증거, scope, Cartography 상태를 전달한다. finding이면 build-worker rework로 코드를 고친 뒤 수렴과 Sanity를 새 revision에서 재감사한다. PASS이면 `SANITY_RECEIPT_DIR="$("$HELPER" sanity-receipt-dir --project-root "$PROJECT_ROOT")"`로 persistent primary-worktree 경로를 구해 prose의 최소 의미를 `$SANITY_RECEIPT_DIR/<tree-identity>.md` local receipt로 보존한다. helper는 linked worktree의 `git --git-common-dir`을 기준으로 primary worktree의 `.dcness-work/codebase-sanity/`를 반환하므로 `ExitWorktree`가 임시 worktree를 제거해도 receipt가 남는다. local-only/ignored 정책이면 code PR에 포함하지 않는다.
6. mode 없는 foreground `impl-validator`는 lifecycle hook 경로로 열고, build-worker provider의 반대편으로 review provider를 resolve 한다. 최종 stack tip 커밋 id와 변경 파일 목록을 선행 전달해 일반 merge-review mode가 커밋 진본을 직접 펼치게 하고, task별 build-worker Cartography impact, affected Root Cartography 좌표, 관련 epic/decision을 plan ∪ target GitHub issue AC와 함께 리뷰한다. `(JOURNEY)`가 있으면 선언된 각 `target_ac` ↔ flow의 실제 assertion 대조를 고정 항목으로 수행한다. Story-only close는 Step 4~5 없이 이 단계로 바로 온다.
7. 영향 없음 또는 Root와 일치하면 기존 경로를 계속한다. system boundary는 유지되지만 route/state/as-built edge가 stale이면 메인이 기존 `module-architect:CARTOGRAPHY_REFRESH`를 호출해 affected Root 좌표만 bounded refresh하고 같은 diff+갱신 Root로 impl-validator 재검증한다. system boundary·global decision 변경이면 route-only patch로 흡수하지 않고 `/design --revise` 또는 system checkpoint backpressure에서 멈춘다.
8. 일반 merge review `PASS` 후 close를 발동할 final tip에서 `product-acceptance`의 `STORY_ACCEPTANCE` × N을 story별로 판정하고, epic close 시 `EPIC_ACCEPTANCE`를 수행한다. `journey_deferred`가 담당하는 story는 close candidate에서 제외해 sealed journey 실행을 발동하지 않고 human verification/follow-up으로 보고한다. build-worker 수렴 PASS는 나머지 journey의 sealed 실행과 final tip cross-story 스위프를 대체하지 않는다.
9. product-acceptance PASS 뒤 close를 발동할 `target GitHub issue AC close audit`을 수행하고 자동 typed AC 전항목을 close 경계에서 한 번 갱신·감사한다. `journey_deferred` target AC가 있는 story/epic은 close audit을 발동하지 않는다. checklist 밖 사람 항목은 미체크로 둔 별도 merge gate로 보존하며, 자동 audit PASS 뒤 clean cut은 계속한다.
10. close audit 뒤 수렴 iteration 노이즈가 있을 때만 **커밋 consolidate**를 수행해 독립 검토 가능한 의미 단위로 재구성한다. 작업 전후 `git rev-parse <tip>^{tree}`가 같아 최종 tree 불변임을 확인하며, 이미 의미 단위면 no-op이다. tree가 바뀌면 기존 Sanity·review·acceptance·AC 증거를 stale 처리하고 수렴 이후부터 다시 수행한다.
11. consolidate가 끝난 clean branch stack에서 repo git-spec의 push + `gh pr create` 절차로 **PR 생성**을 처음 수행한다. task commit으로 이미 clean인 branch에 새 commit을 요구하는 `scripts/pr-create.sh`는 이 경계에 사용하지 않는다. 단일 story close candidate는 acceptance PASS·AC close audit 뒤 최초 PR 1개를 cut한다. `journey_deferred` production-only candidate는 review와 consolidate 뒤 close 없이 PR을 cut한다. 다중 story는 봉인한 base로 story PR과 조건부 QA PR을 clean 상태에서 cut해 수렴 노이즈가 열린 PR에 append되지 않게 한다.
12. 숫자 story close candidate PR body에는 `Closes #story`를 두고, QA PR 유무를 확정한 마지막 merge 대상 PR body에만 `Closes #epic`을 둔다. `journey_deferred` target AC가 있는 production-only PR에는 `Closes`를 붙이지 않고 `Part of`와 `Document-Exception-PR-Close: journey deferred human verification/follow-up` 사유로 연결한다. 그 외 story/QA PR에는 epic `Closes`가 남지 않았는지 확인한다.
13. PR 이후 CI 실패가 rerun이나 외부 인프라 복구만으로 해소돼 tree가 같으면 acceptance verdict와 tree-identity Sanity receipt는 유효하다. tracked code나 harness를 수정하면 기존 증거를 stale 처리하고 수렴·검증·acceptance·audit·consolidate 뒤 PR에 새 commit을 반영한다.
14. 사용자가 merge를 승인할 때 story PR을 순서대로 base=`main`으로 리타겟·리베이스한다. checklist 밖 사람 항목이 남아 있으면 먼저 `human verification 대기`로 멈춘다. 현재 story tip이 바뀌면 아직 열린 downstream branch를 새 tip 위에 순서대로 restack하고 `--force-with-lease`로 갱신한다. restack 충돌 해결로 최종 tree가 달라지면 기존 review/acceptance 증거를 stale 처리하고 통합 review부터 다시 수행한다. 각 PR은 해당 story acceptance verdict와 AC close audit을 확인한 뒤 `$PLUGIN_ROOT/scripts/pr-finalize.sh`를 호출한다. QA PR이 있으면 마지막에 같은 절차로 merge한다.

### QA 산출물 배치

- **1-story**: branch 1개 = PR 1개다. 수렴/review/acceptance가 찾은 fix와 tracked flow/manifest 보정은 PR cut 전 해당 story branch에 반영한다. 별도 QA PR은 만들지 않는다.
- **N-story**: 최종 stack tip에서 수렴과 sealed acceptance를 실행해 story별 verdict를 만든다. story-local production 수정은 해당 story branch에 commit하고 downstream branch를 restack한다. cross-cutting production 수정과 tracked flow/manifest 보정은 마지막 story branch 기반 **QA branch/PR**이 흡수한다. tracked 변경이 없으면 빈 QA PR을 만들지 않는다.
- receipt/log/screenshot은 ignored `.dcness-work/product-journey/`에만 두고 어떤 PR에도 commit하지 않는다. acceptance 보고에는 receipt 경로만 참조한다.
- impl-validator의 story-local FAIL은 해당 story PR 브랜치에 commit하고 downstream branch를 restack한다. story PR 이 2개 이상인 run의 cross-cutting FAIL은 QA branch가 흡수하며 모든 PR은 재검증·consolidate 뒤 cut한다.

Epic 마감의 고정 순서는 `JOURNEY_CONVERGENCE → impl-validator:CODEBASE_SANITY → impl-validator:merge review → 필요 시 CARTOGRAPHY_REFRESH → 같은 diff+갱신 Root impl-validator 재검증 → product-acceptance → close audit → commit consolidate → PR cut → 사용자 merge gate`다. Sanity PASS 이후 어떤 단계에서든 코드가 다시 바뀌면 기존 Sanity와 일반 impl-validator 증거를 모두 stale 처리하고 새 기계적 증거를 수집해 수렴과 Sanity부터 재진입한다. Cartography 문서만 bounded refresh되고 code tree가 같거나 consolidate가 tree identity를 보존하면 Sanity receipt는 그대로 유효하지만 일반 impl-validator는 같은 diff와 갱신 Root를 재검증한다.

Sanity receipt에는 rigid JSON/marker 없이 code revision/tree identity, 실제 scope, 명령·exit/warning, coverage 값 또는 `UNKNOWN` 근거, dead-code 후보별 `removable`/`intentional stub`/`planned seam`/`framework-reachable`/`unknown`, example/scaffold·duplicate path·stale suppression/deprecation·convention drift·code-smell, clean 여부와 남은 finding/rework surface를 보존한다. receipt는 canonical Root refresh 완료 증거나 다음 `/design`의 affected capability/entrypoint 현재 코드 대조를 대신하지 않는다. `ExitWorktree` 전에 위 persistent 경로에 receipt가 실존하는지 확인한다.

`CARTOGRAPHY_REFRESH`는 새 agent나 공개 진입점이 아니라 기존 bounded module-architect write 계약을 구현 종료 경계에서 재사용하는 workflow mode다. tracked docs는 현재 branch/PR 정책으로 반영한다. local-only/ignored private docs는 code PR에 강제 포함하지 않고 canonical local Root를 갱신하거나 exact affected 좌표·상태 증거·다음 producer를 durable impact handoff로 보존한다. durable impact handoff만으로 freshness가 해소되지는 않으며 canonical local Root refresh 확인 전에는 최종 clean이 아니다. build-worker와 읽기 전용 impl-validator는 docs write를 떠안지 않는다.

producer 호출은 `begin-step module-architect CARTOGRAPHY_REFRESH`로 열고, module-architect prose를 `end-step module-architect CARTOGRAPHY_REFRESH --prose-file <cartography-refresh-prose>`로 기록한다. `PASS` 뒤에만 같은 merge candidate diff와 갱신 Root로 mode 없는 foreground `impl-validator` lifecycle hook 재검증을 열고, `SYSTEM_CHECKPOINT_REQUIRED`이면 Root patch 없이 `/design --revise` 또는 system checkpoint backpressure로 보낸다.

close 를 발동할 각 PR candidate 는 product-acceptance 와 impl-validator PASS 만으로 clean 이 아니다. 최종 acceptance verdict가 확정되면 최초 PR cut 전에 메인이 `Closes` 대상 story/epic issue의 target GitHub issue AC를 대조한다. verdict가 자동 판정 또는 `(JOURNEY)`로 충족했다고 판정한 AC만 체크하고, `사람 확인 안내`는 미체크로 둔다. 그 뒤 이슈 본문 write를 issue별 close 경계에서 한 번 수행한다. 진행 중 task/story 경계에서는 issue mutation이나 재조회를 추가하지 않는다. 각 최종 body는 다음 감사가 PASS 해야 한다.

```bash
node "$PLUGIN_ROOT/scripts/check_issue_body.mjs" \
  --body-file <issue-body.md> \
  --acceptance-only \
  --require-complete
```

미충족·미체크 typed target GitHub issue AC 가 하나라도 있으면 clean 마감과 merge 를 금지한다. close audit의 정확한 `PASS`만 close 경로를 연다. AC 부재·검증 주체 미기재 항목은 실패하며 body를 현행 typed AC로 갱신하기 전 merge를 정지한다. 사람 판정은 checklist와 분리한 human verification 목록으로 보고한다.

`impl-validator:CODEBASE_SANITY FAIL`이면 finding의 affected surface를 build-worker rework로 넘기고 수렴·Sanity부터 재감사한다. 일반 `impl-validator FAIL`의 story-local FAIL은 해당 story PR 브랜치에 commit하고 downstream story/QA branch를 restack한다. story PR 이 2개 이상인 run의 cross-cutting FAIL은 QA branch가 흡수한다. 단일 story는 해당 branch에 commit한다. 어느 경로든 코드가 바뀌면 수렴·Sanity·merge-review 증거가 stale이며 같은 finding을 줄 단위 점 패치로 반복하지 않는다. cycle 한도는 routing 문서가 소유한다.

review provider resolve:

```bash
IMPLEMENTATION_PROVIDER="${DCNESS_IMPLEMENTATION_PROVIDER:-headless-chain}"
REVIEW_PROVIDER=$("$HELPER" routing resolve impl-validator --implementation-provider "$IMPLEMENTATION_PROVIDER")
```

`routing.json` 에 `impl-validator` 가 명시되어 있으면 그 값이 우선한다. 명시값이 없으면 headless-chain build-worker 의 리뷰는 Claude, claude-headless/claude build-worker 의 리뷰는 Codex 가능 시 Codex·불가 시 Claude 다.

## 마감 acceptance

story/epic 마감마다 제품 검수(`product-acceptance`)를 끼워 **PASS 후에만 마감 PR 을 머지**한다. 기본 ON — `--no-acceptance` 또는 "검수 없이" 발화 시에만 생략한다. 자동 merge 금지이며 사용자가 유일한 merge gate다.

다중 story는 최종 stack tip에서 `product-acceptance:STORY_ACCEPTANCE`를 story × N으로 수행해 story별 acceptance verdict를 만든 뒤, epic close가 실제 발동되면 `product-acceptance:EPIC_ACCEPTANCE`를 1회 수행한다. merge 순서에서 각 PR의 코드가 이 tip verdict와 동일함을 확인하고 해당 verdict를 story-close gate에 사용한다. gap 수정 commit이 생기면 이전 STORY PASS는 stale이므로 STORY_ACCEPTANCE부터 다시 돌린다.

product-acceptance 는 외부 상태 변경(`gh` issue/PR mutation, push, merge) 금지 경계라 `gh` 호출이 불가다. 아직 PR을 만들지 않은 branch stack/base 메타·final tip commit·검증 결과·동작 증거·UI 목업 정합 증거와 build-worker Cartography impact, affected Root Cartography 좌표, 상태 증거, 관련 epic/decision, 현재 run의 `journey_deferred` 목록을 메인이 prompt 에 직접 담는다. UI task 는 확정 목업 경로, 구현 화면 스크린샷, 화면 증거를 함께 넣어 목업 불일치와 화면 증거 부재를 판정할 수 있게 한다. 핵심 AC 증거가 mock-only green 이거나 대상 사용자에게 부적합한 입력/진행 동선이면 gap 이다.

핵심 journey가 마감 AC이면 build-worker가 인계한 `(JOURNEY)` REQ, `JOURNEY_CONVERGENCE` 증거와 owner module/소스 영역의 journey 매니페스트/e2e flow 경로를 product-acceptance prompt에 넣는다. `journey_deferred`가 아닌 journey는 수렴 receipt를 acceptance 판정에 재사용하지 않고 product-acceptance가 최종 tip에서 [`product-journey.md`](../../docs/plugin/product-journey.md)에 따라 `"$PLUGIN_ROOT/scripts/dcness-product-journey" run --project-root "$PROJECT_ROOT" --config <contract>`를 다시 실행해 sealed receipt를 만든다. deferred journey는 sealed 실행 비발동이며 PASS/close 증거로 세지 않고 human verification/follow-up으로 남긴다. exit 1은 구현 gap 증거이며 mock-only, app-not-started, journey 미실행, assertion 미평가, UI evidence 누락을 PASS로 세지 않는다. helper가 쓰는 영역은 ignored `.dcness-work/product-journey/`로 한정되고 tracked 구현·설계는 write-zero로 유지한다. receipt는 어떤 PR에도 commit하지 않고 경로만 acceptance 보고에 남긴다.

호출(modeful foreground Claude Agent; 완료는 PostToolUse가 기록하므로 별도 end-step 없음):

```text
begin-step product-acceptance STORY_ACCEPTANCE
Agent(subagent_type="product-acceptance")  # current explicit mode=STORY_ACCEPTANCE
begin-step product-acceptance EPIC_ACCEPTANCE
Agent(subagent_type="product-acceptance")  # current explicit mode=EPIC_ACCEPTANCE
```

`PASS` → target GitHub issue AC close audit 로 진행한다. `FAIL` → auto-fixable gap 은 build-worker rework 로 수정한다. 코드 수정이면 Epic close run은 `JOURNEY_CONVERGENCE`와 Sanity부터 재진입하고, Story-only run은 수렴·impl-validator 재리뷰 후 acceptance를 재검수한다. capability 상태 drift가 route-only stale이면 `module-architect:CARTOGRAPHY_REFRESH` → 같은 diff+갱신 Root impl-validator 재검증 → acceptance 재검수 순서로 닫는다. system boundary/global decision gap이면 `/design --revise` 또는 system checkpoint backpressure로 보낸다. `ESCALATE` → 사용자 위임. acceptance FAIL, Cartography freshness 미해소, AC close audit 미해소 상태로 최초 PR cut이나 `pr-finalize.sh`를 강행하지 않는다.

## 진행 뷰 task 리스트

진행 뷰는 [`harness/chain_view.py`](../../harness/chain_view.py) helper 가 산출한다. 입력은 task list JSON `{tasks:[{name, engine:"build-worker", closes?}], current}` 이며, UI task 는 `engine:"ui-build-worker"` 로 표현한다. 그 외 변종은 `substeps:[...]` 명시 라벨을 사용한다. 구현 주체 enum 을 늘리지 않는다.

sub-step:

- 기본 task: `build-worker` → `impl-validator`
- UI task: `canvas-design` → `build-worker` → `impl-validator`
- story close: `build-worker:JOURNEY_CONVERGENCE`(조건부) → `impl-validator` → `product-acceptance`
- epic close: `build-worker:JOURNEY_CONVERGENCE`(조건부) → `impl-validator:CODEBASE_SANITY` → `impl-validator` → `product-acceptance:STORY` → `product-acceptance:EPIC`

완료 task 는 한 줄, 현재 task 만 sub-step 펼침, 예정 task 는 대기 줄이다. 총 task 수 기준 redraw strategy 는 ≤10 full / 11~20 partial / >20 minimal 이다.

## review 출력 재정의 (#446)

chain 안에서는 매 task 전수 review.md 출력을 하지 않는다. 메인 컨텍스트 출력 = 5줄 요약이며 자유 형식 단축 금지.

```text
[task<i> · <slug>] <clean|error|blocked>
build-worker: N tests RED→GREEN · M files +X -Y · validate PASS|FAIL · commit <sha>
finding: <PASS 시 "없음" / FAIL·NICE TO HAVE 시 1-2 문장>
PR <#NNN> open · base <branch> · closes #<MMM>
next: <다음 task slug 진입 | story-pr | integrated-review | 정지 사유>
```

PR cut 전에는 `PR pending · acceptance/AC audit/consolidate 선행`으로, cut 뒤 열린 stack은 `PR <#NNN> open · base <branch>`로 표시한다. close 발동 PR은 acceptance 줄을 PR 상태 줄 앞에 추가한다. 디스크의 `<run_dir>/review.md`는 원본 그대로 저장한다.

## 종료 조건

전체 완료 후 메인은 처리 N/N, task commit sha, story PR URL, 조건부 QA PR URL, stack tip, impl-validator round, acceptance 결과, target GitHub issue AC close audit 결과를 보고한다. clean 판정 전에는 다음 흔적을 확인한다.

- build-worker phase prose 3개.
- build-worker local commit sha.
- `dcness-story-runner` state mark.
- `journey_deferred`가 아닌 수렴 대상 자동 journey가 있으면 worker 실행 컨텍스트의 `JOURNEY_ENV_PREFLIGHT` 증거와 final tip `JOURNEY_CONVERGENCE` PASS. deferred journey는 종료 조건의 수렴 PASS Must 비대상이다.
- merge candidate impl-validator PASS.
- Epic close이면 현재 code revision을 덮는 `.dcness-work/codebase-sanity/` receipt와 `impl-validator:CODEBASE_SANITY` PASS.
- 필요한 product-acceptance PASS.
- build-worker Cartography impact가 affected Root Cartography 및 관련 epic/decision과 대조됐고 route-only stale 또는 system backpressure가 남지 않음.
- target issue 가 있으면 자동 판정 가능한 typed AC 전항목 충족·체크 + `require-complete`의 정확한 `PASS`.
- 수렴 노이즈가 있으면 tree identity 불변 commit consolidate, 이미 의미 단위면 no-op 근거, 그 뒤 최초 PR URL.
- 자동 판정할 수 없는 사람 확인 항목이 남으면 `human verification 대기`로 보고하고 merge 전에 정지한다.
- `journey_deferred` production-only PR은 해당 story/epic issue를 닫지 않고 `Closes` 미부착, human verification/follow-up과 남은 target AC를 보고한다.

이 중 하나라도 없는데 clean 이라고 쓰면 false-clean → blocked.

전체 완료 보고 뒤 메인이 이슈 등록, cleanup, 측정 같은 자율 작업으로 이어갈 때는 진입 전 `dcness-helper post-task-begin --reason "<사유>"` 를 호출한다. 이 marker 는 task ROI 측정 분리를 위한 #472 계약이다.

## 안티패턴

- task N 개를 한 build-worker 호출에 묶어 한 번에 처리.
- task commit/mark 전 다음 task 진입.
- build-worker 가 push / PR 생성 / merge / issue mutation 수행.
- main 컨텍스트가 worker 대신 env probe나 journey 수렴 실행을 떠안기.
- acceptance·AC close audit 전에 최초 story/QA PR을 만들거나 수렴 iteration commit을 열린 PR에 누적하기.
- story PR을 건너뛰고 epic 구현을 단일 PR로 묶기.
- story PR을 사용자 승인 없이 자동 merge하거나 merge 전 main 리타겟·리베이스를 생략하기.
- 모든 구현 뒤 impl-validator 통합 리뷰 없이 stack PR을 머지하기.
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
