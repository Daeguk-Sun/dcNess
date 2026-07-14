---
name: impl
description: 구현 요청을 받아 메인이 직접 구현하고 격리 impl-validator 리뷰까지 거쳐 PR 로 끝내는 기본 구현 진입점. 사용자가 "구현해줘", "수정해줘", "고쳐줘", "버그픽스", "한 줄 수정", "리뷰까지 돌려", "/impl" 등을 말할 때 사용한다. 이슈번호/링크/파일/테스트처럼 concrete signal 이 있으면 읽고 바로 구현한다. 자연어뿐이면 GitHub issue 1개 등록 여부를 한 번 확인한다. high-risk 신호는 설계 선행 권장으로 경고하되, 사용자가 진행을 선택하면 구현한다. 일반 구현을 별도 구현 worker 로 넘기지 않는다.
---

# Impl Skill — 기본 구현 진입점

> `/impl` 은 사용자-facing 기본 구현 진입점이다. 공개 command 는 하나이고, 메인이 직접 구현한다. 격리되는 것은 `impl-validator` review step 이다. 공개 진입점 계약은 [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md), 자유 요청의 진입점 선택은 [`docs/plugin/workflow-router.md`](../../docs/plugin/workflow-router.md), 용어는 [`docs/plugin/terms.md`](../../docs/plugin/terms.md) 를 따른다.

> 🔴 **분기 규칙 SSOT** — `/impl` 내부의 issue-intake / direct / design-doc echo, retry, review provider 설명은 [`impl-routing.md`](impl-routing.md) 가 소유한다. 본 파일은 실행 절차를 담는다.

## 구현 모델 — 메인 구현 + 격리 리뷰

일반 `/impl` 구현 주체는 **항상 메인**이다. 일반 `/impl` 은 별도 구현 agent 를 구현자로 호출하지 않는다. `dcness-implementation-chain` 과 `build-worker` 는 story/epic impl task 파일을 처리하는 [`/impl-loop`](../impl-loop/SKILL.md) 영역이다.

격리되는 것은 review step 이며, `impl-validator` 는 read-only provider 분기 대상이다. 기본 review provider 는 구현자와 반대 진영이다.

- `/impl` 메인 구현(Claude) → Codex CLI 가 있으면 Codex `impl-validator`, 없으면 Claude `impl-validator` 폴백.
- `/impl-loop` build-worker 구현 → 구현 provider 의 반대 진영. codex-headless 구현이면 Claude 리뷰, claude-headless 구현이면 Codex 리뷰(불가 시 Claude).
- `routing.json` 에 명시 provider 가 있으면 override 를 존중한다.
- Codex wrapper 가 실행 중 비정상 종료해도 같은 provider 로 밀어붙이지 말고 Claude `impl-validator` 로 재시도한 뒤, 폴백 사실을 한 줄로 보고한다.

## 입력 처리

- **이슈번호/링크/파일/symbol/테스트 명령**: 실존을 확인하고 바로 구현한다.
- **설계 문서 경로**: `begin-run impl --design-doc <경로>` 로 기록하고 받은 설계도대로 구현한다. design-doc 기반 구현 — 설계도 기반 구현에서도 구현은 여전히 메인이 직접 수행하고, review 만 격리 provider 로 보낸다. 이 기록은 boundary pre-flight 와 review 근거다.
- **자연어뿐인 구현 요청**: 바로 코드를 고치지 않는다. `지금까지 이야기한 내용을 GitHub issue로 등록하고, 그 이슈 번호 기준으로 구현을 진행할까요?` 를 한 번만 묻는다. OK 면 `/to-issue` 로 이슈를 만들고 그 번호를 concrete signal 로 삼아 진행한다.
- **high-risk 신호**: 새 product feature/epic, 외부 dependency/API/SDK/model 선택, auth/security/PII/compliance, migration/destructive change, public API breakage, cross-module/cross-story interface 등은 "설계 선행을 권장"한다고 한 줄 경고한다. 사용자가 그대로 진행을 택하면 `/impl` 안에서 구현한다. LLM 판단만으로 `/spec`·`/design` 으로 되돌리지 않는다.
- **신규 시각 구조 UI 작업**: UI 기준 확보 분기에서 목업부터 만드는 것을 권장한다고 한 줄 안내한다. 내부 `canvas-design` wrapper 로 확정 목업을 만들 수 있지만, 사용자가 "그냥 가" 또는 "목업 없이"라고 하면 기존 `ux-flow` / 확정본이 있으면 참고하고, 없으면 메인이 구현한다.

UI 기준 확보 분기 echo:

```text
UI 기준: 기준 있음 — 사용자 제공 이미지·스케치·HTML 또는 기존 확정본을 구현 입력으로 사용
UI 기준: 신규 시각 구조 + 기준 없음 — 목업 선행 권장, 동의 시 canvas-design 으로 확정본 승격
UI 기준: 시각 구조 불변 — 목업 없이 구현
```

## Step 0 — 실존 검증

추측으로 시작하지 않는다.

- GitHub issue/PR 이 입력이면 `gh issue view <N> --comments` 또는 `gh pr view <N>` 로 본문과 댓글을 확인한다.
- 파일/symbol 입력이면 `rg` / 부분 read 로 현재 상태를 확인한다.
- 선행 조건/의존 PR 이 있으면 merge 여부를 확인한다.
- 이 repo 의 실제 lint/build/test 명령, PR helper, hook 존재 여부를 확인한다.
- GitHub issue 번호가 대상이면 구현 실행 전 [`issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#issuelabel-status-lifecycle)에 따라 `in-progress` label 을 붙인다. Project 좌표가 설정된 repo 에서는 Project `Status=In progress` 도 best-effort 로 미러한다.

GitHub issue 가 대상이면 이 진입 preflight 에서 한 번 읽은 본문을 run 전체의 **target GitHub issue AC** snapshot 으로 재사용한다. 각 AC 에 구현 범위와 검증 증거를 대응시키고, task/commit/validator 단계마다 issue 를 반복 조회하지 않는다. `[command]` 는 명령과 종료코드, `[agent-read]` 는 읽은 산출물·diff·계약과 관찰 사실로 판정한다. 검증 주체 표기가 없는 기존 AC 도 같은 두 부류로 분류해 다룬다. `구현이 완료된다`나 `정상 동작한다` 같은 일반론은 snapshot 에서 구체적인 관측 조건으로 교체해 구현 계약으로 쓰고, issue body 반영은 close 경계의 1회 write 에 포함한다. 구체화에 사용자 판단이 필요하면 추측하지 않는다.

## Step 0.2 — 파일 경계 override 후보 확인

구현 전 한 번 실행한다.

```bash
"$HELPER" boundary-suggestions
# 설계 문서 경로가 있으면:
"$HELPER" boundary-suggestions --impl-plan <docs/epics/.../impl/...md>
```

코어 `ALLOW_MATRIX` 로 커버되지 않는 비표준 소스 디렉터리가 있으면 `.dcness/boundary.json` 의 implementation add 후보만 출력한다. 설계 문서가 있는 design-doc 구현에서는 설계 문서의 `### 수정 허용` 경로도 같은 기준으로 대조한다. 후보가 있으면 사람 승인 후에만 메인이 boundary 파일을 작성한다.

표준 레이아웃·빈 프로젝트·이미 override 로 커버된 프로젝트는 no-op 이다. 이 pre-flight 는 `/impl-loop` 의 `begin-step build-worker` 에도 provider-independent 로 강제된다. 직접 구현은 계획 파일 없이 메인 직접 구현이므로 plan-specific boundary 대조 대상이 아니다.

## Step 0.3 — generated TDD hook 부재 확인

구현 진입 전에 project-local TDD hook 상태를 확인한다.

프로젝트 로컬 **TDD 계약**은 `.dcness/tdd-hooks.json` 이 SSOT 다. custom 플랫폼은 `test_candidate_templates` 를 포함해야 하며, 생성 전 `self-test` 로 계약을 먼저 검증한다.

```bash
"$PLUGIN_ROOT/scripts/dcness-tdd-hooks" status --project-root "$PROJECT_ROOT"
```

플랫폼 또는 project-local 계약이 있는데 generated hook 이 없으면 사용자에게 생성 제안을 보여준다. 승인 시 self-test fixture 확인 → CC hook 후보 생성/self-test/등록 → Codex hook 후보 생성/self-test/등록 순서로 진행한다.

```bash
"$PLUGIN_ROOT/scripts/dcness-tdd-hooks" ensure --project-root "$PROJECT_ROOT" --targets cc,codex --plugin-root "$PLUGIN_ROOT"
```

`status` 또는 `ensure` 가 `commit-required` 를 출력하면 생성 파일(`.dcness/tdd-hooks.json`, `.claude/settings.json`, `.claude/hooks/dcness-tdd-guard.sh`, `.codex/hooks.json`, `.codex/hooks/dcness-tdd-guard.sh`)을 bootstrap commit 에 포함해야 한다. `commit-advisory` 는 linked worktree/headless worker 체크아웃 재사용을 위해 commit 이 필요하다는 뜻이다.

## Step 1 — advisory preview echo

`impl-preview` 는 deterministic echo helper 다. 더 이상 `/spec`·`/design` 되돌림 route 를 만들지 않는다. 출력 route 는 `issue-intake`, `direct`, `design-doc` 만 사용한다. `--needs-design` / `--workflow-risk high` 는 경고 reason 으로 남기되 구현을 차단하지 않는다.

```bash
"$HELPER" impl-preview \
  [--design-doc <docs/epics/.../impl/...md>] \
  [--concrete | --natural-language-only | --ambiguous | --needs-design] \
  [--workflow-risk normal|high] \
  [--review-provider claude|codex] \
  [--skip-design]
```

메인 echo:

```text
구현 경로: issue-intake — concrete signal 없음, next = /to-issue 등록 여부 확인
구현 경로: direct — concrete signal = <파일/이슈/테스트>, 구현 = 메인 직접, review_provider = <claude|codex>
구현 경로: design-doc — 설계도 = <경로>, 구현 = 메인 직접, review_provider = <claude|codex>
권고: high-risk 신호 감지 — 설계 선행을 권장하지만 사용자가 진행하면 구현
UI 기준: 신규 시각 구조 — 목업 선행 권장, 사용자가 생략 지시하면 ux-flow 참고 후 구현
```

## Step 2 — 구현 완료조건

메인 직접 구현도 [`build-worker` 완료 기준](../../docs/plugin/agents/build-worker/build-worker-agent.md)과 같은 수준의 완료조건을 만족해야 종료한다.

- **TDD 신뢰성**: 테스트 가능한 코드 변경은 테스트를 먼저 RED 로 확인하고, 구현 후 GREEN 을 실제 실행으로 확인한다. docs-only / 단순 설정 변경은 TDD skip 사유를 남긴다.
- **자체 검증 실제 실행**: lint/build/test/typecheck/compile 게이트를 명령 실제 실행 + 종료코드로 판정한다. 코드 읽기만으로 PASS 처리하지 않는다. 실행 불가 시 `VALIDATION_BLOCKED` 로 남기고 가능한 환경에서 복원한다.
- **동작 증거**: 핵심 AC 를 mock-only green 으로 닫지 않는다. AC 성격에 맞게 정적 타입검사/compile, 실데이터 통합테스트, UI 자동화, API/CLI smoke, 실제 앱 진입점 실행 중 적절한 증거를 확보한다.
- **경계**: 변경 파일이 impl scope / 권한 경계 안에 있어야 한다.
- **커밋**: green 변경은 독립 검토 가능한 단위 commit 으로 닫는다.
- **UI**: 확정 목업이 있으면 레이아웃·상태·`design:required` 토큰 정합을 대조하고 보고한다.
- **Cartography impact**: 구현 결과에서 runtime entrypoint, capability/state owner, dependency edge, public surface, 상태 before/after와 증거, 관련 epic/decision의 변화 여부를 자유 prose로 남긴다. 영향이 없으면 `영향 없음`과 대조한 Root 좌표를 명시한다.
- **target issue AC**: 대상 GitHub issue 가 있으면 target GitHub issue AC 전항목 충족과 자동 판정 가능한 체크박스 전부 check 가 공통 종료 조건이다. 하나라도 미충족·미체크면 `require-complete` 감사가 실패하므로 clean 마감, `Closes` PR 머지, 완료 보고를 금지한다. 이 계약은 계획 파일 유무와 무관하다.

### Cartography freshness boundary

direct와 design-doc 구현 모두 메인이 작성한 Cartography impact, merge candidate diff, affected Root Cartography 좌표, 관련 epic/decision을 `impl-validator` 입력에 전달한다. `impl-validator`는 읽기 전용이므로 직접 문서를 수정하지 않으며, 메인이 prose를 읽어 다음 세 결과로 분기한다.

- **영향 없음 또는 Root와 일치**: 기존 review/PR 경로를 계속한다.
- **system boundary는 유지되지만 route/state/as-built edge가 stale**: 기존 `module-architect`를 workflow 내부 `CARTOGRAPHY_REFRESH` producer로 호출한다. affected Root 좌표만 bounded하게 갱신하고 system boundary나 impl task를 재설계하지 않는다. tracked docs는 현재 branch/PR 정책으로 반영하고, local-only/ignored 문서는 code PR에 강제 포함하지 않은 채 canonical local Root를 갱신하거나 exact affected 좌표·상태 증거를 durable impact handoff로 보존한다. durable impact handoff만으로 freshness가 해소되지는 않으며, 그 뒤 같은 merge candidate diff와 갱신된 Root를 `impl-validator`가 재검증해야 한다.
- **system boundary·global decision 변경**: route-only patch로 흡수하지 않는다. clean 진행을 멈추고 `/design --revise` 또는 system checkpoint backpressure와 영향 범위를 사용자에게 제시한다. 사용자의 구현 지시를 무시한 자동 재설계는 하지 않는다.

standalone acceptance가 생략 가능한 direct `/impl`에서는 이 `impl-validator` 종료 경계가 최소 freshness 책임이다. 미해소 route-only stale이나 system backpressure가 있으면 commit/PR clean 판정으로 진행하지 않는다.

## Step 3 — 실행 절차

1. branch/worktree 격리
   - git-spec 이 있으면 [`git-spec.md`](../../docs/plugin/git-spec.md) 패턴을 따른다.
   - 사용자가 "워크트리 없이"라고 하지 않으면 worktree 격리를 기본으로 한다.
   - worktree 진입 후 Read/Edit/Write 대상은 worktree 절대경로 또는 worktree cwd 상대경로로 다시 잡는다.
   - 종료 시 `ExitWorktree` 정리 판단은 [`loop-procedure` worktree 분기](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정)를 따른다. 커밋 diff 흡수와 clean worktree 가 모두 확인될 때만 remove/discard 하고, dirty 상태는 keep 한다.
2. 테스트 선작성
   - 테스트 가능한 코드 변경은 구현 전에 실패 테스트를 먼저 쓴다.
   - docs-only / 단순 설정 변경은 TDD skip 사유를 명시한다.
3. 구현
   - 메인이 직접 Edit/Write 한다. 별도 구현 agent 를 호출하지 않는다.
4. lint/build/test green
   - 프로젝트에 실제 존재하는 명령만 실행한다.
   - 하나라도 red 면 commit/PR 로 가지 않는다.
5. `impl-validator` review
   - `begin-run impl` 또는 `begin-run impl --design-doc <경로>` → `begin-step impl-validator` 로 merge candidate를 리뷰한다.
   - 검토 대상이 커밋으로 존재하면 커밋 id와 변경 파일 목록을 1급 입력으로 선행 전달하고, validator가 `git show` / `git diff` / `git log`로 커밋 진본을 직접 펼치게 한다. 호출자는 별도 diff 파일을 덤프하지 않는다. 커밋이 없는 uncommitted local diff일 때만 diff 파일 전달을 폴백으로 사용한다.
   - prompt에 위 리뷰 대상, 메인의 Cartography impact 자유 prose, affected Root Cartography 좌표, 관련 epic/decision을 필요한 만큼 넣는다.
   - provider 가 `codex` 이면 `dcness-codex-validator impl-validator` wrapper 를 사용한다.
   - Codex CLI 부재나 wrapper 비정상 종료 시 Claude `impl-validator` 로 폴백하고 폴백 사실을 보고한다.
   - review-only 다. 코드 수정은 메인이 한다. PASS 전 commit/PR 로 가지 않는다.
6. finding 및 Cartography freshness 수정 루프
   - 최대 3회. finding 의 줄만 고치지 말고 root cause 와 같은 계열 결함을 함께 확인한다.
   - route/state/as-built edge stale은 `module-architect:CARTOGRAPHY_REFRESH` 후 impl-validator 재검증하고, system boundary/global decision 변경은 `/design --revise` 또는 system checkpoint 사용자 backpressure에서 멈춘다.
   - producer 실행은 `begin-step module-architect CARTOGRAPHY_REFRESH`로 열고, 결과 prose를 `end-step module-architect CARTOGRAPHY_REFRESH --prose-file <cartography-refresh-prose>`로 기록한다. `PASS`이면 같은 merge candidate diff와 갱신 Root로 `begin-step impl-validator` 재검증을 열며, `SYSTEM_CHECKPOINT_REQUIRED`이면 Root patch를 적용하지 않고 backpressure에서 멈춘다.
   - 각 round 마다 lint/build/test 재통과 후 `impl-validator` 재호출.
7. 단위 commit + PR 생성
   - 의미 단위 커밋 분할은 [`git-spec.md#의미-단위-커밋-분할`](../../docs/plugin/git-spec.md#의미-단위-커밋-분할)이 SSOT 다. hook 우회 금지.
   - 독립 검토 가능한 의미 단위로 commit 을 나누고, 각 커밋은 hook 을 통과해야 한다.
   - PR body 는 template, 관련 issue trailer, 배경/문제, 근본원인, 작업내용, 결정근거, Test Plan 을 포함한다.
   - dcNess plugin 배포물 변경이면 PR body 에 배포 경로 검증을 적는다.
8. CI / merge policy
   - PR 생성 후 CI 를 확인한다.
   - CI green 과 최종 review 증거가 확정된 뒤, target issue 를 `Closes` 하는 PR 경계에서 메인이 보관한 AC 증거를 전수 대조한다. `Closes` 대상이 여러 개면 issue 별로 모두 수행한다. 자동 판정 가능한 항목을 모두 충족한 뒤 이슈 본문 체크박스 write 를 issue 별 close 경계에서 한 번 수행하고, 같은 body 를 `node "$PLUGIN_ROOT/scripts/check_issue_body.mjs" --body-file <issue-body.md> --acceptance-only --require-complete` 로 감사한다. 진행 중에는 issue mutation 을 하지 않는다.
   - 머지는 host repo 정책을 따른다. 사용자 승인 대기 정책 repo 에서는 임의 머지하지 않는다.

최소 gate 는 테스트 선작성 또는 skip 사유, lint/build/test green, 격리 `impl-validator`, 단위 commit/PR, CI, false-clean 방지다. TDD 게이트는 삭제하지 않는다.

사람이 직접 판정해야 하는 항목은 `Human verification / 사람 확인 안내`에 체크박스 없이 있어야 한다. 기존 이슈의 AC 체크박스에 사람 판정 항목이 남아 있으면 agent 가 체크하지 않는다. 자동 항목을 모두 충족·체크한 뒤 잔여 human verification 목록을 보고하고 merge 전에 정지한다. 이 상태는 구현·자동 검증 실패를 뜻하는 `blocked` 가 아니라 `human verification 대기`다.

## Sub-agent prompt 작성 checkpoint (#780)

`impl-validator` review 를 격리 provider 로 호출하면 `begin-step` stdout 의 `[PROMPT_SLOT_CHECK]` 를 prompt 작성 전에 읽는다. prompt 는 [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md) 3슬롯을 사용한다.

- **대상 + 읽을 진본**: 이슈·설계도·task 파일·merge candidate diff·Cartography impact·affected Root Cartography 좌표·관련 epic/decision 등 agent 가 자체 read 할 SSOT 포인터만 둔다.
- **리뷰 대상 전달 우선순위**: 커밋이 있으면 커밋 id와 변경 파일 목록을 선행 전달한다. diff 파일은 커밋이 없는 uncommitted local diff의 폴백으로만 전달한다.
- **worktree**: worktree 활성 시 worktree 절대경로를 넣는다.
- **이 호출 특유**: 진본에 없는 제약·신호만 둔다.
- **방법 처방 금지**: 구현 방식, 테스트 assert 방식, 알고리즘 같은 방법 처방은 넣지 않는다.

## Review Provider

`impl-validator` provider resolve 예시:

```bash
PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"
PROVIDER=$("$HELPER" routing resolve impl-validator)
if [ "$PROVIDER" = "codex" ]; then
  if command -v codex >/dev/null 2>&1; then
    "$PLUGIN_ROOT/scripts/dcness-codex-validator" impl-validator --prompt-file "$PROMPT_FILE" \
      || Agent(subagent_type="impl-validator", ...)
  else
    echo "[dcness] Codex unavailable; falling back to Claude impl-validator"
    Agent(subagent_type="impl-validator", ...)
  fi
else
  Agent(subagent_type="impl-validator", ...)
fi
```

Codex 분기는 review provider 구현일 뿐 별도 public workflow 가 아니다. Codex wrapper receipt 는 실제 provider 를 `codex-headless` 로 기록한다.

## 종료 보고

최종 보고에는 구현 경로, review provider, 변경 요약, 검증 명령 결과, review round 수, PR URL 을 포함한다. 실패 시에는 남은 finding 과 다음 판단 지점을 명확히 쓴다.

helper 기반 `begin-run impl` 이 열린 경로에서는 대표 workflow 종료 시 `"$HELPER" end-run` 으로 review.md 를 만들며, review.md 안에 CLAUDE.md/AGENTS.md 현행화 후보 read-only 섹션이 포함된다. 이 섹션은 제안만 출력하고 CLAUDE.md/AGENTS.md 를 자동 수정하지 않는다.

대표 구현 workflow 완료 후 메인이 이슈 등록, cleanup, 측정 같은 자율 작업으로 이어갈 때는 진입 전 `dcness-helper post-task-begin --reason "<사유>"` 를 호출한다. 이 marker 는 task ROI 측정 분리를 위한 #472 계약이다.

## 참조

- 용어 사전: [`docs/plugin/terms.md`](../../docs/plugin/terms.md)
- 공개 진입점: [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
- 진입점 분기 규칙: [`docs/plugin/workflow-router.md`](../../docs/plugin/workflow-router.md)
- 구현 분기 규칙: [`impl-routing.md`](impl-routing.md)
- branch / commit / PR: [`docs/plugin/git-spec.md`](../../docs/plugin/git-spec.md)
