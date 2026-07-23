# Hooks SSOT — 3-layer enforcement map

> **Status**: ACTIVE
> **Scope**: `/init-dcness` 로 활성화된 사용자 프로젝트에서 dcNess 가 어떤 시점에 무엇을 막는지 설명한다.
> **Cross-ref**: [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) (대원칙), [`terms.md`](terms.md) (사용자-facing 용어), [`harness/agent_boundary.py`](../../harness/agent_boundary.py) (권한 매트릭스). 순서 차단 훅 진본 = 본 문서 [catastrophic-gate.sh](#catastrophic-gatesh).

dcNess 의 강제 영역은 두 가지뿐이다.

1. **작업 순서** — agent 시퀀스 + retry 전제
2. **접근 영역** — 파일 경계 + 외부 상태 변경 차단

그 외 prose 형식, handoff 형식, preamble, marker, status JSON, flag 는 agent 자율이다. 이 문서는 위 두 강제 영역이 실제 실행 환경에서 어느 레이어에 걸려 있는지 보여준다.

## 한눈 요약

| Layer | 실행 주체 | 발화 시점 | 주 역할 | 대표 차단 |
|---|---|---|---|---|
| **1. runtime hooks/helpers** | Claude Code plug-in hook + dcness helper/wrapper | Claude 가 tool 을 쓰기 전/후, helper step 시작, headless worker 종료, sub-agent 종료, 메인 응답 종료 | 작업 순서, 파일 경계, TDD, run state 보존 | 잘못된 agent 순서, out-of-bound file write, test 없는 TS/JS 구현 |
| **2. git hooks** | local git | commit / checkout / push lifecycle | 로컬 git 조작 조기 차단 | 커밋 제목 위반, main 직접 push, 브랜치명 위반 |
| **3. CI/CD workflows** | GitHub Actions | PR / issue / merge event | 로컬 우회와 원격 상태 drift 검증 | PR 제목/body 위반, 문서 경로 위반, Project lifecycle drift |

주의: CI workflow 파일이 설치되어 실행되는 것과 branch protection 또는 ruleset 의 required check 로 merge 를 막는 것은 별개다. 활성 프로젝트에서 hard merge gate 로 쓰려면 해당 repo 의 GitHub 설정에서 required check 로 연결해야 한다.

## Layer 1 — CC hooks

등록 SSOT: [`hooks/hooks.json`](../../hooks/hooks.json). Claude Code 가 plug-in 활성 시 이 파일을 읽어 hook 을 등록한다. 모든 wrapper 는 `CLAUDE_PLUGIN_ROOT` 를 기준으로 plug-in 코드를 찾고, 현재 프로젝트가 dcNess 활성 whitelist 에 없으면 즉시 no-op 한다.

| Hook | Event / matcher | 언제 | 하는 일 | 차단 |
|---|---|---|---|---|
| `session-start.sh` | `SessionStart` | 새 세션, resume, `/clear` 직후 | sid/live state 초기화 + 활성 안내 inject | X |
| `catastrophic-gate.sh` | `PreToolUse / Agent` | sub-agent 호출 직전 | 작업 순서 보호 + 진행 순서 검사 | O |
| `subagent-start-lifecycle.sh` | `SubagentStart` | 실제 sub-agent spawn 직후 | foreground step 시작 + 동적 context 주입 | X |
| `file-guard.sh` | `PreToolUse / Edit|Write|NotebookEdit|Read|Bash|mcp__.*` | file/bash/MCP tool 호출 직전 | agent 별 파일 경계 + 외부 변경 차단 목록 검사 | O |
| `tdd-guard.sh` | `PreToolUse / Edit|Write|NotebookEdit|Bash` | 파일 수정 직전 | project-local generated TDD hook 우선 실행, 없으면 TS/JS fallback 으로 매칭 test 존재 확인 | O |
| `post-agent-clear.sh` | `PostToolUse / Agent` | Agent tool 성공 결과 직후 | completed foreground prose + receipt 기록 | X |
| `post-agent-failure.sh` | `PostToolUseFailure / Agent` | Agent tool 실패 직후 | step abort + 복구 진단 | X |
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

Guard hit 관측성: 정책 위반을 실제로 차단한 경우는 `<project>/.claude/harness-state/guard-telemetry.jsonl` 또는 active run의 `guard-telemetry.jsonl`에 최소 `guard_hit` receipt를 append한다. 기록 필드는 guard 이름, category, source, 시각, 필요한 식별자이며 기록 실패는 원래 차단/허용 판정을 바꾸지 않는다. runtime hook은 이 receipt를 집계하거나 효과를 해석하지 않는다.

기존 `dcness-helper guard-telemetry`와 `insight` 명령명은 조용히 사라지지 않고 exit 2와 migration 안내를 반환한다. 전자는 dcNess source checkout의 `scripts/loop_diagnose.py`, 완료 run 복기는 `/run-review`를 사용한다.

Stop hook 은 tool 호출을 막는 hook 이 아니다. 필요할 때 `decision: "block"` JSON 을 stdout 으로 내보내 메인 turn 을 재발화시킨다.

## Safety 범위

dcNess hook 은 보안 sandbox 가 아니다. file boundary 와 외부 상태 변경 denylist 의 목적은 활성화된 개발 프로젝트에서 agent 가 실수로 순서·역할·외부 상태 경계를 넘는 일을 줄이는 것이다. 신뢰하지 않는 코드를 OS 수준으로 격리하거나, shell/runtime 의 모든 우회 형태를 완전 차단하는 보안 장치로 해석하면 안 된다.

구체적으로, `file-guard.sh` 는 payload 에 드러난 `agent_type`, file path, Bash write target, 알려진 `gh`/GitHub MCP mutation 패턴을 검사한다. sub-agent 권한은 각 tool payload의 `agent_type`으로만 귀속하며, 동시 호출에서 서로 덮어쓸 수 있는 공유 `live.active_agent`를 폴백으로 사용하지 않는다. `agent_type`이 없는 payload는 메인 호출로 취급한다. 새 CLI subcommand, shell command substitution, 런타임 안에서 생성되는 두 번째 명령, 권한 있는 외부 프로세스처럼 payload 정적 검사에 드러나지 않는 경로는 차단 대상이 아닐 수 있다. `tdd-guard.sh` 도 test 존재와 생성형 hook 계약을 확인하지만 test 품질이나 실제 green 상태를 보장하지 않는다.

이 한계 때문에 dcNess 는 hook 자체 오류나 판정 불가를 과차단하지 않고 fail-open 으로 기록한다. 활성 프로젝트에서 payload 파싱 실패, session id 부재, state read/write 오류, handler 비정상 종료 때문에 검사를 평가하지 못하고 allow 한 경우는 `<project>/.claude/harness-state/fail-open-events.jsonl` 에 남고, `dcness-helper status` 의 `hook fail-open 진단` 항목이 최근 24시간 count 와 reason category 를 `WARN` 으로 보여준다.

보안 경계가 필요한 작업은 별도 sandbox, 컨테이너, OS 권한 분리, secret 격리 정책으로 다뤄야 한다. dcNess hook 은 그 위에서 개발 workflow 순서와 역할 경계를 보조하는 장치다.

### session-start.sh

**시점**: Claude Code 세션 시작, resume, `/clear` 직후.

**역할**:

- sid 추출, `.by-pid/<cc_pid>` 작성, `live.json` 초기화
- 상태 위생 청소 (세션당 1회, fail-open): stale by-pid 파일(24h) + 본 세션의 만료 run 슬롯(24h) + 전 세션의 run 디렉토리(prose/ledger, 7d — `/run-review` 원자료라 슬롯보다 길게 보관). TTL 상수 SSOT = `harness/session_state.py`
- `hookSpecificOutput.additionalContext` 로 dcNess 활성 사실과 핵심 guard 안내 inject
- 이전 세션이 `/handoff` 로 남긴 `.dcness-work/handoffs/next-session.md` 가 있으면 `.dcness-work/handoffs/archive/<ts>.md` 로 먼저 옮겨(mv) 원자적으로 소비한 뒤 그 내용을 `additionalContext` 최상단에 최우선 주입함(무손실 clear) — 다음다음 세션 stale 재주입 차단. mv(rename)를 read 보다 선행하므로 병렬 peer 세션 중 rename 에 성공한 first-consumer 만 소비(단일 소비자 계약). `.dcness-work/` 는 writable 이라 심어진 심링크(→ 로컬 시크릿)를 따라가 컨텍스트로 유출하지 않도록 정규 파일(심링크 아님)일 때만 소비. 파일 부재 시 기존 동작 그대로
- 메인 Claude 첫 응답 첫 줄에 `[dcness 활성 확인]` 토큰을 요구해 활성 여부를 사용자가 바로 확인 가능하게 함
- 프로젝트 상태나 다음 작업 질문에는 `docs/index.md` 와 `## 진행 상태 · 다음 작업` 섹션이 실제로 있을 때만 해당 포인터를 안내하고, 파일/섹션이 없으면 `/next-work` issue/label 조회와 `/init-dcness` 보강 경로를 안내함
- 설치된 plug-in 버전과 `main` 의 최신 버전을 비교(하루 1회 캐시)해 더 높은 버전이 있을 때만 `claude plugin update` 알림을 함께 inject — 외부 활성 프로젝트가 옛 plug-in 버전 운영 룰에 묶이는 drift 회피

**차단**: 없음. 실패해도 세션 시작을 막지 않는다.

### catastrophic-gate.sh

사용자-facing 용어: **순서 차단 훅**. 코드 식별자는 `catastrophic-gate.sh` 다.

**시점**: 메인 Claude 가 `Agent` tool 로 sub-agent 를 호출하기 직전, 그리고 `dcness-helper begin-step` 이 headless/modeful step 시작을 기록하기 직전. Claude Agent provider 는 전자를 타고, Codex/headless provider 는 후자를 탄다.

**역할**: 작업 순서와 호출 적합성만 검사한다. 모든 matching PreToolUse hook은 병렬 평가되므로 이 시점에는 `step_started`/`active_agent`를 확정하지 않고, `tool_use_id` correlation intent만 runtime state에 둔다. sibling hook deny 뒤 실제 spawn이 없으면 ledger lifecycle event도 없다. build-worker 설계 산출물 사전 조건과 impl-validator step 순서를 provider와 무관하게 같은 판정 함수로 검사한다. repo scan이나 generated TDD 설치 health 같은 advisory preflight는 여기서 실행하지 않는다.

PASS prose 판정은 `end-step` 저장 규칙과 같은 파일명을 본다. 즉 `<agent>.md`, 재호출 occurrence 인 `<agent>-1.md`, mode-suffix 인 `<agent>-MODE.md`, mode 재호출인 `<agent>-MODE-1.md` 안의 `PASS` 모두 같은 agent 의 완료 증거로 인정한다.

| Gate | 차단 조건 |
|---|---|
| implementation gate | 설계 산출물 없이 build-worker 가 src 구현으로 진입 — 같은 run 의 module-architect PASS *또는* `begin-run --design-doc` 으로 기록된 설계 문서 실존 *또는* direct 구현 경로 기록, 셋 중 하나로 충족 |
| 진행 순서 검사 | 명시적 modeful/current step과 다른 agent/mode 호출, 이미 완료된 stale step. mode 없는 foreground Claude Agent의 current step 부재는 SubagentStart 자동 시작 대상으로 허용 |

**진행 순서 검사 대상**: `entry_point=design|impl|ux`. 정상 `/design` 은 `begin-run design` 로 시작하며 같은 진행 순서 검사를 탄다. module-architect 는 `/design` 기본 선두 진입, greenfield thin bootstrap 이후 진입, opt-in system checkpoint 이후 재진입 모두 별도 validator 게이트 없이 허용한다. checkpoint 필요 여부와 재진입 흐름은 `skills/design/design-routing.md` 의 agent enum(`SYSTEM_CHECKPOINT_REQUIRED`)과 lifecycle identity/mode 검사로만 다룬다.

**implementation gate 의 design_doc 경로**: 설계(impl 문서)가 *별도 run* 에서 작성·머지된 뒤 구현 run 으로 진입하는 흐름(예: `/impl-loop` story/epic runner)에서는 같은 run 안에 module-architect prose 가 없다. 이때 `begin-run impl --design-doc <머지된 설계 문서 경로>` 로 run 에 설계 산출물을 기록하면 implementation gate 가 그 실존을 사전 조건 증거로 인정한다. 경로는 설계 산출물 규약(`docs/epics/**`) 안의 실존 `.md` 만 허용 — 기록 시점에 resolve 절대경로로 fail-fast 검증(traversal / repo 밖 경로 거부)하고, 게이트 시점에 실존을 재확인한다. `--design-doc` 은 `entry_point=impl` run 에서만 수용된다(다른 entry_point 는 begin-run 이 거부) — design / architect-loop run 의 기존 module-architect PASS 강제는 코드 보장으로 유지된다.

**impl mutation-time scope**: `begin-run --design-doc`이 가리키는 impl 문서의 정규화된 `### 수정 허용` 경로는 현재 run에 한해 task-scope capability로 재사용한다. 이 경로는 preflight scan이나 `.dcness/boundary.json` 영구 확장이 아니다. INFRA, 코드 agent 전용 deny, 프로젝트 `remove`, repo 밖 경로는 먼저 차단되므로 hard boundary를 열 수 없다. task-scope 밖 변경은 실제 file-op 또는 headless post-run boundary guard에서 차단하고, headless chain은 같은 provider/workspace에서 bounded rework 뒤 guard를 다시 실행한다.

**implementation gate 의 direct 경로 면제 (#714)**: `/impl` direct 경로(설계도 없음)는 module-architect PASS 도 design_doc 도 없으므로, `begin-run impl --lane lite` 로 run 슬롯에 구현 경로를 기록하면 implementation gate 가 그 기록을 build-worker 설계 산출물 사전 조건 면제 신호로 인정한다. **면제 경계** — (1) `--lane` 값은 닫힌 enum(`lite` / `standard`)만 수용(임의 문자열 거부), (2) `--lane lite` 는 `entry_point=impl` run 에서만 수용(다른 entry_point 는 begin-run 이 거부)되어 design / architect-loop 의 module-architect PASS 강제는 영향받지 않음, (3) 면제는 *명시적으로 기록된* `lane=lite` 한정 — 값 미기록(`/impl-loop` story/epic runner / 기본)과 `lane=standard` 는 종전대로 설계 산출물을 요구한다.

**tech-review 관례**: `/design` 진입 후 tech-reviewer 재호출은 관례상 비권장이지만 코드 차단은 아니다. /design 도중 미검증 새 외부 의존이 발견되면 design 의 `NEW_DEP_ESCALATE` 경로로 처리한다.

**차단**: Claude Code PreToolUse 에서는 위반 시 `exit 2` + stderr, helper `begin-step` 에서는 비-0 종료 + stderr. implementation / 진행 순서 게이트 위반은 `[순서 차단 훅: <gate>]`, 진행 순서 검사 위반은 `[진행 순서 검사]` 접두사를 포함한다. 게이트 자체 예외는 fail-open 계측으로 남기고 과차단하지 않는다.
차단이 발생하면 `guard-telemetry.jsonl` 에 `guard=catastrophic-gate` 로 기록된다.

### subagent-start-lifecycle.sh

**시점**: Claude Code가 Agent tool의 sub-agent를 실제 spawn한 직후, sub-agent가 첫 prompt를 처리하기 전.

**역할**:

- PreToolUse correlation intent의 agent type과 최신 미claim `tool_use_id`를 `agent_id`에 bind
- mode 없는 foreground Claude Agent면 실제 spawn 뒤 `step_started`를 1건 기록
- modeful Claude Agent면 선행 explicit `begin-step <agent> <mode>`에 identity만 bind하고 시작 receipt를 중복 생성하지 않음
- background intent는 lifecycle step을 시작하지 않음
- worktree 절대경로와 build-worker `[PREVIOUS_TASKS]`를 `additionalContext`로 sub-agent의 첫 prompt 처리 전에 직접 전달
- 같은 `agent_id` 재전달은 멱등 처리

PreToolUse intent가 없거나 current step identity가 다르면 ledger를 추측 보정하지 않고 `lifecycle 복구` 진단만 전달한다.

**차단**: 없음. SubagentStart는 실제 spawn 이후 event라 state/context만 다룬다.

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

차단이 발생하면 `guard-telemetry.jsonl` 에 `guard=file-guard` 로 기록된다.

#### 프로젝트별 write 경계 override — `.dcness/boundary.json`

코어 `ALLOW_MATRIX` 는 흔한 언어·레이아웃의 합리적 기본값만 잡는다. 프로젝트 사정은 무한하므로(비표준 소스 디렉토리, 또는 코어 기본 제외를 의도적으로 완화하고 싶은 경우), 프로젝트가 **루트의 `.dcness/boundary.json`** 으로 자기 사정을 직접 선언한다. 코어는 건드리지 않고, 예외는 프로젝트가 SSOT 로 가진다.

```json
{
  "build-worker": { "add": ["(^|/)remotion/", "(^|/)custom-e2e/"], "remove": ["^app/"] }
}
```

- **형식**: agent 별 `add` / `remove` 정규식(코어 `ALLOW_MATRIX` 와 동일한 `re.search` 패턴) 배열.
- **`add`**: 코어 `ALLOW_MATRIX` 에 없는 경로를 그 agent 에 허용 (비표준 레이아웃 / 의도적 기본 제외 완화).
- **`remove`**: 코어 기본 허용 경로를 이 프로젝트에서 제거 (ALLOW 보다 우선하는 DENY 오버레이).
- **탐색**: `harness/agent_boundary.py` 가 cwd 에서 **working tree top-level(`git rev-parse --show-toplevel`)까지만** 조상을 거슬러 이 파일을 찾는다. nested·linked worktree 와 하위 디렉토리에서도 worktree 루트 설정이 적용되지만, 그 *위* 상위 워크스페이스·home 디렉토리의 `.dcness/boundary.json` 은 무시된다 (무관한 상위 설정이 경계를 약화하지 못하도록).
- **제안 트리거**: `/init-dcness` 설정/진단 시 `dcness-helper boundary-suggestions` 가 비표준 소스 디렉터리의 `build-worker.add` 후보를 read-only 로 출력한다. 일반 `/impl`·`/impl-loop` 착수 앞에서는 실행하지 않으며, 실제 파일 작성은 사람 승인 뒤 메인이 수행한다.
- **build-worker override**: `/impl-loop` 의 mutation agent 는 build-worker 이므로 `build-worker` 키로 `add`·`remove` 를 선언한다. 다른 agent key는 build-worker에 전파되지 않는다.
- **안전 degrade**: 파일 부재·깨진 JSON·형식 위반·컴파일 불가 정규식은 조용히 무시하고 코어 기본값을 유지한다 (잘못된 설정이 경계를 깨뜨리지 않는다).
- **배포**: 읽는 로직은 plugin 본체(`harness/`)라 plugin 버전업으로 자동 적용 (cp 0). 설정 파일은 프로젝트가 직접 작성한다.

**override 가 뚫지 못하는 가드 (되돌릴 수 없는 경계만)**:

- **INFRA 경로** (`DCNESS_INFRA_PATTERNS` — `hooks/`, `harness/*.py` 등) 는 `add` 로 열 수 없다. INFRA 검사가 ALLOW(코어+add) 검사보다 *먼저* 발화하기 때문.
- **`.dcness/boundary.json` 자신**(과 `.dcness/` 디렉토리 전체) 은 sub-agent write 차단 영역 (자기 경계 셀프 확장/축소 금지). INFRA 로 보호되며 `remove` 로도 풀 수 없고, 디렉토리 타깃 write 우회도 닫힌다.
- **판정/검증 전용 agent**(`impl-validator` / `architecture-validator` / `product-acceptance` — 코어 ALLOW 가 빈 `()`) 는 `add` 로도 write 를 열 수 없다. "검증자는 자기가 검증하는 것을 못 고친다" 는 역할 격리는 catastrophic gate 신뢰의 근간이라 되돌릴 수 없는 경계 — `add` 로 mutation agent 로 승격시킬 수 없다.
- **guard self-disable 마커** (`.no-dcness-guard` = file-guard 임시 우회 / `.claude-plugin/` = `is_infra_project` self-repo 신호) 도 INFRA 로 보호된다. broad `add`(예 `.*`)로도 sub-agent 가 file guard 자체를 끄는 통제 파일을 쓸 수 없다.
- 그 외 기본값은 **강제 가드가 아니라 권고** 다. 프로젝트가 `add` 로 풀 수 있고, 그 경우 self-grading drift(구현자가 자기 코드를 통과시키도록 테스트를 편향) 위험은 프로젝트가 감수한다.

GitHub issue 외부 상태 변경은 경로에 따라 다르게 처리한다 — 같은 "issue 변경"이라도 차단 여부가 갈린다.

| issue 외부 상태 변경 경로 | file-guard 동작 |
|---|---|
| Bash `gh issue create/edit/close/comment/...` | **차단** (Bash 외부 변경 차단 목록 — `harness/agent_boundary.py` 의 `check_bash_mutation`) |
| GitHub MCP issue 도구 (`mcp__github__create_issue`, `update_issue`, `add_issue_comment` 등) | **통과** (의도된 예외 — `check_github_mcp_mutation`). per-agent `tools:` 권한이 이미 gate 하므로 도구 미부여 agent 는 호출 자체 불가. designer 등 issue 도구를 가진 agent 의 설계된 흐름을 막지 않는다. |

PR/repo 외부 상태 변경 (`gh pr ...` / `merge_pull_request` / `push_files` / `create_or_update_file` 등) 은 Bash·MCP 양쪽 다 sub-agent 에서 차단한다.

**차단**: 경계 위반 시 `exit 2` + stderr. `.no-dcness-guard` marker 는 file-guard 만 임시 우회한다.

### tdd-guard.sh

**시점**: `Edit`, `Write`, `NotebookEdit` 로 파일을 수정하기 직전. `Bash` 는 명시적 write target 추출 직후, 각 target 에 같은 검사를 적용한다. Codex/headless 구현 worker 는 Codex 성공 종료 후 `end-step` 저장 전에 변경 파일 목록에 같은 검사를 적용한다.

**우선순위**: 프로젝트에 generated TDD hook 이 있으면 project-local hook 이 TDD 판단을 소유한다. Interactive Claude Code 경로에서 `.claude/settings.json` 이 generated hook 을 등록한 상태라면 중앙 plug-in `tdd-guard.sh` 는 중복 판단을 피하고 즉시 allow 한다. Headless worker 와 synthetic 검사 경로는 `DCNESS_HEADLESS_TDD_CHECK=1` 로 중앙 hook 을 호출해 `.claude/hooks/dcness-tdd-guard.sh` 에 위임한다. generated hook 이 없을 때만 중앙 TS/JS fallback 이 돈다.

**TDD 계약 + self-test**: 계약은 생성물과 독립이다. `scripts/dcness-tdd-hooks self-test` 는 fixture 로 `무-test 구현 파일 → deny`, `매칭 test 있음 → allow`, `test 파일 자체 → allow` 를 재현한다. `/init-dcness` 의 `scripts/dcness-tdd-hooks ensure --targets cc,codex` 는 이 계약 self-test 를 먼저 실행하고, 통과한 후보만 hook 으로 등록한다.

**프로젝트 로컬 계약**: `.dcness/tdd-hooks.json` 이 있으면 helper 는 코어 프리셋보다 이 파일을 우선한다. 모든 계약은 `source_roots`, `impl_exts` 가 필요하고, custom 플랫폼은 `test_candidate_templates` 도 필요하다. `test_file_globs` 는 test 파일 자체를 구현 파일로 오인하지 않게 하는 선택 필드다. template placeholder 는 `{parent}`, `{stem}`, `{base}`, `{ext}`, `{path}`, `{path_no_ext}`, `{filename}` 을 지원한다. 기존 파일이 깨진 JSON 이거나 필수 필드가 없으면 덮어쓰지 않고 등록을 중단한다.

**지원 플랫폼**: helper 는 `python`, `web`, `go`, `android`, `ios` 프리셋으로 기본 project-local config 를 만들 수 있다. 새 플랫폼은 코어 프리셋을 추가하지 않아도 프로젝트 에이전트나 사람이 위 형식의 `.dcness/tdd-hooks.json` 을 승인·커밋하면 같은 self-test/등록 경로를 쓴다. 빈 프로젝트 또는 project-local 계약이 없는 미지원 플랫폼은 생성 skip 이며 안전 no-op 이다. 중앙 fallback 은 TS/JS (`*.ts`, `*.tsx`, `*.js`, `*.jsx`)만 검사한다. 그 외 확장자는 generated hook 이 없으면 silent skip 이다.

**생성/등록 순서**: CC hook 이 먼저다. `.claude/hooks/dcness-tdd-guard.sh` 후보가 self-test 를 통과해야 `.claude/settings.json` PreToolUse(`Edit|Write|NotebookEdit|Bash`) 에 등록된다. Codex hook 은 그 다음 같은 패턴으로 `.codex/hooks/dcness-tdd-guard.sh` 와 `.codex/hooks.json` PreToolUse(`Edit|Write|apply_patch`) 에 등록된다. 기존 `.claude/settings.json` 또는 `.codex/hooks.json` 이 깨진 JSON 이면 등록을 거부하고 파일을 덮어쓰지 않는다. Codex 쪽은 CLI 의 사용자 신뢰 승인(`~/.codex/config.toml` trusted hash 흐름)이 추가로 필요할 수 있으므로, `registered` 는 project-local 파일 등록 상태이지 사용자 trust 승인 완료를 뜻하지 않는다.

**Git 도달성**: 생성 파일(`.dcness/tdd-hooks.json`, `.claude/settings.json`, `.claude/hooks/dcness-tdd-guard.sh`, `.codex/hooks.json`, `.codex/hooks/dcness-tdd-guard.sh`)은 linked worktree 와 headless worker 체크아웃에서 같은 계약을 재사용하려면 Git 에 커밋되어야 한다. 자동 workflow PR 대상은 아니지만 worktree/headless 재사용이 필요한 프로젝트에서는 activation bootstrap commit 대상이다. `scripts/dcness-tdd-hooks status` 는 linked worktree 에서 커밋이 필요한 생성 파일을 `commit-required` 로 표시하고, in-place 에서만 실존하는 생성 파일은 `commit-advisory` 로 표시한다. `dcness-helper status` 는 linked worktree 에서 커밋이 필요한 경우만 WARN 으로 표시한다.

**공존 규칙**: generated hook 이 interactive CC project hook 으로 등록되어 있으면 중앙 hook 은 중복 실행하지 않는다. Headless/synthetic 경로는 중앙 hook 이 generated hook 에 위임한 뒤 종료한다. 따라서 TS/JS 프로젝트에서도 중앙 fallback 과 project-local hook 이 같은 파일을 이중 deny 하지 않는다. generated hook 이 실패하거나 self-test 를 통과하지 못한 후보는 등록되지 않으며, 미설정·생성 실패 시 no-op 으로 안전 통과한다.

**중앙 fallback 역할**: generated hook 이 없는 프로젝트에서는 TS/JS 구현 파일에 대응하는 test/spec 파일이 *존재하는지* 확인한다. 없으면 구현 파일 작성을 막는다. **test 의 존재만 검사하고, test 를 실행하지는 않는다** — green/red 판정이 아니라 "작성 전 test 가 먼저 있는가" 강제다.

**파일 단위 override marker**: 테스트가 구조적으로 불필요한 파일은 파일 내용 또는 이번 `Write` / `Edit` / `apply_patch` payload 에 `tdd-exempt: <사유>` 를 남기면 해당 파일의 test 부재 차단만 통과한다. 콜론 뒤 사유는 같은 줄에 최소 1단어 이상 있어야 하며, 빈 `tdd-exempt:` 는 통과하지 않는다. 주석 형태를 권장한다. 마커는 코드에 커밋되므로 `rg "tdd-exempt:"` 로 사용 빈도를 확인하고 impl-validator 가 남용 여부를 검토할 수 있다.

**skip 대상**:

- test/spec 파일 자체 — basename 의 `.test.` / `.spec.` 접미 컨벤션 (`foo.test.ts`, `bar.spec.tsx`)
- 표준 test 디렉터리 마디 — `__tests__/`, `__test__/`, `__mocks__/`, `test/`, `tests/`, `spec/`, `specs/`, `e2e/`
- 설정, markdown, yaml, env, css, 타입 선언
- Next.js 특수 파일 (`layout`, `page`, `loading`, `error`, `not-found`, `globals.css`)
- entry-file 예외 — path heuristic (`*/App.{ts,tsx,js,jsx}`, `*/_layout.*`, `*/apps/*/index.*`, `*/src/main.*`) + 내용 시그니처 (`registerRootComponent(`, `AppRegistry.registerComponent(`)
- `templates/`, `docs/design-variants/`
- TS/JS 외 언어

> basename 에 우연히 `test`/`spec` 이 든 **구현 파일** (`contest.ts`, `spectrum.ts`, `latest.ts`) 은 skip 하지 않는다 — TDD 강제 대상이다 (#681). skip 은 `.test.`/`.spec.` 접미와 슬래시로 구분된 표준 test 디렉터리 마디에만 적용된다.

**매칭 위치**: 같은 디렉터리, 같은 디렉터리의 `__tests__`, 부모/조부모 `__tests__`, monorepo `src_root/__tests__`, 프로젝트 root `src/__tests__`.

**Bash write target 정책**: `Bash` payload 는 [`harness.agent_boundary.extract_bash_paths`](../../harness/agent_boundary.py) 가 추출하는 명시적 write target 에 한해 검사한다. 예: redirect(`>`, `>>`), `tee`, in-place edit(`sed/perl/awk -i`), `cp`/`mv`/`rm` target. 추출된 target 이 TS/JS 구현 파일이면 직접 `Edit`/`Write`/`NotebookEdit` 와 동일한 skip 규칙 및 6-tier matching-test 존재 검사를 탄다. write target 이 없거나 TS/JS 구현 파일이 아니면 silent skip 한다.

**Headless worker 정책**: [`scripts/dcness-codex-worker`](../../scripts/dcness-codex-worker) 와 [`scripts/dcness-claude-worker`](../../scripts/dcness-claude-worker) 는 성공 prose 생성 후 file-boundary 검사를 먼저 수행하고, 그 다음 changed path(`git diff`/staged diff/untracked) 중 삭제가 아닌 파일을 synthetic `Edit` payload 로 `tdd-guard.sh` 에 다시 넣는다. 중앙 `tdd-guard.sh` 가 generated hook 을 위임하므로 headless worker 도 non-TS/JS 플랫폼에서 같은 project-local **TDD 계약**을 재사용한다. 단, 이 재사용은 generated hook 파일들이 Git 에 커밋되어 해당 worktree 에 존재할 때만 성립한다. `exit 2` 는 step 성공 종료를 차단하고 위반 파일 목록을 출력한다. guard 자체 오류는 `headless-tdd-guard` fail-open event 로 기록하고 작업을 과차단하지 않는다.

**Codex build-worker sandbox 승인 복구**: 기본 호출은 환경변수를 추가하지 않은 기존 계약 그대로 `-s workspace-write`만 전달한다. build-worker가 `VALIDATION_BLOCKED`를 보고하고 raw log에 `SocketException: Operation not permitted` 같은 좁은 Codex sandbox signature가 있을 때만 wrapper가 run 디렉터리에 helper-generated `permission_required` receipt를 남긴다. assertion/compile/test 실패, 일반 `Permission denied`, Codex CLI/auth/timeout 실패는 permission request로 분류하지 않는다.

메인 `/impl-loop`은 receipt의 capability, 제안 writable root 절대경로, 근거를 읽고 다음 사실을 사용자에게 설명한 뒤 승인을 받는다.

- `network_access`는 loopback만 여는 옵션이 아니라 Codex `workspace-write`의 **outbound network** 접근을 허용한다.
- 추가 writable root는 로그에서 확인된 `GRADLE_USER_HOME` 또는 `~/.gradle`처럼 안전하게 좁힌 절대경로만 제안한다. 안전한 root를 추론하지 못하면 root 권한을 제안하지 않는다.
- 승인 여부와 무관하게 sandbox는 `workspace-write`로 유지한다. `danger-full-access`는 자동 폴백이나 사용자 선택지로 제공하지 않는다.
- 선택지는 **이번 실행에만 허용 / 이 프로젝트에 저장 / 거부**다.

`이번 실행에만 허용`은 승인한 env를 Codex build-worker 재시도 프로세스 한 번에만 전달하며 `.claude/settings.local.json`을 생성하거나 수정하지 않는다. `이 프로젝트에 저장`은 기존 JSON의 다른 최상위 키와 기존 `env` 키를 보존하면서 승인한 키만 아래처럼 병합하고, 현재 세션의 제한 재시도에도 같은 값을 명시적으로 전달한다. 저장값은 이미 실행 중인 임의 프로세스에 소급 적용되지 않으며, 이후 **새 세션**에서는 Claude Code가 `.claude/settings.local.json`의 `env`를 로드한 뒤 spawn하는 Codex worker부터 적용된다.

```json
{
  "env": {
    "DCNESS_CODEX_NETWORK_ACCESS": "1",
    "DCNESS_CODEX_WRITABLE_ROOTS": "/Users/name/.gradle:/Users/name/.konan"
  }
}
```

- `DCNESS_CODEX_NETWORK_ACCESS=1|true|on`은 `-c sandbox_workspace_write.network_access=true`만 추가한다. 미설정 또는 `0|false|off`는 옵션을 추가하지 않으며, 그 밖의 값은 오타로 보고 worker 시작을 거부한다.
- `DCNESS_CODEX_WRITABLE_ROOTS`는 플랫폼 path separator(macOS/Linux `:`)로 구분한 절대경로 목록이다. wrapper가 각 원소를 JSON 호환 TOML string array로 encode한 뒤 `-c sandbox_workspace_write.writable_roots=[...]`를 추가하므로 공백·따옴표·backslash가 한 CLI 인자 안에서 보존된다.
- 두 opt-in은 서로 독립이며 `workspace-write`를 유지한다. `danger-full-access` 전환은 제공하지 않는다.
- 승인 후 자동 재시도는 최대 1회다. 같은 sandbox 거부가 반복되면 추가 root/network 확대 없이 중단한다. malformed settings는 덮어쓰지 않으며, 사용자 거부·안전한 root 추론 실패와 함께 `VALIDATION_BLOCKED` 상태를 유지한다. 이 permission 경로에서는 host 직접 검증이나 다른 provider로 우회하지 않는다.
- 이 계약은 Codex 설정 키를 사용하는 `codex-headless` build-worker 전용이다. `claude-headless` worker는 Claude Code의 `--permission-mode acceptEdits` 경로이며 Codex sandbox 설정을 소비하지 않으므로 동일 env를 적용하지 않는다. 다른 provider로의 자동 확장은 범위 밖이다.

**차단**: test 부재 시 `exit 2` + 한국어 안내. Bash write target 차단 메시지는 `TDD GUARD[Bash]` 로 시작해 어떤 target 이 matching-test enforcement 에 실패했는지 함께 표시한다. Headless worker 차단 메시지는 `[dcness-codex-worker] BLOCKED: TDD GUARD ...` 또는 `[dcness-claude-worker] BLOCKED: TDD GUARD ...` 로 시작하고 위반 파일 목록을 포함한다.

### post-agent-clear.sh

**시점**: `Agent` tool 결과가 돌아온 직후.

**역할**:

- `tool_response.status=completed`인 foreground 최종 응답에서만 비어 있지 않은 prose를 `<run_dir>/<agent>[-<MODE>].md`로 저장
- 동일 `tool_use_id`/`agent_id`로 `step_completed` receipt를 즉시 기록하고 `live.json.active_agent / active_mode` clear
- `status=async_launched`, status 누락/미인식, 빈 prose는 false `step_completed`를 만들지 않음. 이미 시작된 foreground step은 `step_aborted` 진단으로 닫음
- 같은 `tool_use_id` 재전달은 prose occurrence 파일과 ledger receipt를 중복 생성하지 않음
- current step의 agent/mode/tool_use_id/agent_id가 다르면 prose write와 receipt append 전에 거부하고 `hookSpecificOutput.additionalContext`로 복구 진단

**차단**: 없음.

### post-agent-failure.sh

**시점**: `Agent` tool이 오류나 failure result로 끝난 직후.

**역할**: `PostToolUseFailure`의 `tool_use_id`로 pending/current identity를 대조한다. matching foreground step이 실제 시작됐다면 `step_aborted(category=tool_failure)`로 닫고, spawn 전 deny/failure면 ledger step을 만들지 않는다. 어느 경우든 `step_completed` receipt는 만들지 않고 오류와 재시도 지점을 `additionalContext`로 전달한다.

**차단**: 없음.

### subagent-stop-clear.sh

**시점**: sub-agent 컨텍스트 종료 직후.

**역할**: `SubagentStop` payload 의 `agent_type` 을 사용해 active agent state 를 정리한다. PostToolUse Agent clear 보다 sub-agent 종료 시점에 더 가깝기 때문에 stale state 를 줄이는 보조 안전망이다.

**차단**: 없음. SubagentStop 은 차단 권한이 있지만 dcNess 는 state clear 만 수행하고 항상 종료를 허용한다.

### stop-end-run.sh

**시점**: 메인 Claude 응답 종료 시.

**역할**:

- 마지막 step 이 완료됐고 run 이 미finalized 상태면 `end-run` 을 자동 수행
- 마지막 `end-step` 이후 새 `begin-step` 이 열린 run 은 동일 agent 재라운드여도 진행 중으로 보고 자동 `end-run` 대상에서 제외
- 마지막 step 결론이 다음 step 으로 이어져야 하는 enum 이고 종료 agent 가 아니면 continuation signal 을 내보내 메인 turn 재발화
- `begin-run impl --acceptance-required` 로 기록된 마감 task run 에서는 `impl-validator` 를 종료 agent 로 취급하지 않는다. `impl-validator` 결론이 `PASS` 이면 Stop hook 이 `product-acceptance` 진입용 continuation signal 을 내보내며, marker 가 없는 중간 task / `--no-acceptance` run / verify-only run 은 기존 종료 동작을 유지한다.
- `impl-validator:CODEBASE_SANITY` `PASS`는 종료 결과가 아니다. impl run에서는 같은 final merge candidate의 일반 `impl-validator` merge review를, design run에서는 Cartography freshness preflight를 이어가도록 continuation signal을 낸다. Sanity mode 직후 acceptance로 건너뛰지 않는다.
- 같은 step 에서 반복 block 횟수가 한도를 넘으면 사용자/메인의 종료 의도를 존중하고 skip

**차단**: tool 차단은 아니다. 필요 시 stdout JSON 으로 메인 turn 을 재발화한다.

## Layer 2 — git hooks

설치 경로: 사용자 repo 의 `.git/hooks/`. `/init-dcness` bootstrap 이 plug-in 의 `scripts/hooks/*` thin shim 을 복사한다. 본체 검증 로직은 사용자 repo 에 복사하지 않고 plug-in SSOT 를 직접 호출한다.

| Hook | Source | 언제 | 하는 일 | 차단 |
|---|---|---|---|---|
| `.git/hooks/pre-commit` | `scripts/hooks/pre-commit` | commit 직전 | main 직접 commit 차단 (+ self 는 python test gate) | O |
| `.git/hooks/commit-msg` | `scripts/hooks/commit-msg` | commit message 확정 전 | 커밋 제목 git-spec 검증 | O |
| `.git/hooks/post-checkout` | `scripts/hooks/post-checkout` | branch checkout/switch 직후 | 브랜치명 위반 경고 + rename 안내 | X |
| `.git/hooks/pre-push` | `scripts/hooks/pre-push` | push 직전 | main 직접 push 차단 + 브랜치명 검증 | O |

`pre-commit` 은 외부 활성 프로젝트에도 배포되지만 그 역할은 main 직접 commit 차단 전용이다. python test gate 단계는 `scripts/check_python_tests.sh` 가 존재할 때만 실행되므로 그 스크립트가 없는 외부 repo 에서는 main-block 만 강제한다. TDD 강제는 git hook 이 아니라 Layer 1 의 `tdd-guard.sh` 가 구현 파일 작성 전에 수행한다.
git hook 차단도 같은 receipt 체계를 쓰되, 기록은 `is-active` 또는 dcness self repo 판정 통과 뒤에만 수행한다. 비활성 외부 프로젝트에서 남아 있는 git hook 이 차단하더라도 `guard-telemetry.jsonl` 을 만들지 않는다. dcness self repo 는 plugin hook 전체를 active 로 만들지 않고, self 작업 중 발생한 `pre-commit` / `commit-msg` / `pre-push` 차단 신호만 git hook shim 기록 지점에서 보존한다. `DCNESS_SESSION_ID` / `DCNESS_RUN_ID` 가 있는 headless worker 컨텍스트에서는 active run 로그에 귀속하고, 없으면 프로젝트 로그에 fallback 한다. `commit-msg` 차단은 `guard=git-commit-msg`, `pre-push` 차단은 `guard=git-pre-push`, `pre-commit` 차단은 `guard=git-pre-commit` 으로 기록한다.

### .git/hooks/pre-commit

**Source**: `scripts/hooks/pre-commit`

**시점**: `git commit` 이 커밋을 만들기 직전.

**역할**:

- 현재 브랜치가 `main` 이면 commit 을 차단한다 (branch → PR → merge 절차 강제). 외부 활성 프로젝트에도 동일 적용된다.
- `scripts/check_python_tests.sh` 가 존재하는 repo(사실상 dcness self)에서만 python test gate 를 실행한다. 외부 활성 프로젝트에는 이 스크립트가 없어 main-block 만 강제한다.

**차단**: main 브랜치 commit 또는 (self 에서) python test gate 실패 시 commit 실패.
차단 시 `guard-telemetry.jsonl` 에 `category=main_block` 또는 `category=python_tests` hit 가 남는다.

### .git/hooks/commit-msg

**Source**: `scripts/hooks/commit-msg`

**시점**: `git commit` 이 commit message 를 확정하기 직전.

**역할**: commit title 을 읽고 `check_git_naming.mjs --title` 로 git-spec 제목 규칙을 검증한다. merge commit 제목은 면제한다.

**차단**: 제목 위반 시 commit 실패.
차단 시 `guard-telemetry.jsonl` 에 `category=git_naming` hit 가 남는다.

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
차단 시 `guard-telemetry.jsonl` 에 `category=main_push_block` 또는 `category=branch_naming` hit 가 남는다.

## Layer 3 — CI/CD workflows

설치 경로: 사용자 repo 의 `.github/workflows/`. `/init-dcness` 에서 사용자가 Y 를 선택한 경우 thin workflow 를 생성한다. workflow 본체는 `Daeguk-Sun/dcNess` 의 composite action 을 호출한다.

| Workflow | Trigger | 언제 | 하는 일 | 성격 |
|---|---|---|---|---|
| `.github/workflows/git-naming-validation.yml` | `pull_request` opened/synchronize/reopened/edited | PR 생성/수정/동기화 | 브랜치명 + PR 제목 git-spec 검증 | 선택형 CI gate |
| `.github/workflows/pr-body-validation.yml` | `pull_request` opened/synchronize/reopened/edited | PR 생성/수정/동기화 | PR body issue trailer 검증 | 선택형 CI gate |
| `.github/workflows/doc-path-integrity.yml` | `pull_request` opened/synchronize/reopened/edited | PR 생성/수정/동기화 | repo-relative 경로 참조 실존 검증 | 선택형 CI gate |
| `.github/workflows/doc-sync.yml` | `pull_request` opened/synchronize/reopened/edited | PR 생성/수정/동기화 | index epic 표 drift 검증 + `/design` 산출물 구조 감사 | 선택형 CI gate |
| `.github/workflows/github-project-lifecycle.yml` | `issues`, `pull_request closed` | issue 변경 또는 PR merge | issue/label drift 검출, merged PR `in-progress` label cleanup, 선택적 Project 미러 warning | 선택형 CI/CD |

### .github/workflows/git-naming-validation.yml

**설치**: `/init-dcness` 의 선택형 CI workflow 질문에서 사용자가 CI git-naming 강제를 선택하면 생성한다.

**시점**: `main` 대상 PR 이 opened, synchronize, reopened, edited 될 때.

**역할**: `Daeguk-Sun/dcNess/.github/actions/git-naming@main` 을 호출해 `github.head_ref` 와 PR title 을 검증한다.

**차단**: workflow 실패. hard merge gate 여부는 사용자 repo 의 branch protection/ruleset 설정에 달려 있다.

### .github/workflows/pr-body-validation.yml

**설치**: `/init-dcness` 의 선택형 CI workflow 질문에서 사용자가 PR body close-keyword gate 를 선택하면 생성한다.

**시점**: `main` 대상 PR 이 opened, synchronize, reopened, edited 될 때.

**역할**: `Daeguk-Sun/dcNess/.github/actions/pr-body@main` 을 호출해 PR body 에 issue trailer 가 있는지 확인한다.

허용 패턴:

- `Closes #N`, `Fixes #N`, `Resolves #N`
- `Part of #N`
- `Document-Exception-PR-Close: <사유>`

**차단**: workflow 실패. hard merge gate 여부는 사용자 repo 의 branch protection/ruleset 설정에 달려 있다.

### .github/workflows/doc-path-integrity.yml

**설치**: `/init-dcness` 의 선택형 CI workflow 질문에서 사용자가 doc-path 무결성 검증을 선택하면 생성한다.

**시점**: `main` 대상 PR 이 opened, synchronize, reopened, edited 될 때. 문서가 그대로여도 참조 대상 파일이 삭제·이동되면 stale path 가 생길 수 있으므로 path filter 를 두지 않는다.

**역할**: `Daeguk-Sun/dcNess/.github/actions/doc-path-integrity@main` 을 호출해 활성 프로젝트의 context/SSOT 문서(`CLAUDE.md`, `AGENTS.md`, root `architecture.md`, `docs/index.md`, `docs/project-context.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/modules/**`, `docs/decisions/**`) 안 repo-relative path 참조가 실제 파일 또는 디렉토리를 가리키는지 확인한다.

**차단**: workflow 실패. hard merge gate 여부는 사용자 repo 의 branch protection/ruleset 설정에 달려 있다.

### .github/workflows/doc-sync.yml

**설치**: `/init-dcness` 의 선택형 CI workflow 질문에서 사용자가 doc-sync 신선도 검증을 선택하면 생성한다.

**시점**: `main` 대상 PR 이 opened, synchronize, reopened, edited 될 때.

**역할**: `Daeguk-Sun/dcNess/.github/actions/doc-sync@main` 을 호출해 활성 프로젝트의 `docs/index.md` `## 에픽` / `## 모듈` 생성 표가 파생 원본과 일치하는지 확인한다. index 표는 `docs/epics/epic-NN-*` 디렉토리, `stories.md` frontmatter, `docs/modules/<module-id>/` 에서 파생된다. 같은 composite action 안에서 `check_design_artifact_structure.mjs` 도 실행해 신규 `/design` 산출물의 agent-first 핵심 섹션과 line budget 을 감사한다.

**빈 환경**: `docs/index.md`, `docs/architecture.md`, 또는 유효 epic/module 이 없는 갓 시드된 프로젝트에서는 no-op PASS 한다.

**차단**: workflow 실패. hard merge gate 여부는 사용자 repo 의 branch protection/ruleset 설정에 달려 있다.

### .github/workflows/github-project-lifecycle.yml

**설치**: `/init-dcness` 의 GitHub Project lifecycle bootstrap 에서 사용자가 lifecycle guard 를 선택하면 생성한다.

**시점**:

- issue opened/edited/labeled/unlabeled
- PR closed, 단 merged PR 만 `in-progress` label cleanup 후보

**역할**:

- issue/label drift 검출. Project 좌표가 있으면 Project field drift 는 warning 으로만 보고
- merged PR body 의 close keyword 대상 issue 에서 `in-progress` label 제거. Project 좌표가 있으면 Project Status `Done` 도 best-effort 미러
- `Part of #N` 만 있는 PR 은 cleanup 후보로 보지 않음

**필수 설정**: label cleanup 에는 workflow `issues: write` 권한이 필요하다. Project v2 미러까지 쓰려면 `secrets.DCNESS_PROJECT_TOKEN`, `vars.DCNESS_PROJECT_NUMBER`, `vars.DCNESS_PROJECT_OWNER` 가 필요하다.

**차단/보정**: issue/label drift 는 workflow 실패로 드러난다. Project field drift 와 미러 실패는 warning 으로만 보고한다. merged PR 보정은 `apply: "true"` 로 label 을 수정하고, 좌표가 있으면 선택적 Project 상태를 best-effort 로 미러한다.

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

**git hooks**: `/init-dcness` bootstrap 이 사용자 repo 의 `.git/hooks/` 에 thin shim 을 always-overwrite 한다. hook 본체는 self-repo, `CLAUDE_PLUGIN_ROOT`, plug-in cache 중 실행 문맥에 맞는 검증 script 를 resolve 한다.

**CI/CD workflows**: `/init-dcness` 가 사용자 선택에 따라 thin workflow 를 `.github/workflows/` 에 always-overwrite 한다. 사용자가 tag pin 을 원하면 `@main` 대신 release tag 로 바꿀 수 있다.

`CLAUDE_PLUGIN_ROOT` 는 plug-in hook 실행 시 Claude Code 가 자동 설정하는 env 다. 이 값은 모든 활성 프로젝트 hook 에서 존재하므로 infra mode 신호로 쓰면 안 된다.

## 우회 / opt-out

| Mechanism | Scope | Effect |
|---|---|---|
| 미활성 프로젝트 | 전체 CC hook | `is-active` 게이트에서 즉시 no-op |
| `.no-dcness-guard` cwd marker | file-guard | file boundary / 외부 변경 차단 목록 임시 우회 |
| `tdd-exempt: <사유>` 파일 marker | tdd-guard | 해당 파일의 test 부재 차단만 사유와 함께 override |
| `DCNESS_INFRA=1`, `~/.claude/.dcness-infra`, dcNess self repo marker | file boundary | dcNess 자체 작업에서 infra path 보호 해제 |

catastrophic-gate 에는 marker override 가 없다. `tdd-exempt: <사유>` 는 tdd-guard 의 test 부재 차단에만 적용되며, file-guard / catastrophic-gate / git hook 을 우회하지 않는다. git hook 의 `--no-verify` 우회는 가능하지만 dcNess 절차상 금지다. CI/CD workflow 는 GitHub 에 올라온 PR/issue 이벤트에서 다시 검증한다.

## 참조

자연어 SSOT:

- [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) — 강제 영역 2가지
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
