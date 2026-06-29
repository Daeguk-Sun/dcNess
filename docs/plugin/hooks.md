# Hooks SSOT — 3-layer enforcement map

> **Status**: ACTIVE
> **Scope**: `/init-dcness` 로 활성화된 사용자 프로젝트에서 dcNess 가 어떤 시점에 무엇을 막는지 설명한다.
> **Cross-ref**: [`CLAUDE.md`](../../CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) (대원칙), [`terms.md`](terms.md) (사용자-facing 용어), [`harness/agent_boundary.py`](../../harness/agent_boundary.py) (권한 매트릭스). 순서 차단 훅 진본 = 본 문서 [catastrophic-gate.sh](#catastrophic-gatesh).

dcNess 의 강제 영역은 두 가지뿐이다.

1. **작업 순서** — agent 시퀀스 + retry 전제
2. **접근 영역** — 파일 경계 + 외부 상태 변경 차단

그 외 prose 형식, handoff 형식, preamble, marker, status JSON, flag 는 agent 자율이다. 이 문서는 위 두 강제 영역이 실제 실행 환경에서 어느 레이어에 걸려 있는지 보여준다.

## 한눈 요약

| Layer | 실행 주체 | 발화 시점 | 주 역할 | 대표 차단 |
|---|---|---|---|---|
| **1. CC hooks** | Claude Code plug-in hook | Claude 가 tool 을 쓰기 전/후, sub-agent 종료, 메인 응답 종료 | 작업 순서, 파일 경계, TDD, run state 보존 | 잘못된 agent 순서, out-of-bound file write, test 없는 TS/JS 구현 |
| **2. git hooks** | local git | commit / checkout / push lifecycle | 로컬 git 조작 조기 차단 | 커밋 제목 위반, main 직접 push, 브랜치명 위반 |
| **3. CI/CD workflows** | GitHub Actions | PR / issue / merge event | 로컬 우회와 원격 상태 drift 검증 | PR 제목/body 위반, 문서 경로 위반, Project lifecycle drift |

주의: CI workflow 파일이 설치되어 실행되는 것과 branch protection 또는 ruleset 의 required check 로 merge 를 막는 것은 별개다. 활성 프로젝트에서 hard merge gate 로 쓰려면 해당 repo 의 GitHub 설정에서 required check 로 연결해야 한다.

## Layer 1 — CC hooks

등록 SSOT: [`hooks/hooks.json`](../../hooks/hooks.json). Claude Code 가 plug-in 활성 시 이 파일을 읽어 hook 을 등록한다. 모든 wrapper 는 `CLAUDE_PLUGIN_ROOT` 를 기준으로 plug-in 코드를 찾고, 현재 프로젝트가 dcNess 활성 whitelist 에 없으면 즉시 no-op 한다.

| Hook | Event / matcher | 언제 | 하는 일 | 차단 |
|---|---|---|---|---|
| `session-start.sh` | `SessionStart` | 새 세션, resume, `/clear` 직후 | sid/live state 초기화 + 활성 안내 inject | X |
| `catastrophic-gate.sh` | `PreToolUse / Agent` | sub-agent 호출 직전 | 작업 순서 보호 + 진행 순서 검사 | O |
| `file-guard.sh` | `PreToolUse / Edit|Write|NotebookEdit|Read|Bash|mcp__.*` | file/bash/MCP tool 호출 직전 | agent 별 파일 경계 + 외부 변경 차단 목록 검사 | O |
| `tdd-guard.sh` | `PreToolUse / Edit|Write|NotebookEdit|Bash` | 파일 수정 직전 | TS/JS 구현 파일에 매칭 test 존재 확인 | O |
| `post-agent-clear.sh` | `PostToolUse / Agent` | sub-agent 호출 직후 | active agent clear, prose 자동 staging, histogram inject | X |
| `post-file-op-trace.sh` | `PostToolUse / Edit|Write|NotebookEdit|Read|Bash|mcp__.*` | file/bash/MCP tool 호출 직후 | agent trace append | X |
| `subagent-stop-clear.sh` | `SubagentStop` | sub-agent 컨텍스트 종료 직후 | active agent clear 보강 | X |
| `stop-end-run.sh` | `Stop` | 메인 응답 종료 시 | end-run 자동화 + 다음 step continuation signal | 조건부 재발화 |

### CC hook 공통 실행 패턴

```bash
set -uo pipefail
export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"
python3 -m harness.session_state is-active >/dev/null 2>&1 || exit 0
CC_PID=$PPID
python3 -m harness.hooks <handler> --cc-pid "$CC_PID"
```

PreToolUse 차단 hook 은 정책 위반만 `exit 2` 로 내보낸다. Claude Code 에서 `exit 2` 는 tool 호출을 막고 stderr 를 모델에게 보여준다. import 오류나 hook 자체 오류는 fail-open 쪽으로 처리해 hook 버그가 전체 작업을 과차단하지 않게 한다.

Fail-open 관측성: 미활성 프로젝트 no-op, main Claude turn, active run 밖 Agent 호출처럼 예상된 benign skip 은 조용히 통과한다. 반대로 활성 프로젝트에서 enforcement hook 이 payload 파싱 실패, session id 부재, state read/write 오류, handler 비정상 종료 때문에 검사를 평가하지 못하고 allow 한 경우는 `<project>/.claude/harness-state/fail-open-events.jsonl` 에 structured event 로 남긴다. `dcness-helper status` 의 `hook fail-open 진단` 항목은 최근 24시간 count 와 reason category 를 WARN 으로 보여준다.

Stop hook 은 tool 호출을 막는 hook 이 아니다. 필요할 때 `decision: "block"` JSON 을 stdout 으로 내보내 메인 turn 을 재발화시킨다.

### session-start.sh

**시점**: Claude Code 세션 시작, resume, `/clear` 직후.

**역할**:

- sid 추출, `.by-pid/<cc_pid>` 작성, `live.json` 초기화
- 상태 위생 청소 (세션당 1회, fail-open): stale by-pid 파일(24h) + 본 세션의 만료 run 슬롯(24h) + 전 세션의 run 디렉토리(prose/ledger, 7d — `/run-review` 원자료라 슬롯보다 길게 보관). TTL 상수 SSOT = `harness/session_state.py`
- `hookSpecificOutput.additionalContext` 로 dcNess 활성 사실과 핵심 guard 안내 inject
- 메인 Claude 첫 응답 첫 줄에 `[dcness 활성 확인]` 토큰을 요구해 활성 여부를 사용자가 바로 확인 가능하게 함
- 설치된 plug-in 버전과 `main` 의 최신 버전을 비교(하루 1회 캐시)해 더 높은 버전이 있을 때만 `claude plugin update` 알림을 함께 inject — 외부 활성 프로젝트가 옛 plug-in 버전 운영 룰에 묶이는 drift 회피

**차단**: 없음. 실패해도 세션 시작을 막지 않는다.

### catastrophic-gate.sh

사용자-facing 용어: **순서 차단 훅**. 파일명과 hook command 는 호환성을 위해 `catastrophic-gate.sh` 를 유지한다.

**시점**: 메인 Claude 가 `Agent` tool 로 sub-agent 를 호출하기 직전.

**역할**: 작업 순서 보호와 active run 의 `begin-step -> Agent -> end-step` 물리 순서를 강제한다.

| Gate | 차단 조건 |
|---|---|
| pr-reviewer gate | engineer 산출물이 있는데 code-validator PASS 없이 pr-reviewer 호출 |
| engineer gate | 설계 산출물 없이 engineer 가 src 구현으로 진입 — 같은 run 의 module-architect PASS *또는* `begin-run --design-doc` 으로 기록된 설계 문서 실존 *또는* `begin-run --lane lite` 로 기록된 Lite 구현 경로(#714), 셋 중 하나로 충족 |
| module-architect gate | architecture-validator 1차 PASS 없이 design 의 module-architect 반복 진입 |
| 진행 순서 검사 | active run 안에서 직전 `begin-step` 과 다른 agent/mode 호출, `current_step` 부재, 이미 staged 된 stale step |

**진행 순서 검사 대상**: `entry_point=design|impl|ux`. 정상 `/design` 은 `begin-run design` 로 시작하며 같은 진행 순서 검사와 module-architect gate 를 탄다.

**engineer gate 의 design_doc 경로**: 설계(impl 문서 / compact plan)가 *별도 run* 에서 작성·머지된 뒤 구현 run 으로 진입하는 흐름(예: `/impl-loop` 풀 4-agent)에서는 같은 run 안에 module-architect prose 가 없다. 이때 `begin-run impl --design-doc <머지된 설계 문서 경로>` 로 run 에 설계 산출물을 기록하면 engineer gate 가 그 실존을 사전 조건 증거로 인정한다. 경로는 설계 산출물 규약(`docs/epics/**` / `docs/compact-plans/**`) 안의 실존 `.md` 만 허용 — 기록 시점에 resolve 절대경로로 fail-fast 검증(traversal / repo 밖 경로 거부)하고, 게이트 시점에 실존을 재확인한다. `--design-doc` 은 `entry_point=impl` run 에서만 수용된다(다른 entry_point 는 begin-run 이 거부) — design / architect-loop run 의 기존 module-architect PASS 강제는 코드 보장으로 유지된다.

**engineer gate 의 구현 경로 면제 (#714)**: `/impl` 2축 모델의 Lite 구현 경로(설계도 없음)에 sub-agent 엔진(풀4 / 경량 build-worker)을 붙이는 4번째 조합용 면제 경로다. Lite 는 정의상 설계도가 없어 module-architect PASS 도 design_doc 도 없으므로, `begin-run impl --lane lite` 로 run 슬롯에 구현 경로를 기록하면 engineer gate 가 그 기록을 설계 산출물 사전 조건 면제 신호로 인정한다. **면제 경계** — (1) `--lane` 값은 닫힌 enum(`lite` / `standard`)만 수용(임의 문자열 거부), (2) `--lane lite` 는 `entry_point=impl` run 에서만 수용(다른 entry_point 는 begin-run 이 거부)되어 design / architect-loop 의 module-architect PASS 강제는 영향받지 않음, (3) 면제는 *명시적으로 기록된* `lane=lite` 한정 — 값 미기록(impl-loop 풀4 / 기본)과 `lane=standard` 는 종전대로 설계 산출물을 요구(면제 누수 차단), (4) 면제는 engineer gate *하나만* 푼다 — engineer 산출물 이후 `pr-reviewer ← code-validator PASS` 잔존 보호는 구현 경로와 무관하게 그대로 강제된다(풀4 경로의 중대 차단 보호 불변).

**tech-review 관례**: `/design` 진입 후 tech-reviewer 재호출은 관례상 비권장이지만 코드 차단은 아니다. /design 도중 미검증 새 외부 의존이 발견되면 design 의 `NEW_DEP_ESCALATE` 경로로 처리한다.

**차단**: 위반 시 `exit 2` + stderr. engineer / pr-reviewer / module-architect 게이트 위반은 `[순서 차단 훅: <gate>]`, 진행 순서 검사 위반은 `[진행 순서 검사]` 접두사를 포함한다.

### file-guard.sh

**시점**: `Edit`, `Write`, `NotebookEdit`, `Read`, `Bash`, `mcp__.*` tool 호출 직전.

**역할**: [`harness/agent_boundary.py`](../../harness/agent_boundary.py) 권한 매트릭스를 강제한다.

| Rule | 효과 |
|---|---|
| `DCNESS_INFRA_PATTERNS` | sub-agent 의 `.claude/`, `hooks/`, `harness/*.py`, `docs/plugin/*.md`, `scripts/*.mjs` 등 infra path 접근 차단 |
| `RUN_DIR_PROSE_ALLOW` | build-worker 가 자기 run dir 의 `build-{test,impl,validate,polish}.md` prose 를 쓰는 좁은 예외 |
| `ALLOW_MATRIX` | agent 별 Write 허용 path 제한 |
| `.dcness/boundary.json` | **프로젝트별 override** — agent 별 `add`(허용 확장) / `remove`(코어 기본 제거)로 코어 `ALLOW_MATRIX` 를 양방향 커스텀 (아래 참조) |
| `READ_DENY_MATRIX` | agent 별 Read 금지 path 제한 |
| 외부 변경 차단 목록 | sub-agent 의 `git push`, Bash `gh pr create/merge/review`, Bash `gh issue create/edit/close/comment`, 상태 변경 `gh api`, GitHub MCP PR/repo 외부 상태 변경 차단 |

메인 Claude turn 은 file boundary 를 통과한다.

#### 프로젝트별 write 경계 override — `.dcness/boundary.json`

코어 `ALLOW_MATRIX` 는 흔한 언어·레이아웃의 합리적 기본값만 잡는다. 프로젝트 사정은 무한하므로(비표준 소스 디렉토리, 또는 코어 기본 제외를 의도적으로 완화하고 싶은 경우 — 예: engineer 의 `tests/` 제외를 "구현·테스트 한 호흡" 워크플로에서 열기), 프로젝트가 **루트의 `.dcness/boundary.json`** 으로 자기 사정을 직접 선언한다. 코어는 건드리지 않고, 예외는 프로젝트가 SSOT 로 가진다.

```json
{
  "engineer":      { "add": ["(^|/)remotion/", "(^|/)tests?/"], "remove": ["^app/"] },
  "test-engineer": { "add": ["(^|/)custom-e2e/"] }
}
```

- **형식**: agent 별 `add` / `remove` 정규식(코어 `ALLOW_MATRIX` 와 동일한 `re.search` 패턴) 배열.
- **`add`**: 코어 `ALLOW_MATRIX` 에 없는 경로를 그 agent 에 허용 (비표준 레이아웃 / 의도적 기본 제외 완화).
- **`remove`**: 코어 기본 허용 경로를 이 프로젝트에서 제거 (ALLOW 보다 우선하는 DENY 오버레이).
- **탐색**: `harness/agent_boundary.py` 가 cwd 에서 **working tree top-level(`git rev-parse --show-toplevel`)까지만** 조상을 거슬러 이 파일을 찾는다. nested·linked worktree 와 하위 디렉토리에서도 worktree 루트 설정이 적용되지만, 그 *위* 상위 워크스페이스·home 디렉토리의 `.dcness/boundary.json` 은 무시된다 (무관한 상위 설정이 경계를 약화하지 못하도록).
- **build-worker 전파**: 코어 `ALLOW_MATRIX["build-worker"]` 가 `engineer ∪ test-engineer` 합집합이듯, `engineer` / `test-engineer` 의 `add`·`remove` 는 `build-worker`(`/impl-loop` 의 실제 mutation agent)에도 합쳐 전파된다. 즉 `"engineer": {"remove": ["^app/"]}` 만 선언해도 build-worker 의 `app/` write 가 함께 막힌다 (별도 `build-worker` 키 불필요).
- **안전 degrade**: 파일 부재·깨진 JSON·형식 위반·컴파일 불가 정규식은 조용히 무시하고 코어 기본값을 유지한다 (잘못된 설정이 경계를 깨뜨리지 않는다).
- **배포**: 읽는 로직은 plugin 본체(`harness/`)라 plugin 버전업으로 자동 적용 (cp 0). 설정 파일은 프로젝트가 직접 작성한다.

**override 가 뚫지 못하는 가드 (되돌릴 수 없는 경계만)**:

- **INFRA 경로** (`DCNESS_INFRA_PATTERNS` — `hooks/`, `harness/*.py` 등) 는 `add` 로 열 수 없다. INFRA 검사가 ALLOW(코어+add) 검사보다 *먼저* 발화하기 때문.
- **`.dcness/boundary.json` 자신**(과 `.dcness/` 디렉토리 전체) 은 sub-agent write 차단 영역 (자기 경계 셀프 확장/축소 금지). INFRA 로 보호되며 `remove` 로도 풀 수 없고, 디렉토리 타깃 write 우회도 닫힌다.
- **판정/검증 전용 agent**(`code-validator` / `pr-reviewer` / `architecture-validator` / `product-acceptance` / `plan-reviewer` — 코어 ALLOW 가 빈 `()`) 는 `add` 로도 write 를 열 수 없다. "검증자는 자기가 검증하는 것을 못 고친다" 는 역할 격리는 catastrophic gate 신뢰의 근간이라 되돌릴 수 없는 경계 — `add` 로 mutation agent 로 승격시킬 수 없다.
- **guard self-disable 마커** (`.no-dcness-guard` = file-guard 임시 우회 / `.claude-plugin/` = `is_infra_project` self-repo 신호) 도 INFRA 로 보호된다. broad `add`(예 `.*`)로도 sub-agent 가 file guard 자체를 끄는 통제 파일을 쓸 수 없다.
- 그 외 기본값(예: engineer 의 `tests/` 제외 = self-grading 방어)은 **강제 가드가 아니라 권고** 다. 프로젝트가 `add` 로 풀 수 있고, 그 경우 self-grading drift(구현자가 자기 코드를 통과시키도록 테스트를 편향) 위험은 프로젝트가 감수한다.

GitHub issue 외부 상태 변경은 경로에 따라 다르게 처리한다 — 같은 "issue 변경"이라도 차단 여부가 갈린다.

| issue 외부 상태 변경 경로 | file-guard 동작 |
|---|---|
| Bash `gh issue create/edit/close/comment/...` | **차단** (Bash 외부 변경 차단 목록 — `harness/agent_boundary.py` 의 `check_bash_mutation`) |
| GitHub MCP issue 도구 (`mcp__github__create_issue`, `update_issue`, `add_issue_comment` 등) | **통과** (의도된 예외 — `check_github_mcp_mutation`). per-agent `tools:` 권한이 이미 gate 하므로 도구 미부여 agent 는 호출 자체 불가. designer 등 issue 도구를 가진 agent 의 설계된 흐름을 막지 않는다. |

PR/repo 외부 상태 변경 (`gh pr ...` / `merge_pull_request` / `push_files` / `create_or_update_file` 등) 은 Bash·MCP 양쪽 다 sub-agent 에서 차단한다.

**차단**: 경계 위반 시 `exit 2` + stderr. `.no-dcness-guard` marker 는 file-guard 만 임시 우회한다.

### tdd-guard.sh

**시점**: `Edit`, `Write`, `NotebookEdit` 로 파일을 수정하기 직전. `Bash` 는 명시적 write target 추출 직후, 각 target 에 같은 검사를 적용한다.

**지원 언어**: TS/JS 만 (`*.ts`, `*.tsx`, `*.js`, `*.jsx`). 그 외 확장자는 silent skip — Python·Rust·Go 등 다른 ecosystem 의 TDD 강제는 현재 범위 밖이다.

**역할**: 위 TS/JS 구현 파일에 대응하는 test/spec 파일이 *존재하는지* 확인한다. 없으면 구현 파일 작성을 막는다. **test 의 존재만 검사하고, test 를 실행하지는 않는다** — green/red 판정이 아니라 "작성 전 test 가 먼저 있는가" 강제다.

**skip 대상**:

- test/spec 파일 자체 — basename 의 `.test.` / `.spec.` 접미 컨벤션 (`foo.test.ts`, `bar.spec.tsx`)
- 표준 test 디렉터리 마디 — `__tests__/`, `__test__/`, `__mocks__/`, `test/`, `tests/`, `spec/`, `specs/`, `e2e/`
- 설정, markdown, yaml, env, css, 타입 선언
- Next.js 특수 파일 (`layout`, `page`, `loading`, `error`, `not-found`, `globals.css`)
- entry-file 예외 — path heuristic (`*/App.{ts,tsx,js,jsx}`, `*/_layout.*`, `*/apps/*/index.*`, `*/src/main.*`) + 내용 시그니처 (`registerRootComponent(`, `AppRegistry.registerComponent(`)
- `templates/`, `design-variants/`
- TS/JS 외 언어

> basename 에 우연히 `test`/`spec` 이 든 **구현 파일** (`contest.ts`, `spectrum.ts`, `latest.ts`) 은 skip 하지 않는다 — TDD 강제 대상이다 (#681). skip 은 `.test.`/`.spec.` 접미와 슬래시로 구분된 표준 test 디렉터리 마디에만 적용된다.

**매칭 위치**: 같은 디렉터리, 같은 디렉터리의 `__tests__`, 부모/조부모 `__tests__`, monorepo `src_root/__tests__`, 프로젝트 root `src/__tests__`.

**Bash write target 정책**: `Bash` payload 는 [`harness.agent_boundary.extract_bash_paths`](../../harness/agent_boundary.py) 가 추출하는 명시적 write target 에 한해 검사한다. 예: redirect(`>`, `>>`), `tee`, in-place edit(`sed/perl/awk -i`), `cp`/`mv`/`rm` target. 추출된 target 이 TS/JS 구현 파일이면 직접 `Edit`/`Write`/`NotebookEdit` 와 동일한 skip 규칙 및 6-tier matching-test 존재 검사를 탄다. write target 이 없거나 TS/JS 구현 파일이 아니면 silent skip 한다.

**차단**: test 부재 시 `exit 2` + 한국어 안내. Bash write target 차단 메시지는 `TDD GUARD[Bash]` 로 시작해 어떤 target 이 matching-test enforcement 에 실패했는지 함께 표시한다.

### post-agent-clear.sh

**시점**: `Agent` tool 결과가 돌아온 직후.

**역할**:

- `live.json.active_agent / active_mode` clear
- sub-agent prose 를 `<run_dir>/<agent>[-<MODE>].md` 로 자동 저장
- `live.json.current_step.prose_file` 기록
- tool histogram 과 staging 진단을 `hookSpecificOutput.additionalContext` 로 inject

**차단**: 없음.

### post-file-op-trace.sh

**시점**: file/bash/MCP tool 호출 직후.

**역할**: 활성 sub-agent 가 있을 때 `agent-trace.jsonl` 에 post phase 1줄을 append 한다. 메인 Claude turn 이거나 비활성 프로젝트면 no-op 한다.

**차단**: 없음.

### subagent-stop-clear.sh

**시점**: sub-agent 컨텍스트 종료 직후.

**역할**: `SubagentStop` payload 의 `agent_type` 을 사용해 active agent state 를 정리한다. PostToolUse Agent clear 보다 sub-agent 종료 시점에 더 가깝기 때문에 stale state 를 줄이는 보조 안전망이다.

**차단**: 없음. SubagentStop 은 차단 권한이 있지만 dcNess 는 state clear 만 수행하고 항상 종료를 허용한다.

### stop-end-run.sh

**시점**: 메인 Claude 응답 종료 시.

**역할**:

- 마지막 step 이 완료됐고 run 이 미finalized 상태면 `end-run` 을 자동 수행
- 마지막 step 결론이 다음 step 으로 이어져야 하는 enum 이고 종료 agent 가 아니면 continuation signal 을 내보내 메인 turn 재발화
- `begin-run impl --acceptance-required` 로 기록된 마감 task run 에서는 `pr-reviewer` 를 종료 agent 로 취급하지 않는다. `pr-reviewer` 결론이 `PASS`/`LGTM` 이면 Stop hook 이 `product-acceptance` 진입용 continuation signal 을 내보내며, marker 가 없는 중간 task / `--no-acceptance` run / verify-only run 은 기존 종료 동작을 유지한다.
- 같은 step 에서 반복 block 횟수가 한도를 넘으면 사용자/메인의 종료 의도를 존중하고 skip

**차단**: tool 차단은 아니다. 필요 시 stdout JSON 으로 메인 turn 을 재발화한다.

## Layer 2 — git hooks

설치 경로: 사용자 repo 의 `.git/hooks/`. `/init-dcness` bootstrap 이 plug-in 의 `scripts/hooks/*` thin shim 을 복사한다. 본체 검증 로직은 사용자 repo 에 복사하지 않고 plug-in SSOT 를 직접 호출한다.

| Hook | Source | 언제 | 하는 일 | 차단 |
|---|---|---|---|---|
| `.git/hooks/commit-msg` | `scripts/hooks/commit-msg` | commit message 확정 전 | 커밋 제목 git-spec 검증 | O |
| `.git/hooks/post-checkout` | `scripts/hooks/post-checkout` | branch checkout/switch 직후 | 브랜치명 위반 경고 + rename 안내 | X |
| `.git/hooks/pre-push` | `scripts/hooks/pre-push` | push 직전 | main 직접 push 차단 + 브랜치명 검증 | O |

활성 프로젝트 기준으로 `pre-commit` 은 기본 설치 대상이 아니다. TDD 강제는 git hook 이 아니라 Layer 1 의 `tdd-guard.sh` 가 구현 파일 작성 전에 수행한다.

### .git/hooks/commit-msg

**Source**: `scripts/hooks/commit-msg`

**시점**: `git commit` 이 commit message 를 확정하기 직전.

**역할**: commit title 을 읽고 `check_git_naming.mjs --title` 로 git-spec 제목 규칙을 검증한다. merge commit 제목은 면제한다.

**차단**: 제목 위반 시 commit 실패.

### .git/hooks/post-checkout

**Source**: `scripts/hooks/post-checkout`

**시점**: branch checkout/switch 직후.

**역할**: 현재 브랜치명이 git-spec 을 어기면 경고와 `git branch -m <올바른-브랜치명>` 안내를 출력한다.

**차단**: 없음. Git 이 post-checkout exit code 로 checkout 을 취소하지 않기 때문에 경고 전용이다.

### .git/hooks/pre-push

**Source**: `scripts/hooks/pre-push`

**시점**: `git push` 직전.

**역할**:

- `refs/heads/main` 으로 직접 push 하는 경우 차단
- push 대상 브랜치명이 git-spec 을 어기면 차단

**차단**: main push 또는 브랜치명 위반 시 push 실패.

## Layer 3 — CI/CD workflows

설치 경로: 사용자 repo 의 `.github/workflows/`. `/init-dcness` 에서 사용자가 Y 를 선택한 경우 thin workflow 를 생성한다. workflow 본체는 `alruminum/dcNess` 의 composite action 을 호출한다.

| Workflow | Trigger | 언제 | 하는 일 | 성격 |
|---|---|---|---|---|
| `.github/workflows/git-naming-validation.yml` | `pull_request` opened/synchronize/reopened/edited | PR 생성/수정/동기화 | 브랜치명 + PR 제목 git-spec 검증 | 선택형 CI gate |
| `.github/workflows/pr-body-validation.yml` | `pull_request` opened/synchronize/reopened/edited | PR 생성/수정/동기화 | PR body issue trailer 검증 | 선택형 CI gate |
| `.github/workflows/doc-path-integrity.yml` | `pull_request` opened/synchronize/reopened/edited | PR 생성/수정/동기화 | repo-relative 경로 참조 실존 검증 | 선택형 CI gate |
| `.github/workflows/github-project-lifecycle.yml` | `issues`, `pull_request closed` | issue 변경 또는 PR merge | Project field/label drift 검출, merged PR Done 보정 | 선택형 CI/CD |

### .github/workflows/git-naming-validation.yml

**설치**: `/init-dcness` 의 선택형 CI workflow 질문에서 사용자가 CI git-naming 강제를 선택하면 생성한다.

**시점**: `main` 대상 PR 이 opened, synchronize, reopened, edited 될 때.

**역할**: `alruminum/dcNess/.github/actions/git-naming@main` 을 호출해 `github.head_ref` 와 PR title 을 검증한다.

**차단**: workflow 실패. hard merge gate 여부는 사용자 repo 의 branch protection/ruleset 설정에 달려 있다.

### .github/workflows/pr-body-validation.yml

**설치**: `/init-dcness` 의 선택형 CI workflow 질문에서 사용자가 PR body close-keyword gate 를 선택하면 생성한다.

**시점**: `main` 대상 PR 이 opened, synchronize, reopened, edited 될 때.

**역할**: `alruminum/dcNess/.github/actions/pr-body@main` 을 호출해 PR body 에 issue trailer 가 있는지 확인한다.

허용 패턴:

- `Closes #N`, `Fixes #N`, `Resolves #N`
- `Part of #N`
- `Document-Exception-PR-Close: <사유>`

**차단**: workflow 실패. hard merge gate 여부는 사용자 repo 의 branch protection/ruleset 설정에 달려 있다.

### .github/workflows/doc-path-integrity.yml

**설치**: `/init-dcness` 의 선택형 CI workflow 질문에서 사용자가 doc-path 무결성 검증을 선택하면 생성한다.

**시점**: `main` 대상 PR 이 opened, synchronize, reopened, edited 될 때. 문서가 그대로여도 참조 대상 파일이 삭제·이동되면 stale path 가 생길 수 있으므로 path filter 를 두지 않는다.

**역할**: `alruminum/dcNess/.github/actions/doc-path-integrity@main` 을 호출해 활성 프로젝트의 context/SSOT 문서(`CLAUDE.md`, `AGENTS.md`, root `architecture.md`, `docs/index.md`, `docs/project-context.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/**`) 안 repo-relative path 참조가 실제 파일 또는 디렉토리를 가리키는지 확인한다.

**차단**: workflow 실패. hard merge gate 여부는 사용자 repo 의 branch protection/ruleset 설정에 달려 있다.

### .github/workflows/github-project-lifecycle.yml

**설치**: `/init-dcness` 의 GitHub Project lifecycle bootstrap 에서 사용자가 Project lifecycle guard 를 선택하면 생성한다.

**시점**:

- issue opened/edited/labeled/unlabeled
- PR closed, 단 merged PR 만 Done 보정 후보

**역할**:

- issue label 과 Project IssueType drift 검출
- merged PR body 의 close keyword 대상 issue 를 Project Status `Done` 으로 보정
- `Part of #N` 만 있는 PR 은 Done 후보로 보지 않음

**필수 설정**: Project v2 쓰기에는 `secrets.DCNESS_PROJECT_TOKEN`, `vars.DCNESS_PROJECT_NUMBER`, `vars.DCNESS_PROJECT_OWNER` 가 필요하다.

**차단/보정**: issue drift 는 workflow 실패로 드러나고, merged PR 보정은 `apply: "true"` 로 Project 상태를 수정한다.

## 문서 동기화 게이트

hook 또는 workflow 를 추가/삭제/이름 변경할 때 이 문서가 빠지지 않도록 `tests/test_surface_docs_sync.py` 가 다음을 검사한다.

| Source | 문서에 있어야 하는 것 |
|---|---|
| `hooks/hooks.json` | 모든 CC hook script 의 `### <script>.sh` 상세 섹션 |
| `commands/init-dcness.md` / `docs/plugin/init-dcness.md` 의 `scripts/hooks/*` copy 목록 | 모든 사용자 repo git hook 의 `### .git/hooks/<name>` 상세 섹션 |
| `commands/init-dcness.md` / `docs/plugin/init-dcness.md` 의 선택형 `.github/workflows/*.yml` 목록 | 모든 workflow 의 `### .github/workflows/<name>.yml` 상세 섹션 |

이 테스트는 hook 구현 변경의 의미까지 판정하지 않는다. 하지만 등록 공개 노출 범위가 바뀌었는데 `hooks.md` 요약/상세가 누락되는 회귀는 CI에서 막는다.

## 등록 메커니즘

**CC hooks**: [`hooks/hooks.json`](../../hooks/hooks.json) 이 event, matcher, script command 를 정의한다. Claude Code 가 plug-in 활성 시 표준 경로를 자동 인식한다.

**git hooks**: `/init-dcness` bootstrap 이 사용자 repo 의 `.git/hooks/` 에 thin shim 을 always-overwrite 한다. hook 본체는 `CLAUDE_PLUGIN_ROOT`, plug-in cache, legacy repo script 순서로 검증 script 를 resolve 한다.

**CI/CD workflows**: `/init-dcness` 가 사용자 선택에 따라 thin workflow 를 `.github/workflows/` 에 always-overwrite 한다. 사용자가 tag pin 을 원하면 `@main` 대신 release tag 로 바꿀 수 있다.

`CLAUDE_PLUGIN_ROOT` 는 plug-in hook 실행 시 Claude Code 가 자동 설정하는 env 다. 이 값은 모든 활성 프로젝트 hook 에서 존재하므로 infra mode 신호로 쓰면 안 된다.

## 우회 / opt-out

| Mechanism | Scope | Effect |
|---|---|---|
| 미활성 프로젝트 | 전체 CC hook | `is-active` 게이트에서 즉시 no-op |
| `.no-dcness-guard` cwd marker | file-guard | file boundary / 외부 변경 차단 목록 임시 우회 |
| `DCNESS_INFRA=1`, `~/.claude/.dcness-infra`, dcNess self repo marker | file boundary | dcNess 자체 작업에서 infra path 보호 해제 |

우회 marker 는 catastrophic-gate 와 tdd-guard 에 없다. git hook 의 `--no-verify` 우회는 가능하지만 dcNess 절차상 금지다. CI/CD workflow 는 GitHub 에 올라온 PR/issue 이벤트에서 다시 검증한다.

## 참조

자연어 SSOT:

- [`CLAUDE.md`](../../CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) — 강제 영역 2가지
- 본 문서 [catastrophic-gate.sh](#catastrophic-gatesh) — 순서 차단 훅 진본
- [`git-spec.md`](git-spec.md) — branch / commit / PR naming + PR trailer
- [`issue-lifecycle.md`](issue-lifecycle.md) — Project lifecycle workflow 의미
- [`loop-procedure.md`](loop-procedure.md) — begin-run / begin-step / end-step / end-run mechanics

코드 SSOT:

- [`harness/hooks.py`](../../harness/hooks.py) — CC hook handler dispatch
- [`harness/session_state.py`](../../harness/session_state.py) — 활성 프로젝트 판정 + run state machine
- [`harness/agent_boundary.py`](../../harness/agent_boundary.py) — file boundary + 외부 변경 차단 목록
- [`scripts/check_git_naming.mjs`](../../scripts/check_git_naming.mjs) — git naming validator
- [`scripts/check_pr_body.mjs`](../../scripts/check_pr_body.mjs) — PR body validator
- [`scripts/github_project_lifecycle.mjs`](../../scripts/github_project_lifecycle.mjs) — Project lifecycle validator/applicator

등록 manifest:

- [`hooks/hooks.json`](../../hooks/hooks.json) — CC hook 등록
- [`.claude-plugin/plugin.json`](../../.claude-plugin/plugin.json) — plug-in metadata
