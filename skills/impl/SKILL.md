---
name: impl
description: 구현 요청을 받아 메인이 직접 구현하고 격리 리뷰까지 거쳐 PR 로 끝내는 기본 구현 진입점. 사용자가 "구현해줘", "수정해줘", "고쳐줘", "버그픽스", "한 줄 수정", "리뷰까지 돌려", "/impl" 등을 말할 때 사용한다. 내부적으로 구현 경로(설계도 유무 — Lite/Standard)와 review provider 만 판정하며, 일반 구현을 별도 구현 worker 로 넘기지 않는다.
---

# Impl Skill — 기본 구현 진입점

> `/impl` 은 사용자-facing 구현 진입점이다. 구현 경로는 내부 분기이며 command 로 노출하지 않는다. 기본 공개 진입점 계약은 [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md), 진입점 판정은 [`docs/plugin/workflow-router.md`](../../docs/plugin/workflow-router.md) 가 진본이다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때는 [`docs/plugin/terms.md`](../../docs/plugin/terms.md) 를 확인한다.

> 🔴 **분기 규칙 SSOT** — 구현 경로 판정 / 각 경로의 다음 호출 / retry / escalate 는 [`impl-routing.md`](impl-routing.md) 가 본 skill 의 단일 진본. 본 파일은 진행 절차만 담는다.

## 구현 모델 — 메인 구현 + 격리 리뷰

`/impl` 은 설계를 하지 않는다 — 설계도(설계 문서)가 있으면 보고 구현만 하고, 없으면 concrete signal 기준으로 메인이 직접 구현한다. 일반 `/impl` 구현 주체는 **항상 메인**이다. 격리되는 것은 review step 이며, review provider 는 local routing 으로 `claude` sub-agent 또는 `codex` headless wrapper 중 하나를 쓴다.

구현 경로 = 설계도 유무:

| 구현 경로 | 쓰는 경우 | 실행 |
|---|---|---|
| Lite | 설계 문서 없음 + concrete signal 충분 + high-risk 0개 + 구현 경계/테스트 기준 명확 | 메인 직접 구현 + 격리 `impl-validator` |
| Standard | 설계 문서(경로)가 들어옴 | 메인이 받은 설계도를 충실히 구현 + 격리 `impl-validator` |

구현 경로는 진입 시 미리 고르는 게 아니라 **설계도 유무**로 갈린다 — 설계 문서 경로가 들어오면 Standard, 없으면 Lite. 설계가 없는데 메인이 "설계 필요" 로 판단하면 impl *밖*으로 되돌려(빠꾸) 설계를 산출하고, 그 경로를 들고 Standard 로 (재)진입한다. impl 은 설계를 *어떻게* 만드는지 모른다 — "설계도 있다/없다" 만 본다. 단, 사용자가 "설계 건너뛰고 빨리 고쳐" 류로 지시하면 메인의 "Standard 판단" 보다 사용자 지시가 우선이라 곧장 Lite 다.

일반 `/impl` 은 `test-engineer` / `engineer` / `build-worker` 를 구현자로 호출하지 않는다. `dcness-implementation-chain` 은 story/epic impl task 를 돌리는 `/impl-loop` headless runner 또는 사용자가 명시한 특수 실행용이다. CC 에서 `/impl` 을 호출하면 메인 Claude 가 구현하고, review provider 가 `codex` 로 설정돼 있으면 `impl-validator` 만 Codex headless 로 간다. Codex 에서 같은 흐름을 운용할 때도 구현은 현재 메인 agent 가 맡고, 상대 provider review 만 격리한다.

**high-risk 는 impl 밖**: 새 product feature/epic, 외부 dependency/API/SDK/model 선택, auth/security/PII/compliance, migration/destructive change, public API breakage, cross-module/cross-story interface 같은 high-risk trigger 는 impl 의 관심사가 아니다. impl 진입 *전* [`workflow-router`](../../docs/plugin/workflow-router.md) 가 이를 설계 선행(`/spec`·`/design`)으로 보내고, 설계도 확보 후 그 경로로 Standard 진입한다.

concrete signal: 파일 path, 함수/클래스/symbol, 이미 분류·승인된 issue/PR 번호, 명시 테스트 명령, 작은 docs-only 변경, 작은 refactor, 요구사항과 수용 기준이 이미 충분히 구체적인 bugfix.

## Loop

- **Lite 구현 경로 — 메인 직접**: 코드/문서 변경은 메인이 수행하고, review step 은 `begin-run impl` 안에서 `impl-validator` 로 기록한다. 계획 파일이 없으므로 spec 렌즈는 끄고 quality 렌즈만 본다.
- **Standard 구현 경로 — 메인 직접**: `begin-run impl --design-doc <경로>` 로 설계 문서를 기록한 뒤 메인이 구현한다. 설계 문서는 boundary pre-flight 입력과 review 근거로 쓰며, 구현 주체를 바꾸는 신호가 아니다.
- **Review**: `impl-validator` 는 read-only provider 분기 대상이다. `claude` 면 sub-agent, `codex` 면 headless wrapper 로 local diff 를 검토한다. PASS 전 commit/PR 로 가지 않는다.
- **high-risk → impl 밖**: high-risk trigger 가 있으면 impl 이 직접 처리하지 않는다. impl 진입 *전* 분기 규칙([`workflow-router`](../../docs/plugin/workflow-router.md))이 설계 선행(`/spec`·`/design`)으로 보내고, deep impl task 파일이 이미 있으면 `/impl-loop <task>` 로 위임한다.

## Step 0 — 실존 검증

추측으로 구현 경로를 고르지 않는다.

- GitHub issue/PR 이 입력이면 `gh issue view <N> --comments` 또는 `gh pr view <N>` 로 본문과 댓글을 확인한다.
- 파일/symbol 입력이면 `rg` / 부분 read 로 현재 상태를 확인한다.
- 선행 조건/의존 PR 이 있으면 merge 여부를 확인한다.
- 이 repo 의 실제 lint/build/test 명령과 PR helper 존재 여부를 확인한다.

GitHub issue 등록이 목표인 요청이면 `/to-issue` 로 보내고, 수정/구현이 목표인 버그 신고는 아래 구현 경로 판정으로 처리한다.

GitHub issue 번호가 대상이면 구현 실행 전 [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#issuelabel-status-lifecycle)에 따라 `in-progress` label 을 붙인다. Project 좌표가 설정된 repo 에서는 Project `Status=In progress` 도 best-effort 로 함께 미러된다.

## Step 0.2 — 파일 경계 override 후보 확인

구현 경로 판정 전에 한 번 실행한다.

```bash
"$HELPER" boundary-suggestions
# 설계 문서 경로가 이미 있으면:
"$HELPER" boundary-suggestions --impl-plan <docs/epics/.../impl/...md>
```

코어 `ALLOW_MATRIX` 로 커버되지 않는 비표준 소스 디렉터리가 있으면 `.dcness/boundary.json` 의 `engineer.add` 후보만 출력한다. 설계 문서가 있는 Standard 경로에서는 설계 문서의 `### 수정 허용` 경로도 같은 기준으로 대조한다. 후보가 있으면 사람 승인 후에만 메인이 boundary 파일을 작성한다. 표준 레이아웃·빈 프로젝트·이미 override 로 커버된 프로젝트는 no-op 이다.

이 pre-flight 는 `/impl-loop` 같은 deep task runner 가 `begin-step engineer/build-worker` 를 여는 경우에도 provider-independent 로 강제된다. Standard run 의 `--design-doc` 이 가리키는 impl 문서 안 `### 수정 허용` 경로가 `ALLOW_MATRIX ∪ .dcness/boundary.json` 으로 커버되지 않으면 구현 step 시작이 차단된다. Lite 기본 경로는 계획 파일 없이 메인 직접 구현이므로 plan-specific boundary 대조 대상이 아니다.

## Step 0.3 — generated TDD hook 부재 확인

구현 진입 전에 project-local TDD hook 상태를 한 번 확인한다. dcNess 는 **TDD 계약**과 생성 직후 **self-test** 를 소유하고, hook 본문은 현재 helper 의 플랫폼 프리셋(`python`, `web`, `go`, `android`, `ios`) 또는 사람 승인된 `.dcness/tdd-hooks.json` 계약(`source_roots`, `impl_exts`, custom 플랫폼의 `test_candidate_templates`, 선택 `test_file_globs`)에 맞게 생성된다.

```bash
"$PLUGIN_ROOT/scripts/dcness-tdd-hooks" status --project-root "$PROJECT_ROOT"
```

플랫폼이 감지됐거나 project-local 계약이 있는데 generated hook 이 없으면 사용자에게 생성 제안을 보여준다. 미지원 플랫폼에서 새 규칙이 필요하면 구현 에이전트가 `.dcness/tdd-hooks.json` 초안을 만들 수 있지만, 사람 승인 뒤에만 `ensure` 를 실행한다. 승인 시 `/init-dcness` 와 같은 순서로 진행한다: TDD 계약 self-test fixture 확인 → CC hook 후보 생성/self-test/등록 → Codex hook 후보 생성/self-test/등록.

```bash
"$PLUGIN_ROOT/scripts/dcness-tdd-hooks" ensure --project-root "$PROJECT_ROOT" --targets cc,codex --plugin-root "$PLUGIN_ROOT"
```

빈 프로젝트와 미지원 플랫폼은 no-op 으로 안전 통과한다. 플랫폼 또는 project-local 계약이 감지된 프로젝트에서 generated hook 이 없거나 생성/self-test 가 실패하면 구현 진입 전 사용자 위임으로 멈춘다. 생성 훅이 있으면 중앙 `tdd-guard.sh` 와 headless worker 사후 검사는 그 generated hook 을 먼저 실행한다.

`status` 또는 `ensure` 가 `commit-required` 를 출력하면 생성 파일(`.dcness/tdd-hooks.json`, `.claude/settings.json`, `.claude/hooks/dcness-tdd-guard.sh`, `.codex/hooks.json`, `.codex/hooks/dcness-tdd-guard.sh`)을 bootstrap commit 에 포함해야 한다. `commit-advisory` 는 현재 in-place 실행에서는 디스크 실존·등록만으로 guard 배선을 확인할 수 있지만, 새 linked worktree/headless worker 체크아웃에서 project-local TDD 계약을 재사용하려면 commit 이 필요하다는 뜻이다.

## Step 0.4 — UI 기준 확보 분기

UI 작업이면 구현 경로(Lite/Standard) 판정과 별도로 **UI 기준 확보 분기**를 먼저 판정한다. 목업은 무조건 만들지 않는다. 강제되는 불변식은 "신규 시각 구조 작업은 기대 고정 기준을 확보하고, 기준이 존재하면 구현까지 배선된다" 이다.

사용자의 "목업 없이" 지시는 항상 우선한다.

| 분기 | 조건 | 행동 |
|---|---|---|
| 기준 있음 | 사용자 제공 이미지·스케치·HTML, 기존 확정본 `docs/design-variants/<screen-id>.html`, 이전에 PICK 된 화면 기준이 있음 | 내부 [`canvas-design`](../canvas-design/SKILL.md) 을 호출해 승격·참조 상태를 확인하고 확정 목업 경로 + 핵심 node-id 매핑을 구현 입력에 싣는다 |
| 신규 시각 구조 + 기준 없음 | 새 화면/큰 레이아웃 변경/상태 구조 변경인데 기준이 없음 | 내부 [`canvas-design`](../canvas-design/SKILL.md) 이 designer draft 생성 → 사용자 PICK → 확정본 승격 → `canvas.html` frame 등록을 수행한다 |
| 시각 구조 불변 | 문구, 데이터 wiring, 접근성 속성, 작은 스타일 조정처럼 기존 시각 구조가 그대로거나 사용자가 "목업 없이" 지시 | 목업 없이 구현한다. 기존 디자인 참조가 있으면 읽되 새 draft/승격은 하지 않는다 |

메인은 판정 결과를 한 줄로 echo 한다.

```text
UI 기준: 기준 있음 — <사용자 제공 이미지|스케치|기존 확정본> → docs/design-variants/<screen-id>.html, 구현 입력에 node-id 매핑 포함
UI 기준: 신규 시각 구조 + 기준 없음 — canvas-design 으로 draft/PICK/확정본 승격 후 구현
UI 기준: 시각 구조 불변 — 목업 없이 구현
```

`canvas-design` 이 반환한 확정 목업 경로는 impl task 의 `## 디자인 참조` 섹션에 기록한다. `design: required` 는 UI 감지 신호이며, `design: optional` 이라도 신규 시각 구조면 이 분기를 탄다. 단, 시각 구조 불변이면 `design: optional` + `해당 없음` 으로 남길 수 있다.

## Step 0.5 — 설계 산출물 유무 분기 (되돌림 1차 기준)

> impl 이 보는 **1차 분기는 "설계 문서 유무"** 다. 설계 깊이(경량/full) 판단은 impl 이 직접 하지 않고 설계 레이어로 내려보낸다. 원리 SSOT = [`workflow-router.md` 되돌림 원리](../../docs/plugin/workflow-router.md#되돌림backpressure-원리).

구현 경로를 고르기 전에 먼저 묻는다 — **이 작업을 닫을 설계 산출물이 이미 있는가?** (머지된 `docs/epics/**/impl/*.md`).

- **있음** → **Standard**. 그 설계도를 기준으로 메인이 구현한다. `begin-run impl --design-doc <설계 문서 경로>` 로 산출물을 기록해 boundary pre-flight 와 review 근거로 사용한다.
- **없음** → 메인이 "직접 고칠 수준인가 / 설계가 필요한가" 를 판단한다. 단, 사용자가 "설계 생략·빨리 고쳐" 로 지시하면 사용자 지시가 우선이라 곧장 Lite 다.
  - 직접 고칠 수준(concrete signal 충분, high-risk 0개) → **Lite** 로 직접 구현.
  - 설계 필요(구현 경계·테스트 기준·작은 contract 가 애매) → impl *밖*으로. `/design` 을 선행해 설계도를 확보한 뒤 그 경로로 Standard 진입한다. impl 은 설계를 직접 만들지 않는다.
  - full 설계 필요(high-risk trigger 있음) → impl *밖*으로. `/design`(또는 PRD 부재 시 `/spec`)을 선행해 설계도를 확보한 뒤 그 경로로 Standard 진입한다.

이 되돌림은 한 번으로 끝나지 않는다. 구현 중 설계가 또 부족하면 다시 `/design` 으로 되돌릴 수 있다 — 되돌림은 정상 루프다.

## Step 1 — 구현 경로 판정

메인이 실존 검증으로 얻은 신호를 먼저 정규화한 뒤, 결정론 preview 를 실행한다. 자연어 해석(모호함/설계 필요/high-risk 여부)은 메인이 책임지고, route/begin-run/review provider 후보 산출은 helper 에 맡긴다.

```bash
"$HELPER" impl-preview \
  [--design-doc <docs/epics/.../impl/...md>] \
  [--concrete | --natural-language-only | --ambiguous | --needs-design] \
  [--workflow-risk normal|high] \
  [--review-provider claude|codex] \
  [--skip-design]
```

출력의 `route`, `begin-run`, `implementation_owner`, `review_provider`, `reasons` 를 판정 echo 의 근거로 사용한다. 모호한 신호를 helper 플래그로 숨기지 않는다 — 먼저 사용자 확인, issue intake, 또는 `/spec` 로 보낸다.

`route=issue-intake` 이면 바로 구현하지 않는다. 사용자에게 먼저 묻는다.

```text
지금까지 이야기한 내용을 GitHub issue로 등록하고, 그 이슈 번호 기준으로 구현을 진행할까요?
```

사용자가 OK 하면 `/to-issue` 를 호출해 issue 를 생성하고, 생성된 issue 번호를 concrete signal 로 삼아 `/impl #<issue>` 와 같은 흐름으로 재진입한다. 이 issue 본문은 간단한 설계도, AC, 히스토리 기준 역할을 하므로 자연어-only 요청을 바로 코드 수정으로 밀지 않는다. 사용자가 issue 생성을 거부하면 빠진 파일/범위/AC를 짧게 확인하거나, 사용자가 명시적으로 "이슈 없이 진행"을 선택했을 때만 Lite 로 진행한다.

판정 순서:

1. GitHub issue 초안/등록 요청인가? → `/to-issue`
2. UI 작업인가? → **UI 기준 확보 분기** echo. 기준이 필요하면 `canvas-design` 으로 확정 목업 경로를 확보한다. 사용자의 "목업 없이" 는 우선한다.
3. 설계 문서(경로)가 들어왔는가? → **Standard** (받은 설계도로 메인이 구현)
4. high-risk trigger 가 있는가? → impl *밖* — `/design`(또는 `/spec`) 선행으로 설계도 확보 후 Standard 재진입 (impl 진입 전 분기 규칙은 [`workflow-router`](../../docs/plugin/workflow-router.md))
5. concrete signal 없이 자연어뿐인가? → **issue-intake**. `/to-issue` 로 이슈 등록 후 그 번호 기준으로 진행할지 묻는다.
6. 목표/범위/성공 기준이 모호한가? → issue intake, 사용자 명확화, 또는 `/spec`
7. concrete signal 이 있고 즉시 구현 경계가 명확한가? → **Lite**
8. 설계 필요(구현 경계·테스트 기준 애매)? → `/design` 으로 되돌려 설계도 산출 후 **Standard**

메인은 사용자에게 한 줄로 echo 한다.

```
구현 경로: issue-intake — concrete signal 없음, next = /to-issue 등록 여부 확인
구현 경로: Lite — 설계도 없음, concrete signal = <파일/이슈/테스트>, 구현 = 메인 직접, review_provider = <claude|codex>
구현 경로: Standard — 설계도 = <경로>, 구현 = 메인 직접, review_provider = <claude|codex>
```

## Sub-agent prompt 작성 checkpoint (#780)

`impl-validator` review 를 격리 provider 로 호출하면 `begin-step` stdout 의 `[PROMPT_SLOT_CHECK]` 를 prompt 작성 전에 읽는다. prompt 는 [`agent-prompt-slots.md`](../../docs/plugin/templates/agent-prompt-slots.md) 3슬롯을 사용한다.

- **대상 + 읽을 진본**: 이슈·설계도·task 파일·diff 등 agent 가 자체 read 할 SSOT 포인터만 둔다. 이미 진본에 있는 수용 기준·인터페이스·구현 결정을 prompt 에 재나열하지 않는다.
- **worktree**: worktree 활성 시 worktree 절대경로를 넣는다. main repo 절대경로를 worktree 경로처럼 넘기지 않는다.
- **이 호출 특유**: 진본에 없는 제약·신호만 둔다. 정규식·구현 단계·알고리즘·테스트 assert 방식 같은 방법 처방은 넣지 않는다.

## Lite 구현 경로 — 메인 직접 구현 (기본)

Lite 는 `/impl-loop` 경량 모드가 아니다. impl 계획 파일 없이 메인이 직접 구현하는 single PR 경로다.

실행:

0. 입력 확인
   - 작업 대상이 비어 있으면 한 줄로 요구하고 멈춘다.
1. branch/worktree 격리
   - git-spec 이 있으면 [`git-spec.md`](../../docs/plugin/git-spec.md) 패턴을 따른다.
   - 사용자가 "워크트리 없이"라고 하지 않으면 worktree 격리를 기본으로 한다.
   - worktree 진입 후 Read/Edit/Write 대상은 worktree 절대경로 또는 worktree cwd 상대경로로 다시 잡는다. 진입 전에 읽은 main repo 절대경로를 그대로 Edit 하지 않는다.
   - 종료 시 `ExitWorktree` 정리 판단은 [`loop-procedure` worktree 분기](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정) 를 따른다.
2. 테스트 선작성
   - 테스트 가능한 코드 변경은 구현 전에 실패 테스트를 먼저 쓴다.
   - docs-only / 단순 설정 변경은 TDD skip 사유를 명시한다.
3. 구현
   - 메인 Claude 가 직접 Edit/Write 한다. `engineer` sub-agent 를 호출하지 않는다.
4. lint/build/test green
   - 프로젝트에 실제 존재하는 명령만 실행한다.
   - lint/build/test 단계가 없으면 skip 사유를 명시한다.
   - 하나라도 red 면 commit/PR 로 가지 않는다.
5. `impl-validator` review
   - `begin-run impl` → `begin-step impl-validator` 로 local diff 를 리뷰한다.
   - provider 분기가 `codex` 이면 기존 `dcness-codex-validator impl-validator` wrapper 를 사용한다. 그래도 사용자-facing 단계 이름은 `impl-validator` 다.
   - Lite 는 quality 렌즈만, Standard 는 spec 렌즈 + quality 렌즈를 모두 사용한다.
   - review-only 다. 코드 수정은 메인이 한다.
   - `PASS` 전 commit/PR 로 가지 않는다.
6. finding 수정 루프
   - 최대 3회.
   - finding 의 줄만 고치지 말고 왜 그 지적이 나왔는지 root cause 를 보고 같은 계열 결함을 함께 정리한다.
   - 각 round 마다 lint/build/test 재통과 후 `impl-validator` 재호출.
   - 3회 안에 수렴하지 않으면 남은 finding, follow-up 분리 후보, 보류/진행 판단 지점을 사용자에게 보고하고 멈춘다.
7. 단위 commit + PR 생성
   - 의미 있는 단위로 commit 한다. hook 우회 금지.
   - 변경량이 크면 리뷰어가 단계별로 따라갈 수 있게 테스트/결정적 helper/문서 surface/후속 cleanup 처럼 독립적으로 검토 가능한 커밋으로 쪼갠다. 단, 각 커밋은 hook 을 통과할 수 있는 일관된 상태여야 한다.
   - PR body 는 template, 관련 issue trailer, 배경/문제, 근본원인, 작업내용, 결정근거, Test Plan 을 포함한다.
   - dcNess plugin 배포물 변경이면 PR body 에 배포 경로 검증을 적는다.
8. CI / merge policy
   - PR 생성 후 CI 를 확인한다.
   - 머지는 host repo 정책을 따른다. dcNess self 작업은 [`CLAUDE.md`](../../CLAUDE.md) 절차에 따라 `scripts/pr-finalize.sh` 로 진행한다. 사용자 승인 대기가 정책인 repo 에서는 임의 머지하지 않는다.

메인 직접 경로에서도 `impl-validator` 를 호출한다. Lite 는 검증 대상 impl 계획 파일이 없으므로 spec 렌즈를 비활성화하고 quality 렌즈만 적용한다. 최소 gate 는 테스트 선작성 또는 skip 사유, lint/build/test green, `impl-validator`, 단위 commit/PR, CI, false-clean 방지다.

## Standard 구현 경로 — 설계도 기반 구현

Standard 는 **설계 문서(경로)가 들어온** 구현 경로다. impl 은 설계를 만들지 않는다 — 받은 설계도(`docs/epics/**/impl/*.md`)를 충실히 구현만 한다. 설계 산출 자체는 impl 밖 `/design` 이 담당하고, 그 산출물 경로가 Standard 진입의 사전 조건이다.

진입 시 `begin-run impl --design-doc <설계 문서 경로>` 로 설계도를 기록한다. impl 은 같은 run 에서 설계를 생성하지 않으므로 Standard 는 **항상 `--design-doc` 기록 하나로** 진입한다 (same-run module-architect step 없음). 이 경로가 기록되면 begin-step 게이트가 `### 수정 허용` boundary 대조도 자동 수행한다. 구현은 여전히 메인이 직접 수행하고, review 만 격리 provider 로 보낸다.

구현 중 설계가 또 부족하면 `/design` 으로 되돌려 설계도를 보강한다 — 되돌림은 정상 루프다. 새 외부 의존·high-risk 가 드러나면 impl *밖* 설계 선행으로 escalate 한다.

## impl 밖 — high-risk 선행 (impl 내부 구현 경로 아님)

high-risk trigger 가 있거나 사전 설계 합의가 필요한 작업은 impl *내부 구현 경로가 아니다*. impl 진입 *전* 분기 규칙([`workflow-router`](../../docs/plugin/workflow-router.md))이 다음으로 보낸다.

- deep impl task 파일이 이미 있다 → `/impl-loop <task>` 또는 task glob 으로 위임한다.
- PRD/stories 가 없다 → `/spec` 부터 시작한다.
- PRD/stories 는 있으나 architecture/impl task 가 없다 → `/design` 으로 설계한다.
- 외부 의존 검증이 필요하면 `/tech-review` 를 선행한다.

위 경로가 설계도를 산출하면 그 경로를 들고 **Standard 로 (재)진입**한다. `/impl-loop` 는 일반 구현 진입점이 아니라 story/epic impl task 파일용 headless runner 다.

## Review Provider

`impl-validator` 는 read-only validation provider 분기 대상이다. 메인은 호출 직전 provider 를 resolve 한다.

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
  "$PLUGIN_ROOT/scripts/dcness-codex-validator" impl-validator --prompt-file "$PROMPT_FILE"
else
  Agent(subagent_type="impl-validator", ...)
fi
```

Codex 분기는 review provider 구현일 뿐 별도 public workflow 가 아니다. Codex wrapper 가 저장하는 receipt 는 실제 provider 를 `codex-headless` 로 기록한다.

## 종료 보고

최종 보고에는 구현 경로, review provider, 변경 요약, 검증 명령 결과, review round 수, PR URL 을 포함한다. 실패 시에는 남은 finding 과 다음 판단 지점을 명확히 쓴다.

helper 기반 `begin-run impl` 이 열린 경로에서는 대표 workflow 종료 시 `"$HELPER" end-run` 으로 review.md 를 만들며, review.md 안에 CLAUDE.md/AGENTS.md 현행화 후보 read-only 섹션이 포함된다. 이 섹션은 제안만 출력하고 CLAUDE.md/AGENTS.md 를 자동 수정하지 않는다.

## 참조

- 용어 사전: [`docs/plugin/terms.md`](../../docs/plugin/terms.md)
- 공개 진입점: [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
- 진입점 분기 규칙: [`docs/plugin/workflow-router.md`](../../docs/plugin/workflow-router.md)
- 구현 경로 분기 규칙: [`impl-routing.md`](impl-routing.md)
- branch / commit / PR: [`docs/plugin/git-spec.md`](../../docs/plugin/git-spec.md)
