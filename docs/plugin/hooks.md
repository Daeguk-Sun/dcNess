# Hooks SSOT — dcness 코드 강제 백본

> **Status**: ACTIVE
> **Scope**: dcness plug-in 이 활성 프로젝트에 적용하는 7 hook 의 시점 / 역할 / 차단 동작 / 우회 메커니즘 SSOT.
> **Cross-ref**: [`CLAUDE.md`](../../CLAUDE.md) §0.7 (대원칙), [`harness/agent_boundary.py`](../../harness/agent_boundary.py) (권한 매트릭스). catastrophic 시퀀스 진본 = 본 문서 §3.2.

---

## 0. 정체성 — hook 은 dcness 의 *유일한* 코드 강제 백본

dcness 가 강제하는 영역은 단 2가지 ([`CLAUDE.md`](../../CLAUDE.md) §0.7):
1. **작업 순서** — agent 시퀀스 + retry 정책
2. **접근 영역** — 파일 경계 (ALLOW/READ_DENY) + 외부 시스템 mutation 차단

그 *외* 모든 영역 = agent 자율 / 권고 / 측정. hook 은 위 2 영역의 *유일한 코드 구현*. 다른 모든 SSOT (routing / loop-procedure) 는 hook 동작을 *문서화* 한 자연어 spec 이며, 위반 시 실제로 *차단* 하는 주체는 본 문서가 다루는 7 hook.

---

## 1. CC hook event 모델

dcness 가 사용하는 CC hook event 4종:

| Event | 시점 | 차단 권한 | dcness 사용 hook |
|---|---|---|---|
| `SessionStart` | CC 새 conversation 시작 시 (resume / `/clear` 포함). user 첫 prompt 처리 *전*. | X (inject 만) | session-start.sh |
| `PreToolUse` | tool 호출 *직전*. matcher 매치 시 fire. | ✓ (`exit 1` 또는 `permissionDecision: deny` 로 차단) | catastrophic-gate / file-guard / tdd-guard |
| `PostToolUse` | tool 호출 *직후* (결과 반환 후, 메인 다음 turn 시작 전). | X (inject 만) | post-agent-clear / post-file-op-trace |
| `Stop` | 메인 응답 종료 시점. 무한 루프 방지 `stop_hook_active=true` 플래그 동반. | ✓ (`decision: "block"` JSON stdout 으로 메인 turn 재 발화 강제) | stop-end-run.sh |

**미사용 event**: `UserPromptSubmit` / `PreCompact` / `SubagentStop` / `Notification` / `SessionEnd` — dcness 강제 백본은 SessionStart + PreToolUse + PostToolUse + Stop 4종으로 충족.

**차단 권한 비대칭**:
- PreToolUse 만 tool 호출 *차단* 가능 → catastrophic-gate / file-guard / tdd-guard 가 실제 강제 백본.
- Stop 은 메인 종료 *차단* 가능 (`decision: "block"`) → stop-end-run.sh 가 중간 step PASS 후 메인 침묵 회귀 차단 (issue #469 결함 A).
- SessionStart + PostToolUse 는 `hookSpecificOutput.additionalContext` 로 *컨텍스트 inject* — 메인 Claude 의 다음 turn 에 system reminder 로 보임.

---

## 2. 공통 패턴 (전 7 hook 공유)

모든 hook 의 bash wrapper 가 동일한 부트스트랩 4 단계 수행:

```bash
set -uo pipefail

# 1. plug-in root 를 PYTHONPATH 에 prepend — cross-project 시나리오 대응
export PYTHONPATH="${CLAUDE_PLUGIN_ROOT:-.}:${PYTHONPATH:-}"

# 2. 활성화 게이트 — dcness whitelist 외 프로젝트면 즉시 pass-through
python3 -m harness.session_state is-active >/dev/null 2>&1 || exit 0

# 3. CC PID 추출 (bash 의 PPID = CC main process)
CC_PID=$PPID

# 4. Python dispatch
python3 -m harness.hooks <handler> --cc-pid "$CC_PID"
```

**활성화 게이트 메커니즘**:
- `harness/session_state.py is-active` 가 현재 프로젝트가 dcness 활성 여부 판정 (`/init-dcness` 로 등록된 whitelist + marker 검사)
- 미활성 프로젝트 → hook 즉시 `exit 0` (no-op). plug-in 설치만 했고 활성화 안 한 프로젝트엔 영향 X.

**Python handler dispatch**: 모든 차단 / inject 로직은 [`harness/hooks.py`](../../harness/hooks.py) 안. bash wrapper 는 thin shim.

### 2.1 local provider routing 은 hook 이 아니다

`code-validator` / `architecture-validator` / `pr-reviewer` 만 Codex read-only 실행으로 opt-in route 할 수 있다. 이는 hook 강제 백본이 아니라 메인 Claude 의 agent 호출 선택지다.

- config: `~/.claude/plugins/data/dcness-dcness/routing.json`
- CLI: `dcness-helper routing status|doctor|enable-codex-validation|disable-codex-validation|set|resolve`
- wrapper: `scripts/dcness-codex-validator`
- 대상: read-only validation 3종만. engineer / build-worker / module-architect 등 mutation agent 는 Claude route 고정.

Codex wrapper 는 설치된 `dcness-<agent>/SKILL.md` 내용을 prompt 에 직접 포함하며 repo mutation 을 금지한다. 실행 전후 git status snapshot 이 달라지면 block 하고 자동 revert 하지 않는다.

---

## 3. 7 hook 상세

### 3.1 session-start.sh

**Event**: `SessionStart`
**시점**: CC 가 새 conversation 시작 시. user 첫 prompt 처리 *전*.

**역할**:
- (a) sid 추출 + `.by-pid-current-run` 작성 + `live.json` 초기화 (state machine bootstrap)
- (b) **슬림 inject** — `hookSpecificOutput.additionalContext` 로 강제 영역 / 메인 Claude 필수 / 진입 매트릭스 / 안티패턴 본문 직접 inject (~30줄)
  - 메인 Claude 첫 응답 첫 줄에 토큰 `[dcness 활성 확인]` 출력 의무 — 토큰 부재 시 사용자가 즉시 룰 위반 확인 가능

**차단 동작**: SessionStart 는 차단 권한 X. `additionalContext` inject 만. 실패 시 silent (`exit 0`).

---

### 3.2 catastrophic-gate.sh

**Event**: `PreToolUse`
**Matcher**: `Agent`
**시점**: 메인 Claude 가 sub-agent 호출 (Task tool with `subagent_type`) *직전*.

**역할**: **catastrophic 시퀀스 강제** — 본 §3.2 = catastrophic 시퀀스 **진본 SSOT**. 다음 룰은 *어떤 동적 결정* 으로도 우회 금지. 원칙 — "흐름 강제는 catastrophic 시퀀스만, 그 외 모든 시퀀스 = agent 자율".

| 룰 ID | 내용 | 강제 주체 |
|---|---|---|
| §2.1.1 | src/ 변경 후 code-validator PASS 없이 pr-reviewer 호출 금지 | catastrophic-gate (코드) |
| §2.1.3 | engineer 가 module-architect `PASS` enum 발화 없이 src/ 작성 금지 (신규/보강/버그픽스 동일) | catastrophic-gate (코드) |
| §2.1.4 | PRD 변경 후 `/tech-review` 사용자 2차 OK 없이 `/architect-loop` 진입 금지 + `/architect-loop` 진입 후 tech-reviewer 재호출 금지 (단방향) | **자연어 룰 — 메인 영역** (코드 강제 X) |
| §2.1.5 | module-architect × K (architect-loop Step 4) 진입 직전 architecture-validator 1차 PASS 없이 진입 금지 | catastrophic-gate (코드) |

> **룰 ID `§2.1.N` 보존**: `harness/hooks.py` / `catastrophic-gate.sh` 가 에러 메시지·분기 ID 로 사용 (번호 = 룰 ID). §2.1.2 / §2.1.6~§2.1.8 은 자연어 폐기 (결번).
> **§2.1.4 단방향 catastrophic** 만 코드 강제가 아닌 *자연어 룰* — `skills/tech-review/SKILL.md` / `skills/architect-loop/SKILL.md` 가 기능 참조. architect-loop 도중 tech-review 미검증 새 외부 의존 발견 시 처리 = `NEW_DEP_ESCALATE` 3안 (채택+수동검증 / 대안 우회 / 전체 회귀 — 어느 경우든 tech-reviewer 재호출 0). 라우팅 = [`routing.md`](routing.md) §3 escalate.

**차단 동작**: `exit 1` → CC 가 Agent 호출 거부 + stderr 메시지 노출. 메인이 회복 또는 사용자 위임. (§2.1.4 는 메인 prose 가 자율 보존)

---

### 3.3 file-guard.sh

**Event**: `PreToolUse`
**Matcher**: `Edit|Write|NotebookEdit|Read|Bash|mcp__.*`
**시점**: 모든 file / bash / mcp tool 호출 *직전* (sub-agent 활성 시 + 메인 직접 모두).

**역할**: [`harness/agent_boundary.py`](../../harness/agent_boundary.py) 권한 매트릭스 강제

| § | 룰 | 영향 |
|---|---|---|
| §4.3 | `DCNESS_INFRA_PATTERNS` | 전 sub-agent 의 인프라 path 차단 (`.claude/`, `hooks/`, `harness/*.py`, `docs/plugin/*.md`, `scripts/*.mjs`) |
| §4.1 | `ALLOW_MATRIX` | agent 별 Write 허용 path (예 engineer = `src/**`, designer = `design-variants/**`) |
| §4.2 | `READ_DENY_MATRIX` | agent 별 Read 금지 (예 designer 는 `src/` 못 읽음) |
| §4.4 | `is_infra_project()` | dcness 자체 작업 시 위 모두 해제 |

**메인 Claude turn** (sub-agent 비활성): pass-through. `mcp__.*` tool: `file_path` 부재 시 boundary skip, trace 만.
**차단 동작**: `exit 1` → tool 호출 거부. custom agent 추가 시 §4.1 행 등록 의무 (미정의 시 차단).

**코드 SSOT**: [`harness/agent_boundary.py`](../../harness/agent_boundary.py) — ALLOW / READ_DENY / DCNESS_INFRA_PATTERNS 권한 경계 (권한 진본).

---

### 3.4 tdd-guard.sh

**Event**: `PreToolUse`
**Matcher**: `Edit|Write|NotebookEdit`
**도입**: release 0.2.16 (PR #339 / #340)
**시점**: Edit / Write tool 호출 *직전*.

**역할**: TS / JS 파일 (`*.ts|*.tsx|*.js|*.jsx`) Edit / Write 시 매칭 test 파일 *존재* 검사. 없으면 deny.

**skip 대상** (no-op, exit 0):
- test 파일 자체 — `*test*`, `*spec*`, `*__tests__*`
- 설정 / 비-코드 — `*.json`, `*.css`, `*.scss`, `*.md`, `*.yml`, `*.yaml`, `*.env*`, `*.config.*`, `*tailwind*`, `*postcss*`, `*next.config*`, `*tsconfig*`
- 타입 — `*/types/*`, `*/types.ts`, `*/types.d.ts`, `*.d.ts`
- Next.js 특수 — `*/layout.tsx`, `*/page.tsx`, `*/loading.tsx`, `*/error.tsx`, `*/not-found.tsx`, `*/globals.css`
- 시드 / 시안 — `*/templates/*`, `*/design-variants/*`
- 그 외 확장자 (`*.py`, `*.go` 등) — silent skip

**매칭 test 파일 검사 6-tier 12 location** (DCN-CHG-20260522 — issue #469 결함 C 영역 확장):
```
Tier 1: <dir>/<name>.{test,spec}.{ts,tsx,js,jsx}
Tier 2: <dir>/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
Tier 3: <parent>/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
Tier 4: <grandparent>/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
Tier 5: <src_root>/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
Tier 6: <PROJECT_ROOT>/src/__tests__/<name>.{test,spec}.{ts,tsx,js,jsx}
```

`<src_root>` = 파일 경로 안 `src/` 마디 직전까지 trim. monorepo `apps/<X>/src/...` / `packages/<X>/src/...` cover. trim 실패 (`src/` 부재) 시 `<PROJECT_ROOT>/src` fallback. Tier 4 (grandparent) + Tier 5 (src_root) = #469 결함 C 영역 확장 — build-worker 가 회피 stub 박는 안티패턴 차단.

**차단 동작**: `permissionDecision: deny` + 한국어 안내 (테스트 부재 + 검사 위치 12곳 + 본 파일의 실측 `<dir>` / `<parent>` / `<grandparent>` / `<src_root>` / `<PROJECT_ROOT>` 값). TDD 미이행 환경에선 plug-in 활성화 후 광범위한 deny 발생 가능.

---

### 3.5 post-agent-clear.sh

**Event**: `PostToolUse`
**Matcher**: `Agent`
**시점**: sub-agent 호출 *직후* (Task tool 결과 반환 후, 메인 다음 turn 시작 전).

**역할**:
- (a) `live.json.active_agent / active_mode` clear — 메인 Claude 복귀 표시
- (b) **sub-agent prose 자동 저장** — `tool_response.text` → `<run_dir>/<agent>[-<MODE>].md` + `live.json.current_step.prose_file` 기록. 메인이 직접 Write 불필요.
- (c) agent-trace 집계 → tool histogram + anomaly 검출
- (d) **`additionalContext` inject** (`hookSpecificOutput` JSON) — 메인 다음 turn 의 Agent tool result 옆에 system reminder 로 보임
- (issue #392 — redo_log auto append + routing_telemetry.record_agent_call 폐기. baseline + 매커니즘 실측 0건)

**차단 동작**: X (PostToolUse). stdout = JSON (`hookSpecificOutput`) inject. stderr = `/tmp/dcness-hook-stderr.log` 보존 (디버그용).

---

### 3.6 post-file-op-trace.sh

**Event**: `PostToolUse`
**Matcher**: `Edit|Write|NotebookEdit|Read|Bash|mcp__.*`
**시점**: file / bash / mcp tool 호출 *직후*.

**역할**: 활성 sub-agent 가 있을 때만 `agent-trace.jsonl` 에 post phase 1줄 append.
- 메인 Claude turn (active_agent 미설정) = noop
- 비활성 프로젝트 = noop

**차단 동작**: X. agent 별 행동 trace 누적 → review report ([`harness/run_review.py`](../../harness/run_review.py)) 의 tool histogram + anomaly 검출 입력.

---

### 3.7 stop-end-run.sh

**Event**: `Stop`
**시점**: 메인 Claude 응답 종료 시. `stop_hook_active=true` 동반 시 즉시 skip (무한 루프 가드).
**도입**: issue #382 (자동 end-run) + issue #469 결함 A fix (continuation signal)

**역할 1 — 자동 end-run (issue #382)**:
- `active_runs[rid]` 슬롯 미finalized + 마지막 step end-step 호출 완료 매칭 시 in-process `_cli_end_run` 호출.
- 부산물: `<run_dir>/review.md` 생성 + loop-insights 누적 + active_runs slot finalize.
- 배경: `/impl-loop` / `/architect-loop` 종료 후 메인이 end-run 까먹는 회귀 차단.

**역할 2 — continuation signal (issue #469 결함 A)**:
- end-run 호출 *전* 마지막 step prose (`<run_dir>/<agent>[-<MODE>].md`) 결론 enum 추출.
- 다음 step 진입 가능 enum (`PASS` / `IMPL_DONE` / `POLISH_DONE` / `TESTS_WRITTEN` / `UX_FLOW_DONE`) **AND** 마지막 step agent 가 종료 agent (`pr-reviewer`) 아닌 경우 → `{"decision": "block", "reason": "..."}` JSON stdout 씀.
- CC 가 본 신호 인식 → 메인 turn 재 발화 강제. 메인이 reason 읽고 다음 sub-step 진입 (예: build-worker PASS → pr-reviewer 호출).
- 무한 루프 가드: 같은 step 에서 block 쓴 횟수 (`slot.stop_block_count[<agent>:<mode>]`) 가 `_STOP_BLOCK_COUNT_MAX = 2` 초과 시 skip — 메인이 reason 받고도 발화 안 하는 진짜 종료 의도 인정.
- 배경: jajang Epic 20 multi-task `/impl-loop` 실측에서 build-worker tool_result 후 메인 turn 자동 발화 부재 = 9시간 16분 침묵 사례 ([issue #469](../../) 본문 참조).

**차단 동작**:
- 역할 1 분기 → `exit 0` + `_cli_end_run` 호출 (block 안 함, 정상 종료 허용).
- 역할 2 분기 → `exit 0` + `decision:"block"` JSON stdout (메인 재 발화 강제).
- 본 hook 의 차단 메커니즘 = stdout JSON 으로 CC 에 신호. stderr 는 `/tmp/dcness-hook-stderr.log` 보존 (디버그용).

**코드 SSOT**: [`harness/hooks.py`](../../harness/hooks.py) `handle_stop` + `_maybe_emit_continuation_signal`.

---

## 4. 등록 메커니즘

**[`hooks/hooks.json`](../../hooks/hooks.json)**: CC plug-in 의 hook 등록 표준 형식. event 별 matcher + 실행 스크립트 정의.

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh\"" }] }],
    "PreToolUse": [
      { "matcher": "Agent", "hooks": [...] },
      { "matcher": "Edit|Write|NotebookEdit|Read|Bash|mcp__.*", "hooks": [...] },
      { "matcher": "Edit|Write|NotebookEdit", "hooks": [...] }
    ],
    "PostToolUse": [
      { "matcher": "Agent", "hooks": [...] },
      { "matcher": "Edit|Write|NotebookEdit|Read|Bash|mcp__.*", "hooks": [...] }
    ],
    "Stop": [{ "hooks": [{ "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/stop-end-run.sh\"" }] }]
  }
}
```

**[`.claude-plugin/plugin.json`](../../.claude-plugin/plugin.json)**: plug-in 메타데이터 (`name`, `version`, `description`, `homepage`, `repository`). hook 등록은 본 파일에 없음 — `hooks/hooks.json` 가 별도 SSOT.

**자동 로딩**: CC 가 plug-in 활성 시 `hooks/hooks.json` 표준 경로를 자동 인식해 등록.

**`${CLAUDE_PLUGIN_ROOT}`**: CC 가 plug-in hook 실행 시 자동 설정하는 환경변수. plug-in 의 cache 경로 (`~/.claude/plugins/cache/dcness/dcness/<version>/`) 를 가리킴.

---

## 5. 우회 / opt-out

| 메커니즘 | 적용 범위 | 효과 |
|---|---|---|
| **미활성 프로젝트** | 자동 | `is-active` 게이트 즉시 통과 — 모든 hook no-op |
| **`.no-dcness-guard`** (cwd marker) | 임시 | file-guard 만 우회. cwd 에 빈 파일 |
| **인프라 모드** (`DCNESS_INFRA=1` 환경변수 / `~/.claude/.dcness-infra` marker / `CLAUDE_PLUGIN_ROOT` non-empty / cwd whitelist 매칭 중 1+) | 영구 | dcness 자체 작업 — `DCNESS_INFRA_PATTERNS` 해제 |

**우회 불가**:
- `--no-verify` 등 git hook bypass — [`CLAUDE.md`](../../CLAUDE.md) §2 명시 금지
- catastrophic-gate / tdd-guard 우회 marker 없음 (의도적 — 잘못된 시퀀스는 회복 비용 ↑)

---

## 6. 참조

**자연어 SSOT (본 hook 들이 강제하는 룰의 spec)**:
- [`CLAUDE.md`](../../CLAUDE.md) §0.7 — 대원칙 (강제 영역 2가지)
- 본 문서 §3.2 — catastrophic 시퀀스 진본 (catastrophic-gate 강제 대상)
- [`harness/agent_boundary.py`](../../harness/agent_boundary.py) — 권한 매트릭스 (file-guard 강제 대상)
- [`loop-procedure.md`](loop-procedure.md) — Step 0~8 mechanics (hook 시점이 절차 어디에 끼는지)

**코드 SSOT**:
- [`harness/hooks.py`](../../harness/hooks.py) — 모든 hook handler dispatch
- [`harness/session_state.py`](../../harness/session_state.py) — `is-active` 게이트 + run state machine
- [`harness/agent_boundary.py`](../../harness/agent_boundary.py) — `DCNESS_INFRA_PATTERNS` + ALLOW/READ_DENY 코드 SSOT

**등록 manifest**:
- [`hooks/hooks.json`](../../hooks/hooks.json) — hook 등록 표준 형식
- [`.claude-plugin/plugin.json`](../../.claude-plugin/plugin.json) — plug-in 메타데이터
