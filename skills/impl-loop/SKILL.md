---
name: impl-loop
description: impl task (architect-loop 의 module-architect × K 산출물) 를 받아 정식 impl 루프로 구현하는 스킬. task 1개(single) 또는 여러 개(chain) 를 메인 Claude 한 세션 안에서 순차 처리 — 각 task = 1 PR + 1 이슈 close. 엔진은 풀 4-agent (test-engineer → engineer → code-validator → pr-reviewer, 엄정) 또는 build-worker (2/3-step, 경량) 를 개수·발화로 선택. 사용자가 "구현해줘", "/impl-loop <task>", "이 task 구현", "전부 구현", "task 다 돌려", "epic 전체 구현", "끝까지 구현", "/architect-loop 후 자동", "버그픽스", "한 줄 수정" 등을 말할 때 반드시 이 스킬을 사용한다. /architect-loop 의 후속.
---

# Impl Loop Skill — impl task 구현 루프 (single / chain × 풀 / build-worker)

> 본 스킬 = `/architect-loop` 가 `impl/NN-*.md` 본문 detail 까지 채운 산출물의 task 를 구현으로 옮긴다. task 1개든 여러 개든, 엄정 모드든 경량 모드든 본 스킬 하나가 처리한다. 버그픽스 케이스 = `/issue-report` 분류 후 본 스킬 fallback path (module-architect 선두 추가) 진입.

> 🔴 **라우팅 SSOT** — agent 결론 → 다음 호출 / retry 한도 / escalate 처리는 [`impl-loop-routing.md`](impl-loop-routing.md) 가 본 skill 의 단일 진본. 본 파일은 *진행 절차(Step)* 만 담는다. 분기·재진입·escalate 판단이 필요하면 그 파일을 읽는다.

## Loop

- **loop**: `impl-task-loop` (UI 감지 시 `impl-ui-design-loop` — designer + 사용자 PICK 2 step 선두 추가, 아래 `## UI 작업 시 designer 선두`)
- **entry_point**: `impl`
- **task_list** (Step 1): (풀 4-agent, default=single) test-engineer → engineer:IMPL → code-validator → pr-reviewer · (build-worker, default=chain) build-worker → pr-reviewer · (fallback: impl 부재 시 module-architect 선두 추가) · (impl-ui-design-loop) designer → 사용자 PICK 선두
- **advance**: `PASS` → `IMPL_DONE` → `PASS` → `PASS` (풀 4-agent) · `PASS` → `PASS` (build-worker) · `PASS`(designer) → 사용자 PICK → `PASS` → `IMPL_DONE` → `PASS` → `PASS` (impl-ui-design-loop)
- **expected_steps**: 4 (풀) / 5 (fallback) / 2 (build-worker) · impl-ui-design-loop = 6 (default) / 7 (fallback)
- **routing**: [`impl-loop-routing.md`](impl-loop-routing.md)

본 skill 본문 = impl-task-loop / impl-ui-design-loop 풀스펙 진본. catastrophic 보존 = [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh). chain (N task) 은 `impl-task-loop × N` driver — 각 task 가 독립 `begin-run impl` … `end-run` run 1개씩 (N task = N run = N review.md). 절차 mechanics = [`loop-procedure.md`](../../docs/plugin/loop-procedure.md).

## Inputs (메인이 사용자에게 받아야 할 정보)

- task 경로 (필수) — 단일 task (예: `docs/milestones/v0.2/epics/epic-01-*/impl/01-*.md`) 또는 task list / glob / epic 경로 (예: `.../impl/*.md`)
- 이슈 번호 (있으면)
- (선택) `--retry-limit N` — task 당 자동 재시도 한도 (default 3, 0 = 첫 실패 즉시 정지)
- (선택) `--escalate-on <signals>` — 즉시 정지 신호 (default `blocked`)

## 비대상 (다른 skill 추천)

- spec / design 단계 → `/product-plan` (PRD) 또는 `/architect-loop` (설계)
- task 부재 (계획 X) → `/issue-report` (분류 후 본 skill fallback) 또는 `/product-plan`

## 진입 분기 (개수 × 엔진 — 직교)

진입 시 메인이 **두 축을 독립으로 판정**한다. hook 강제 아님 — 메인 prose 자율 영역 ([`CLAUDE.md`](../../CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)).

**개수 축** — 절차 골격을 정한다.
- 인자가 **단일 task 경로** → `single` (1 run)
- **glob / 복수 / epic 경로** → `chain` (impl-task-loop × N run)

**엔진 축** — 각 run 안의 시퀀스를 정한다.
- **디폴트**: `single` → 풀 4-agent (엄정) · `chain` → build-worker (경량). 개수가 적으면 컨텍스트 여유 → 엄정, 많으면 누적 절감 → 경량 (#446 의도된 티어링을 디폴트로 보존).
- **override (사용자 발화)**: `엄정|꼼꼼|제대로|풀|rigor` 매치 → **풀 4-agent 강제** · `빠르게|경량|worker|가볍게` 매치 → **build-worker 강제**. 개수와 무관하게 적용 (1개를 worker 로 빠르게, N개를 풀로 엄정하게도 가능).

| 개수 \ 엔진 | 풀 4-agent | build-worker |
|---|---|---|
| **single (1 task)** | 디폴트 | override (`빠르게`) |
| **chain (N task)** | override (`엄정하게`) | 디폴트 |

판정 결과를 진입 시 사용자에게 1줄 echo (예: `single · 풀 4-agent (엄정)` / `chain 7 task · build-worker (경량)`).

## UI 작업 시 designer 선두 (impl-ui-design-loop)

UI 작업 감지 시 (풀 4-agent 엔진 한정) 시퀀스 **선두에 designer + 사용자 PICK 2 step 추가**:
- **designer** (`PASS,ESCALATE`) — 시안 생성. 환경 = `docs/design.md` frontmatter `medium: pencil|html` (부재 시 designer 가 detect + 역질문).
- **사용자 PICK** (helper begin/end-step 비대상) — 메인이 시안 경로 (Pencil 캔버스 / `design-variants/<screen>-v<N>.html`) + node-id 안내 + OK/NG. NG 시 designer 재호출 (sub_cycle `designer-ROUND-<n>`, round 한도 X).

이후 test-engineer → engineer:IMPL → code-validator → pr-reviewer = 풀 4-agent 동일. fallback 이면 designer 앞에 module-architect 1 step. designer `ESCALATE` → 사용자 위임.

---

## 절차 — 공통 골격 (single · chain 공유)

[`loop-procedure.md`](../../docs/plugin/loop-procedure.md) 의 Step mechanics 따름. 아래 룰은 single 1 run 과 chain 의 매 task run 에 **공통 적용**된다.

### 워크트리 (기본 켜짐)

진입 시 자동 `EnterWorktree(name="impl-{ts_short}")`. chain 은 outer 1회 — 모든 task 가 같은 worktree cwd 에서 직렬 진행 (git 충돌 X). 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 시에만 건너뜀. 자세히 = [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정).

**prev-tasks 초기화 (#525, build-worker 엔진 한정)**: `[PREVIOUS_TASKS]` 는 build-worker 진입 시 직전 task 산출을 주입(인접 task 인터페이스 정합용)한다. `begin-step build-worker` 가 *그 시점에* prev-tasks 파일을 읽어 stdout 으로 emit 하므로 ([`session_state.py`](../../harness/session_state.py) — single/chain 구분 안 함) — **reset 은 반드시 `begin-step build-worker` *호출 전* 에 해야 한다** (begin-step 후 reset 은 이미 emit 된 stdout 에 늦음). 따라서: **build-worker 진입이 (a) chain 의 첫 task 거나 (b) single 모드(`빠르게`/`worker` override 포함) 이면 `begin-step build-worker` 직전에 `dcness-helper prev-tasks-reset` 1회 호출 의무**. 안 하면 직전 chain 의 `[PREVIOUS_TASKS]` 잔재가 새 worker prompt 에 주입돼 stale 인터페이스에 맞출 위험. **chain 의 2번째+ task 는 reset 안 함** (직전 task 누적이 정합 입력). 까먹어도 FIFO cap(10) 안전망이나 명시 호출 권장. 풀 4-agent 엔진은 build-worker 미사용 → 본 룰 비대상.

**Base ref 분기 (MUST, #424)**: epic 단위 stories.md (impl task 경로의 `epic-NN-<slug>/stories.md`; root `docs/stories.md` 는 legacy 폴백) 상단 `**Base Branch:** feature/<slug>` 마커 매치 시 = 통합 브랜치 모드. outer worktree base ref 도 integration branch 와 정합 필요 (chain 은 `git worktree add -b <new> <path> origin/<integration>` + `EnterWorktree(path=<path>)` 패턴). 절차 = [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#base-ref-분기-통합-브랜치-모드-424).

### Pre-flight gate (진입 직후, 1회)

[`issue-lifecycle.md` mid-flow 누락 차단](../../docs/plugin/issue-lifecycle.md#mid-flow-누락-차단-pre-flight-gate) 매치 강제 — 부모 epic stories.md 상단 `**GitHub Epic Issue:** [#\d+]` 또는 `미등록 (사유: …)` 매치 0건 시 즉시 STOP + 사용자 보고. silent skip 금지.

### 부모 이슈 본문 read 의무 (MUST)

Pre-flight gate 통과 후, 매치된 **epic / story 이슈** 번호 *각 본문 read 의무*. **task 는 GitHub 이슈가 없다** ([`issue-lifecycle.md` 이슈 계층](../../docs/plugin/issue-lifecycle.md#이슈-계층) — PR 1개 = task 1개, PR 자체가 추적 단위) → `<task-num>` read 하지 않는다. task 컨텍스트는 impl 파일 frontmatter + 본문이 진본.

```bash
gh issue view <epic-num> | head -80
gh issue view <story-num> | head -80
# (bugfix 케이스로 invocation 에 이슈 번호가 명시된 경우만) gh issue view <그 이슈> | head -80   # optional 추가 컨텍스트
```

epic/story 이슈 본문에 수용 기준 / 추가 컨텍스트 / 결정 사항이 적혀있을 수 있음. read 안 하면 *impl 파일 누락 컨텍스트* 미인지 위험. chain 은 매 task 의 부모 epic/story 이슈 read 의무 ([#375](https://github.com/alruminum/dcNess/issues/375)).

### 진입 직전 — task 진행 상태 1회 확인 (MUST, #346)

본 task 가 *이미 머지된 상태* 인지 / *부분 진행 후 후속 정보* 가 plan tail 에 적혀있는지 1회 확인. 발견 시 wasted run 회피.

```bash
TASK_SLUG=$(basename "<task-path>" .md)
git log --oneline --grep "$TASK_SLUG" | head -5
tail -50 "<task-path>"
```

- 이미 머지됨 → (single) 사용자 보고 + 종료 / (chain) 해당 task skip + 다음 task
- 부분 진행 + tail section 후속 결정 → 그 내용을 진행 컨텍스트에 반영 후 정상 진입

근거: 실측 — 이미 머지된 task 재진입 시 ~3 분 + 컨텍스트 ~5% wasted. 진입 *전* 30 초 확인이 사후 회복보다 압도적 저비용.

### 강제 사전 — TaskCreate / TaskUpdate (사용자 가시성, MUST)

본 skill 의 모든 step 은 Claude Code 의 **TaskCreate / TaskUpdate 호출과 한 묶음**. 자율 skip 금지.

**WHY**: dcness helper `begin-step` / `end-step` 은 **dcness 내부 트래킹** (메인 컨텍스트 외, conveyor state 파일만 갱신, 사용자 UI 불가시). TaskCreate / TaskUpdate 는 **Claude Code UI 에 사용자가 직접 보는 진행 표시** — 별 역할, 중복 X, 보완 관계. 둘 다 호출 의무.

**catastrophic 안티패턴**: "begin-step 으로 트래킹 충분하다 자율 판단해서 TaskCreate skip" — 사용자가 진행 상태 불가시 → "왜 task 안 만들고 셀프로 돌려?" 지적 회귀.

**호출 시점** (skip 불가):
- 진입 직후 (Pre-flight 통과 후, 절차 진입 *전*) — task list 생성. single = task 헤더 1개 + 엔진별 sub-step. chain = 전체 task list ([진행 뷰](#진행-뷰-task-리스트)).
- 각 step 전환 — sub-step `TaskUpdate(status=in_progress | completed)`
- 종료 직전 — 헤더 + sub-step 전부 `TaskUpdate(status=completed)`

retry / POLISH 시 기존 sub-step 재활용 — 신규 TaskCreate X.

### 브랜치명 결정 (loop clean 후 자동 commit/PR)

브랜치·커밋·PR 네이밍은 [`git-spec.md`](../../docs/plugin/git-spec.md#브랜치) 이 **단일 SSOT** — 본 skill 은 자체 네이밍 규칙을 두지 않고 task 성격에 맞는 SSOT 패턴을 고른다. (`feat/`·`chore/` 류 자체 분류 금지 — git-naming 게이트 [`check_git_naming.mjs`](../../scripts/check_git_naming.mjs) 가 거부해 push/pre-push 에서 막힘.)

- **정식 impl task** (epic/story 컨텍스트 — impl 파일 frontmatter `story: N` (숫자) + 경로 `.../epic-NN-*/impl/`) → `feature/epic{N}_story{M}_{desc}` ([git-spec 브랜치](../../docs/plugin/git-spec.md#브랜치) "스토리 작업 impl")
- **공통 task** (impl 파일 frontmatter `story: 공통` + `task_index: —` — module-architect 공통 호출 산출) → `feature/epic{N}_common_{desc}` ([git-spec 브랜치](../../docs/plugin/git-spec.md#브랜치) `feature/{desc}` 의 epic-traceable 형 — story 번호 없음, 게이트는 generic feature 로 통과). 제목 = `[feature] {설명}`, 트레일러 = `Part of #<epic>` (부모 = epic 단일 룰, task-index trailer omit — [git-spec 기본 룰](../../docs/plugin/git-spec.md#기본-룰))
- **버그픽스 fallback** (invocation 에 이슈 번호 명시) → `fix/issue{N}_{desc}` ([git-spec 브랜치](../../docs/plugin/git-spec.md#브랜치) "버그픽스")
- `{desc}` = impl 파일 basename 의 앞 순번 `NN-` 를 **제거**한 설명부 (소문자 시작 + `[a-z0-9_-]` + 최소 3자 — [git-spec 브랜치](../../docs/plugin/git-spec.md#브랜치) `{desc}` 제약). 순번을 안 떼면 `feature/05-foo` 처럼 desc 가 숫자로 시작해 게이트 FAIL. 예: `impl/03-revival-button.md` + `story: 2` + `epic-07-*` → `feature/epic7_story2_revival-button`.
- base 분기 = [`git-spec.md`](../../docs/plugin/git-spec.md#git-절차) (통합 브랜치 마커 매치 시 그 base, 아니면 main).

### PR 생성 직전 — base 분기 체크 (MUST)

`gh pr create` 직전 epic 단위 stories.md (impl task 경로의 `epic-NN-<slug>/stories.md` = task 경로 조부모; root `docs/stories.md` 는 legacy 폴백) 상단 `**Base Branch:**` 줄 매치 1회 확인:
- 매치 → `gh pr create --base <매치 값>` (통합 브랜치 케이스, sub-PR base = `feature/<slug>`)
- 매치 없음 → `gh pr create --base main` (default, trunk-based)

까먹으면 sub-PR 이 잘못된 base 로 가서 epic atomic transaction 깨짐.

### git 권한

worktree branch 안 commit / push / PR 생성·머지 = **메인 Claude 전담**. engineer / build-worker / test-engineer 등 sub-agent 는 git commit/push/branch + `gh pr create/merge` 금지 — 코드 변경만 (worker 는 PR 본문·commit message *초안* 만 prose return, 실제 명령은 메인). main 직접 commit/push = ❌ (main-block hook 차단). 상세 = [`git-spec.md`](../../docs/plugin/git-spec.md#git-절차) + [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#impl-task-loop-commit-구조) + [`build-worker.md` 권한 경계](../../agents/build-worker.md#권한-경계-catastrophic).

### 사전 read (lazy — 필요시만, #400)

정상 흐름은 본 skill 본문 + 인용된 docs 섹션 링크 만으로 진행. 본문에 있는 catastrophic / Pre-flight gate / agent boundary 룰이 1차. *룰 모호 / 분기 발생* 시에만 [`impl-loop-routing.md`](impl-loop-routing.md) (라우팅) / `loop-procedure.md` (절차 mechanics) / `issue-lifecycle.md` 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

### impl 파일 사전 read 의무 (MUST — module-architect 7 원칙 + cost-aware #436)

진입 시 engineer / test-engineer / build-worker 가 impl 파일의 `## 사전 준비` 섹션 따라 다음 파일 read 의무. **단 통째 read 금지** — `CLAUDE.md` (글로벌) 의 cost-aware 행동 (#402) 정합: 200 line 초과 doc 은 grep + offset/limit 부분 read.

| 항목 | read 범위 |
|---|---|
| `docs/architecture.md` | 200 line 초과 시 본 task 의 `task_index` 에 해당하는 섹션만 grep + offset read (예: `grep -n "## 3\." docs/architecture.md` 로 위치 잡고 offset). 100 line 이하면 통째 OK |
| `docs/adr.md` | 본 task 영향 ADR 만 read (예: `grep "ADR-19A\|ADR-19E" docs/adr.md` 후 매치 줄 ±10 line). 부재 시 silent skip |
| `docs/prd.md` | 본 task 의 Story 항목 섹션만. 통째 read 금지 |
| 의존 task 머지 PR | `gh pr view <num> --json body --jq '.body' | head -20` — 1~2줄 결정 사항만 필요. 통째 body json 금지 (이슈 #436) |
| 형제 PR 환기 (같은 epic) | `gh pr list --search "[epic<N>]" --state merged --limit 10 --json title,url` 로 *title + url 만* 1회 훑음. body 통째 read 금지 — 인터페이스 변경 의심되면 그때 `--json body` 단건 fetch |
| 의존 모듈 (수정 X 영역) | **grep + 시그니처만** read. 예: `grep "^export" path/to/file.ts | head -10` + 매치 줄 ±2 line. 통째 read 금지 — 본 task 가 수정하지 않는 영역의 구현 디테일 불요 |
| 의존 모듈 (수정 영역) | 통째 read OK |

→ agent prompt 에 impl 파일 경로 쓰면 agent 가 위 룰 따라 자체 read. *메인 Claude 가 사전 inject* 불필요.

**추가 — 메인 직접 read 의무 (강조 + cost-aware, #436)**: 메인 Claude 는 *진입 분기 판단* 에 필요한 **최소** 만 read. agent prompt 경로 박는 것 외에 메인이 통째 read 하지 말 것 — agent 가 자체 read 함.

- 메인 진입 분기 판단 필요 정보 = (a) 이번 task 의 Scope (impl 파일 Scope 섹션 grep) / (b) 의존 task 산출물 위치 (impl 파일 사전 준비 섹션 grep) / (c) ADR 위반 의심 시 해당 ADR 만 grep.
- `docs/architecture.md` / `docs/adr.md` *통째 read* 금지 (이슈 #436 실측 — task 진입 직후 80k messages / 12% context 누적, 코드 1줄 안 썼는데). 부분 read 의무.
- 정합: `CLAUDE.md` 의 cost-aware 행동 (#402) — "큰 plan/docs 통째 read 회피 → grep + offset/limit. sub-agent 위임 우선".

### validation provider resolve (Codex opt-in)

`code-validator` / `pr-reviewer` (또는 build-worker self-validate 후 pr-reviewer) 호출 직전 provider 를 local routing config 로 resolve 한다. config = `~/.claude/plugins/data/dcness-dcness/routing.json`.

```bash
PROVIDER=$("$HELPER" routing resolve <agent>)
if [ "$PROVIDER" = "codex" ]; then
  "$PLUGIN_ROOT/scripts/dcness-codex-validator" <agent> --prompt-file "$PROMPT_FILE"
else
  # 기존 Claude Agent(subagent_type="<agent>") 경로.
fi
```

wrapper 가 Codex 마지막 응답을 `/tmp` 에 받고 `dcness-helper end-step <agent> --prose-file ...` 까지 수행하므로 Codex route 에서는 별도 `end-step` 중복 호출 금지.

---

## 엔진 A — 풀 4-agent (default = single)

default 시퀀스 = **test-engineer → engineer (IMPL) → code-validator → pr-reviewer**. 4 단계 *모두 호출* 의무 (MUST — false-clean 차단, #431).

✅ 정상 흐름:
1. **test-engineer** (TESTS_WRITTEN) → 테스트 선작성
2. **engineer:IMPL** (IMPL_DONE) → 구현 + 테스트 PASS
3. **code-validator** (PASS) — impl 계획 ↔ 구현 정합 검증
4. **pr-reviewer** (LGTM, read-only) — 코드 품질·보안 검토만. `tools: Read, Glob, Grep` — *commit/push/PR 생성·머지 권한 없음*. **엔진 A 는 PR 생성 *전* 단계라 pr-reviewer 입력 = impl 경로 + 구현 변경 파일 목록(로컬 diff)** — PR 객체 아님 (build-worker 엔진과 달리 PR 미생성 상태. [`pr-reviewer.md`](../../agents/pr-reviewer.md) 입력 규약 참조)
5. **메인 Claude (git/PR)** — pr-reviewer PASS 후, **engineer/code-validator prose (변경 요약·의도) + [`git-spec.md`](../../docs/plugin/git-spec.md#pr-본문) 템플릿 기반으로 메인이 commit message·PR 본문 작성** (엔진 A 는 build-worker 미사용 → "worker prose" 아님. PR 트레일러 `Closes/Part of` 는 impl frontmatter `task_index`/`story` + [git-spec PR 트레일러](../../docs/plugin/git-spec.md#pr-트레일러-part-of-closes) 적용) → `scripts/pr-create.sh` 호출 → `scripts/pr-finalize.sh` 머지

❌ 안티패턴 (#431 실측 회귀): test-engineer + engineer 만 호출하고 commit/push/PR 안 만들고 prose "PASS" 박고 종료. 1 자식 = 1 PR + 1 이슈 close 보장 깨짐.

후반 3 단계 (code-validator + pr-reviewer + 메인 PR) skip 차단: task 를 clean 표기 *전*, code-validator 가 PASS 를 냈고 pr-reviewer 가 실행된 뒤 *메인 Claude 가* PR 생성·머지까지 마쳤는지 직접 확인. 흔적 부재 시 → false-clean 의심 → `blocked` 강등 + 사용자 개입.

- fallback (정식 위치 부재 / impl 파일 부재) → 시퀀스 선두에 module-architect 1 step 추가.
- UI 감지 → 선두에 designer + 사용자 PICK (위 `## UI 작업 시 designer 선두`).

## 엔진 B — build-worker (default = chain)

시퀀스 = **build-worker (2-step: test+impl+self-validate 통합) → pr-reviewer**. impl 파일 부재 시 module-architect 선두 (3-step).

1. **begin-run + (reset) + build-worker step** — `begin-run impl` → **(chain 의 첫 task 또는 single 모드면 `dcness-helper prev-tasks-reset` — `begin-step` *전*, prev-tasks 초기화)** → `begin-step build-worker` → `Agent(build-worker, prompt=<impl 경로 + task slug + RUN_ID + (begin-step stdout 의 [PREVIOUS_TASKS] 섹션 있으면 그대로 포함, #525)>)` → 반환 prose 결론 분기 (= [`impl-loop-routing.md`](impl-loop-routing.md#결론-다음-호출-매핑)). 이후 `end-step build-worker`. worker 안 phase 별 prose (`build-test.md` / `build-impl.md` / `build-validate.md`) 는 worker 자체 Write — [`loop-procedure.md` build-worker phase prose](../../docs/plugin/loop-procedure.md#build-worker-phase-prose-impl-loop-hybrid-a-한정).
2. **git/PR 생성 (메인)** — worker prose 의 commit message + PR 본문 초안을 임시 파일로 박고 `scripts/pr-create.sh` 통합 호출:
   ```bash
   cat > /tmp/pr-body-<slug>.md <<'PR'
   <worker prose 의 PR 본문 그대로>
   PR
   cat > /tmp/commit-msg-<slug>.md <<'COMMIT'
   <worker prose 의 commit message 그대로>
   COMMIT
   bash scripts/pr-create.sh \
     --branch <§브랜치명 결정 산출: feature/epic{N}_story{M}_{desc} 또는 fix/issue{N}_{desc}> --base <base> \
     --title "<...>" --body-file /tmp/pr-body-<slug>.md \
     --commit-msg-file /tmp/commit-msg-<slug>.md
   ```
   분리 명령 (`git checkout -b` / `add` / `commit` / `push` / `gh pr create` 각각) 은 *비권장* — 메인 turn 누적 영역.
3. **pr-reviewer step + 머지** — `begin-step pr-reviewer` → `Agent(pr-reviewer, ...)` → `PASS` 시 `bash scripts/pr-finalize.sh <PR>` (gh pr merge --auto + watch + main sync 자동). `FAIL` 시 engineer POLISH 단발 진입 → **POLISH_DONE 후 메인이 POLISH 변경을 PR 브랜치에 `git add`/`commit`/`push` 1회** (PR 은 step 2 에서 이미 생성됨 — 변경이 worktree 에만 남으면 stale PR 머지/ dirty finalize 위험) → pr-reviewer 재리뷰 (cycle ≤ 2). `end-step pr-reviewer`.

> **impl 파일 부재 시 module-architect 선두** — build-worker 직전에 `begin-step module-architect` → `Agent(module-architect, prompt=<task 컨텍스트 + impl 파일 생성 위치>)` → `PASS` 시 impl 파일 생성 확인 후 `end-step module-architect` → 정상 build-worker 진입. `ESCALATE` 시 사용자 위임.
>
> **자동 폴백** — build-worker 가 진행 중 `SPEC_GAP_FOUND` 던지면 분량 메타 (small/medium/large) 기반 분기 (= [`impl-loop-routing.md`](impl-loop-routing.md#결론-다음-호출-매핑)). attempt 한도 초과 시 사용자 위임.

❌ build-worker 안티패턴: phase 2 종료 전 GREEN 미확인 (false-clean) / build-worker 가 `Agent(pr-reviewer)` 또는 `git commit` 직접 호출 (권한 경계 위반 — 메인이 별 turn 처리) / phase prose 자체 Write 확인 skip (`build-{test,impl,validate}.md` 3개 실존 검증 의무, 부재 시 `blocked` 강등).

---

## chain 모드 (N task 오케스트레이션)

chain = 위 공통 골격 + 엔진을 **task 한 개씩** 반복. task N 이 완전히 끝난 (PR 머지 + 이슈 close) 뒤에만 task N+1 진입. 한 번에 한 task.

### 실행 전 계획 확인 (dry preview)

`impl/NN-*.md` prefix 기준 직렬 순서 확정 후, **task1 진입 *전* 실행 계획을 1회 표로 echo** (사용자 가시성 + 잘못된 순서·범위 사전 포착, #526). 각 task frontmatter (`story:` / `task_index:`) awk 추출 + PR 트레일러 판정 = [`git-spec.md`](../../docs/plugin/git-spec.md#적용-절차-pr-생성-직전-사전-체크-impl-파일-frontmatter-기반) + [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#impl-task-loop-commit-구조) 재사용.

```
📋 실행 계획 (K task · 엔진 <풀 4-agent | build-worker>)
| # | 모듈 | impl 파일 | task_index | PR 트레일러 | sub-step |
|---|------|----------|-----------|-----------|----------|
| 1 | <slug> | `NN-<slug>.md` | <i/total 또는 —> | Part of #<story> | <sub-step> |
전체: K task · 예상 PR K개
```

**확인 강도 (task 수 임계값)**:
- task **< 10** → 계획 표만 echo 후 **자동 task1 진입**.
- task **≥ 10** → 계획 표 echo + `진행할까요? (Y/n)` 1회 확인 후 진입.
- **yolo 모드** (`yolo` / `auto` / `끝까지` / `막힘 없이` / `다 알아서`, [`loop-procedure.md`](../../docs/plugin/loop-procedure.md) yolo 키워드) → task 수 무관 자동 진입.

### task 경계 — next-task 통합 호출 (#471)

마지막이 아닌 task 종료 시 `dcness-helper next-task --entry-point impl` 1회 호출 — helper 가 (이전 run end-run + previous review.md stdout + 새 run begin-run) 통합 처리 → 메인은 stdout 의 `[new] run_id` 만 받아 다음 task 진입. *마지막* task = `next-task` 대신 `end-run` 단독.

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dcness-helper" next-task --entry-point impl   # 마지막 아님
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dcness-helper" end-run                         # 마지막
```

### enum 별 분기

- `clean` → next-task → 다음 task 진입
- `error` → 자동 재시도 (한도 `--retry-limit`, default 3). 한도 초과 시 정지 + 사용자 위임.
- `blocked` → 즉시 정지 + 사용자 위임.
- **전체 완료** → 보고 (처리 N/N + 각 PR URL). 본 시점 *이후* 메인이 자율 작업 (이슈 등록 / cleanup / 측정) 진입 시 진입 *전* `dcness-helper post-task-begin --reason "<사유>"` 호출 의무 (task ROI 측정 분리 marker, #472).

### review 출력 재정의 (#446)

chain 안에서는 [종료 조건](#종료-조건-must-메인-claude-의무) 의 review.md *원본 그대로 출력 MUST* 가 **재정의** 된다 (매 task 전수 출력 시 N × review.md 누적 → cache_read 폭주). 메인 컨텍스트 출력 = 5줄 요약:

```
[task<i> · <slug>] <clean|error|blocked>
<2번째 줄 — 엔진별 (아래)>
finding: <PASS 시 "없음" / FAIL·NICE TO HAVE 시 1-2 문장>
PR <#NNN> merged · closes #<MMM>
next: <다음 task slug 진입 | 정지 사유>
```

**2번째 줄 = 엔진별 (chain 은 build-worker / 풀 4-agent 둘 다 가능 — 엔진에 맞춰 채운다)**:
- **build-worker 엔진**: `build-worker: N tests RED→GREEN · M files +X -Y · validate PASS|FAIL · pr-reviewer: LGTM|FAIL` (impl 부재로 module-architect 선두면 앞에 `module-architect: PASS|ESCALATE · ` 추가)
- **풀 4-agent 엔진** (chain + `엄정하게` override): `test-engineer: N tests · engineer: M files +X -Y · code-validator: PASS|FAIL · pr-reviewer: LGTM|FAIL` (fallback module-architect 선두면 앞에 `module-architect: PASS · ` 추가)

**5줄 작성 책임 = 메인 (PR 생성·머지 완료 후)** — `PR <#NNN> merged` 의 번호·merged 상태는 `scripts/pr-create.sh` / `pr-finalize.sh` 완료 후에야 확정된다. 특히 **풀 4-agent 엔진은 PR 이 pr-reviewer PASS *후* 생성**되므로 pr-reviewer 는 PR 번호조차 모른다 — pr-reviewer 가 5줄을 박을 수 없다. 따라서 pr-reviewer 는 자기 결론(LGTM/FAIL) + 엔진별 메트릭 *재료* 만 prose 에 제공하고 ([`pr-reviewer.md` 산출물 정보 의무](../../agents/pr-reviewer.md#산출물-정보-의무-형식-자유) 정합), **메인이 머지(pr-finalize) 완료 후 위 5줄을 종합해 chat 에 echo** 한다 — 자유 형식 단축 금지 (외부 사용자 [F8 실측](https://github.com/alruminum/dcNess/issues/507)). build-worker 엔진은 PR 이 pr-reviewer *전* 생성되지만, merged 상태는 동일하게 머지 후 확정이라 5줄 종합은 메인 책임으로 통일.

**디스크** — `<run_dir>/review.md` 는 end-run 안전망이 원본 그대로 저장. `/run-review` 진단 / compaction 후 재진입 시 디스크에서 read.

### 진행 뷰 (task 리스트)

사용자가 *현재 진행 페이즈* 를 한눈에 보도록 관리. Task 시스템 = 평탄 리스트 (부모/자식 필드 X) + 생성순 표시 — 중첩은 subject 들여쓰기로 흉내. 완료 task 는 한 줄, 현재 task 만 sub-step 펼침, 예정 task 는 대기 줄:

```
✓ task1 · <모듈명>
▾ task2 · <모듈명>          ← 현재 (in_progress)
   ㄴ build-worker          ← sub-step (엔진별)
   ㄴ pr-reviewer
○ task3 · <모듈명>          ← 예정 (pending)
```

- sub-step 수 = 엔진별. build-worker: 2 (`build-worker` / `pr-reviewer`), impl 부재 시 3 (`module-architect` 선두). 풀 4-agent: 4 (`test-engineer` / `engineer:IMPL` / `code-validator` / `pr-reviewer`), fallback 5.
- **task 완료 → 다음 (다시 그리기 — task 수 별 분기)**:

| 총 task 수 | 절차 | 비용 |
|---|---|---|
| **≤ 10** | 4 단계 완전 다시 그리기 — 가시성 우선 | 매 task ~N 호출 |
| **11~20** | 3 단계 부분 (재생성 skip) — 다음 헤더만 in_progress | 매 task ~3 호출 |
| **> 20** | 최소 갱신 — sub-step deleted + 다음 헤더 in_progress | 매 task ~2 호출 |

4 단계 (완전 다시 그리기): ① task i sub-step 전부 `deleted` ② task i 헤더 `completed` ③ task i+1~N 헤더 `deleted` ④ TaskCreate `task(i+1) 헤더(in_progress)` → sub-step → 남은 헤더. 생성순 = 표시순 + 중간삽입 불가라 다시 그려야 sub-step 이 부모 밑에 옴. (trade-off 근거: 외부 사용자 [F9 실측](https://github.com/alruminum/dcNess/issues/507).)

### compaction 중 진행 (안전망) + 세션 분할 권장

긴 chain 중 auto-compaction 가능. 진행 상태는 conveyor state 파일 (`live.json` / `.by-pid-current-run/` / `run-NN` / `current_step`) 이 SSOT — compaction 돼도 손실 0. compaction 직후 chain 도중이라 판단되면 run state 재read 해서 현재 task index + step 식별 후 재개.

| 총 task 수 | 권고 |
|---|---|
| ≤ 9 | single-session 진행. |
| 10~19 | single-session 가능, task 절반 진입 시점에 *"context 60%+ 추정 — /smart-compact 권장"* 1줄 안내. |
| ≥ 20 | **multi-session 권장** — epic 을 절반/3분할로 쪼개 별 세션 진행. conveyor state SSOT 가 task 경계 재개 보장. |

---

## single 모드

single = 위 공통 골격 + 엔진을 **1 run** 진행. chain 의 진행 뷰 다시그리기 / next-task / review 재정의 **비대상**.

### 종료 조건 (MUST — 메인 Claude 의무)

> ⚠️ **함정**: PR merge 까지 자동 완료된다. 메인 본능 "merge = 작업 끝" 으로 *반드시* 다음을 skip → 자동 회고 마비. skip 금지.

PR merge 직후 *반드시* 실행 (issue #396):

```bash
"$HELPER" end-run
```

- end-run 안전망 (`session_state.py`) 이 finalize-run --auto-review 자동 발사 → `<run_dir>/review.md` 저장 + stderr `[REVIEW_READY] <path>` emit.
- **REVIEW_READY 후속 — echo MUST**: stderr `[REVIEW_READY] <run_dir>/review.md` 감지 시 `review.md` 본문을 *character-for-character* 세션 응답에 복사 ([`loop-procedure.md`](../../docs/plugin/loop-procedure.md#step-8-review-결과-인지)). 압축 / 요약 / 재배치 / 테이블 ASCII 변환 절대 금지 (single = rigor, review.md 원본 그대로 — chain 의 5줄 재정의와 차이).

**메인 인사이트 (자율, #396)**: review.md 끝 `## 📝 메인 인사이트` prompt 보고 *구체적 학습 1줄* 쓸 수 있음:

```bash
"$HELPER" insight <agent>[-<mode>] "<자연어 한 줄>"
```

- agent+mode 별 FIFO 10 한도. 다음 run begin-step 자동 inject. 미호출 = noop (자율). *실수 환기* 형태로만 (예: "🚨 X 실수 — 반복 X"). "잘 됐던 케이스" 누적은 학습 가치 0.

---

## 안티패턴 (회귀 방지)

- ❌ task N 개를 한 sub-agent 호출에 묶어 한 번에 처리 — task 별 PR / 이슈 close 분리가 깨지고 `/run-review` 분석 단위 붕괴. 한 번에 한 task. (build-worker 는 1 task 통합 — 충돌 X)
- ❌ task 동시 병렬 진행 — git 충돌 + cache_read 폭주 ([#216](https://github.com/alruminum/dcNess/issues/216) — \$1,531 / 단일 세션). 직렬 진행.
- ❌ 한 task 의 PR 머지 전 다음 task 진입 — task 간 의존 깨짐.
- ❌ escalate 신호 무시하고 다음 task 진행 — 사용자 부재 환경 추측 진행 = 폭주.
- ❌ chain 전체 완료 후 자율 작업 (이슈 등록 / cleanup / 분석) 진입 시 `post-task-begin` marker 누락 — task ROI 측정 왜곡 (#472).
- ❌ **TaskCreate / TaskUpdate skip — `begin-step` 트래킹으로 충분 자율 판단** (catastrophic). [강제 사전](#강제-사전-taskcreate-taskupdate-사용자-가시성-must) 참조.

## 참조

- 라우팅 (결론→다음 / retry / escalate): [`impl-loop-routing.md`](impl-loop-routing.md) — 본 skill 라우팅 SSOT
- loop spec: 본 skill `## Loop` + 본문. 공통 절차 mechanics: [`loop-procedure.md`](../../docs/plugin/loop-procedure.md#진입-모델)
- 권한 경계: [`agent_boundary.py`](../../harness/agent_boundary.py)
- 브랜치·커밋·PR 네이밍: [`git-spec.md`](../../docs/plugin/git-spec.md)
- agent 정의: [`test-engineer.md`](../../agents/test-engineer.md) / [`engineer.md`](../../agents/engineer.md) / [`code-validator.md`](../../agents/code-validator.md) / [`pr-reviewer.md`](../../agents/pr-reviewer.md) / [`build-worker.md`](../../agents/build-worker.md) / [`module-architect.md`](../../agents/module-architect.md) / [`designer.md`](../../agents/designer.md)
- 트랙 SSOT (Hybrid A): [issue #446](https://github.com/alruminum/dcNess/issues/446)
