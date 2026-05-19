# Loop Execution Procedure (메인 Claude 컨베이어 mechanics)

> **Status**: ACTIVE
> **Scope**: dcness 8 loop 의 *공통 실행 절차* SSOT — Step 0~8 mechanics. 메인 Claude 가 skill 트리거 또는 직접 발화로 루프 시작 시 본 문서를 컨베이어 매뉴얼처럼 따른다.
> **Cross-ref**: 8 loop 별 행별 풀스펙 (allowed_enums / 분기 / sub_cycles / branch_prefix) + 시퀀스 mermaid + 결정표 = [`orchestration.md`](orchestration.md) §2~§4.

---

## 0. 진입 모델

skill 트리거 또는 직접 발화 → 메인 Claude 가 **[`orchestration.md`](orchestration.md) §4.1 인덱스 + 해당 loop 풀스펙 sub-section** 보고 task 리스트 동적 구성 → §1~§6 mechanics 따름.

- **skill 경유**: `commands/<skill>.md` 의 `Loop` 필드가 orchestration §4 행 가리킴. skill 은 input 정형화 + 라우팅 추천만 — 절차는 본 SSOT, loop spec 은 orchestration §4.
- **직접 발화** ("이거 impl 로 가자"): orchestration.md §3 mini-graph + §4.1 인덱스 보고 메인이 자율 구성. 강제 X.
- **SessionStart inject**: 슬림 본문 (강제 영역 / 메인 Claude 필수 / 진입 매트릭스 / 안티패턴) 매 세션 자동 노출. 첫 응답 첫 줄 `[dcness 활성 확인]` 토큰 의무.

---

## 1. Step 0 — worktree + begin-run

### 1.1 worktree 분기 (impl 류 루프 한정)

**행동형 skill 중 *코드 변경 batch* (`/impl` `/impl-loop` `/auto-loop`) 진입 시만 EnterWorktree 자동 호출**. 동시 다중 세션 충돌 회피 + 메인 working tree 보호.

**`/product-plan` / 모듈 설계 / 문서·시드 작업은 워크트리 X** — 본 작업은 충돌 회피 목적 부재. 메인 working tree 에서 별 branch 따고 직접 진행.

```
EnterWorktree(name="<skill>-{ts_short}")   # impl 류만
```

**거부 표현 시에만 건너뜀** — 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 (예: "워크트리 빼고", "워크트리 없이", "워크트리 말고") 시 EnterWorktree 호출 0, 일반 cwd 그대로 진행.

수동 `git worktree add` 우회 금지 — CC permission 시스템이 EnterWorktree 만 자동 권한 처리. 수동 워크트리는 sub-agent Write 거부 회귀 (#255 W1). **예외 = §1.1.1 base-ref 분기** (사전 `git worktree add` 후 `EnterWorktree(path=)` 진입 — CC 가 path= 도 권한 처리, #255 회귀 아님).

### 1.1.1 base-ref 분기 (통합 브랜치 모드, #424)

`docs/stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 = **통합 브랜치 모드** (long-lived integration branch + sub-PR 누적 패턴, `commands/product-plan.md` Step 6.5/7). 이 경우 outer worktree base ref 도 integration branch 와 정합해야 함 — `EnterWorktree(name=)` default 인 `worktree.baseRef=fresh` (origin/main 기반) 은 base mismatch → sub-PR diff 거대화 ("삭제 변경" false).

EnterWorktree tool 은 base parameter 미지원 → 사전 `git worktree add` 후 `EnterWorktree(path=)` 진입 패턴:

```bash
# stories.md base branch 매치
BASE_BRANCH=$(grep -m1 -E '^\*\*Base Branch:\*\*' docs/stories.md 2>/dev/null \
  | sed -E 's/.*Base Branch:\*\*[[:space:]]+//')

if [ -n "$BASE_BRANCH" ] && [ "$BASE_BRANCH" != "main" ]; then
  # 통합 브랜치 모드 — outer worktree base = integration branch
  git fetch origin "$BASE_BRANCH"
  TS=$(date +%s | tail -c 6)
  WORKTREE_PATH=".claude/worktrees/<skill>-${TS}"
  git worktree add -b "<skill>-${TS}" "$WORKTREE_PATH" "origin/${BASE_BRANCH}"
  # EnterWorktree(path="$WORKTREE_PATH")  — 기존 worktree 진입
else
  # default trunk-based — fresh = origin/main 기반
  # EnterWorktree(name="<skill>-{ts_short}")
fi
```

→ sub-PR diff = (worktree HEAD) vs (`feature/<slug>` HEAD) = 본 task 변경만 표시. 정상.

자식 자체 sub-worktree 패턴 (자식이 `git worktree add` 호출해 sibling worktree 만드는) 도 옵션이나, outer 가 base 정합되면 main repo 안 직접 작업 위험 + 자식 cwd 분기 복잡도 회피.

종료 시 squash 흡수 검사 후 자동:

```bash
UNMERGED_DIFF=$(git diff "main..$WORKTREE_BRANCH" -- ':^.claude' 2>/dev/null)
if [ -z "$UNMERGED_DIFF" ]; then
  ExitWorktree(action="remove", discard_changes=true)
else
  ExitWorktree(action="keep")
fi
```

자세히 = [`../archive/conveyor-design.md`](../archive/conveyor-design.md) §13.

### 1.2 begin-run

```bash
HELPER="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)/scripts/dcness-helper"
RUN_ID=$("$HELPER" begin-run <entry_point> [--issue-num N])
echo "[<entry>] run started: $RUN_ID"
```

`<entry_point>` = §7 매트릭스 행의 `entry_point` 컬럼 (예: `impl`, `issue-report`, `architect-loop`, `ux`). begin-run 동작: sid auto-detect + run_id 발급 + `live.json.active_runs` 슬롯 + `.by-pid-current-run/{cc_pid}` 박음.

> `/impl-loop` 은 자기 entry_point 가 없다 — `impl-task-loop × N` driver 이므로 각 task 가 독립 `begin-run impl` … `end-run` run 1개씩 (N task = N run = N review.md). 자세히 = [`orchestration.md`](orchestration.md) §4.8 + [`commands/impl-loop.md`](../../commands/impl-loop.md).

---

## 2. Step 1 — TaskCreate

[`orchestration.md`](orchestration.md) §4 행의 `task_list` 컬럼대로 일괄 등록. **단 `/impl-loop` 아래의 `impl` run 은 TaskCreate skip** — task 리스트는 impl-loop skill 이 진행 뷰로 일괄 관리한다 ([`commands/impl-loop.md`](../../commands/impl-loop.md) §진행 뷰). impl run 은 이미 생성된 sub-step task 를 TaskUpdate 만 한다.

```
TaskCreate("<agent>: <mode 또는 짧은 설명>")
... (loop 정의 수만큼)
```

---

## 3. Step 2~N — agent 호출 골격

### 3.1 표준 1 step 시퀀스 (per-agent 의무)

```
TaskUpdate("<task>", in_progress)
"$HELPER" begin-step <agent> [<MODE>]
Agent(subagent_type="<agent>", mode="<MODE>", description="...")
"$HELPER" end-step <agent> [<MODE>]   # prose-only mode (stdout=PROSE_LOGGED)
# legacy compat: ENUM=$("$HELPER" end-step <agent> [<MODE>] --allowed-enums "<csv>")
# 의무 echo (5~12 줄) — 아래 "결과 echo + 평가" 섹션
TaskUpdate("<task>", completed)
```

begin-step stdout 에 `[INSIGHTS: <agent>/<mode>]` 섹션이 있으면 Agent prompt 끝에 그대로 포함시킨다. 해당 agent 의 과거 루프 학습 — "하지 말 것" / "잘 됐던 것" — 이 프로젝트 레벨로 누적된 것.

메인이 prose를 직접 Write 할 필요 없음 — PostToolUse Agent hook 이 sub 종료 시 `tool_response.text` 에서 prose 를 자동으로 `<run_dir>/<agent>[-<MODE>].md` 에 저장하고 `live.json.current_step.prose_file` 에 경로 기록. `end-step` 이 이 경로를 자동 읽는다.

**호출 prompt 작성 — MUST**: 호출 직전 해당 `agent.md` §"호출자가 prompt 로 전달하는 정보" 항목 read 후 prompt 작성 (형식 자유, 정보 명시 의무).

**worktree 활성 시 worktree 절대 경로 prompt 에 추가 명시 — MUST**: cwd 가 `.claude/worktrees/<name>/` 안이면 sub-agent prompt 에 worktree 절대 경로 명시. main repo abs path 사용 금지 — 머지 전 옛 코드 read 로 false positive (CC #31546 / #48096). 근거: CC Task tool 에 cwd parameter 부재 (#12748), subagent frontmatter cwd field 부재 (#31940) — 메인이 명시 책임.

**prose-only mode** (이슈 #284): `--allowed-enums` 미지정 시 stdout = `PROSE_LOGGED`. 메인 Claude 가 prose 자체 (`<run_dir>/<agent>[-<MODE>].md`) 를 직접 읽고 routing 결정 — [`handoff-matrix.md`](handoff-matrix.md) §1 자연어 가이드 참조. 결정 못 하면 사용자에게 위임 (prose 본문에 "결정 불가" 명시 — issue #392: routing_telemetry cascade marker 폐기, 자연어 위임만).

#### 결과 echo + 평가 — MUST (5~12줄)

```
[<task-id>.<agent>] echo

▎ <prose 의 ## 결론 / ## Summary / ## 변경 요약 섹션 본문 5~12줄>
▎ <섹션 부재 시 prose 첫 5~10줄 fallback>
▎ <필요 시 추가 본문 인용 — 12줄 cap>

결론: <ENUM>
평가: PASS / REDO_SAME / REDO_BACK / REDO_DIFF — <사유>
```

- `<task-id>` = step 이름 (`/impl-loop` 아래선 진행 뷰 sub-step task — [`commands/impl-loop.md`](../../commands/impl-loop.md) §진행 뷰)
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

#### AMBIGUOUS 처리 (legacy enum mode 한정)

`--allowed-enums` 박은 legacy 호출에서 `end-step` stdout = `AMBIGUOUS` 시: 재호출 1회 (결론 enum 명시 요청) → 재호출도 AMBIGUOUS → 사용자 위임 (enum 후보 + prose 발췌). prose-only mode 는 AMBIGUOUS 자체 X — 결정 못 하면 prose 본문에 "결정 불가" 명시 후 사용자 위임 (issue #392).

#### helper 안전망 (자동 검출)

- **drift WARN**: live.json `current_step` 과 `args.agent` 불일치 → stderr WARN
- **step count WARN**: `finalize-run --expected-steps N` row count 미달 → stderr WARN
- 자동 보정 X — 메인이 사후 인지 + `/run-review` 진단

### 3.2 step 명명 + prose 파일 자동 명명

**step 명명 규칙**: begin/end-step 은 `agent mode` 두 인자 형식만 허용.

```bash
"$HELPER" begin-step <agent> [<MODE>]
"$HELPER" end-step   <agent> [<MODE>] [--allowed-enums "..."]
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

### 3.3 ENUM 분기

| ENUM | 처리 |
|------|------|
| advance enum (catalog 행의 `advance` 컬럼) | 다음 step 있으면 진행 / **마지막 step이면 사용자 대기 없이 즉시 Step 7** |
| `SPEC_GAP_FOUND` | module-architect (보강 케이스) cycle (≤2) 또는 사용자 위임 |
| `TESTS_FAIL` / code-validator `FAIL` | engineer 재시도 (attempt < 3) |
| code-validator `ESCALATE` (사유: spec 부재) | module-architect (보강 케이스) |
| code-validator `ESCALATE` (사유: 재시도 한도 초과 등) | 사용자 위임 |
| `*_ESCALATE` (hard) | 사용자 위임 (escalate) |
| `*_ESCALATE` (soft) | 비-yolo: 사용자 위임 / yolo: `auto-resolve` |
| `FAIL` | engineer POLISH cycle (≤2) |
| `AMBIGUOUS` | 재호출 1회 (결론 enum 명시 요청) → 재호출도 AMBIGUOUS 시 사용자 위임 (enum 후보 + prose 발췌) |
| architecture-validator `FAIL` | system-architect 재진입 (cycle ≤2) |
| `FAIL` | 메인이 findings 항목별 사용자 confirm + `docs/prd.md` / `docs/stories.md` Edit patch → plan-reviewer 재진입 (cycle ≤2) |
| `ESCALATE` | 사용자 위임 (외부 검증 불가 / 권한 경계 밖 / 동일 finding 반복 / URL 부재 PASS 시도) |

cycle 한도 = orchestration.md §5.

### 3.3.1 retry / POLISH 분기 시 task 재활용 (MUST)

위 표의 **재시도 / 재호출 / cycle / POLISH** 분기로 진입할 때, 신규 `TaskCreate` 금지 — *기존 task 를 `in_progress` 로 되돌린다*.

| 분기 | 재활용 대상 task | 행동 |
|---|---|---|
| `TESTS_FAIL` → engineer 재시도 | 직전 engineer IMPL task | `TaskUpdate(<task>, in_progress)` |
| `FAIL` → engineer POLISH | 직전 engineer IMPL task | `TaskUpdate(<task>, in_progress)` |
| POLISH 후 pr-reviewer 재실행 | 직전 pr-reviewer task | `TaskUpdate(<task>, in_progress)` |
| `IMPL_PARTIAL` → engineer 재호출 | 직전 engineer IMPL task | `TaskUpdate(<task>, in_progress)` |
| architecture-validator `FAIL` → system-architect 재진입 | 직전 system-architect task | `TaskUpdate(<task>, in_progress)` |
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

### yolo 모드

발화에 `yolo` / `auto` / `끝까지` / `막힘 없이` / `다 알아서` 키워드 시 ON.

| 상황 | 비-yolo | yolo |
|---|---|---|
| `*_ESCALATE` (soft) / `AMBIGUOUS` | 사용자 위임 | `auto-resolve` 적용 |
| `SPEC_GAP_FOUND` | 사용자 위임 | module-architect (보강 케이스) cycle (≤2) |
| `TESTS_FAIL` / code-validator FAIL | 재시도 (≤3) | 동일 |
| `IMPL_PARTIAL` | engineer 재호출 (split ≤ 3) | 동일 — 새 context window |
| `FAIL` | 사용자 위임 | engineer POLISH (cycle ≤2) |
| Step 7 caveat (NICE TO HAVE only, MUST FIX 0) | 사용자 위임 | 7a 자동 |
| catastrophic 룰 | hard safety | hard safety (yolo 우회 X) |

```bash
RESOLVE_JSON=$("$HELPER" auto-resolve "<agent>:<enum_or_mode>")
# JSON: {"action":..., "hint":..., "next_enum":...}
# unmapped 시 yolo 도 사용자 위임 fallback
```

---

## 3.4 impl-task-loop commit 구조 (orchestration §4.3 한정)

`impl-task-loop` / `impl-ui-design-loop` / `direct-impl-loop` 에서 루프 종료 전 src commit + PR create. **커밋 메시지·브랜치·PR 네이밍 규칙 SSOT** = [`git-naming-spec.md`](git-naming-spec.md). 본 §3.4 는 *시점·포함 파일* 만 정의.

| 시점 | 내용 |
|---|---|
| code-validator PASS 직후 | branch 새로 + `src/**` commit + push + `gh pr create` |
| PASS 직후 | `gh pr merge` (merge) |

> `docs/.../impl/NN-*.md` 는 `/architect-loop` 산출물이 *미리 main 에 머지* 한 상태. impl-task-loop 안에서 별도 commit X. fallback 모드 (정식 위치 부재) 는 module-architect 가 그 자리에서 새로 작성하는데, 본 PR 의 src commit 에 같이 포함.

> **commit = `src/**` only** — stories.md / backlog.md 등 다른 path 섞지 않는다. 진행 추적은 PR body `Closes #N` / `Part of #N` 트레일러 + GitHub native sub-issue API 가 SSOT.

### commit 골격

```bash
# 메시지 형식 = git-naming-spec.md §2~§5 참조.

# branch 생성 + src commit (code-validator PASS 직후)
BRANCH="<prefix>/<task-slug>"   # prefix = feat/fix/chore (decision rule = orchestration §4.3)
git checkout -b "$BRANCH" main
git add src/**
git commit -m "<git-naming-spec §2 형식>"
git push -u origin "$BRANCH"

# PR body: Closes vs Part of 자동 판단 (issue-lifecycle.md §1.4 적용 절차)
# 입력 = impl 파일 frontmatter `task_index: i/total` + `story: N` (module-architect × K 시점에 박힘)
TASK_FILE="docs/milestones/.../impl/NN-*.md"
TASK_INDEX=$(awk '/^task_index:/ {gsub(/[",]/,""); print $2; exit}' "$TASK_FILE")  # "3/3"
STORY_NUM=$(awk '/^story:/ {gsub(/[",]/,""); print $2; exit}' "$TASK_FILE")
I="${TASK_INDEX%/*}"
TOTAL="${TASK_INDEX#*/}"

if [ "$I" = "$TOTAL" ]; then
  # Story 마지막 task → Closes
  PR_BODY="Closes #${STORY_ISSUE}"
  # epic 마지막 story 판정 (issue-lifecycle.md §2.2)
  EPIC_OPEN_STORIES=$(gh issue list --label "epic-${EPIC_NUM}-${EPIC_SLUG}" --milestone Story --state open --json number --jq 'length' 2>/dev/null || echo 0)
  if [ "$EPIC_OPEN_STORIES" = "1" ]; then
    PR_BODY="${PR_BODY}
Closes #${EPIC_ISSUE}"
  fi
else
  PR_BODY="Part of #${STORY_ISSUE}"
fi
gh pr create --title "<git-naming-spec §4 형식>" --body "$PR_BODY"
```

### Step 7a (impl-task-loop)

PR 이미 생성된 상태 — merge only:

```bash
gh pr merge || echo "[impl] merge 대기 — CI / reviewers"
git checkout main && git pull --ff-only 2>/dev/null || true
```

---

## 4. Step 4.5 — 폐기 (2026-05-12)

> **이전 정의**: `stories.md` task `[x]` 체크 + `backlog.md` epic `[x]` 체크 (engineer `IMPL_DONE` 직후, 메인 mechanical edit).
>
> **폐기 사유**: stories.md 양식 단순화 (user story 만, task `[ ]` 박지 않음 — PR3-A) + `backlog.md` 자체 폐기. 진행 추적 SSOT = GitHub issue close 시스템 (PR body `Closes #N` / `Part of #N` 트레일러) 단일화. impl task PR diff 에는 stories.md / backlog.md 변경 0 (commit3 = src/** only).
>
> **마이그레이션**: 기존 활성 프로젝트의 옛 stories.md (task `[ ]` 박힌) 는 *그대로 잔재 허용* — backfill 강제 X. 새 작성만 새 양식 ([`commands/product-plan.md`](../../commands/product-plan.md) §stories.md 산출물). 자동 마이그레이션 원하는 사용자용 = `scripts/migrate_stories_to_new_format.sh`.

---

## 5. Step 7 — finalize-run + clean 매트릭스 + commit/PR

### 5.1 end-run 호출 (issue #396 — 단일화)

> **트리거**: 마지막 step advance enum 확인 직후 사용자 대기 없이 즉시 호출 — 루프 종류 무관.

```bash
"$HELPER" end-run
```

end-run 안전망 (`session_state.py:1001`) 이 자동으로 `finalize-run --auto-review` 발사 → in-process `harness.run_review` → STATUS JSON + review.md.

- review 결과는 `<run_dir>/review.md` 에 저장 + stderr `[REVIEW_READY] <path>` 신호 출력. 메인 Claude 가 §6 따라 세션에 그대로 출력 의무.
- (예전 2개 명령 — `finalize-run --expected-steps <N> --auto-review` + `end-run` — 폐기. end-run 1개로 단순화. issue #396)
- (issue #392 — `loop-insights` 자동 누적 매커니즘 폐기. 메인 자율 평가는 `$HELPER insight <agent>[-<mode>] "<한 줄>"` CLI 로 대체. review.md 끝 prompt 안내)

### 5.2 STATUS JSON 구조

```
{
  run_id, session_id,
  steps[{agent, mode, enum, must_fix, prose_excerpt}],
  has_ambiguous, has_must_fix, step_count
}
```

### 5.3 clean 판정 매트릭스

다음 모두 충족 → **clean** (자동 7a):
1. `has_ambiguous == false` && `has_must_fix == false`
2. step enum 매트릭스: catalog 행 `clean_enum` 컬럼 모두 정합
3. git 안전 가드:
   - `git status --porcelain` 에 `.env` / `secrets.*` / `credentials.*` 없음
   - unstaged + untracked ≤ 10
   - submodule 변경 없음

clean 아니면 **7b (caveat)**.

### 5.4 7a — Clean 자동 commit/PR

> **impl-task-loop 제외**: §3.4 에서 branch/commit/push/PR 이미 완료. Step 7a = merge only (`gh pr merge`).

자동 진행 (사용자 확인 X, **impl-task-loop 외** 루프 적용):

```bash
CHANGED=$(git diff --name-only HEAD)
HAS_REMOTE=$(git remote get-url origin >/dev/null 2>&1 && echo yes || echo no)

BRANCH="<prefix>/<short-slug>"   # prefix = catalog 행
git checkout -b "$BRANCH" main
git add $CHANGED
git commit -m "$(cat <<'EOF'
<한 줄 제목>

<2~3 줄 본문 — engineer prose_excerpt + run_id 참조>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

if [ "$HAS_REMOTE" = "yes" ]; then
  git push -u origin "$BRANCH"
  gh pr create --title "<제목>" --body "<요약 + Test plan + run_id>"
  gh pr merge --merge --auto 2>/dev/null || gh pr merge --merge || \
    echo "[<entry>] PR merge 차단 — branch protection / CI 대기"
  git checkout main && git pull --ff-only 2>/dev/null || true
fi
```

worktree 진입 시 squash 흡수 검사 후 `ExitWorktree(action="<keep|remove>")` (guidelines §7).

### 5.5 7b — Caveat 확인

```
[<entry>] 완료 (caveat)
- run_id: $RUN_ID · 변경: <src/ 변경 파일>
- prose 종이: .claude/harness-state/.sessions/{sid}/runs/$RUN_ID/

⚠️ Caveat: <has_ambiguous / has_must_fix / unexpected enum / sensitive untracked>

📝 메모리 candidate (#149):
- <caveat 발생 사유의 회고 — feedback / project type 후보. 다음 세션 회귀 방지용>
- <waste finding 의 반복 패턴 (예: ECHO_VIOLATION 2회+, MISSING_SELF_VERIFY 등)>
- <pr-reviewer NICE TO HAVE 중 자주 등장하는 항목>
- 후보 없음 시 "없음" 1줄

커밋/PR 진행할까요? (branch → PR → regular merge 자동) + 메모리 저장 진행?
```

worktree 처리도 사용자 결정.

**메모리 candidate 의무 (#149)**: caveat 발생 = 회귀 방지 신호. prose 본문에만 적고 끝내면 다음 세션에서 동일 caveat 재발. 메인은 위 양식의 *📝 메모리 candidate* 섹션을 *반드시* emit (없으면 "없음" 명시) — 사용자가 저장 여부 결정. 양식 없이 7b 보고 종료 = 룰 위반. 7a (clean) 도 review report 의 waste finding 이 있으면 같은 양식 적용.

**yolo 시**: `has_must_fix == false` + enum unexpected 만 (FAIL 1건 등) → 자동 7a 시도. `has_must_fix` 또는 `has_ambiguous` true → yolo 도 7b. yolo 라도 메모리 candidate 양식은 emit (사용자 위임 X — 본인이 저장 후 진행).

---

## 6. Step 8 — review 결과 인지

`--auto-review` stdout 자동 출력. 메인이 review 결과를 **세션에 직접 출력 — MUST**.

수동 호출 (auto-review 없이 실행됐을 경우):
```bash
"$(dirname "$HELPER")/dcness-review" --run-id "$RUN_ID" --repo "$(pwd)"
```

skip 금지 — 사용자 보고 전 1회 의무.

**세션에 직접 출력 — MUST**: Bash stdout 은 CC UI 에서 collapsed (펼쳐야 보임). 리뷰 결과를 **텍스트 응답으로 그대로 복사**해서 출력한다.
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

## 7. Loop 카탈로그 (cross-ref)

8 loop 별 풀스펙 (`entry_point` / `task_list` / `advance` / `clean_enum` / `expected_steps` / `branch_prefix` / Step 별 `allowed_enums` / 분기 / `sub_cycles`) = [`orchestration.md`](orchestration.md) §4.

**메인 Claude 진입 시 의무**: orchestration §4.1 인덱스 → 해당 loop sub-section read.

### 7.1 catastrophic 룰 정합

[`orchestration.md`](orchestration.md) §2.1 catastrophic 시퀀스 = `hooks/catastrophic-gate.sh` 강제. orchestration §4 의 각 loop sequence 가 이 룰 자연 충족 (code-validator → pr-reviewer 직전 PASS / engineer 직전 module-architect `PASS` enum / architect-loop §4.2 Step 4 (module-architect × K) 진입 직전 architecture-validator PASS / PRD 변경 후 plan-reviewer PASS).

> Note: 이전 §7.0 인덱스 + §7.2~§7.10 행별 풀스펙은 [`orchestration.md`](orchestration.md) §4 로 흡수 (loop-catalog.md 폐기, 8 → 7 SSOT).

---

## 8. 참조

- [`orchestration.md`](orchestration.md) §2~§4 — 시퀀스 mini-graph / 8 loop 행별 풀스펙 / handoff cross-ref
- 본 문서 §3.1 + §6 — echo / 자가점검 / REDO 분류 / 개선점 코멘트 (옛 dcness-rules §3/§4 흡수)
- [`../archive/conveyor-design.md`](../archive/conveyor-design.md) §2 / §3 / §7 — 컨베이어 디자인 + catastrophic gate (역사 자료)
- `harness/session_state.py` — helper CLI (`begin-run` / `end-run` / `begin-step` / `end-step` / `finalize-run` / `run-dir` / `auto-resolve`)
- `harness/run_review.py` — review 엔진 (`--auto-review` 호출 대상)
- `commands/<skill>.md` — skill 진입점 (input 정형화 + Loop 추천)
