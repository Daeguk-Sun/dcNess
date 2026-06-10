---
name: impl
description: 구현 요청을 받아 가장 작은 안전 workflow 로 PR 까지 끝내는 기본 구현 진입점. 사용자가 "구현해줘", "수정해줘", "고쳐줘", "버그픽스", "한 줄 수정", "꼼꼼구현", "꼼꼼하게 구현", "리뷰까지 돌려", "/impl" 등을 말할 때 사용한다. 내부적으로 lane(설계도 유무 — Lite/Standard)과 엔진(풀4/경량 build-worker)을 직교로 판정하며, 사용자는 lane 별 command 를 외우지 않는다.
---

# Impl Skill — 기본 구현 진입점

> `/impl` 은 사용자-facing 구현 표면이다. lane 은 내부 routing 이며 command 로 노출하지 않는다. 기본 표면 계약은 [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md), entrypoint 판정은 [`docs/plugin/workflow-router.md`](../../docs/plugin/workflow-router.md) 가 진본이다.

> 🔴 **라우팅 SSOT** — lane 판정 / 각 lane 의 다음 호출 / retry / escalate 는 [`impl-routing.md`](impl-routing.md) 가 본 skill 의 단일 진본. 본 파일은 진행 절차만 담는다.

## 2축 모델 — lane(설계도 유무) × 엔진

`/impl` 은 설계를 하지 않는다 — 설계도(설계 문서)를 보고 **구현만** 한다. 진입은 직교 2축으로 판정한다.

**축 1 — lane = 설계도 유무**

| lane | 쓰는 경우 | 실행 |
|---|---|---|
| Lite | 설계 문서 없음 + concrete signal 충분 + high-risk 0개 + 구현 경계/테스트 기준 명확 | 메인 직접 구현 + `pr-reviewer` |
| Standard | 설계 문서(경로)가 들어옴 | 받은 설계도를 충실히 구현 (설계 생성 X) |

lane 은 진입 시 미리 고르는 게 아니라 **설계도 유무**로 갈린다 — 설계 문서 경로가 들어오면 Standard, 없으면 Lite. 설계가 없는데 메인이 "설계 필요" 로 판단하면 impl *밖*으로 되돌려(빠꾸) 설계를 산출하고, 그 경로를 들고 Standard 로 (재)진입한다. impl 은 설계를 *어떻게* 만드는지 모른다 — "설계도 있다/없다" 만 본다. 단, 사용자가 "설계 건너뛰고 빨리 고쳐" 류로 지시하면 메인의 "Standard 판단" 보다 사용자 지시가 우선이라 곧장 Lite 다.

**축 2 — 엔진 (lane 과 직교 · 4조합 모두 유효)**

| 엔진 | 시퀀스 | 언제 |
|---|---|---|
| 풀 4-agent | `test-engineer → engineer:IMPL → code-validator → pr-reviewer` | 디폴트 (엄정) |
| 경량 build-worker | build-worker 1 step (테스트·구현·자체검증) | 사용자 "빠르게/경량" 발화 또는 메인 추천 |

엔진 선택은 **사용자 우선, 미지정 시 메인 추천**이고 lane 과 직교다 — `lane × 엔진` 4조합이 모두 유효하다. lane 별로 engineer 게이트 prerequisite 충족 메커니즘이 다르다:

- **Standard + sub-agent 엔진**: 설계도(`begin-run impl --design-doc <경로>`)가 engineer 게이트 prerequisite.
- **Lite + sub-agent 엔진**: Lite 는 정의상 설계도가 없으므로 `begin-run impl --lane lite` 로 lane 을 기록해 engineer 게이트의 설계 산출물 prerequisite 를 면제한다(#714). 면제 경계는 *명시적으로 기록된* lane=lite 한정이며, 뒤따르는 `pr-reviewer ← code-validator PASS` 잔존 보호는 lane 무관하게 그대로 강제된다([`hooks.md` engineer gate](../../docs/plugin/hooks.md#catastrophic-gatesh)).

Lite 의 기본 경로는 여전히 **메인 직접 구현**이고(engineer sub-agent 미호출 → 게이트 무관), sub-agent 엔진은 사용자/메인이 명시 선택할 때의 옵션이다.

**high-risk 는 impl 밖**: 새 product feature/epic, 외부 dependency/API/SDK/model 선택, auth/security/PII/compliance, migration/destructive change, public API breakage, cross-module/cross-story interface 같은 high-risk trigger 는 impl 의 관심사가 아니다. impl 진입 *전* [`workflow-router`](../../docs/plugin/workflow-router.md) 가 이를 설계 선행(`/spec`·`/design`)으로 보내고, 설계도 확보 후 그 경로로 Standard 진입한다.

concrete signal: 파일 path, 함수/클래스/symbol, 이미 분류·승인된 issue/PR 번호, 명시 테스트 명령, 작은 docs-only 변경, 작은 refactor, 요구사항과 수용 기준이 이미 충분히 구체적인 bugfix.

## Loop

- **Lite lane — 메인 직접 (기본)**: 코드/문서 변경은 메인이 수행하고, review step 만 `begin-run impl` 안에서 `pr-reviewer` 로 기록한다. `code-validator` 는 호출하지 않는다.
- **Lite lane — sub-agent 엔진 (#714)**: 사용자/메인이 풀4·경량 엔진을 명시 선택하면 `begin-run impl --lane lite` 로 진입한다. lane=lite 기록이 engineer 게이트 설계 산출물 prerequisite 를 면제한다. 엔진 시퀀스는 Standard 와 동일(풀4: test-engineer → engineer:IMPL → code-validator → pr-reviewer / 경량: build-worker 1 step). 잔존 보호(`pr-reviewer ← code-validator PASS`)는 그대로 강제된다.
- **Standard lane — 풀 4-agent 엔진 (디폴트)**
  - **loop**: `impl-standard`
  - **entry_point**: `impl`
  - **prerequisite**: 설계 문서 경로 — `begin-run impl --design-doc <경로>` 로 기록 (engineer 게이트 prerequisite, [`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh))
  - **task_list**: test-engineer → engineer:IMPL → code-validator → pr-reviewer
  - **advance**: `TESTS_WRITTEN` → `IMPL_DONE` → `PASS` → `PASS`
  - **expected_steps**: 4
  - **routing**: [`impl-routing.md`](impl-routing.md)
- **Standard lane — 경량 build-worker 엔진**: 사용자 "빠르게/경량" 발화 또는 메인 추천 시. 동일하게 `begin-run impl --design-doc <경로>` 로 설계도를 기록한 뒤 build-worker 가 테스트·구현·자체검증을 한 step 으로 수행한다. 엔진은 lane 과 직교다.
- **high-risk → impl 밖**: high-risk trigger 가 있으면 impl 이 직접 처리하지 않는다. impl 진입 *전* 라우팅([`workflow-router`](../../docs/plugin/workflow-router.md))이 설계 선행(`/spec`·`/design`)으로 보내고, deep impl task 파일이 이미 있으면 `/impl-loop <task>` 로 위임한다.

## Step 0 — 실존 검증

추측으로 lane 을 고르지 않는다.

- GitHub issue/PR 이 입력이면 `gh issue view <N> --comments` 또는 `gh pr view <N>` 로 본문과 댓글을 확인한다.
- 파일/symbol 입력이면 `rg` / 부분 read 로 현재 상태를 확인한다.
- 선행 조건/의존 PR 이 있으면 merge 여부를 확인한다.
- 이 repo 의 실제 lint/build/test 명령과 PR helper 존재 여부를 확인한다.

GitHub issue 등록이 목표인 요청이면 `/to-issue` 로 보내고, 수정/구현이 목표인 버그 신고는 아래 lane 판정으로 처리한다.

GitHub issue 번호가 대상이면 lane 실행 전 [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#github-project-status-lifecycle)에 따라 Project `Status=In progress` 로 이동한다. Project bootstrap 이 안 되어 있으면 `/init-dcness` 의 GitHub Project lifecycle bootstrap 을 먼저 수행한다.

## Step 0.5 — 설계 산출물 유무 분기 (되돌림 1차 기준)

> impl 이 보는 **1차 분기는 "설계 문서 유무"** 다. 설계 깊이(경량/full) 판단은 impl 이 직접 하지 않고 설계 레이어로 내려보낸다. 원리 SSOT = [`workflow-router.md` 되돌림 원리](../../docs/plugin/workflow-router.md#되돌림backpressure-원리).

lane 을 고르기 전에 먼저 묻는다 — **이 작업을 닫을 설계 산출물이 이미 있는가?** (머지된 `docs/milestones/**/impl/*.md` / `docs/compact-plans/<slug>.md` / `docs/bugfix/**`).

- **있음** → **Standard**. 그 설계도를 기준으로 구현만 한다. `begin-run impl --design-doc <설계 문서 경로>` 로 산출물을 기록해 engineer 게이트 prerequisite 를 충족한다([`hooks.md` engineer gate](../../docs/plugin/hooks.md#catastrophic-gatesh)). 엔진(풀4/경량)은 직교로 별도 판정한다.
- **없음** → 메인이 "직접 고칠 수준인가 / 설계가 필요한가" 를 판단한다. 단, 사용자가 "설계 생략·빨리 고쳐" 로 지시하면 사용자 지시가 우선이라 곧장 Lite 다.
  - 직접 고칠 수준(concrete signal 충분, high-risk 0개) → **Lite** 로 직접 구현.
  - 경량 설계 필요(구현 경계·테스트 기준·작은 contract 가 애매) → 메인이 내부 [`compact-design`](../../skills/compact-design/SKILL.md) skill 을 호출해 compact plan(`docs/compact-plans/<slug>.md`)을 산출한 뒤, **그 경로를 `begin-run impl --design-doc <경로>` 로 기록하고 Standard 로 (재)진입**한다. impl 은 설계를 직접 만들지 않는다 — compact-design 은 impl 밖 호출이고, Standard 는 same-run module-architect step 없이 그 설계도를 받아 구현만 한다.
  - full 설계 필요(high-risk trigger 있음) → impl *밖*으로. `/design`(또는 PRD 부재 시 `/spec`)을 선행해 설계도를 확보한 뒤 그 경로로 Standard 진입한다.

이 되돌림은 한 번으로 끝나지 않는다. 구현 중 설계가 또 부족하면 다시 `compact-design`/`/design` 으로 되돌릴 수 있다 — 되돌림은 정상 루프다.

## Step 1 — lane 판정

판정 순서:

1. GitHub issue 초안/등록 요청인가? → `/to-issue`
2. 설계 문서(경로)가 들어왔는가? → **Standard** (받은 설계도로 구현, 엔진 직교 판정)
3. high-risk trigger 가 있는가? → impl *밖* — `/design`(또는 `/spec`) 선행으로 설계도 확보 후 Standard 재진입 (impl 진입 전 라우팅은 [`workflow-router`](../../docs/plugin/workflow-router.md))
4. 목표/범위/성공 기준이 모호한가? → 사용자에게 명확화 또는 `/spec`
5. concrete signal 이 있고 즉시 구현 경계가 명확한가? → **Lite**
6. 경량 설계 필요(구현 경계·테스트 기준 애매)? → `compact-design` 으로 되돌려 설계도 산출 후 **Standard**

메인은 사용자에게 한 줄로 echo 한다.

```
lane: Lite — 설계도 없음, concrete signal = <파일/이슈/테스트>, 엔진 = 메인 직접, 검증 gate = test + pr-reviewer
lane: Standard — 설계도 = <경로>, 엔진 = 풀4(디폴트), 검증 gate = test + code-validator + pr-reviewer
```

## Lite Lane — 꼼꼼 직접 구현 (기본)

Lite 는 `/impl-loop` 경량 모드가 아니다. impl 계획 파일 없이 메인이 직접 구현하는 single PR 경로다. 아래는 **메인 직접 구현** 기본 경로이며, sub-agent 엔진을 붙이는 변형은 바로 다음 절에서 다룬다(#714).

실행:

0. 입력 확인
   - 작업 대상이 비어 있으면 한 줄로 요구하고 멈춘다.
1. branch/worktree 격리
   - git-spec 이 있으면 [`git-spec.md`](../../docs/plugin/git-spec.md) 패턴을 따른다.
   - 사용자가 "워크트리 없이"라고 하지 않으면 worktree 격리를 기본으로 한다.
   - worktree 진입 후 Read/Edit/Write 대상은 worktree 절대경로 또는 worktree cwd 상대경로로 다시 잡는다. 진입 전에 읽은 main repo 절대경로를 그대로 Edit 하지 않는다.
2. 테스트 선작성
   - 테스트 가능한 코드 변경은 구현 전에 실패 테스트를 먼저 쓴다.
   - docs-only / 단순 설정 변경은 TDD skip 사유를 명시한다.
3. 구현
   - 메인 Claude 가 직접 Edit/Write 한다. `engineer` sub-agent 를 호출하지 않는다.
4. lint/build/test green
   - 프로젝트에 실제 존재하는 명령만 실행한다.
   - lint/build/test 단계가 없으면 skip 사유를 명시한다.
   - 하나라도 red 면 commit/PR 로 가지 않는다.
5. `pr-reviewer` review
   - `begin-run impl` → `begin-step pr-reviewer` 로 local diff 를 리뷰한다.
   - provider routing 이 `codex` 이면 기존 `dcness-codex-validator pr-reviewer` wrapper 를 사용한다. 그래도 사용자-facing 단계 이름은 `pr-reviewer` 다.
   - review-only 다. 코드 수정은 메인이 한다.
   - `PASS` 전 commit/PR 로 가지 않는다.
6. finding 수정 루프
   - 최대 3회.
   - finding 의 줄만 고치지 말고 왜 그 지적이 나왔는지 root cause 를 보고 같은 계열 결함을 함께 정리한다.
   - 각 round 마다 lint/build/test 재통과 후 `pr-reviewer` 재호출.
   - 3회 안에 수렴하지 않으면 남은 finding, follow-up 분리 후보, 보류/진행 판단 지점을 사용자에게 보고하고 멈춘다.
7. 단위 commit + PR 생성
   - 의미 있는 단위로 commit 한다. hook 우회 금지.
   - PR body 는 template, 관련 issue trailer, 배경/문제, 근본원인, 작업내용, 결정근거, Test Plan 을 포함한다.
   - dcNess plugin 배포물 변경이면 PR body 에 배포 경로 검증을 적는다.
8. CI / merge policy
   - PR 생성 후 CI 를 확인한다.
   - 머지는 host repo 정책을 따른다. dcNess self 작업은 [`CLAUDE.md`](../../CLAUDE.md) 절차에 따라 `scripts/pr-finalize.sh` 로 진행한다. 사용자 승인 대기가 정책인 repo 에서는 임의 머지하지 않는다.

메인 직접 경로에서 `code-validator` 를 호출하지 않는 이유: 검증 대상인 impl/compact 계획 파일이 없다. 최소 gate 는 테스트 선작성 또는 skip 사유, lint/build/test green, `pr-reviewer`, 단위 commit/PR, CI, false-clean 방지다.

## Lite Lane — sub-agent 엔진 (#714)

메인 직접 구현 대신 sub-agent 엔진(풀4 / 경량 build-worker)으로 Lite 를 돌리는 변형이다. 사용자가 "에이전트로/풀4로/경량 엔진으로" 류로 명시 선택하거나 메인이 추천할 때 쓴다. Lite 는 정의상 설계도가 없으므로 Standard 의 `--design-doc` 대신 **lane 기록**으로 engineer 게이트를 충족한다.

진입 시 `begin-run impl --lane lite` 로 lane 을 기록한다 — 이 기록이 engineer 게이트의 설계 산출물 prerequisite 면제 신호다([`hooks.md` engineer gate](../../docs/plugin/hooks.md#catastrophic-gatesh)). 면제 경계는 *명시적으로 기록된* lane=lite 한정이고, lane 은 `entry_point=impl` 에서만 기록되므로 design/architect-loop 의 module-architect PASS 강제는 영향받지 않는다.

- **풀 4-agent**: `test-engineer → engineer:IMPL → code-validator → pr-reviewer`. Standard 풀4 와 동일 시퀀스이며, 설계도가 없으므로 engineer/code-validator 는 이슈 본문·concrete signal·테스트 기준을 근거로 구현·검증한다.
- **경량 build-worker**: `build-worker` 1 step (테스트·구현·자체검증) 후 `pr-reviewer`.

면제는 engineer 게이트 *하나만* 푼다 — engineer 산출물 이후 `pr-reviewer ← code-validator PASS` 잔존 보호는 lane 무관하게 그대로 강제된다(풀4 경로). 변경이 작지 않거나 high-risk 가 드러나면 Lite 가 아니라 설계 선행(Standard 재진입 / impl 밖)으로 되돌린다 — lane=lite 면제를 무분별하게 넓히지 않는다.

## Standard Lane — 설계도 기반 구현

Standard 는 **설계 문서(경로)가 들어온** lane 이다. impl 은 설계를 만들지 않는다 — 받은 설계도(`docs/compact-plans/<slug>.md` / `docs/milestones/**/impl/*.md` / `docs/bugfix/**`)를 충실히 구현만 한다. 경량 설계 산출 자체는 impl 밖 내부 skill [`compact-design`](../../skills/compact-design/SKILL.md)(= `module-architect:COMPACT_PLAN` wrapper) 또는 full `/design` 이 담당하고, 그 산출물 경로가 Standard 진입의 prerequisite 다.

진입 시 `begin-run impl --design-doc <설계 문서 경로>` 로 설계도를 기록한다 — 이것이 engineer 게이트의 설계 산출물 prerequisite 증거다([`hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh)). 설계도가 (a) 이전에 머지된 설계 문서든 (b) `compact-design` 이 방금 산출한 compact plan 이든, impl 은 같은 run 에서 설계를 생성하지 않으므로 Standard 는 **항상 `--design-doc` 기록 하나로** 진입한다 (same-run module-architect step 없음).

엔진(풀4/경량)은 lane 과 직교로 별도 판정한다 — 사용자 우선, 미지정 시 메인 추천.

**풀 4-agent 엔진 (디폴트) 실행:**

1. `test-engineer`
   - 설계도의 테스트 기준을 실패 테스트로 만든다.
2. `engineer:IMPL`
   - 설계도 기준으로 구현한다.
3. `code-validator`
   - 설계도와 구현 diff 정합을 읽기 전용으로 검증한다.
4. `pr-reviewer`
   - local diff 를 리뷰한다.
5. 단위 commit + PR 생성
6. CI / merge policy

**경량 build-worker 엔진:** 사용자 "빠르게/경량" 발화 또는 메인 추천 시. 동일하게 `--design-doc` 으로 설계도를 기록한 뒤 build-worker 가 테스트·구현·자체검증을 한 step 으로 수행하고 commit + PR 로 간다.

구현 중 설계가 또 부족하면 `compact-design`/`/design` 으로 되돌려 설계도를 보강한다 — 되돌림은 정상 루프다. 새 외부 의존·high-risk 가 드러나면 impl *밖* 설계 선행으로 escalate 한다(경량 범위를 넘어섰다는 신호).

## impl 밖 — high-risk 선행 (impl 내부 lane 아님)

high-risk trigger 가 있거나 사전 설계 합의가 필요한 작업은 impl *내부 lane 이 아니다*. impl 진입 *전* 라우팅([`workflow-router`](../../docs/plugin/workflow-router.md))이 다음으로 보낸다.

- deep impl task 파일이 이미 있다 → `/impl-loop <task>` 또는 task glob 으로 위임한다.
- PRD/stories 가 없다 → `/spec` 부터 시작한다.
- PRD/stories 는 있으나 architecture/impl task 가 없다 → `/design` 으로 설계한다.
- 외부 의존 검증이 필요하면 `/tech-review` 를 선행한다.

위 경로가 설계도를 산출하면 그 경로를 들고 **Standard 로 (재)진입**한다. `/impl-loop` 는 normal implementation entrypoint 가 아니라 deep impl task 파일용 legacy/advanced runner 다.

## Review Provider

`pr-reviewer` 는 read-only validation provider routing 대상이다. 메인은 호출 직전 provider 를 resolve 한다.

```bash
PROVIDER=$("$HELPER" routing resolve pr-reviewer)
if [ "$PROVIDER" = "codex" ]; then
  "$PLUGIN_ROOT/scripts/dcness-codex-validator" pr-reviewer --prompt-file "$PROMPT_FILE"
else
  Agent(subagent_type="pr-reviewer", ...)
fi
```

Codex route 는 review provider 구현일 뿐 별도 public workflow 가 아니다.

## 종료 보고

최종 보고에는 lane, 엔진, 변경 요약, 검증 명령 결과, review round 수, PR URL 을 포함한다. 실패 시에는 남은 finding 과 다음 판단 지점을 명확히 쓴다.

## 참조

- public surface: [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
- entrypoint router: [`docs/plugin/workflow-router.md`](../../docs/plugin/workflow-router.md)
- lane routing: [`impl-routing.md`](impl-routing.md)
- branch / commit / PR: [`docs/plugin/git-spec.md`](../../docs/plugin/git-spec.md)
- compact plan template: [`agents/module-architect/templates/compact-plan.md`](../../agents/module-architect/templates/compact-plan.md)
