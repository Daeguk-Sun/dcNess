# Loop Execution Procedure (메인 Claude loop 실행 절차)

> **Status**: ACTIVE
> **단일 목적**: **"메인 Claude 가 helper 기반 loop 실행 절차를 운전하는 법"** — `begin-run → [ begin-step → Agent → end-step → echo·평가 ] ×N → end-run → review echo`. dcness loop 공통 골격(복붙·drift 차단) + `harness/session_state.py` helper CLI 의 유일 사용 매뉴얼.
> **이건 여기 없음 (각 진본)**: loop 진입 spec (entry_point / task_list / advance / expected_steps) = 해당 skill 의 `## Loop` contract + 본문 (예: impl-task-loop = [`skills/impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md)). 결론→다음 호출·retry·escalate 분기 규칙 = 각 `<skill>-routing.md`. 순서 차단 훅 = [`hooks.md`](hooks.md#catastrophic-gatesh). 용어 기준 = [`terms.md`](terms.md). 브랜치·커밋·PR·트레일러 규칙 = [`git-spec.md`](git-spec.md).

---

## 진입 모델

skill 트리거 또는 직접 발화 → 메인 Claude 가 **해당 skill 의 `## Loop` contract + 본문 (entry_point / task_list / advance / expected_steps / 분기 규칙)** 보고 task 리스트 동적 구성 → 본 문서 Step 0~8 mechanics 따름.

- **skill 경유**: skill 본문이 loop spec 진본 (예: impl-task-loop = [`skills/impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md)). skill 은 input 정형화 + 분기 추천. 절차는 본 SSOT.
- **직접 발화** ("이거 impl 로 가자"): 각 loop skill 의 `## Loop` + `<skill>-routing.md` 보고 메인이 자율 구성. 단 `begin-run` 이후 active run 안의 `Agent` 호출은 아래 표준 1 step 시퀀스가 PreToolUse hook 으로 강제된다.
- **SessionStart inject** (#596): *최소 활성 안내만* 매 세션 노출 — dcness 활성 사실 + 코드 강제 gate 가 켜져 있다는 안내 + hook-first recovery 원칙. 문서 진입 매트릭스·절차·분기 규칙은 **미주입** (skill 진입 시 해당 skill 이 안내, 위반 복구는 각 blocking hook 메시지가 그 자리에서 제공). 첫 응답 첫 줄 `[dcness 활성 확인]` 토큰.

---

## Step 0 — worktree + begin-run

### worktree 분기 (action 루프 한정)

**worktree 격리로 산출물을 커밋하는 action 루프 (`/impl` · `/impl-loop` · `/design`) 진입 시 Step 0 에서 EnterWorktree 자동 호출** — 동시 다중 세션 충돌 회피 + 메인 working tree 보호. `/spec` / `/tech-review` / `/ux` / `/to-issue` (commit 없음) 는 commit 격리 목적 부재라 워크트리 X (메인 working tree 에서 직접 또는 별 branch). loop 별 적용 여부는 각 skill 본문 (예: [`impl/SKILL.md`](../../skills/impl/SKILL.md) · [`design/SKILL.md`](../../skills/design/SKILL.md) 워크트리 절 · [`impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md)).

```
EnterWorktree(name="<skill>-{ts_short}")   # action 루프 (impl / impl-loop / design)
```

- **거부 표현 시에만 건너뜀** — 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시 EnterWorktree 호출 0, 일반 cwd 그대로 진행.
- 수동 `git worktree add` 우회 금지 — CC permission 시스템이 EnterWorktree 만 자동 권한 처리. 수동 워크트리는 sub-agent Write 거부 회귀 (#255 W1). **예외 = 통합 브랜치 모드** ([base-ref 분기](#base-ref-분기-통합-브랜치-모드-424) — 사전 `git worktree add` 후 `EnterWorktree(path=)` 진입, CC 가 path= 도 권한 처리).
- **종료 시 ExitWorktree (squash 흡수 자동 분기)** — `main..<worktree-branch>` diff (`.claude` 제외) 가 비면 이미 머지 흡수된 것 → `ExitWorktree(action="remove", discard_changes=true)`, 남아있으면 `ExitWorktree(action="keep")`.

### base-ref 분기 (통합 브랜치 모드, #424)

**운전 원칙만 여기, 규칙은 git-spec.** epic 단위 stories.md 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 = 통합 브랜치 모드 → outer worktree base ref 도 integration branch 와 정합해야 한다 (`EnterWorktree(name=)` default `baseRef=fresh` = origin/main 이라 base mismatch → sub-PR diff 거대화 false). EnterWorktree 가 base parameter 미지원이라 사전 `git fetch origin <integration>` → `git worktree add -b <new> <path> origin/<integration>` → `EnterWorktree(path=<path>)` 로 진입한다. **fetch 선행 필수** — remote-tracking ref 미갱신 시 `origin/<integration>` 이 stale / unknown revision 이라 worktree add 실패 또는 stale base 로 sub-PR diff 거대화 재발.

- **base 값 판정 규칙** (`**Base Branch:**` 마커 → base, 없으면 main · checkout/PR base 둘 다 적용) = [`git-spec.md` Git 절차](git-spec.md#git-절차).
- **loop 별 적용** (epic 단위 stories.md 경로 유도 / chain outer 1회) = [`skills/design/SKILL.md`](../../skills/design/SKILL.md) · [`skills/impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md).
- **stale env 가드 (MUST)**: epic 단위 stories.md 경로 유도 시 `EPIC_DIR`(design) 와 `TASK_FILE`(impl-loop) 가 *둘 다* set 이면 (resume/chain) 두 경로가 같은 epic 의 stories.md 로 수렴하는지 검증 — 서로 다른 epic 을 가리키면 stale env 의심으로 **정지** (조용히 한쪽 택1 금지). 잘못된 epic 의 `**Base Branch:**` 로 worktree/PR base 가 어긋나는 사고 차단.

### begin-run

```bash
HELPER="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)/scripts/dcness-helper"
RUN_ID=$("$HELPER" begin-run <entry_point> [--issue-num N] [--design-doc <path>] [--acceptance-required])
echo "[<entry>] run started: $RUN_ID"
```

`<entry_point>` = 해당 skill 의 `## Loop` 의 `entry_point` 필드 (예: `impl`, `design`, `ux`). begin-run 동작: sid auto-detect + run_id 발급 + `live.json.active_runs` 슬롯 + `.by-pid-current-run/{cc_pid}` 씀.

`--design-doc <path>` — 이 run 이 참조하는 **머지된 설계 문서**(impl task 문서 / compact plan) 경로. 설계가 별도 run 에서 머지된 뒤 구현 run 으로 진입하는 흐름(예: `/impl-loop` 풀 4-agent)에서 기록하면, engineer 게이트가 같은-run module-architect PASS 의 등가 사전 조건으로 인정한다 ([`hooks.md` 순서 차단 훅](hooks.md#catastrophic-gatesh)). `entry_point=impl` 전용이며, 설계 산출물 규약 경로(`docs/milestones/**` / `docs/compact-plans/**` / `docs/bugfix/**`)의 실존 `.md` 만 허용 — 아니면 begin-run 이 fail-fast 거부한다. 기록값은 resolve 된 절대경로(hook 프로세스와 cwd 가 달라도 안전). chain 의 다음 task 진입은 `next-task --design-doc <path>` 로 동일 기록.

`--acceptance-required` — story/epic 마감 task 처럼 `pr-reviewer` 뒤 inline `product-acceptance` 를 거쳐야 run 이 정상 종료되는 경우에만 기록한다. Stop hook 은 이 marker 가 있는 `entry_point=impl` run 에서 `pr-reviewer` 를 종료 agent 로 취급하지 않고 product-acceptance 진입 turn 을 재발화한다. 중간 task / `--no-acceptance` run / verify-only run 은 이 플래그를 주지 않는다. chain 의 다음 task 진입은 `next-task --acceptance-required` 로 동일 기록한다.

> `/impl-loop` 의 **chain 모드(N task)** 는 자기 run 을 갖지 않는 driver 다 — `impl-task-loop × N` 이므로 각 task 가 독립 `begin-run impl` … `end-run` run 1개씩 (N task = N run = N review.md). **single 모드(1 task)** 는 `impl` entry_point 로 run 1개. 자세히 = [`/impl-loop`](../../skills/impl-loop/SKILL.md).

---

## Step 1 — TaskCreate

해당 skill 의 `## Loop` 의 `task_list` 필드대로 일괄 등록. **단 `/impl-loop` chain 모드 아래의 `impl` run 은 TaskCreate skip** — task 리스트는 impl-loop skill 이 진행 뷰로 일괄 관리한다 ([진행 뷰](../../skills/impl-loop/SKILL.md#진행-뷰-task-리스트)). impl run 은 이미 생성된 sub-step task 를 TaskUpdate 만 한다.

```
TaskCreate("<agent>: <mode 또는 짧은 설명>")
... (loop 정의 수만큼)
```

---

## Step 2~N — agent 호출 골격

### 표준 1 step 시퀀스 (per-agent 의무)

```
TaskUpdate("<task>", in_progress)
"$HELPER" begin-step <agent> [<MODE>]
Agent(subagent_type="<agent>", mode="<MODE>", description="...")  # 또는 validation provider 분기
"$HELPER" end-step <agent> [<MODE>]   # 자유서술 방식(stdout=PROSE_LOGGED). Codex wrapper 경로는 wrapper 가 호출
# 의무 echo (5~12 줄) — 아래 "결과 echo + 평가" 섹션
TaskUpdate("<task>", completed)
```

begin-step stdout 에 `[INSIGHTS: <agent>/<mode>]` 또는 `[PREVIOUS_TASKS]` 섹션이 있으면 Agent prompt 끝에 그대로 포함시킨다.
- `[INSIGHTS]` — 해당 agent 의 과거 루프 학습 ("하지 말 것" / "잘 됐던 것"), 프로젝트 레벨 누적.
- `[PREVIOUS_TASKS]` — `/impl-loop` chain 의 직전 task 산출 요약 list (build-worker 진입 시만, #525). 인접 task 인터페이스 정합 참고용 — build-worker 가 phase 3 통과 시 `prev-tasks-append` 로 자기 산출을 누적한 것.

active run(`entry_point=design|impl|ux`) 안에서 `begin-step` 없이 `Agent` 를 직접 호출하거나, `begin-step` 의 agent/mode 와 다른 `Agent` 를 호출하면 PreToolUse hook 의 진행 순서 검사가 호출 전 차단한다. 정상 `/design` 은 `begin-run design` 로 시작하며 같은 gate 를 탄다. Agent 결과가 hook 에 의해 staged 된 뒤에는 반드시 `end-step` 으로 기록하고 다음 `begin-step` 으로 넘어간다.

메인이 prose를 직접 Write 할 필요 없음 — PostToolUse Agent hook 이 sub 종료 시 `tool_response.text` 에서 prose 를 자동으로 `<run_dir>/<agent>[-<MODE>].md` 에 저장하고 `live.json.current_step.prose_file` 에 경로 기록. `end-step` 이 이 경로를 자동 읽는다.

**validation provider 분기 (local opt-in)**: `code-validator` / `architecture-validator` / `pr-reviewer` 는 호출 직전 provider 를 resolve 한다.

```bash
PROVIDER=$("$HELPER" routing resolve <agent>)
if [ "$PROVIDER" = "codex" ]; then
  "$PLUGIN_ROOT/scripts/dcness-codex-validator" <agent> [MODE] --prompt-file "$PROMPT_FILE"
else
  Agent(subagent_type="<agent>", ...)
  "$HELPER" end-step <agent> [MODE]
fi
```

Codex wrapper 는 설치된 `dcness-<agent>/SKILL.md` 내용을 prompt 에 직접 포함한 뒤 `codex exec -C "$PROJECT_ROOT" -s read-only` 로 실행한다. 마지막 응답은 `/tmp` prose 파일에 받은 뒤 `dcness-helper end-step <agent> --prose-file ...` 로 저장한다. 따라서 Codex 분기 경로에서는 메인이 별도 `end-step` 을 한 번 더 부르지 않는다. 분기 config 파일명은 `routing.json` 이고 repo 파일이 아니라 `~/.claude/plugins/data/dcness-dcness/routing.json` 에 있으며, 비활성/미설정 기본값은 Claude 다.

#### 호출 prompt 슬림 포인터 규약

**MUST.** 호출 직전 해당 `agent.md` 의 "입력" / "호출자가 prompt 로 전달하는 정보" 항목 read 후 prompt 작성 (형식 자유, 정보 명시 의무). prompt 에는 **(1) 읽을 SSOT 문서 포인터 (agent 가 자체 read 할 경로) (2) 대상 단위 (어떤 task / Story / 모듈) (3) 그 호출에 특유한 제약·주의 (4) 산출 경로·번호 규약·write 경계** 만 담는다.

- ❌ **이미 SSOT 문서에 기록된 결정의 사본을 prompt 에 재기입 금지** — 합의 스택·계약·설계 결정은 agent 가 자기 "먼저 읽을 문서" 규약대로 SSOT 문서를 직접 읽어 획득한다. 같은 결정이 prompt 와 문서 두 곳에 살면 진본이 둘이 되어, 한쪽만 갱신될 때 어느 쪽이 맞는지 모르는 drift 가 생긴다 (dcNess 가 본래 막으려는 사본 drift 를 절차 자신이 유발).
- ❌ **agent 본업을 "뭐뭐 해라"로 절차 재지시 금지** — 판단 축·작업 흐름·완료 기준은 각 `agent.md` 가 소유한다. 메인은 컨텍스트·제약·사실관계만 넘기고 *어떻게 할지* 는 agent 가 정한다 (아래 [finding 수용 원칙](#finding-수용-원칙-점-패치-금지-근본-수정) 의 relay 와 동형 — "해법 메커니즘은 메인이 처방하지 말 것").
- ✅ **예외 — 미기록 결정**: 아직 어떤 SSOT 문서에도 적히지 않은 결정 (예: 기술 스택 그릴미 합의) 은 prompt 에 담되 (= 일회성 전달 채널), 그 결정을 SSOT 문서에 기록하도록 해당 agent 에게 지시한다 (문서 = 영구 진본).
- 위 4요소·금지는 *의미* 규약이다 — 고정 헤더·형식으로 강제하지 않는다 (출력·handoff 형식은 agent 자율, [`CLAUDE.md` 강제 원칙](../../CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)).

**worktree 활성 시 worktree 절대 경로 prompt 에 추가 명시 — MUST**: cwd 가 `.claude/worktrees/<name>/` 안이면 sub-agent prompt 에 worktree 절대 경로 명시. main repo abs path 사용 금지 — 머지 전 옛 코드 read 로 false positive (CC #31546 / #48096). 근거: CC Task tool 에 cwd parameter 부재 (#12748), subagent frontmatter cwd field 부재 (#31940) — 메인이 명시 책임.

**자유서술 방식** (이슈 #280/#284): end-step stdout = `PROSE_LOGGED`. 메인 Claude 가 prose 자체 (`<run_dir>/<agent>[-<MODE>].md`) 를 직접 읽고 다음 호출을 판단한다 — 호출한 loop skill 의 `<skill>-routing.md` (분기 규칙 진본) 참조. 결정 못 하면 사용자에게 위임 (prose 본문에 "결정 불가" 명시 — issue #392: routing_telemetry cascade marker 폐기, 자연어 위임만).

#### 결과 echo + 평가 — MUST (5~12줄)

```
[<task-id>.<agent>] echo

▎ <prose 의 ## 결론 / ## Summary / ## 변경 요약 섹션 본문 5~12줄>
▎ <섹션 부재 시 prose 첫 5~10줄 fallback>
▎ <필요 시 추가 본문 인용 — 12줄 상한>

결론: <ENUM>
평가: PASS / REDO_SAME / REDO_BACK / REDO_DIFF — <사유>
```

- `<task-id>` = step 이름 (`/impl-loop` chain 모드 아래선 진행 뷰 sub-step task — [진행 뷰](../../skills/impl-loop/SKILL.md#진행-뷰-task-리스트))
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

**step 명명 규칙**: begin/end-step 은 `agent mode` 두 인자 형식만 허용.

```bash
"$HELPER" begin-step <agent> [<MODE>]
"$HELPER" end-step   <agent> [<MODE>]
```

- `agent` — 소문자·하이픈만 (`^[a-z][a-z0-9-]{0,63}$`)
- `mode` — 대문자·숫자·언더스코어만 (`^[A-Z][A-Z0-9_]{0,63}$`)
- 콜론 표기 금지 — `"engineer:POLISH-1"` 형식은 `_validate_agent` 거부 → prose 미기록

**prose 파일 자동 명명** (PostToolUse hook 이 `signal_io.signal_path` 기준 결정):
- 단순: `<run_dir>/<agent>.md`
- mode 보유: `<run_dir>/<agent>-<MODE>.md`
- 같은 (agent, mode) N번째 반복: `<run_dir>/<agent>[-<MODE>]-N.md` (occurrence 카운터 자동 충돌 처리)

| 상황 | begin/end-step | 생성 파일 |
|---|---|---|
| POLISH 1회 | `begin-step engineer POLISH` | `engineer-POLISH.md` |
| POLISH 2회 | `begin-step engineer POLISH` | `engineer-POLISH-1.md` |
| IMPL 재시도 | `begin-step engineer IMPL` | `engineer-IMPL-1.md` |

재호출마다 별도 begin/end-step 1쌍 필수 (DCN-30-25 안전망). `--prose-file` 명시적 전달은 legacy/override 용도로 여전히 허용.

**안티패턴** (begin/end-step 쌍 누락): ❌ engineer commit/PR 후 git status 확인 → end-step skip / ❌ FAIL 후 POLISH Agent 호출 시 begin/end-step 미포함 / ❌ end-step 보류 중 다음 step 진입으로 망각 / ❌ task 간 보고 작성 후 begin-step 재호출 누락.

### build-worker phase prose (`/impl-loop` Hybrid A 한정)

build-worker 는 한 sub-agent 호출(= 메인 1 step) 안에서 3 phase (test → impl → validate) 를 직렬 진행하며, **phase 별 begin-step/end-step 을 worker 가 helper Bash 로 직접 호출하고 phase prose (`build-test.md` / `build-impl.md` / `build-validate.md`) 를 *자체 Write*** 한다 (PostToolUse 자동 staging 은 sub-agent 내부 Bash 엔 미도달). 명명 규약은 [step 명명 + prose 파일 자동 명명](#step-명명-prose-파일-자동-명명) 그대로. phase 분할·각 phase 책임·검증 항목 풀스펙 = [`agents/build-worker.md`](../../agents/build-worker.md) + [`skills/impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md).

phase prose 실제 기록 디렉토리 = `dcness-helper run-dir` 이 출력하는 harness-state run_dir (`.claude/harness-state/.sessions/<sid>/runs/<run-id>`). worktree 안 `phases/<RUN_ID>/` 는 현행 규약이 아니다. build-worker 는 phase prose 3개를 쓴 뒤 `ls <run_dir>/build-test.md <run_dir>/build-impl.md <run_dir>/build-validate.md` 로 실존을 확인하고, 부재 시 PASS 를 내지 않는다.

선택적 polish/retry 기록이 필요하면 `build-polish.md` 도 같은 run_dir 에만 둔다. clean 게이트가 요구하는 필수 phase prose 는 `build-test.md` / `build-impl.md` / `build-validate.md` 3개다.

### ENUM 분기

**공통 골격만 본 문서 책임** — agent 결론이 그 loop 의 advance enum (해당 skill `## Loop` 의 `advance`) 이면 다음 step 진행, **마지막 step 이면 사용자 대기 없이 즉시 Step 7 (end-run)**. 그 외 결론 (`FAIL` / `*_ESCALATE` / `SPEC_GAP_FOUND` / `TESTS_FAIL` / `AMBIGUOUS` 등) → 다음 호출·재시도·cycle 한도·escalate 판정은 **각 loop skill 의 `<skill>-routing.md` 가 진본** ([`impl-routing.md`](../../skills/impl/impl-routing.md) / [`design-routing.md`](../../skills/design/design-routing.md) / [`impl-loop-routing.md`](../../skills/impl-loop/impl-loop-routing.md) / [`ux-routing.md`](../../skills/ux/ux-routing.md) / [`tech-review-routing.md`](../../skills/tech-review/tech-review-routing.md)). loop-procedure 는 enum→처리 표를 재서술하지 않는다.

### retry / POLISH 분기 시 task 재활용 (MUST)

**재시도 / 재호출 / cycle / POLISH** 분기 (각 `<skill>-routing.md`) 로 진입할 때, 신규 `TaskCreate` 금지 — *기존 task 를 `in_progress` 로 되돌린다*.

| 분기 | 재활용 대상 task | 행동 |
|---|---|---|
| `TESTS_FAIL` → engineer 재시도 | 직전 engineer IMPL task | `TaskUpdate(<task>, in_progress)` |
| `FAIL` → engineer POLISH | 직전 engineer IMPL task | `TaskUpdate(<task>, in_progress)` |
| POLISH 후 pr-reviewer 재실행 | 직전 pr-reviewer task | `TaskUpdate(<task>, in_progress)` |
| `IMPL_PARTIAL` → engineer 재호출 | 직전 engineer IMPL task | `TaskUpdate(<task>, in_progress)` |
| architecture-validator 1차 `FAIL` → system-architect 재진입 | 직전 system-architect task | `TaskUpdate(<task>, in_progress)` |
| architecture-validator 2차 `FAIL` → module-architect 또는 system-architect 재진입 | 직전 해당 agent task | `TaskUpdate(<task>, in_progress)` |
| ux-architect self-check FAIL → ux-architect 재진입 | 직전 ux-architect task | `TaskUpdate(<task>, in_progress)` (prose 내부 cycle — 별도 task X) |
| `AMBIGUOUS` 재호출 1회 | 직전 동일 agent task | `TaskUpdate(<task>, in_progress)` |
| `SPEC_GAP_FOUND` → module-architect (보강) | 신규 task (다른 agent) | `TaskCreate` 가능 |

이유: retry / POLISH 는 *동일 step 의 재실행*. 신규 TaskCreate 시 같은 step 이 task list 에 중복 등장 → 진행 추적 오염. cycle 카운터는 step occurrence (`<agent>[-<MODE>]-N.md`) 로 보존되므로 task 는 1개로 유지.

**MUST 순서** (retry / POLISH 진입 시):

```
TaskUpdate(<기존 task>, in_progress)   # 신규 TaskCreate 금지
"$HELPER" begin-step <agent> [<MODE>]   # occurrence 자동 증가 → -N.md
Agent(...)
ENUM=$("$HELPER" end-step ...)
TaskUpdate(<기존 task>, completed)
```

### finding 수용 원칙: 점 패치 금지, 근본 수정

validator (`code-validator` / `architecture-validator` / `pr-reviewer`) 의 FAIL finding·수정 권고는 **"그 점/그 줄만 고쳐라"가 아니다.** 권고가 나온 *의미* = finding 이 가리키는 **근본 원인을 파악해 그 영역을 재설계하라** 이다.

- **메인 (relay)**: 재진입 prompt 에 finding 을 "이 점만 고쳐"로 좁게 전달 금지. finding 이 구조적 누수의 *증상*인지 먼저 판단 → 증상이면 "근본 원인 + 증상 패턴 전체"를 주고 "이 접근을 재설계하라"로 프레이밍한다. **같은 영역 finding 이 2회+ 반복 = 점 패치 신호 → 즉시 근본 재설계로 전환** (위 REDO 분류의 `REDO_DIFF` 와 정합 — 같은 접근 재시도가 아니라 접근 자체 교체). 해법 메커니즘은 메인이 처방하지 말 것 — 증상·사실관계만 넘기고 설계 소유는 producer agent 가 갖는다.
- **producer (architect / engineer)**: finding 수신 시 점 패치 전에 "더 깊은 설계 문제의 신호인가?"를 먼저 본다. 신호면 점이 아니라 접근을 재설계한다. 재설계가 상위 산출물 (architecture / adr / domain-model 등) 을 건드리면 직접 편집하지 말고 변경점을 prose 로 보고 → 메인이 상위 agent 로 분기 (각 `<skill>-routing.md` 의 retry 경로).
- **이유**: 점 패치는 finding cascade 를 부른다 — 좁은 수정이 다음 결함을 드러내 같은 영역 FAIL 이 N 라운드 반복. 한 번의 근본 재설계 < N 번 점 패치 + N 번 재검증. 같은 영역을 점 패치로 retry 한도 ([design-routing](../../skills/design/design-routing.md#retry-한도) / [impl-loop-routing](../../skills/impl-loop/impl-loop-routing.md#retry-한도)) 까지 소진하지 말 것.

### yolo 모드

발화에 `yolo` / `auto` / `끝까지` / `막힘 없이` / `다 알아서` 키워드 시 ON — 평소 사용자 위임할 신호를 자동 진행한다. yolo↔비-yolo 케이스별 동작은 cross-cutting 운전 규칙이라 본 문서가 SSOT (각 `<skill>-routing.md` 의 enum→호출 매핑과 별개):

| 상황 | 비-yolo | yolo |
|---|---|---|
| soft `*_ESCALATE` / `AMBIGUOUS` | 사용자 위임 | `auto-resolve` 적용 |
| `SPEC_GAP_FOUND` | 사용자 위임 | module-architect (보강 케이스) cycle (≤2) |
| `TESTS_FAIL` / code-validator `FAIL` | 재시도 (≤3) | 동일 |
| `IMPL_PARTIAL` | engineer 재호출 (split ≤3) | 동일 — 새 context window |
| `FAIL` | 사용자 위임 | engineer POLISH (cycle ≤2) |
| Step 7 주의사항 (NICE TO HAVE only, MUST FIX 0) | 사용자 위임 | 7a 자동 |
| 중대 차단 룰 | hard safety | hard safety (yolo 우회 X) |

auto-resolve 의 실제 action/hint/next_enum 매핑 진본 = helper 코드 `session_state.py`:

```bash
RESOLVE_JSON=$("$HELPER" auto-resolve "<agent>:<enum_or_mode>")
# JSON: {"action":..., "hint":..., "next_enum":...} — unmapped 시 yolo 도 사용자 위임 fallback
```

---

## impl-task-loop commit 구조

`impl-task-loop` / `impl-ui-design-loop` 은 루프 종료 전 src commit + PR create 를 **메인 Claude 가 전담**한다 (engineer / build-worker / test-engineer 는 코드 변경만 — race 회피). 본 절은 *시점·포함 파일* 만 정의하고, **브랜치·커밋·PR 네이밍 + 트레일러 판정 규칙은 [`git-spec.md`](git-spec.md) 가 SSOT** 다.

| 시점 | 내용 |
|---|---|
| code-validator (또는 build-worker) PASS 직후 | branch 새로 + `src/**` commit + push + PR create |
| PR 생성 직후 | merge ([Step 7a](#step-7a-impl-task-loop)) |

> `docs/.../impl/NN-*.md` 는 `/design` 산출물이 *미리 머지* 된 상태 — impl-task-loop 안에서 별도 commit X. fallback 모드 (정식 위치 부재) 는 module-architect 산출물을 본 PR src commit 에 같이 포함.

> **commit = `src/**` only** — 이 invariant 의 진본은 *권한 경계* 다: impl 루프 worktree 의 변경은 engineer / build-worker 권한 경계([`agent_boundary.py`](../../harness/agent_boundary.py) ALLOW_MATRIX = `src/**` 계열)상 src 계열뿐이라, stories.md / backlog.md 등은 애초에 worktree 에 안 들어온다. 진행 추적은 PR body 트레일러 (Part of / Closes) + GitHub sub-issue API 가 SSOT.

규칙은 전부 git-spec 위임 — loop-procedure 는 판정 로직(브랜치명·base·트레일러)을 재서술하지 않는다:

- **브랜치명** = [`git-spec.md` 브랜치](git-spec.md#브랜치) (결정 절차 = [`skills/impl-loop/SKILL.md`](../../skills/impl-loop/SKILL.md)).
- **base 분기** = [`git-spec.md` Git 절차](git-spec.md#git-절차) (stories.md `**Base Branch:**` 마커 매치 시 통합 브랜치, 없으면 main · checkout 과 PR base 둘 다 동일 BASE).
- **PR body 트레일러 (Part of vs Closes) 판정** = [`git-spec.md` PR 트레일러](git-spec.md#pr-트레일러-part-of-closes) 의 적용 절차 (impl 파일 frontmatter 기반).
- **실행** = [`scripts/pr-create.sh`](../../scripts/pr-create.sh) — `--branch / --base / --title / --body-file / --commit-msg-file` 받아 branch + add + commit + push + `gh pr create` 한 명령. body-file 은 메인이 위 트레일러 규칙대로 작성해 전달 (스크립트는 판정 X). **주의**: pr-create.sh 는 `git add -A`(worktree 전체 stage) — 위 권한 경계로 worktree 가 src-only 라 곧 src-only 커밋이 되지만, 메인이 stray non-src 변경(임시 파일·`.DS_Store` 등)을 발견하면 호출 *전* 정리하거나 명시 pathspec 으로 직접 stage 한다.

### Step 7a (impl-task-loop)

PR 이미 생성된 상태 — merge only. [`scripts/pr-finalize.sh`](../../scripts/pr-finalize.sh) 가 머지 + CI 대기 + main sync 자동.

---

## Step 7 — finalize-run + clean 매트릭스 + commit/PR

### end-run 호출 (issue #396 — 단일화)

> **트리거**: 마지막 step advance enum 확인 직후 사용자 대기 없이 즉시 호출 — 루프 종류 무관.

```bash
"$HELPER" end-run
```

end-run 안전망 (`session_state.py`) 이 자동으로 `finalize-run --auto-review` 발사 → in-process `harness.run_review` → STATUS JSON + review.md.

- review 결과는 `<run_dir>/review.md` 에 저장 + stderr `[REVIEW_READY] <path>` 신호 출력. 메인 Claude 가 [Step 8 — review 결과 인지](#step-8-review-결과-인지) 따라 세션에 그대로 출력 의무.
- (예전 2개 명령 — `finalize-run --expected-steps <N> --auto-review` + `end-run` — 폐기. end-run 1개로 단순화. issue #396)
- (issue #392 — `loop-insights` 자동 누적 매커니즘 폐기. 메인 자율 평가는 `$HELPER insight <agent>[-<mode>] "<한 줄>"` CLI 로 대체. review.md 끝 prompt 안내)

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

**verify-only 예외 (`/impl-loop`)**: `code-validator:VERIFY_ONLY` prose 가 `PASS`이고 prose 안에 검증 명령 exit 0 + `git status --porcelain` 변경 0 증거가 있으면, step 1개 + PR 0개도 clean 이다. 이 예외에서는 `pr-create.sh` 를 호출하지 않는다.

### 7a — Clean 자동 commit/PR

> **impl-task-loop 제외**: [impl-task-loop commit 구조](#impl-task-loop-commit-구조) 에서 branch/commit/push/PR 이미 완료 → Step 7a = merge only.

clean 판정 통과 시 사용자 확인 없이 자동 진행 (**impl-task-loop 외** 루프): branch (`<prefix>/<short-slug>`, prefix = 해당 loop 의 branch_prefix — [`git-spec.md` 브랜치](git-spec.md#브랜치) valid 패턴) → **변경 파일 commit** → push → PR create → merge → main sync. **commit 대상 = 해당 loop 가 실제 변경한 파일** — design = `docs/**` 설계 산출물, ux = `docs/ux-flow.md` 등 docs/design 아티팩트라 src-only 아님 (src-only 제한은 impl-task-loop 전용, [impl-task-loop commit 구조](#impl-task-loop-commit-구조)). **stray untracked 휩쓸기 주의**: impl 루프와 달리 비-impl loop 은 worktree 권한 경계가 src-only 가 아니고 clean 매트릭스가 untracked ≤ 10 을 허용하므로, `pr-create.sh` 의 `git add -A` 는 무관한 로컬 아티팩트까지 stage 한다 → 호출 *전* 산출물 외 파일을 정리하거나, 해당 loop 산출물만 명시 pathspec 으로 직접 stage 후 commit. 네이밍·본문·트레일러 = [`git-spec.md`](git-spec.md), 커밋 trailer 의 모델 표기는 글로벌 `~/.claude/CLAUDE.md` 기준. 실행 = [`scripts/pr-create.sh`](../../scripts/pr-create.sh) + [`scripts/pr-finalize.sh`](../../scripts/pr-finalize.sh).

worktree 진입 시 squash 흡수 검사 후 `ExitWorktree(action="<keep|remove>")` ([worktree 분기](#worktree-분기-action-루프-한정)).

### 7b — 주의사항 확인

```
[<entry>] 완료 (주의사항)
- run_id: $RUN_ID · 변경: <src/ 변경 파일>
- prose 종이: .claude/harness-state/.sessions/{sid}/runs/$RUN_ID/

⚠️ 주의사항: <has_ambiguous / has_must_fix / unexpected enum / sensitive untracked>

📝 메모리 후보 (#149):
- <주의사항 발생 사유의 회고 — feedback / project type 후보. 다음 세션 회귀 방지용>
- <waste finding 의 반복 패턴 (예: ECHO_VIOLATION 2회+, MISSING_SELF_VERIFY 등)>
- <pr-reviewer NICE TO HAVE 중 자주 등장하는 항목>
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

`begin-run` / `begin-step` / `end-step` / `end-run` 은 prose 저장과 별개로 run_dir 안 `ledger.jsonl` 에 append-only event 를 자동 기록한다. prose 파일 (`<run_dir>/<agent>[-<MODE>].md`) 이 계속 SSOT 이고, ledger 는 긴 prose 를 매번 대화 context 에 재주입하지 않고도 resume / handoff / audit 에 필요한 상태를 담는 색인 장부다. **agent 에게 JSON 출력 형식을 강제하지 않는다** — helper 가 저장된 prose + known state 에서 receipt 를 생성한다.

**자동 기록 event** (코드 경로):
- `run_started` (begin-run) — entry_point / issue_num / design_doc(기록 시)
- `step_started` (begin-step) — agent / mode
- `step_completed` (end-step) — = **receipt**: agent / mode / enum / prose_excerpt / must_fix / prose_file / sha256 / evidence_paths / next_action(hint)
- `run_finished` (end-run)

`ledger.jsonl` 의 `step_completed` receipt 는 read 시점에 primary ledger 한정으로 `prose_file` 실존 + `sha256` digest match 를 strict 검증한다. 검증 실패 step 은 위조/손상으로 보고 소비처(`run-status` / `run-review` / finalize gate)에서 제외한다. 옛 `.steps.jsonl` 폴백은 마이그레이션 호환 경로라 같은 검증을 걸지 않는다.

**선택 기록 event** (메인/skill 이 `ledger-event` 로 — 강제 X): `pr_created` / `pr_merged` / `task_completed` / `blocked` / `validator_passed` / `validator_failed`.

```bash
"$HELPER" ledger-event pr_merged --pr 588 --url <PR_URL>
"$HELPER" ledger-event blocked --reason "<사유>"
```

**resume 복원**: compaction/세션 재개 후 긴 prose 를 다시 읽지 말고 한 명령으로 진행 상태를 복원한다.
```bash
"$HELPER" run-status     # 현재 run 의 phase / task / last event / next action(hint) / evidence pointer
```
출력의 evidence pointer (prose 파일 경로) 로 필요한 prose 만 선택적으로 연다.

**옛 `.steps.jsonl` 흡수** (이슈 #587): step 로그는 `ledger.jsonl` 의 `step_completed` event 로 단일화됐다 (옛 step row 필드의 superset). `ledger.jsonl` 부재 시 옛 `.steps.jsonl` 로 폴백 — plugin 업데이트가 진행 중 run 에 걸친 경우의 마이그레이션 셔틀이다. run-review / 진행 순서 검사 / Stop hook 은 모두 `step_completed` event 를 읽는다.

---

## 순서 차단 훅 정합

각 loop 의 entry_point / task_list / advance / expected_steps 진본 = 해당 skill 의 `## Loop` contract. 그 시퀀스가 중대 차단 룰을 자연 충족한다 — 순서 차단 훅 진본 = [`hooks.md`](hooks.md#catastrophic-gatesh) (`hooks/catastrophic-gate.sh` 강제): code-validator → pr-reviewer 직전 PASS / engineer 직전 module-architect `PASS` enum / module-architect × K 진입 직전 architecture-validator 1차 PASS. (tech-review 진입 gate = PRD 변경 후 사용자 2 차 OK · `/design` 진입 후 tech-reviewer 재호출 비권장 = 코드 강제 아닌 자연어 관례.) 8 hook 전체 시점·차단·우회 = [`hooks.md`](hooks.md).

---

## 참조

- 각 loop skill 의 `<skill>-routing.md` — 분기 규칙 / retry / escalate ([`impl-routing.md`](../../skills/impl/impl-routing.md) / [`design-routing.md`](../../skills/design/design-routing.md) / [`impl-loop-routing.md`](../../skills/impl-loop/impl-loop-routing.md) / [`ux-routing.md`](../../skills/ux/ux-routing.md) / [`tech-review-routing.md`](../../skills/tech-review/tech-review-routing.md)) · loop 진입 spec = 각 skill 의 `## Loop` contract
- [`hooks.md`](hooks.md) — 8 hook (catastrophic-gate / file-guard / tdd-guard / stop-end-run / session-start / post-agent-clear / post-file-op-trace / subagent-stop-clear) 시점·차단·우회 SSOT
- 본 문서 [표준 1 step 시퀀스](#표준-1-step-시퀀스-per-agent-의무) + [Step 8 — review 결과 인지](#step-8-review-결과-인지) — echo / 자가점검 / REDO 분류 / 개선점 코멘트 (옛 dcness-rules §3/§4 흡수)
- `harness/session_state.py` — helper CLI (`begin-run` / `end-run` / `begin-step` / `end-step` / `finalize-run` / `run-dir` / `auto-resolve`)
- `harness/run_review.py` — review 엔진 (`--auto-review` 호출 대상)
- workflow skill 진입점 (input 정형화 + Loop 추천) — `skills/<skill>/SKILL.md` (예: impl-loop / design). 운영 보조 command 는 `commands/<command>.md`.
