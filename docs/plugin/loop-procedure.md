# Loop Execution Procedure (메인 Claude loop 실행 절차)

> **Status**: ACTIVE
> **단일 목적**: **"메인 Claude 가 lifecycle hook/helper 기반 loop 실행 절차를 운전하는 법"** — `begin-run → [ Agent lifecycle 또는 wrapper step → echo·평가 ] ×N → end-run → review echo`. dcness loop 공통 골격(복붙·drift 차단) + `harness/session_state.py` helper CLI 의 유일 사용 매뉴얼.
> **이건 여기 없음 (각 진본)**: loop 진입 spec (entry_point / task_list / advance / expected_steps) = 해당 skill 의 `## Loop` contract + 본문 (예: impl-task-loop = [`skills/impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md)). 결론→다음 호출·retry·escalate 분기 규칙 = 각 `<skill>-routing.md`. 순서 차단 훅 = [`hooks.md`](hooks.md#catastrophic-gatesh). 용어 기준 = [`terms.md`](terms.md). 브랜치·커밋·PR·트레일러 규칙 = [`git-spec.md`](git-spec.md).

---

## 진입 모델

skill 트리거 또는 직접 발화 → 메인 Claude 가 **해당 skill 의 `## Loop` contract + 본문 (entry_point / task_list / advance / expected_steps / 분기 규칙)** 보고 task 리스트 동적 구성 → 본 문서 Step 0~8 mechanics 따름.

- **skill 경유**: skill 본문이 loop spec 진본 (예: impl-task-loop = [`skills/impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md)). skill 은 input 정형화 + 분기 추천. 절차는 본 SSOT.
- **직접 발화** ("이거 impl 로 가자"): 각 loop skill 의 `## Loop` + `<skill>-routing.md` 보고 메인이 자율 구성. 단 `begin-run` 이후 active run 안의 `Agent` 호출은 아래 표준 1 step 시퀀스가 PreToolUse hook 으로 강제된다.
- **SessionStart inject** (#596): *최소 활성 안내만* 매 세션 노출 — dcness 활성 사실 + 코드 강제 gate 가 켜져 있다는 안내 + hook-first recovery 원칙. 문서 진입 매트릭스·절차·분기 규칙은 **미주입** (skill 진입 시 해당 skill 이 안내, 위반 복구는 각 blocking hook 메시지가 그 자리에서 제공). 예외적으로 프로젝트 상태나 다음 작업 질문에는 `docs/index.md` 와 `## 진행 상태 · 다음 작업` 섹션이 실제로 있을 때만 해당 포인터를 안내하고, 없으면 `/next-work` issue/label 조회와 `/init-dcness` 보강 경로를 안내한다. 첫 응답 첫 줄 `[dcness 활성 확인]` 토큰.

---

## Step 0 — worktree + begin-run

### worktree 분기 (action 루프 한정)

**worktree 격리로 산출물을 커밋하는 action 루프 (`/impl` · `/impl-loop` · `/design` · `/ux`) 진입 시 Step 0 에서 EnterWorktree 자동 호출** — 동시 다중 세션 충돌 회피 + 메인 working tree 보호. `/ux` 는 git-tracked 확정 목업(`docs/design-variants/<screen-id>.html` + `canvas.html`)을 만들므로 action 루프다. `/spec` / `/tech-review` / `/to-issue` (commit 없음) 는 commit 격리 목적 부재라 워크트리 X (메인 working tree 에서 직접 또는 별 branch). loop 별 적용 여부는 각 skill 본문 (예: [`impl/SKILL.md`](../../skills/impl/SKILL.md) · [`design/SKILL.md`](../../skills/design/SKILL.md) 워크트리 절 · [`impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md) · [`ux/SKILL.md`](../../skills/ux/SKILL.md)).

```
EnterWorktree(name="<skill>-{ts_short}")   # action 루프 (impl / impl-loop / design / ux)
```

- **거부 표현 시에만 건너뜀** — 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시 EnterWorktree 호출 0, 일반 cwd 그대로 진행.
- 수동 `git worktree add` 우회 금지 — CC permission 시스템이 EnterWorktree 만 자동 권한 처리. 수동 워크트리는 sub-agent Write 거부 회귀 (#255 W1).
- **종료 시 ExitWorktree (커밋 diff 흡수 + clean worktree 자동 분기)** — 자동 remove/discard 조건은 **커밋 diff 흡수 확인 + working tree clean** 둘 다다. 먼저 `main..<worktree-branch>` diff (`.claude` 제외) 가 비어 이미 머지 흡수됐는지 확인하고, 이어서 worktree cwd 에서 `git status --porcelain --untracked-files=all` 이 빈 값인지 확인한다. 두 조건을 모두 만족할 때만 `ExitWorktree(action="remove", discard_changes=true)` 를 호출한다. 커밋 diff 가 남아 있거나 `uncommitted/untracked` 파일이 하나라도 있으면 `ExitWorktree(action="keep")` 으로 강등하며, dirty 상태 자동 discard 금지.

### story 브랜치 스택

`/impl-loop` 다중 story는 먼저 `story1(base=main) → story2(base=story1) → …` 순서로 local branch stack을 만들고, final tip 수렴·review·acceptance·AC audit·tree-preserving consolidate가 끝난 clean cut 경계에서 PR을 만든다. 상세 naming/trailer 규칙은 [`git-spec.md`의 story 브랜치 스택](git-spec.md#story-브랜치-스택)이 소유한다.

- 첫 story branch는 `main`, 다음 story branch는 **직전 story 브랜치** tip에서 만든다. 직전 story tip/base만 봉인하고 PR은 아직 만들지 않으며 자동 merge 금지다.
- PR 생성 시 stack base를 유지해 순수 story diff를 보여 준다. PR은 acceptance와 AC audit 뒤 처음 만들고, 사용자가 merge를 승인한 시점에만 해당 PR을 base=`main` 으로 리타겟하고 최신 main 위로 리베이스한다.
- main rebase가 현재 story tip을 바꾸면 아직 열린 downstream branch를 새 tip 위에 순서대로 restack한 뒤 merge한다. restack 충돌 해결로 최종 tree가 달라지면 기존 review/acceptance 증거는 stale이다.
- 다음 story로 넘어가기 위한 branch 생성은 reversible local/git 작업이며, `$PLUGIN_ROOT/scripts/pr-finalize.sh` 호출은 merge 승인 뒤에만 가능하다.
- `EPIC_DIR`(design)와 `TASK_FILE`(impl-loop)이 둘 다 set이면 두 경로가 같은 epic의 stories.md로 수렴하는지 검증한다. 서로 다르면 stale env로 정지한다.

### begin-run

```bash
PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"
RUN_ID=$("$HELPER" begin-run <entry_point> [--issue-num N] [--design-doc <path>] [--acceptance-required])
echo "[<entry>] run started: $RUN_ID"
```

이 최초 resolve 명령이 출력·확정한 plugin root와 helper 절대경로를 메인이 이후 독립 Bash tool input에 **literal 절대경로**로 재사용한다. `PLUGIN_ROOT`/`HELPER` shell 변수는 같은 Bash 프로세스 안에서만 유효하며 서로 다른 Bash tool 호출 사이에 지속된다고 가정하지 않는다. 아래 코드블록의 `$PLUGIN_ROOT`/`$HELPER`는 한 shell 안의 예시 표기이며, 독립 호출로 옮길 때는 최초 resolve한 literal을 넣는다. `dcness-helper`가 자기 위치에서 plugin root를 찾는 기능은 이미 발견된 executable의 내부 self-location일 뿐 executable 자체를 찾아주지 않는다.

`<entry_point>` = 해당 skill 의 `## Loop` 의 `entry_point` 필드 (예: `impl`, `design`, `ux`). begin-run 동작: sid auto-detect + run_id 발급 + `live.json.active_runs` 슬롯 + `.by-pid-current-run/{cc_pid}` 씀.

`--design-doc <path>` — 이 run 이 참조하는 **머지된 설계 문서**(impl task 문서) 경로. 설계가 별도 run 에서 머지된 뒤 구현 run 으로 진입하는 흐름(예: `/impl-loop` story/epic runner)에서 기록하면, implementation gate 가 같은-run module-architect PASS 의 등가 사전 조건으로 인정한다 ([`hooks.md` 순서 차단 훅](hooks.md#catastrophic-gatesh)). `entry_point=impl` 전용이며, 설계 산출물 규약 경로(`docs/epics/**`)의 실존 `.md` 만 허용 — 아니면 begin-run 이 fail-fast 거부한다. 기록값은 resolve 된 절대경로(hook 프로세스와 cwd 가 달라도 안전). chain 의 다음 task 진입은 `next-task --design-doc <path>` 로 동일 기록.

`--acceptance-required` — story/epic 마감 task처럼 frozen candidate의 `impl-validator` PASS 뒤 `product-acceptance`가 필요한 run에만 기록한다. normal close에서는 validator step이 candidate HEAD/tree/workspace root를 기록하고 먼저 끝난 뒤, PASS일 때만 acceptance step이 같은 identity를 기록한다. Stop hook은 기록된 workspace root에서 현재 candidate를 확인하며, validator만 PASS한 상태에서 acceptance 진입 turn을 재발화하고 둘 다 terminal PASS이며 현재 candidate가 같을 때만 정상 종료한다. 중간 task / `--no-acceptance` run / verify-only run 은 이 플래그를 주지 않는다. chain 의 다음 task 진입은 `next-task --acceptance-required` 로 동일 기록한다.

> `/impl-loop` driver 자체는 run을 갖지 않는다. single/chain 모두 implementation chain이 task마다 독립 `begin-run impl`과 terminal receipt를 만들며, merge candidate `impl-validator` 통합 review는 모든 target task가 completed 된 뒤 1회 수행한다. 자세한 시작은 [`/impl-loop`](../../skills/impl-loop/SKILL.md), 마감은 [`impl-loop-finish.md`](../../skills/impl-loop/impl-loop-finish.md)가 소유한다.

---

## Step 1 — TaskCreate

해당 skill 의 `## Loop` 의 `task_list` 필드대로 일괄 등록한다. `/impl-loop`의
Task 진행 표시는 [`impl-loop` 진행 뷰](../../skills/impl-loop/SKILL.md#진행-뷰-task-리스트)가
소유한다. story runner state와 implementation chain receipt를 실행 진본으로
유지하면서 `dcness-helper chain-view`의 operations를 TaskCreate/TaskUpdate로
적용한다. chain-view와 background implementation-chain은 같은 assistant turn의
독립 tool batch이며, Task UI 적용을 기다리느라 worker 시작을 늦추지 않는다.

```
TaskCreate("<agent>: <mode 또는 짧은 설명>")
... (loop 정의 수만큼)
```

---

## Step 2~N — agent 호출 골격

### 표준 1 step 시퀀스 (per-agent 의무)

```
TaskUpdate("<task>", in_progress) + Agent(subagent_type="<agent>", description="...")
# SubagentStart가 step_started, PostToolUse(status=completed)가 prose + step_completed 기록
# 의무 echo (5~12 줄) — 아래 "결과 echo + 평가" 섹션
TaskUpdate("<task>", completed)
```

표준 경로는 **mode 없는 foreground Claude Agent**다. `TaskUpdate(in_progress)`와 Agent 호출은 서로의 결과를 입력으로 쓰지 않으므로 Claude Code가 같은 assistant turn의 독립 tool batch를 허용하는 경우 함께 발행한다. Task 표시를 생략하는 뜻이 아니며, Agent 결과 prose를 읽고 echo·평가한 뒤 `TaskUpdate(completed)`를 발행한다.

Agent tool input을 만들기 **전** [`agent-prompt-slots.md`](templates/agent-prompt-slots.md)를 읽고 3슬롯을 self-check한다. 이 정적 작성 원칙은 `begin-step` stdout reminder가 아니며 hook이 prompt 내용을 판정·차단하지 않는다. 동적 정보는 대상 실행 경로가 직접 넣는다.

- foreground Claude Agent: `SubagentStart`가 실제 spawn 뒤 worktree와 build-worker의 `[PREVIOUS_TASKS]`를 첫 prompt 처리 전 `additionalContext`로 전달한다.
- headless build-worker: worker wrapper가 project/worktree root와 `[PREVIOUS_TASKS]`를 최종 prompt에 직접 합성한다.
- `[PREVIOUS_TASKS]`는 build-worker가 phase 3 통과 시 `prev-tasks-append`로 누적한 직전 task 산출 요약이며, 메인 Bash stdout relay 대상이 아니다.

active run(`entry_point=design|impl|ux`)의 mode 없는 foreground Claude Agent는 PreToolUse가 순서/호출 적합성을 검사하고 correlation intent만 둔다. sibling PreToolUse hook이 deny하면 `SubagentStart`가 발화하지 않으므로 `step_started`도 없다. 실제 spawn 뒤 `SubagentStart`가 `tool_use_id`와 `agent_id`를 current step에 묶고, `PostToolUse Agent`는 `status=completed`인 비어 있지 않은 최종 prose만 `<run_dir>/<agent>.md`에 저장해 `step_completed` receipt를 만든다. `async_launched`, Agent 실패, 빈 prose는 `step_completed`를 만들지 않으며 시작된 foreground step은 `step_aborted` 진단으로 닫힌다. 같은 lifecycle payload 재전달은 멱등이고 identity가 current step과 다르면 prose/receipt append 전에 거부한다.

한 세션 동시 Agent fan-out은 close에서도 사용하지 않는다. `acceptance_required=true` impl run은 holistic validator를 cheap fail-fast로 먼저 끝내고 terminal PASS일 때만 acceptance를 시작한다.

단, 이 close sequence의 mode 없는 `impl-validator`도 Agent 호출 전에 명시적 `begin-step impl-validator`를 실행한다. modeful acceptance와 함께 두 step 모두 helper가 clean candidate HEAD/tree/workspace root를 원자적으로 freeze해야 하기 때문이다. 이후 spawn identity bind와 completion receipt는 일반 foreground lifecycle과 같다.

modeful Claude Agent는 공개 Agent tool field로 mode를 안정 전달할 수 없으므로 Agent 호출 전에 `begin-step <agent> <mode>`를 명시한다. `SubagentStart`가 그 step에 spawn identity를 bind하고 성공 `PostToolUse`가 완료를 기록하므로 메인의 별도 `end-step`은 없다. `/impl-loop` headless build-worker는 implementation chain이 provider fork 전에 `begin-step`을 정확히 한 번 기록하고 worker wrapper가 성공 `end-step`을 기록한다. 메인이 둘 중 어느 것도 선행 호출하지 않는다.

이 순서 검사는 `entry_point=design|impl|ux` 에 공통이다. 정상 `/design` 은 `begin-run design` 로 시작하며 같은 lifecycle 검사를 탄다.

**validation provider 분기 (local opt-in)**: `impl-validator` / `architecture-validator` 는 호출 직전 provider 를 resolve 한다.

```bash
PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"

PROVIDER=$("$HELPER" routing resolve <agent>)
if [ "$PROVIDER" = "codex" ]; then
  "$PLUGIN_ROOT/scripts/dcness-codex-validator" <agent> [MODE] --prompt-file "$PROMPT_FILE"
else
  # mode가 있으면 Agent 전에 "$HELPER" begin-step <agent> <MODE>
  Agent(subagent_type="<agent>", ...)
fi
```

Codex wrapper 는 설치된 `dcness-<agent>/SKILL.md` 내용을 prompt 에 직접 포함한 뒤 `codex exec -C "$PROJECT_ROOT" -s read-only` 로 실행한다. 마지막 응답은 `/tmp` prose 파일에 받은 뒤 `dcness-helper end-step <agent> --provider codex-headless --prose-file ...` 로 저장한다. 따라서 Codex 분기 경로에서는 메인이 별도 `end-step` 을 한 번 더 부르지 않는다. Claude Agent의 완료는 PostToolUse lifecycle hook이, Codex wrapper의 완료는 wrapper가 소유하며 둘 다 메인이 prose를 읽어 집계한다. wrapper가 end-step까지 수행해도 counter 소유자는 메인이다. `DCNESS_CODEX_MODEL` 을 설정하면 wrapper 가 `-m` 모델 override 를, `DCNESS_CODEX_EFFORT` 를 설정하면 `-c model_reasoning_effort=...` override 를 전달한다. 둘 다 미설정이면 사용자 Codex config 를 그대로 상속하며, dcNess 는 특정 Codex 모델명을 하드코딩하지 않는다. 분기 config 파일명은 `routing.json` 이고 repo 파일이 아니라 `~/.claude/plugins/data/dcness-dcness/routing.json` 에 있으며, validation 비활성/미설정 기본값은 Claude 다.

**implementation provider 분기 (headless-chain 기본)**: `/impl-loop` 메인은 provider resolve·state init·previous-task reset·run/step lifecycle을 각각 호출하지 않는다. feature worktree에서 implementation chain 한 호출이 순서대로 소유한다.

```bash
PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
"$PLUGIN_ROOT/scripts/dcness-implementation-chain" build-worker \
  --chain-state .dcness-work/story-run.json \
  --init-path <impl-task-1> \
  --init-path <impl-task-N> \
  --prompt-file "$PROMPT_FILE"
```

`dcness-implementation-chain` 은 worktree/default-branch 검사를 state mutation보다 먼저 수행하고, story state·previous tasks·현재 task run·`step_started`를 한 번만 준비한 뒤 provider를 fork한다. wrapper는 `.dcness/tdd-hooks.json`을 scan 없이 prompt 계약으로 변환하고 canonical primary run directory 및 phase prose 절대경로를 주입한다. Codex에는 그 exact run directory만 추가 writable root로 연다. PASS 전 wrapper가 phase prose 3개, task boundary, post-run TDD guard를 검사한다. source mutation 전 환경 미충족 같은 routed non-PASS 결론은 phase prose clean 게이트로 재시도하지 않고 원래 terminal receipt를 보존한다.

chain은 `headless-chain`(Codex headless → Claude headless → Claude main), `claude-headless`, `claude` 를 같은 routing config 로 실행한다. workspace 변경 전 실패만 다음 provider로 넘어간다. workspace/HEAD 변경 뒤 `timeout`·`idle_timeout`·`empty_output`·`boundary_violation`·`tdd_guard`·`phase_evidence`는 기존 diff를 보존하고 같은 provider/같은 workspace에서 기본 2회 bounded continuation한다. permission receipt가 있으면 첫 실패에서 사용자 승인 경로로 멈춘다. 복구 불가 category나 한도 소진은 자동 폴백·revert 없이 중단한다.

`/impl-loop`는 single/chain 모두 implementation chain에 `--chain-state`와 전체 `--init-path`를 넘긴다. chain이 missing state를 story runner로 한 번 초기화하고, 같은 task 목록·project root 재호출은 기존 state를 재사용한다. state의 `chain_id`가 수명 진본이며 cache sidecar는 같은 state 디렉터리의 `provider-failure-cache/<chain_id>.json`이다. 완료 chain은 cache를 소비하지 않으며 archive/force init 시 기존 sidecar를 무효화한다. state의 `project_root`가 현재 project/worktree와 다르면 provider fork 전에 거부한다.

worker가 `DCNESS_PROVIDER_FAILURE_FILE` 내부 JSON으로 전달하는 failure category 중 `cli_missing`, `auth_unavailable`, `config_unavailable`만 같은 chain에서 재시도 가치가 없는 cacheable capability 실패다. `timeout`, `idle_timeout`, `empty_output`, `boundary_violation`, `tdd_guard`, `interrupt`, `network_transient`, 그 밖의 `provider_error`와 agent의 구현/검증 결론은 cache하지 않는다. chain은 workspace/HEAD 불변을 다시 확인한 뒤에만 cache를 기록한다. cache hit 진단에는 provider, category, 최초 실패 `first_raw_log`, `scope=chain:<chain_id>`와 현재 skip log가 남는다.

기본 routing 결과는 `--provider-provenance routing`으로 전달한다. 사용자가 provider를 직접 골랐으면 `--provider-provenance explicit`으로 호출해 기존 cache를 우회하며, Codex permission retry도 cache를 우회한다. 우회 실행이 성공하면 해당 provider의 오래된 cache entry를 지운다. `--provider`를 주고 provenance를 생략한 호출은 안전하게 `explicit`으로 간주한다.

#### 호출 prompt 슬림 포인터 규약

**MUST.** 호출 직전 해당 `agent.md` 의 "입력" / "호출자가 prompt 로 전달하는 정보" 항목 read 후 prompt 작성 (형식 자유, 정보 명시 의무). prompt 에는 **(1) 읽을 SSOT 문서 포인터 (agent 가 자체 read 할 경로) (2) 대상 단위 (어떤 task / Story / 모듈) (3) 그 호출에 특유한 제약·주의 (4) 산출 경로·번호 규약·write 경계** 만 담는다.

**호출 직전 self-check (#780).** `/impl`·`/design`·`/ux` action loop가 Agent tool input을 쓸 때와 `/impl-loop`가 GREEN 이후 validator/acceptance Agent를 호출할 때 정적 템플릿을 읽고 아래 3가지를 확인한다. worker 시작 prompt는 `/impl-loop`의 slim prompt 계약이 소유하므로 이 후기 템플릿을 preflight로 읽지 않는다. (a) 대상+읽을 진본이 슬롯 1에 있는가, (b) 슬롯 2가 동적 lifecycle context와 충돌하지 않는가, (c) 슬롯 3이 방법 처방이 아니라 이 호출 특유의 미기록 제약·신호만 담는가. 코드 hook은 prompt 내용을 판정하거나 차단하지 않는다.

- ❌ **이미 SSOT 문서에 기록된 결정의 사본을 prompt 에 재기입 금지** — 합의 스택·계약·설계 결정은 agent 가 자기 "먼저 읽을 문서" 규약대로 SSOT 문서를 직접 읽어 획득한다. 같은 결정이 prompt 와 문서 두 곳에 살면 진본이 둘이 되어, 한쪽만 갱신될 때 어느 쪽이 맞는지 모르는 drift 가 생긴다 (dcNess 가 본래 막으려는 사본 drift 를 절차 자신이 유발).
- ❌ **agent 본업을 "뭐뭐 해라"로 절차 재지시 금지** — 판단 축·작업 흐름·완료 기준은 각 `agent.md` 가 소유한다. 메인은 컨텍스트·제약·사실관계만 넘기고 *어떻게 할지* 는 agent 가 정한다 (아래 [finding 수용 원칙](#finding-수용-원칙-점-패치-금지-근본-수정) 의 relay 와 동형 — "해법 메커니즘은 메인이 처방하지 말 것").
- ✅ **예외 — 미기록 결정**: 아직 어떤 SSOT 문서에도 적히지 않은 결정 (예: 기술 스택 그릴미 합의) 은 prompt 에 담되 (= 일회성 전달 채널), 그 결정을 SSOT 문서에 기록하도록 해당 agent 에게 지시한다 (문서 = 영구 진본).
- 위 4요소·금지는 *의미* 규약이다 — hook 으로 차단(block)하지 않는다 (출력·handoff 형식은 agent 자율, [`CLAUDE.md` 강제 원칙](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)). 강제는 아니지만, 메인이 4요소를 빠짐없이 담고 *방법 처방* 을 흘려넣지 않도록 **권장 슬롯 템플릿** 을 제공한다 — [`agent-prompt-slots.md`](templates/agent-prompt-slots.md) 가 슬롯 헤더 + 칸 내 가드로 layer-by-layer 지시를 억제하는 것과 같은 위상. 슬롯은 메인이 *쓰는 입력* 형식 권고일 뿐, agent 의 출력·작업 방식 자율은 건드리지 않는다.

##### 권장 슬롯 템플릿

호출 prompt 는 [`agent-prompt-slots.md`](templates/agent-prompt-slots.md) 의 3슬롯으로 쓴다 (강제 아님 — 권고). entrypoint·stage(impl/design) 무관하게 동형이고, 슬롯 1 의 *내용물* 만 호출마다 바뀐다.

- 슬롯 1 ↔ 4요소 (1)(2)(4), 슬롯 2 ↔ worktree MUST(아래), 슬롯 3 ↔ 4요소 (3) + 미기록 결정 예외. 4요소를 줄인 게 아니라 *담는 칸* 을 고정한 것이다.
- `이 호출 특유` 칸이 방법 처방을 막는 가드다 — 채울 게 없으면 비우고, 채워도 "무엇" 까지만 적는다.
- **진본 충실 시 수렴**: module-architect 산출물(impl task 파일)이 인터페이스·수용기준 통과조건·테스트 스켈레톤·Scope 까지 담으면, 호출은 포인터+worktree(+미기록 사실 한 줄)로 수렴한다. agent 본업(RED·lint·결론 형식)이나 진본 사본(AC 통과조건·Scope·인터페이스 시그니처)을 prompt 에 다시 적으면 슬림 포인터 규약 위반이다 — 진본이 진본임을 prompt 가 명시하면서 그 사본을 욱여넣는 자기모순.
- direct의 main-direct 구현은 sub-agent 호출 자체가 없어 본 슬롯 대상이 아니다. 복잡 `/impl`과 `/impl-loop`의 build-worker 시작은 별도 slim prompt 계약이고, 본 슬롯은 GREEN 이후 validator/acceptance 호출에 적용된다.

**worktree 활성 시 worktree 절대 경로 전달 — MUST**: foreground Claude Agent는 SubagentStart hook, headless worker는 wrapper가 worktree 절대경로를 첫 prompt에 직접 넣는다. main repo abs path 사용 금지 — 머지 전 옛 코드 read 로 false positive가 난다. hook/wrapper가 동적 경로를 전달하므로 메인이 Bash stdout을 다시 prompt로 relay하지 않는다.

**자유서술 방식** (이슈 #280/#284): end-step stdout = `PROSE_LOGGED`. 메인 Claude 가 prose 자체 (`<run_dir>/<agent>[-<mode>].md`) 를 직접 읽고 다음 호출을 판단한다 — 호출한 loop skill 의 `<skill>-routing.md` (분기 규칙 진본) 참조. 결정 못 하면 사용자에게 위임 (prose 본문에 "결정 불가" 명시 — issue #392: routing_telemetry cascade marker 폐기, 자연어 위임만).

#### 결과 echo + 평가 — MUST (5~12줄)

```
[<task-id>.<agent>] echo

▎ <prose 의 ## 결론 / ## Summary / ## 변경 요약 섹션 본문 5~12줄>
▎ <섹션 부재 시 prose 첫 5~10줄 fallback>
▎ <필요 시 추가 본문 인용 — 12줄 상한>

결론: <ENUM>
평가: PASS / REDO_SAME / REDO_BACK / REDO_DIFF — <사유>
```

- `<task-id>` = step 이름. `/impl-loop` build-worker는 Task UI가 아니라 story runner state와 ledger receipt를 사용한다.
- `▎` 글자 (U+258E) 그대로 — 사용자 인식 패턴
- 5줄 미만 / 12줄 초과 = 룰 위반

**평가 기준**: 에이전트 결과를 받으면 바로 다음 step으로 넘어가지 않고 충분한지 먼저 판단한다. 미진한 결과를 통과시키면 다음 step이 그 위에 쌓여 나중에 더 큰 redo 비용이 발생한다.

| 평가 | 의미 |
|---|---|
| `PASS` | 결과 충분, 다음 step 진입 |
| `REDO_SAME` | 같은 접근으로 재시도 |
| `REDO_BACK` | 이전 step으로 돌아가 재실행 |
| `REDO_DIFF` | 다른 접근 / 다른 에이전트로 재시도 |

REDO 판단 신호: 결과가 질문에 제대로 답하지 못함 / 같은 tool 5회+ 반복 / boundary 위반 stderr / 기대 enum 불일치. 루프 순서 변경도 자유 — system-architect / module-architect 재실행 등 적극.

**echo 안티패턴**: ❌ 압축 paraphrase 1~2줄 / ❌ table / code block 통째 생략 / ❌ 결론만 echo / ❌ 평가 줄 빠뜨리기.

#### 자가 점검 (TaskUpdate(completed) 전)

```
□ prose read 했는가?
□ ## 결론 / ## Summary / ## 변경 요약 섹션 우선 추출했는가?
□ 5~12줄 echo 했는가?
□ 결론 enum + 평가 포함됐는가?
```

#### helper 안전망 (자동 검출)

- **drift WARN**: live.json `current_step` 과 `args.agent` 불일치 → stderr WARN
- **step count WARN**: `finalize-run --expected-steps N` row count 미달 → stderr WARN
- 자동 보정 X — 메인이 사후 인지 + `/run-review` 진단

### step 명명 + prose 파일 자동 명명

**step 명명 규칙**: 명시적 helper lifecycle은 `agent mode` 두 인자 형식만 허용한다. mode 없는 foreground Claude Agent는 원칙적으로 hook-owned라 이 명령을 호출하지 않는다. 예외는 `acceptance_required=true` impl close의 mode 없는 `impl-validator`이며 candidate freeze를 위해 명시적 `begin-step`을 호출한다.

```bash
"$HELPER" begin-step <agent> [<mode>]
"$HELPER" end-step   <agent> [<mode>]
```

- `agent` — 소문자·하이픈만 (`^[a-z][a-z0-9-]{0,63}$`)
- `mode` — agent enum용 대문자·숫자·언더스코어(`^[A-Z][A-Z0-9_]{0,63}$`) 또는 skill 라벨용 소문자·숫자·하이픈(`^[a-z][a-z0-9-]{0,63}$`, 단 occurrence suffix 와 충돌하는 `-<숫자>` 끝맺음 제외)
- 콜론 표기 금지 — `"build-worker:retry-1"` 형식은 `_validate_agent` 거부 → prose 미기록

**prose 파일 자동 명명** (PostToolUse hook 이 `signal_io.signal_path` 기준 결정):
- 단순: `<run_dir>/<agent>.md`
- mode 보유: `<run_dir>/<agent>-<mode>.md`
- 같은 (agent, mode) N번째 반복: `<run_dir>/<agent>[-<mode>]-N.md` (occurrence 카운터 자동 충돌 처리)

| 상황 | begin/end-step | 생성 파일 |
|---|---|---|
| build-worker 재시도 1회 | `begin-step build-worker retry` | `build-worker-retry.md` |
| build-worker 재시도 2회 | `begin-step build-worker retry` | `build-worker-retry-1.md` |
| impl-validator 재리뷰 | `begin-step impl-validator retry` | `impl-validator-retry.md` |
| `/design` epic batch | `begin-step module-architect epic-batch` | `module-architect-epic-batch.md` |

headless wrapper의 동일-provider bounded recovery는 같은 active outer step 안에서 이어지고, 최종 성공 wrapper가 대응 `end-step`을 한 번 기록한다. terminal 실패 뒤 별도 rework launch를 열 때만 implementation chain이 새 outer `begin-step`을 만든다. 메인은 어느 경우에도 lifecycle 호출을 추가하지 않는다. Claude Agent 재호출은 mode가 있을 때만 명시적 begin-step을 다시 열고, mode 없는 foreground 경로는 lifecycle hook이 occurrence를 관리한다. 단, `acceptance_required=true` impl close의 validator 재호출은 위 candidate freeze 예외에 따라 명시적 `begin-step`을 다시 연다. `--prose-file` 명시적 전달은 wrapper/helper override로 허용한다.

**안티패턴** (begin/end-step 쌍 누락): ❌ build-worker local commit 후 git status 확인 → end-step skip / ❌ FAIL 후 build-worker rework 호출 시 begin/end-step 미포함 / ❌ end-step 보류 중 다음 step 진입으로 망각 / ❌ task 간 보고 작성 후 begin-step 재호출 누락.

### build-worker phase prose (`/impl-loop` Hybrid A 한정)

build-worker 는 한 sub-agent 호출(= 메인 outer step) 안에서 3 phase (test → impl → validate) 를 직렬 진행하며 phase prose (`build-test.md` / `build-impl.md` / `build-validate.md`) 를 *자체 Write* 한다. phase prose는 inner 작업 증거이지 outer Agent lifecycle receipt가 아니다. worker가 phase마다 outer `begin-step`/`end-step`을 다시 호출하거나 phase prose를 outer completion으로 append하면 중복 기록이다. outer Claude Agent는 SubagentStart/PostToolUse가 1쌍으로 기록하고, headless worker는 chain `step_started` + wrapper `step_completed` 한 쌍으로 기록한다. phase 분할·각 phase 책임·검증 항목 풀스펙은 [`build-worker-agent.md`](agents/build-worker/build-worker-agent.md)가 소유한다.

phase prose 실제 기록 디렉토리 = wrapper가 prompt에 주입하는 canonical absolute run directory (`.claude/harness-state/.sessions/<sid>/runs/<run-id>`). linked worktree 안에서 같은 상대경로를 다시 계산하거나 `phases/<RUN_ID>/`를 만들지 않는다. build-worker 는 PASS 전에 phase prose 3개를 쓴 뒤 실존을 확인하고, chain-owned wrapper도 PASS terminal receipt 전에 다시 검사한다.

선택적 polish/retry 기록이 필요하면 `build-polish.md` 도 같은 run_dir 에만 둔다. clean 게이트가 요구하는 필수 phase prose 는 `build-test.md` / `build-impl.md` / `build-validate.md` 3개다.

### ENUM 분기

**공통 골격만 본 문서 책임** — agent 결론이 그 loop 의 advance enum (해당 skill `## Loop` 의 `advance`) 이면 다음 step 진행, **마지막 step 이면 사용자 대기 없이 즉시 Step 7 (end-run)**. 그 외 결론 (`FAIL` / `*_ESCALATE` / `SPEC_GAP_FOUND` / `TESTS_FAIL` / `AMBIGUOUS` 등) → 다음 호출·재시도·cycle 한도·escalate 판정은 **각 loop skill 의 `<skill>-routing.md` 가 진본** ([`impl-routing.md`](../../skills/impl/impl-routing.md) / [`design-routing.md`](../../skills/design/design-routing.md) / [`impl-loop-routing.md`](../../skills/impl-loop/impl-loop-routing.md) / [`ux-routing.md`](../../skills/ux/ux-routing.md) / [`tech-review-routing.md`](../../skills/tech-review/tech-review-routing.md)). loop-procedure 는 enum→처리 표를 재서술하지 않는다.

### retry / rework 분기 시 task 재활용 (MUST)

**재시도 / 재호출 / cycle / rework** 분기 (각 `<skill>-routing.md`) 로 진입할 때, 신규 `TaskCreate` 금지 — *기존 task 를 `in_progress` 로 되돌린다*.

| 분기 | 재활용 대상 task | 행동 |
|---|---|---|
| `TESTS_FAIL` → build-worker rework | 직전 build-worker task | `TaskUpdate(<task>, in_progress)` |
| impl-validator `FAIL` → root-cause 수정 | 직전 impl-validator task 또는 main fix task | `TaskUpdate(<task>, in_progress)` |
| rework 후 impl-validator 재실행 | 직전 impl-validator task | `TaskUpdate(<task>, in_progress)` |
| `VALIDATION_BLOCKED` → permission receipt면 사용자 승인·Codex 1회 제한 재시도, 아니면 메인 검증 대행 후 build-worker rework | 직전 build-worker task | `TaskUpdate(<task>, in_progress)` |
| architecture-validator final `FAIL: SYSTEM_BOUNDARY` → system checkpoint | 직전 system-architect task 또는 새 opt-in checkpoint task | `TaskUpdate(<task>, in_progress)` 또는 checkpoint task 생성 |
| architecture-validator final `FAIL: TASK_LOCAL` → module-architect 재진입 | 직전 module-architect task | `TaskUpdate(<task>, in_progress)` |
| ux-architect self-check FAIL → ux-architect 재진입 | 직전 ux-architect task | `TaskUpdate(<task>, in_progress)` (prose 내부 cycle — 별도 task X) |
| `AMBIGUOUS` 재호출 1회 | 직전 동일 agent task | `TaskUpdate(<task>, in_progress)` |
| `SPEC_GAP_FOUND` → module-architect (보강) | 신규 task (다른 agent) | `TaskCreate` 가능 |

이유: retry / rework 는 *동일 step 의 재실행*. 신규 TaskCreate 시 같은 step 이 task list 에 중복 등장 → 진행 추적 오염. cycle 카운터는 step occurrence (`<agent>[-<mode>]-N.md`) 로 보존되므로 task 는 1개로 유지. provider wrapper 가 `end-step` 을 대신 호출해도 retry counter 의 소유자는 메인이다. 메인은 해당 loop 의 `<skill>-routing.md` counter key 로 세며, finding 분류·파일·provider 변경만으로 같은 retry 경로의 counter 를 나누거나 리셋하지 않는다.

Claude Agent 와 Codex wrapper 모두 메인이 집계한다. Codex wrapper 는 end-step 까지 수행하지만 counter 소유자가 아니다.

**MUST 순서** (retry / rework 진입 시):

```
TaskUpdate(<기존 task>, in_progress)   # 신규 TaskCreate 금지
"$HELPER" begin-step <agent> <mode>    # modeful Claude만 메인이 명시
Agent(...)                              # mode 없음: begin/end 모두 lifecycle hook 소유
# headless는 chain begin + wrapper end, foreground Claude Agent는 PostToolUse가 완료
TaskUpdate(<기존 task>, completed)
```

### finding 수용 원칙: 점 패치 금지, 근본 수정

validator (`impl-validator` / `architecture-validator`) 의 FAIL finding·수정 권고는 **"그 점/그 줄만 고쳐라"가 아니다.** 권고가 나온 *의미* = finding 이 가리키는 **근본 원인을 파악해 그 영역을 재설계하라** 이다.

- **메인 (relay)**: 재진입 prompt 에 finding 을 "이 점만 고쳐"로 좁게 전달 금지. finding 이 구조적 누수의 *증상*인지 먼저 판단 → 증상이면 "근본 원인 + 증상 패턴 전체"를 주고 "이 접근을 재설계하라"로 프레이밍한다. **같은 영역 finding 이 2회+ 반복 = 점 패치 신호 → 즉시 근본 재설계로 전환** (위 REDO 분류의 `REDO_DIFF` 와 정합 — 같은 접근 재시도가 아니라 접근 자체 교체). 해법 메커니즘은 메인이 처방하지 말 것 — 증상·사실관계만 넘기고 설계 소유는 producer agent 가 갖는다.
- **producer (설계 agent / build-worker)**: finding 수신 시 점 패치 전에 "더 깊은 설계 문제의 신호인가?"를 먼저 본다. 신호면 점이 아니라 접근을 재설계한다. 재설계가 상위 산출물 (architecture / decisions / conventions / domain-model 등) 을 건드리면 직접 편집하지 말고 변경점을 prose 로 보고 → 메인이 상위 agent 로 분기 (각 `<skill>-routing.md` 의 retry 경로).
- **이유**: 점 패치는 finding cascade 를 부른다 — 좁은 수정이 다음 결함을 드러내 같은 영역 FAIL 이 N 라운드 반복. 한 번의 근본 재설계 < N 번 점 패치 + N 번 재검증. 같은 영역을 점 패치로 retry 한도 ([design-routing](../../skills/design/design-routing.md#retry-한도) / [impl-loop-routing](../../skills/impl-loop/impl-loop-routing.md#retry-한도)) 까지 소진하지 말 것.

### yolo 모드

발화에 `yolo` / `auto` / `끝까지` / `막힘 없이` / `다 알아서` 키워드 시 ON — 평소 사용자 위임할 신호를 자동 진행한다. yolo↔비-yolo 케이스별 동작은 cross-cutting 운전 규칙이라 본 문서가 SSOT (각 `<skill>-routing.md` 의 enum→호출 매핑과 별개):

| 상황 | 비-yolo | yolo |
|---|---|---|
| soft `*_ESCALATE` / `AMBIGUOUS` | 사용자 위임 | `auto-resolve` 적용 |
| `SPEC_GAP_FOUND` | 사용자 위임 | module-architect (보강 케이스) cycle (≤2) |
| `TESTS_FAIL` / impl-validator `FAIL` | 재시도 (≤3) | 동일 |
| build-worker `TESTS_FAIL` | build-worker rework (≤3) | 동일 — 새 context window 가능 |
| impl-validator `FAIL` | 사용자 위임 또는 root-cause 수정 | root-cause 수정 + 재리뷰 (≤3) |
| 승인-gated 산출물 최종 승인 (`/design`, `/ux`) | 사용자 승인 | 동일 (yolo 우회 X) |
| Step 7 주의사항 (NICE TO HAVE only, MUST FIX 0) | 사용자 위임 | 7a 자동 |
| 중대 차단 룰 | hard safety | hard safety (yolo 우회 X) |

auto-resolve 의 실제 action, hint, next_enum 매핑 진본 = helper 코드 `session_state.py`:

```bash
RESOLVE_JSON=$("$HELPER" auto-resolve "<agent>:<enum_or_mode>")
# JSON: {"action":..., "hint":..., "next_enum":...} — unmapped 시 yolo 도 사용자 위임 fallback
```

---

## impl-task-loop commit 구조

`impl-task-loop` / `impl-ui-design-loop` 은 task 단위 local commit 을 **build-worker** 가 만들고, push / PR 생성 / PR merge / issue mutation 은 **메인 Claude** 가 전담한다. 본 절은 *시점·포함 파일* 만 정의하고, **브랜치·커밋·PR 네이밍 + 트레일러 판정 규칙은 [`git-spec.md`](git-spec.md) 가 SSOT** 다.

| 시점 | 내용 |
|---|---|
| runner `plan/init` | path 정렬 뒤 동일 frontmatter `story` 값의 비연속 재등장을 state 변경 전에 차단하고 관련 task 경로를 보고한다. runner 는 story 순서를 임의 재정렬하지 않는다. |
| build-worker PASS 직후 | task local commit sha 확인 + `dcness-story-runner mark --status completed --commit <sha>` |
| 한 story 의 task 전부 completed | story branch tip/base 봉인. PR 없이 다음 story branch를 직전 story branch tip에서 재분기 |
| 모든 target task completed | 자동 journey면 worker 실행 컨텍스트 수렴 호출 → final mutation owner Cartography sync/no-op → tree-preserving consolidate → candidate freeze |
| frozen candidate | 반대 진영 holistic impl-validator(Sanity 렌즈 포함)를 먼저 실행 |
| validator PASS | 같은 candidate에서 close 단위 product-acceptance sealed Journey 실행 |
| validator·acceptance 둘 다 PASS + target issue AC audit PASS | story/조건부 QA PR 최초 생성. 그 뒤 사용자 승인 시 main 리타겟·리베이스 후 merge 결정 대기 |

> `docs/.../impl/NN-*.md` 는 `/design` 산출물이 *미리 머지* 된 상태 — impl-task-loop 안에서 별도 commit X. fallback 모드 (정식 위치 부재) 는 module-architect 산출물을 본 PR src commit 에 같이 포함.

> **task commit = build-worker boundary only** — 이 invariant 의 진본은 *권한 경계* 다: impl 루프 worktree 의 변경은 build-worker 권한 경계([`agent_boundary.py`](../../harness/agent_boundary.py) ALLOW_MATRIX = `src/**` / test 계열)상 구현·테스트 파일뿐이라, stories.md / backlog.md 등은 애초에 worktree 에 안 들어온다. 진행 추적은 task commit sha + story PR body 트레일러 (Part of / Closes) + GitHub sub-issue API 가 SSOT.

규칙은 전부 git-spec 위임 — loop-procedure 는 판정 로직(브랜치명·base·트레일러)을 재서술하지 않는다:

- **브랜치명** = [`git-spec.md` 브랜치](git-spec.md#브랜치) (결정 절차 = [`skills/impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md)).
- **base** = [`git-spec.md` story 브랜치 스택](git-spec.md#story-브랜치-스택) (첫 story=main, 이후 story=직전 story branch, merge 시 main 리타겟·리베이스).
- **PR body 트레일러 (Part of vs Closes) 판정** = [`git-spec.md` PR 트레일러](git-spec.md#pr-트레일러-part-of-closes) 의 story/base 분기.
- **실행** = task·수렴 commit과 선택 consolidate가 이미 끝난 clean branch이므로 repo git-spec의 `git push -u origin <branch>` + `gh pr create --base <base>`를 사용한다. [`scripts/pr-create.sh`](../../scripts/pr-create.sh)는 working tree 변경을 add+commit하는 helper라 이 clean cut 경계에는 사용하지 않는다. body-file은 메인이 위 트레일러 규칙대로 작성한다.

### Step 7a (impl-task-loop)

story 경계에서는 branch tip/base만 봉인하고 PR을 만들지 않는다. 다중 story/epic도 다음 branch를 직전 story branch에서 만들며, final tip 수렴·review/acceptance/AC audit/consolidate 뒤 clean stack에서 최초 PR을 cut한다. 모든 PR에 자동 merge 금지 규칙을 적용하며 사용자가 유일한 merge gate다.

---

## Step 7 — finalize-run + clean 매트릭스 + commit/PR

### end-run 호출 (issue #396 — 단일화)

> **트리거**: 마지막 step advance enum 확인 직후 사용자 대기 없이 즉시 호출 — 루프 종류 무관.

```bash
"$HELPER" end-run
```

end-run 안전망 (`session_state.py`) 이 자동으로 `finalize-run --auto-review` 발사 → in-process `harness.run_review` → STATUS JSON + review.md.

- review 결과는 `<run_dir>/review.md` 에 저장 + stderr `[REVIEW_READY] <path>` 신호 출력. 메인 Claude 가 [Step 8 — review 결과 인지](#step-8-review-결과-인지) 따라 세션에 그대로 출력 의무.
- review.md 에는 `CLAUDE.md/AGENTS.md 현행화 후보` read-only 섹션이 포함된다. 이는 대표 workflow 종료 시 세션 학습 환류 후보를 보여주는 권고이며, CLAUDE.md/AGENTS.md 를 자동 수정하지 않는다.

### STATUS JSON 구조

```
{
  run_id, session_id,
  steps[{agent, mode, enum, must_fix, prose_excerpt}],
  has_ambiguous, has_must_fix, step_count
}
```

### clean 판정 매트릭스

다음 모두 충족 → **clean** (자동 7a), 아니면 **7b (주의사항)**:
1. `has_ambiguous == false` && `has_must_fix == false`
2. step enum 이 해당 skill `## Loop` 의 advance/expected_steps 와 정합
3. git 안전 가드: `git status --porcelain` 에 `.env` / `secrets.*` / `credentials.*` 없음 · unstaged + untracked ≤ 10 · submodule 변경 없음

이 공통 매트릭스는 issue close 계약을 대체하지 않는다. `/impl-loop` 이 target GitHub issue 를 닫는 경우 [`impl-loop-routing.md`](../../skills/impl-loop/impl-loop-routing.md)의 clean 판정에 따라 typed AC 전항목 충족·체크와 `require-complete`의 정확한 `PASS`까지 추가로 만족해야 clean 이다. checklist 밖 사람 확인 항목은 human verification 완료 전까지 merge를 멈춘다.

**verify-only 예외 (`/impl-loop`)**: `impl-validator:VERIFY_ONLY` prose 가 `PASS`이고 prose 안에 검증 명령 exit 0 + `git status --porcelain` 변경 0 증거가 있으면, step 1개 + PR 0개도 clean 이다. 이 예외에서는 `pr-create.sh` 를 호출하지 않는다.

### 7a — Clean commit/PR

> **impl-task-loop 제외**: [impl-task-loop commit 구조](#impl-task-loop-commit-구조) 에서 branch/commit/push/PR 이미 완료 → Step 7a = merge only.

clean 판정은 commit 가능 상태를 뜻하지만, 사용자 승인-gated 산출물의 승인까지 대신하지 않는다. `/design` 과 `/ux` 처럼 사용자가 산출물을 검수해야 하는 loop 는 해당 skill 의 사용자 최종 설계 승인 또는 확정본 승인 checkpoint 를 먼저 닫는다. 승인 응답 전에는 `git add`, `git commit`, `git push`, `gh pr create`, `$PLUGIN_ROOT/scripts/pr-finalize.sh` 를 호출하지 않는다.

승인-gated 가 아니거나 승인 checkpoint 가 이미 닫힌 clean loop 는 branch (`<prefix>/<short-slug>`, prefix = 해당 loop 의 branch_prefix — [`git-spec.md` 브랜치](git-spec.md#브랜치) valid 패턴) → **변경 파일 commit** → push → PR create → merge → default worktree sync/cleanup 으로 진행한다. **commit 대상 = 해당 loop 가 실제 변경한 파일** — design = `docs/**` 설계 산출물, ux = epic `ux-flow.md`, `docs/design.md`, `docs/design-variants/<screen-id>.html`, `docs/design-variants/canvas.html`, 필요 시 `docs/design-variants/_lib/**` seed 라 src-only 아님 (src-only 제한은 impl-task-loop 전용, [impl-task-loop commit 구조](#impl-task-loop-commit-구조)). **stray untracked 휩쓸기 주의**: impl 루프와 달리 비-impl loop 은 worktree 권한 경계가 src-only 가 아니고 clean 매트릭스가 untracked ≤ 10 을 허용하므로, `pr-create.sh` 의 `git add -A` 는 무관한 로컬 아티팩트까지 stage 한다 → 호출 *전* 산출물 외 파일을 정리하거나, 해당 loop 산출물만 명시 pathspec 으로 직접 stage 후 commit. 네이밍·본문·트레일러 = [`git-spec.md`](git-spec.md), 커밋 trailer 의 모델 표기는 글로벌 `~/.claude/CLAUDE.md` 기준. 실행 = `$PLUGIN_ROOT/scripts/pr-create.sh` + `$PLUGIN_ROOT/scripts/pr-finalize.sh`.

worktree 진입 시 [worktree 분기](#worktree-분기-action-루프-한정) 의 커밋 diff 흡수 + working tree clean 검사를 완료한 뒤 `ExitWorktree(action="<keep|remove>")` 를 호출한다.

### 7b — 주의사항 확인

```
[<entry>] 완료 (주의사항)
- run_id: $RUN_ID · 변경: <src/ 변경 파일>
- prose 종이: .claude/harness-state/.sessions/{sid}/runs/$RUN_ID/

⚠️ 주의사항: <has_ambiguous / has_must_fix / unexpected enum / sensitive untracked>

📝 메모리 후보 (#149):
- <주의사항 발생 사유의 회고 — feedback / project type 후보. 다음 세션 회귀 방지용>
- <waste finding 의 반복 패턴 (예: ECHO_VIOLATION 2회+, MISSING_SELF_VERIFY 등)>
- <impl-validator NICE TO HAVE 중 자주 등장하는 항목>
- 후보 없음 시 "없음" 1줄

커밋/PR 진행할까요? (branch → PR → regular merge 자동) + 메모리 저장 진행?
```

worktree 처리도 사용자 결정.

**메모리 후보 의무 (#149)**: 주의사항 발생 = 회귀 방지 신호. prose 본문에만 적고 끝내면 다음 세션에서 동일 주의사항 재발. 메인은 위 양식의 *📝 메모리 후보* 섹션을 *반드시* emit (없으면 "없음" 명시) — 사용자가 저장 여부 결정. 양식 없이 7b 보고 종료 = 룰 위반. 7a (clean) 도 review report 의 waste finding 이 있으면 같은 양식 적용.

**yolo 시**: `has_must_fix == false` + enum unexpected 만 (FAIL 1건 등) → 자동 7a 시도. `has_must_fix` 또는 `has_ambiguous` true → yolo 도 7b. yolo 라도 메모리 후보 양식은 emit (사용자 위임 X — 본인이 저장 후 진행).

---

## Step 8 — review 결과 인지

`--auto-review` stdout 자동 출력. 메인이 review 결과를 **세션에 직접 출력 — MUST**.

수동 호출 (auto-review 없이 실행됐을 경우):
```bash
"$(dirname "$HELPER")/dcness-review" --run-id "$RUN_ID" --repo "$(pwd)"
```

skip 금지 — 사용자 보고 전 1회 의무.

**세션에 직접 출력 — MUST**: Bash stdout 은 CC UI 에서 접힌 상태로 표시 (펼쳐야 보임). 리뷰 결과를 **텍스트 응답으로 그대로 복사**해서 출력한다.
- 섹션 생략 / 축약 / 재배치 금지
- 자체 해석 ("핵심은~", "정리하면~") 본문 사이 삽입 금지

**개선점 코멘트 — MUST**: 리뷰 출력 끝에 메인 Claude 가 1~3줄 코멘트 추가.

```
💡 이번 run 개선점:
- <이번 run 에서 발견된 반복 실수 / 낭비 요약>
- <다음 run 에서 주의할 점>
```

review 리포트의 must-fix / waste finding / per-Agent metric 즉시 인지 + 다음 run 회귀 방지에 활용. review_main 실패 (예외) 시 helper stderr WARN — STATUS JSON 자체는 정상 출력. 메인이 사후 인지 후 수동 `dcness-review` 1회 재시도 권장.

---

## run-ledger + receipt (resume / audit)

`begin-run` / lifecycle hook 또는 wrapper / `end-run` 은 prose 저장과 별개로 run_dir 안 `ledger.jsonl` 에 append-only event 를 자동 기록한다. prose 파일 (`<run_dir>/<agent>[-<mode>].md`) 이 계속 SSOT 이고, ledger 는 긴 prose 를 매번 대화 context 에 재주입하지 않고도 resume / handoff / audit 에 필요한 상태를 담는 색인 장부다. **agent 에게 JSON 출력 형식을 강제하지 않는다** — hook/helper가 저장된 prose + known state 에서 receipt 를 생성한다.

**자동 기록 event** (코드 경로):
- `run_started` (begin-run) — entry_point / issue_num / design_doc(기록 시)
- `step_started` (SubagentStart 또는 implementation chain `begin-step`) — agent / mode + Claude Agent면 tool_use_id / agent_id
- `step_aborted` (PostToolUseFailure·빈 prose·비완료 상태 복구) — false completion 없이 시작된 step을 닫는 진단 event
- `step_completed` (성공 PostToolUse 또는 wrapper `end-step`) — = **receipt**: agent / mode / enum / prose_excerpt / must_fix / prose_file / sha256 / evidence_paths / next_action(hint), Claude Agent면 tool_use_id / agent_id
- `run_finished` (end-run)

`ledger.jsonl` 의 `step_completed` receipt 는 read 시점에 `prose_file` 실존 + `sha256` digest match 를 strict 검증한다. 검증 실패 step 은 위조/손상으로 보고 소비처(`run-status` / `run-review` / finalize gate)에서 제외한다.

**PR lifecycle event**: `scripts/pr-create.sh` 는 PR 생성 성공 뒤 `pr_created`,
`$PLUGIN_ROOT/scripts/pr-finalize.sh` 는 merge 완료 확인 뒤 `pr_merged` 를 자동 기록한다. active
dcNess run 밖에서 호출되면 ledger 기록은 경고만 내고 PR 작업 자체는 계속된다.

**수동 checkpoint event** (메인/skill 이 `ledger-event` 로 — 강제 X):
`task_completed` / `blocked` / `validator_passed` / `validator_failed`.
`pr_created` / `pr_merged` 도 수동 보정이 필요할 때만 직접 기록한다.

```bash
"$HELPER" ledger-event pr_created --pr 588 --url <PR_URL>   # pr-create.sh 사용 시 자동
"$HELPER" ledger-event pr_merged --pr 588 --url <PR_URL>
"$HELPER" ledger-event blocked --reason "<사유>"
```

**resume 복원**: compaction/세션 재개 후 긴 prose 를 다시 읽지 말고 한 명령으로 진행 상태를 복원한다.
```bash
"$HELPER" run-status     # 현재 run 의 phase / task / last event / next action(hint) / evidence pointer
```
출력의 evidence pointer (prose 파일 경로) 로 필요한 prose 만 선택적으로 연다.

step 로그는 `ledger.jsonl` 의 `step_completed` event 로 단일화됐다. run-review / 진행 순서 검사 / Stop hook 은 모두 무결성 검증된 `step_completed` event 를 읽는다.

---

## 순서 차단 훅 정합

각 loop 의 entry_point / task_list / advance / expected_steps 진본 = 해당 skill 의 `## Loop` contract. 그 시퀀스가 중대 차단 룰을 자연 충족한다 — 순서 차단 훅 진본 = [`hooks.md`](hooks.md#catastrophic-gatesh) (`hooks/catastrophic-gate.sh` 강제): build-worker 직전 module-architect `PASS` enum 또는 동등 설계 산출물, 그리고 active run 의 lifecycle identity/mode 순서. `/design` greenfield thin bootstrap 이후 module-architect 진입과 opt-in system checkpoint 이후 module-architect 재진입은 별도 validator 게이트 없이 `skills/design/design-routing.md` 의 thin bootstrap / `SYSTEM_CHECKPOINT_REQUIRED` 흐름과 lifecycle identity/mode 검사로만 다룬다. (tech-review 진입 gate = PRD 변경 후 사용자 2 차 OK · `/design` 진입 후 tech-reviewer 재호출 비권장 = 코드 강제 아닌 자연어 관례.) hook 전체 시점·차단·우회 = [`hooks.md`](hooks.md).

---

## 참조

- 각 loop skill 의 `<skill>-routing.md` — 분기 규칙 / retry / escalate ([`impl-routing.md`](../../skills/impl/impl-routing.md) / [`design-routing.md`](../../skills/design/design-routing.md) / [`impl-loop-routing.md`](../../skills/impl-loop/impl-loop-routing.md) / [`ux-routing.md`](../../skills/ux/ux-routing.md) / [`tech-review-routing.md`](../../skills/tech-review/tech-review-routing.md)) · loop 진입 spec = 각 skill 의 `## Loop` contract
- [`hooks.md`](hooks.md) — hook 시점·차단·우회 SSOT
- 본 문서 [표준 1 step 시퀀스](#표준-1-step-시퀀스-per-agent-의무) + [Step 8 — review 결과 인지](#step-8-review-결과-인지) — echo / 자가점검 / REDO 분류 / 개선점 코멘트 (옛 dcness-rules §3/§4 흡수)
- `harness/session_state.py` — helper CLI (`begin-run` / `end-run` / `begin-step` / `end-step` / `finalize-run` / `run-dir` / `auto-resolve`)
- `harness/run_review.py` — review 엔진 (`--auto-review` 호출 대상)
- workflow skill 진입점 (input 정형화 + Loop 추천) — `skills/<skill>/SKILL.md` (예: impl-loop / design). 운영 보조 command 는 `commands/<command>.md`.
