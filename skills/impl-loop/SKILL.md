---
name: impl-loop
description: Story/공통 impl task 파일을 받아 build-worker로 구현하는 runner. worktree 이후 run/state/step/provider launch를 기존 implementation chain 한 호출로 준비한다. task 1개 또는 story/epic chain을 처리하고, 모든 구현이 끝난 뒤에만 통합 review·acceptance·PR 마감 진본을 읽는다. 일반 구현은 /impl.
---

# Impl Loop — one-shot worker start

`/impl-loop`는 `docs/epics/**/impl/NN-*.md`를 단일 구현 엔진 `build-worker`로 처리한다. 일반 버그픽스·한 줄 수정·설계 문서 없는 구현은 [`/impl`](../impl/SKILL.md)로 간다.

```text
target/AC snapshot → worktree → implementation-chain 한 호출 → worker
```

구현 전 메인은 provider resolve, `prev-tasks-reset`, `begin-run`, `begin-step`, prompt-slot 문서 확인을 따로 수행하지 않는다. 기존 `dcness-implementation-chain`이 story runner와 helper를 호출해 한 번에 소유한다.

모든 task가 completed 되기 전에는 validator provider, Cartography freshness, holistic review/Sanity 렌즈, product acceptance, close audit, PR/merge 상세를 읽지 않는다. 그 경계에서만 [`impl-loop-finish.md`](impl-loop-finish.md)를 읽는다. worker 실패 분기가 실제로 생겼을 때만 [`impl-loop-routing.md`](impl-loop-routing.md)를 읽는다.

## 입력과 소유권

- 입력: impl task 1개, task 목록, glob 또는 epic impl 디렉터리
- 구현: `build-worker` 하나가 test → impl → self-validate → task local commit 수행
- 상태: `dcness-story-runner`가 chain identity, 정렬된 task, commit/status를 저장
- 외부 상태: push, PR, merge, issue mutation은 메인만 수행
- merge: 자동 merge 금지, 사용자가 유일한 merge gate

같은 story 값은 path 정렬 결과에서 한 연속 block이어야 한다. 다중 story는 `story1(base=main) → story2(base=story1)` branch stack이며, 다음 story는 직전 story 브랜치에서 재분기한다.

## 진행 뷰 (task 리스트)

메인은 impl-loop의 실제 진행을 사용자에게 보이도록 `dcness-helper chain-view`
출력을 적용한다. story runner state와 implementation chain receipt는 실행
진본이고, 진행 뷰는 그 상태를 사용자 UI에 투영하는 표시다. 둘은 대체 관계가
아니다.

확정된 순서의 전체 target task는
`{"tasks":[{"name":"<task>","engine":"build-worker","closes":"story"}]}`
형태로 한 번 만들고 run 동안 재사용한다. 별도 파일은 만들지 않고
`chain-view --tasks-json '<json>' --compact`로 넘긴다. UI checkpoint가 있는 task만
`engine: "ui-build-worker"`를 쓴다. `closes`는 마감 task에만 지정한다.
epic 마감이면 값은 `"epic"`이다.
메인이 완료·현재·예정 글리프, 들여쓰기, sub-step 또는 task 수별 다시 그리기
전략을 다시 계산하지 않는다.

정상 fast-start에서는 `chain-view`와 background `dcness-implementation-chain`을
같은 assistant turn의 독립 tool batch로 발행한다. 두 호출은 서로 결과를 입력으로
쓰지 않는다. implementation-chain은 chain-view 결과나 TaskCreate/TaskUpdate
완료를 기다리지 않는다. batch 발행이 불가능한 환경이면 implementation-chain을
먼저 launch하고 바로 chain-view를 호출한다. 진행 뷰 때문에 별도 직렬 tool call을
추가하지 않는다. helper 결과가 돌아오면 worker가 실행되는 동안 `operations`를
순서 그대로 Task 시스템에 적용하고 `view`를 사용자에게 진행 메시지로 표시한다.

호출 경계는 다음 세 곳이다.

1. **chain 진입**: worktree 진입 뒤
   `chain-view --tasks-json '<json>' --current 0 --initial --compact`와 one-shot
   implementation-chain을 같은 첫 tool-bearing turn에 발행한다. worker launch가
   진행 뷰 렌더를 기다리지 않는다.
2. **task 완료마다**: task `i`를 completed로 mark하고 `next-action`을 받은 뒤
   다음 task가 있으면 `chain-view --prev <i> --current <i+1>`과 다음
   implementation-chain을 같은 assistant turn에 발행한다. story branch 전환이
   필요하면 branch를 만든 직후 이 batch를 발행한다. resume처럼 사용자 Task
   목록이 비어 있으면 `--initial`로 현재 index 전체를 다시 그린다.
3. **마감 시퀀스 진입**: 마지막 build-worker가 끝나 `action=done`이면 이미
   펼쳐진 마감 task에서 `build-worker` sub-step을 completed,
   `validation-sequence:STORY|EPIC`을 in_progress로 TaskUpdate하고 그 `view`를
   다시 표시한 뒤 `impl-loop-finish.md`로 이동한다. `--initial`을 기존
   Task 목록 위에 다시 적용해 중복 생성하지 않는다. 마감 시퀀스까지 PASS한
   뒤에만 `--prev <last-index> --current <task-total>` payload를 적용해 전체
   완료를 표시한다.

각 payload의 `create_header`·`create_substep`은 TaskCreate, 상태 변경과 삭제는
TaskUpdate로 적용한다. Task tool이 없거나 helper가 실패하면 같은 완료/현재/예정
표현을 수동으로 다시 만들고 run은 계속한다. helper는 도구이지 gate가 아니며
run state를 변경하지 않는다. 현재 run에 `journey_deferred`가 있으면 렌더된
`view` 바로 아래에 해당 journey id 목록을 유지하고 이후 worker prompt에도
같은 목록을 전달한다.

## Fast start

### 1. 최소 snapshot

warm handoff나 사용자 입력이 exact task path·AC snapshot pointer·slim prompt와
feature worktree 상태를 이미 확정했으면 이 snapshot을 다시 `ls`/`find`/`cat`하지
않는다. one-shot launch가 첫 tool-bearing turn의 독립 batch에 포함된다. 같은
turn의 chain-view는 launch를 기다리게 하는 선행 호출이 아니다.
worktree/default-branch 정합은 chain이 mutation 전에 검증한다.

1. `stories.md`의 parent epic/story issue pointer를 확인한다.
2. 대상 issue 본문을 한 번 읽어 target GitHub issue AC snapshot을 보관한다. 진행 중 재조회하지 않는다.
3. AC가 없거나 검증 주체가 없으면 close 때 현행 typed AC로 갱신한다. 의미를 임의 추론해 체크하거나 재분류하지 않는다.
4. task가 이미 머지됐는지만 `git log --grep <task-slug>`로 확인한다.

전체 repo scan, generated TDD 설치 health, provider preview, branch naming SSOT, 후기 validator/Cartography/close 문서는 worker 전에 읽지 않는다.

### 2. worktree가 첫 mutation보다 먼저

- 사용자가 “워크트리 없이”라고 하지 않았으면 즉시 `EnterWorktree`를 사용한다.
- story branch는 main 또는 직전 story branch를 base로 만든다.
- worktree 진입 뒤 task pointer와 test seam만 다시 잡는다.
- `.dcness-work` state, `begin-run`, issue lifecycle mutation은 worktree 진입 전 실행하지 않는다.
- canvas-design의 seed·draft·확정본 mutation도 worktree 안에서만 수행한다.

첫 메시지는 다음 한 줄이면 충분하다.

```text
착수: <task> · worker 시작
```

### 3. UI checkpoint와 slim prompt

UI 기준은 task/handoff에 드러난 정보만 3분기한다. 확정 목업·사용자 이미지가 있으면
그 pointer를 slim prompt로 넘기고, 시각 구조 불변이면 그대로 진행한다. 신규 시각
구조인데 기준이 없을 때만 main-owned `canvas-design` checkpoint를 열어 사용자
PICK 뒤 `docs/design-variants/<screen-id>.html` 확정본 승격을 마친다. `canvas-design`은
helper begin/end-step 비대상이며 mode 없는 foreground designer Agent의
SubagentStart/PostToolUse lifecycle hook만 사용한다. 이 조건을 알아내려고 별도 UI
전수조사를 하지 않는다.

prompt에는 다음만 둔다.

- 현재 impl task path
- target issue AC snapshot pointer
- 확정된 사용자 선택이 있으면 그 선택 한 줄
- 진본에 없는 scope/test 제약

과거 transcript, review/close 절차, provider 설명, worktree 경로, `[PREVIOUS_TASKS]`를 복사하지 않는다. wrapper가 worktree와 이전 task 요약을 동적으로 합성한다. 구현 방법·assert 방식·알고리즘을 처방하지 않는다.

### 4. one-shot launch

첫 task는 아래 명령 하나를 Bash `run_in_background: true`로 실행한다. shell 안에
`nohup`, `&`, `disown`, redirect, `sleep`/polling을 덧붙이지 않고
`.dcness-work`를 미리 만들지 않는다. `--init-path`는 전체 대상 task에 대해
반복한다. provider를 미리 resolve하지 않는다.

```bash
PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"

"$PLUGIN_ROOT/scripts/dcness-implementation-chain" build-worker \
  --chain-state .dcness-work/story-run.json \
  --init-path <impl-task-1> \
  --init-path <impl-task-N> \
  --prompt-file <slim-prompt> \
  --issue-num <target-issue> \
  --acceptance-required
```

사용자가 provider를 직접 골랐을 때만 `--provider <provider> --provider-provenance explicit`을 추가한다. 기본 호출은 chain 내부 routing이며 provider option을 생략한다.

이 한 호출의 소유권은 다음과 같다.

- chain: feature worktree 여부를 state mutation 전에 검사
- story runner: state를 올바른 worktree에서 정확히 한 번 초기화
- chain: chain 최초 1회만 previous tasks 초기화
- chain/helper: 현재 task의 `begin-run impl --design-doc`를 필요할 때 정확히 한 번 생성
- chain/helper: `--acceptance-required`를 chain의 마지막 task run에만 기록
- chain/helper: completed 이전 task run이 있으면 다음 호출 안에서 닫고 현재 task run을 정확히 한 번 생성
- chain: 같은 run의 `begin-step build-worker`를 provider fork 전에 정확히 한 번 기록
- chain: provider resolve·fallback·same-workspace recovery
- worker wrapper: 마지막 prose와 대응 `step_completed` terminal receipt

같은 state와 같은 `--init-path` 재호출은 task 목록·project root가 일치할 때 기존 state를 재사용하고 중복 초기화하지 않는다. default branch에서 초기 launch하거나 state의 project root가 다르면 provider fork 전에 실패한다.
background task notification의 최종 exit code가 실행 진본이다. exit 0이면 stage 중간
stderr나 partial output에 provider 실패가 보여도 fallback을 포함한 chain이 terminal
prose를 기록한 것이므로 재호출하지 않는다. 최신 prose가 `PASS`일 때만 mark하고,
`TESTS_FAIL`·`SPEC_GAP_FOUND`·`VALIDATION_BLOCKED`·`IMPLEMENTATION_ESCALATE`는
[`impl-loop-routing.md`](impl-loop-routing.md)대로 처리한다. 같은 current run에 이미
`step_completed`가 있으면 chain 재호출도 provider를 다시 fork하지 않는 성공 no-op이다.

### 5. worker task loop

- worker는 impl 파일의 `## 사전 준비` pointer만 따라 focused read한다.
- 200 line 초과 문서는 관련 section만 `rg` + offset read하고, 수정하지 않는 모듈은 signature만 읽는다. 메인은 worker 대신 문서를 통째로 읽지 않는다.
- task local commit과 실제 검증 명령·exit code·clean status가 report에 있어야 PASS다.
- Story 마지막 task는 Story AC 전항목을 종합 검증한다. 종합 REQ가 없으면 `SPEC_GAP_FOUND`다.
- 기본 build-worker는 task를 읽은 직후 자동 `(JOURNEY)` 선언을 감지하고, 같은
  worker context에서 source read/edit보다 먼저 `JOURNEY_ENV_PREFLIGHT`를 내부
  phase로 한 번 수행한다. journey 미선언은 no-op이며 별도 main/provider launch를
  만들지 않는다.

성공 뒤 task commit을 mark하고 `next-action`을 같은 Bash 호출로 묶는다.

```bash
"$PLUGIN_ROOT/scripts/dcness-story-runner" mark \
  --state .dcness-work/story-run.json \
  --task <id> --status completed --commit <sha> &&
"$PLUGIN_ROOT/scripts/dcness-story-runner" next-action \
  --state .dcness-work/story-run.json
```

- `action=task`: 다음 task용 slim prompt로 chain을 다시 호출한다. 기존 state이므로 `--init-path`는 생략하며, chain이 이전 run 종료와 새 run 시작을 같은 호출 안에서 처리한다.
- `action=story-pr`: 직전 story tip/base를 봉인하고 PR 없이 다음 story branch를 만든다.
- `action=done`: 진행 뷰를 마감 시퀀스 상태로 갱신하고 worker loop를 끝낸 뒤 GREEN 이후 진본으로 이동한다.
- `action=error|blocked`: 그때만 routing 문서를 읽어 bounded recovery 또는 사용자 결정을 수행한다.

진행 메시지는 `진행: RED/첫 edit 확인`, `진행: 구현·검증 green`, `진행: 통합 review 시작`처럼 사용자에게 의미 있는 변화만 남긴다. helper PASS/no-op과 polling 자체를 성과처럼 반복 출력하지 않는다.

## 질문 budget과 안전

관련 코드 선택, scope 오타, 일반 test/lint 실패, timeout/empty prose, 같은 workspace recovery는 묻지 않는다. 제품 의미·새 권한·hard boundary·데이터 파괴·복구 한도 소진·merge 승인만 묻는다.

- hard boundary 자동 확대, `tdd-exempt`, provider 간 dirty diff 인계 금지
- build-worker의 push/PR/merge/issue mutation 금지
- TDD와 mutation-time boundary guard 유지
- 새 side script보다 기존 chain/runner 확장 우선
- 대체한 helper·분기·문서·테스트는 함께 삭제하고 옛 호출을 `rg`로 확인

## GREEN 이후

모든 target task가 completed 된 뒤에만 [`impl-loop-finish.md`](impl-loop-finish.md)를 읽어 journey convergence, final Cartography sync, 최종 clean candidate freeze, fail-fast validation sequence, AC close audit, PR cut을 수행한다.
impl-validator review 출력은 merge candidate 경계에서 1회 holistic invocation으로 수집하며, task·commit별 고정 fan-out을 만들지 않는다.

## 참조

- 실패·retry 분기(필요할 때만): [`impl-loop-routing.md`](impl-loop-routing.md)
- completed 이후 마감(필요할 때만): [`impl-loop-finish.md`](impl-loop-finish.md)
- worker 계약: [`build-worker-agent.md`](../../docs/plugin/agents/build-worker/build-worker-agent.md)
