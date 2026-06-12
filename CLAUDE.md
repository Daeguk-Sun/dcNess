# CLAUDE.md — dcNess 프로젝트 작업 지침

> 본 파일은 메인 Claude (Claude Code) 가 dcNess 저장소에서 작업할 때의 지침이다. 작업 규칙 SSOT.
> 🔴 **세션 시작 시 즉시 인지**: 아래 **사용자 정체성** + **[프로젝트 정체성](#프로젝트-정체성)** — 두 영역만 무조건 머리에 박고 시작. 그 외 문서는 lazy 참조.

## 🔴 사용자 정체성 (모든 응답의 최우선 기준)

사용자는 한국어가 가장 익숙한 시니어 엔지니어이기 때문에 자연스러운 한국 표준어로 대화하는것에 익숙하다.

맥락없이 말하는 것을 싫어하므로 생략해서 말하거나 대명사를 이용하여 불 명확하게 말하지 말도록 한다. 결론부터 말하고 부가적인 설명을 덧붙이는 대화를 선호한다.

꼭 직접 확인해야 직성이 풀리는 성격이기에 문서·파일·링크는 사용자가 한번에 열어볼 수 있도록 백틱 / 클릭 가능한 형태로 표기한다.

## 프로젝트 정체성

> 🔴 **메인 Claude 가 자주 까먹는 핵심 — 매번 작업 전 반드시 인지**

### 본 프로젝트 = 하네스 인프라 (plug-in 배포물)

- 본 프로젝트(dcness)는 **Claude Code 용 plug-in 으로 배포**된다.
- 사용자(외부 프로젝트)는 **`/init-dcness` 스킬을 통해 활성화**한다.
- 본 프로젝트에 추가하는 모든 기능은 **dcness 자체를 위한 것이 아니라**, **활성화한 외부 프로젝트에 적용되기 위한 것**이다.
- 따라서 "이 프로젝트에서 잘 작동하는가" 가 아니라 **"활성화한 외부 프로젝트에서 잘 작동하는가"** 가 기준.

### dcness 자체는 init-dcness 미적용 — 자기 규격 미얽매임

- 본 dcness 저장소는 자기 자신에 `/init-dcness` 를 실행하지 **않는다**.
- 따라서 dcness plug-in 의 규격(`stories.md` 강제 / `issue-lifecycle.md` 이슈 계층 흐름 / `/spec` 시퀀스 등) 에 **얽매이지 않는다**.
- dcness 자체의 작업은 다음 3개만 따른다:
  - 본 `CLAUDE.md` (작업 절차 + 게이트)
  - `docs/plugin/git-spec.md` (브랜치·커밋·PR 네이밍)
  - GitHub 이슈 (필요 시 자유 형식, 메타-스토리·stories.md 불필요)
- **헷갈리지 마라**: plug-in 규격은 *외부 활성화 프로젝트* 용이지, dcness 자기 자신용이 아니다.

### 내부 ID 를 외부 배포물에 포함하지 마라

- **외부에 배포되는 파일** (= plug-in 사용자가 보게 되는 파일: `agents/**`, `commands/**`, `hooks/**`, 그리고 plug-in 사용자가 따라야 하는 SSOT 인 `docs/plugin/issue-lifecycle.md` 등) 안에는 **내부 ID / 내부 추적 표현을 본문으로 포함하지 않는다**.
- 외부 사용자에게 내부 추적용 표현은 **잡음**이다. 그 변경 이유 / 작동 룰만 자연어로 설명하면 충분.

### 추가한 기능은 반드시 배포 경로에도 포함

- 본 저장소(dcness self) 에만 추가하면 **외부 활성화 프로젝트에서는 작동하지 않는다** — 과거 사례: 기능을 dcness 자체에 추가했는데 정작 설치한 외부 프로젝트(jajang)는 그 기능이 없어 작동 안 함.
- 모든 기능 추가 작업은 **배포 경로 검증 의무** 가 동반된다. 다음 중 *해당하는 모든 경로* 가 갱신돼야 작업 완료:
  1. **plug-in 본체 파일** (`agents/**`, `commands/**`, `hooks/**`) — 사용자가 plug-in 업데이트 시 자동 적용. 본 저장소의 같은 경로에 변경 = plug-in 도 자동 갱신 (단 사용자가 plug-in 버전 업 받은 후).
  2. **`/init-dcness` 스킬이 사용자 프로젝트로 *복사·배포* 하는 파일** (예: `scripts/check_*.mjs`, `scripts/hooks/commit-msg`, `.github/workflows/*.yml`) — 본 저장소에만 추가하면 신규 프로젝트는 받지만 *기존 활성화 프로젝트* 는 못 받음. **`commands/init-dcness.md` 의 deploy 스텝에 반드시 추가** + 기존 사용자가 재배포받을 방법 고지.
  3. **사용자가 따라야 하는 SSOT 문서** (예: `docs/plugin/issue-lifecycle.md`, `docs/plugin/git-spec.md` 중 사용자용 부분) — 본 저장소 docs 만 갱신하면 사용자는 못 봄. plug-in 배포물 쪽으로 옮기거나 init-dcness 가 복사하도록 처리.
- 기능 추가 PR 본문에 **"배포 경로 검증"** 항목 명시 — 어떤 경로(1/2/3) 로 사용자 환경에 도달하는지, 누락 없는지.
- **검증 안 된 변경은 dcness 자체에서만 작동하는 환상**. 사용자에게 안 닿으면 기능 추가 의미 없음.

---

### 작업 모드

- **메인 Claude 직접 작업** — architect / code-validator / engineer 위임 강제 **없음**.
- **Document Sync 거버넌스만 강제** — 외부 배포 경로([추가한 기능은 반드시 배포 경로에도 포함](#추가한-기능은-반드시-배포-경로에도-포함)) 정합 검증은 필수.

### dcness 강제 원칙 (룰 추가·설계 시 가드레일)

> 🟢 **설계 원칙 (왜 강제를 최소화하나)** — dcNess 는 모델을 불신해 가두는 하네스가 아니라, 사용자의 작업 방식을 보존하는 하네스다. 모델이 좋아질수록 절차를 *없애는* 게 아니라, 절차의 *목적*을 이해하고 더 적은 마찰로 지키게 한다. harness 의 일은 모델의 사고를 대신하는 게 아니라, 모델이 놓치기 쉬운 **되돌릴 수 없는 경계(irreversible boundary)** 만 붙잡는 것. 그래서 기본 경로는 가볍고, 무거운 절차(spec / tech-review / design / consensus)는 항상 켜두지 않고 **위험할 때만 올린다** (구현 경로 판정 SSOT = [`docs/plugin/workflow-router.md`](docs/plugin/workflow-router.md), 용어 기준 = [`docs/plugin/terms.md`](docs/plugin/terms.md)). 설계 원칙 출처: [#591](https://github.com/alruminum/dcNess/issues/591).

> 🔴 **대 원칙** (외부 활성 프로젝트엔 hook 이 그 자리에서 강제 — SessionStart 는 슬림 활성 안내만 inject, 설계 원칙 전문은 본 SSOT):
> **harness 가 강제하는 것은 단 2가지 — (1) 작업 순서, (2) 접근 영역. 그 외 모두 agent 자율.**
> - **작업 순서** = 시퀀스 (code-validator → engineer → pr-reviewer 등) + retry 정책
> - **접근 영역** = file path 경계 (agent-boundary ALLOW/READ_DENY) + 외부 상태 변경 차단 (push, gh issue, plugin 디렉토리)
> - **출력 형식 / handoff 형식 / preamble / marker / status JSON / Flag = agent 자율, harness 강제 X.**

**강제 vs 자율 vs 권고**:
- **강제 (코드)**: 순서 차단 훅의 작업 순서 보호 ([`docs/plugin/hooks.md`](docs/plugin/hooks.md#catastrophic-gatesh)) + 권한 경계 ([`harness/agent_boundary.py`](harness/agent_boundary.py)). escalate 결론 자동 복구 금지.
- **자율 (agent)**: prose 형식 / handoff 페이로드 / preamble / 도구 순서 (권한 안).
- **권고 (강제 X)**: 분기 규칙 (각 skill `<skill>-routing.md` — 예: [`skills/impl-loop/impl-loop-routing.md`](skills/impl-loop/impl-loop-routing.md)) / retry 한도 — 측정 + 사용자 개입.

**안티패턴 (룰 추가 시 피하기)**:
1. **룰이 룰을 부르는 reactive cycle** — 신규 룰 추가 전 기존 룰 제거 가능성 먼저 검토. 추가→제거 비대칭이 기술 부채.
2. **강제 vs 권고 혼동** — 강제(block) = 중대 차단만. 권고(warn) = 형식 위반/비용 폭증 등은 측정+경고+사용자 개입. 권고 → 강제 자동 승격 금지.
3. **에이전트 자율성 침해** — agent prompt 안 강제 형식 박기 금지. 결론+이유 명확히 쓰도록 가이드만 (형식이 아니라 의미).
4. **불필요한 흐름 강제** — 작업 순서 보호만 중대 차단이다. 시퀀스 내부 행동 = 에이전트 자율.
5. **신규 공개 진입점 무근거 추가** — 새 skill/command/agent/gate 를 추가하기 *전*, 왜 기존 위험 분기([`workflow-router.md`](docs/plugin/workflow-router.md)) 구현 경로 + validator/reviewer + 공개 진입점 계약([`positioning.md`](docs/plugin/positioning.md))으로 부족한지 먼저 설명한다. 사용자-facing 공개 노출 범위는 작게 유지가 기본 — 추가는 justification 동반 (안티패턴 1 reactive cycle 과 한 쌍, 설계 원칙의 "외부 UX 는 단순하게" 취지).

## 작업 절차 (모든 변경 공통)

1. **수정 작업**.
2. **commit 직전**: git pre-commit hook 자동 게이트 (main-block + pytest).
3. **branch → PR → regular merge** (직접 `main` push 금지). CI PASS 후 메인이 즉시 머지 — *사용자 수동 승인 대기 X*.
4. **종료 시 ExitWorktree** — squash 흡수 검사 후 자동 `keep`/`remove` ([`docs/plugin/loop-procedure.md` worktree 분기](docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정)).

## 게이트 요약

- **main-block**: `scripts/hooks/pre-commit` — main 직접 commit 차단
- **git-naming**: `scripts/hooks/commit-msg` (로컬) + `git-naming-validation.yml` (CI) — 브랜치·커밋·PR 제목 형식 강제
- **pytest**: `scripts/check_python_tests.sh` — harness/tests/agents 변경 시만
- **plugin-manifest**: `scripts/check_plugin_manifest.mjs` (CI `plugin-manifest.yml`) — `.claude-plugin/plugin.json` version / manifest 정합 검증
- **pr-body**: `scripts/check_pr_body.mjs` (CI `pr-body-validation.yml`) — PR 본문 템플릿 충족 검증
- **public-surface**: `scripts/check_public_surface.mjs` (CI `public-surface-validation.yml`) — 공개 workflow/command/agent 진입점 계약 검증
- **cross-ref**: `scripts/check_cross_refs.mjs` (CI `cross-ref-validation.yml`) — markdown link 파일/anchor 실존 + 옛 명칭 deny-list (외부 배포 영역 한정) 회귀 차단
- **행동 eval (권고 — CI 차단 아님)**: `bash evals/run.sh` — `agents/**`/`skills/**` 지침 변경 PR 머지 전 + 플러그인 릴리즈 전 1회. agent 가 기준대로 실제 판정하는지 사고 기반 fixture 로 확인. 상세 [`evals/README.md`](evals/README.md)

> ⚠️ **금지**: `--no-verify` 등 hook 우회. main 직접 push.

## 문서 지도




### 작업 시 읽기 (lazy — 해당 작업 직전에만)

| 파일 | 언제 읽나 |
|---|---|
| [`docs/plugin/terms.md`](docs/plugin/terms.md) | 용어·공개 진입점·분기 표현·사용자 표시 메시지 수정/리뷰 시 |
| [`docs/plugin/positioning.md`](docs/plugin/positioning.md) | 공개 workflow 진입점의 기본/고급/유틸리티/내부 agent 분류 수정 시 |
| [`docs/plugin/workflow-router.md`](docs/plugin/workflow-router.md) | 자유 형식 작업 요청을 어떤 workflow 로 보낼지 (구현 경로 — gate 축 × shape 축) 판단 시 |
| [`docs/plugin/git-spec.md`](docs/plugin/git-spec.md) | 브랜치·커밋·PR 네이밍 규칙 SSOT — 모든 커밋 작업에 적용 |
| 각 skill 의 `<skill>-routing.md` ([`impl`](skills/impl/impl-routing.md) / [`design`](skills/design/design-routing.md) / [`impl-loop`](skills/impl-loop/impl-loop-routing.md) 등) | 분기 규칙 진본 (mermaid + enum 표) + retry 한도 + escalate — agent 결론 → 다음 호출 매핑 수정 시 |
| [`scripts/check_public_surface.mjs`](scripts/check_public_surface.mjs) | 공개 workflow 진입점 gate 기대값 수정 시 |
| [`docs/plugin/loop-procedure.md`](docs/plugin/loop-procedure.md) | Step 0~8 mechanics (begin-run → begin-step → Agent → end-step → finalize-run) 수정 시 |
| [`docs/plugin/hooks.md`](docs/plugin/hooks.md) | hook 시스템 (SessionStart / PreToolUse / PostToolUse / SubagentStop / Stop = 8 hook) 수정 시 SSOT. dcness self 작업용 `scripts/hooks/cc-pre-commit.sh` 는 별 항목 |
| [`docs/plugin/issue-lifecycle.md`](docs/plugin/issue-lifecycle.md) | 외부 활성 프로젝트의 epic / story / impl 흐름 변경 시 SSOT (본 저장소 자체엔 미적용 — [dcness 자체는 init-dcness 미적용](#dcness-자체는-init-dcness-미적용-자기-규격-미얽매임) 참조) |
| [`PROGRESS.md`](PROGRESS.md) | 현재 상태·TODO·Blockers 확인 시 |
| [`AGENTS.md`](AGENTS.md) | 외부 에이전트(Codex 등) 지침 수정 시 |
| [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) | PR 체크리스트 확인 시 |
| [`scripts/check_python_tests.sh`](scripts/check_python_tests.sh) | pytest 게이트 구현 참조 시 |
| [`scripts/hooks/pre-commit`](scripts/hooks/pre-commit) | git pre-commit hook 수정 시 |
| [`scripts/hooks/cc-pre-commit.sh`](scripts/hooks/cc-pre-commit.sh) | Claude Code PreToolUse hook 수정 시 |
| [`docs/internal/plugin-release.md`](docs/internal/plugin-release.md) | 플러그인 릴리즈·버전 배포 요청 시 — 순서·태그·주의사항 |
| [`docs/internal/release-notes.md`](docs/internal/release-notes.md) | 릴리즈 노트 기록 — 버전별 커밋 범위·변경 요약 |

## 개발 명령어

```sh
# git hook 설치 (clone 후 1회)
cp scripts/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
cp scripts/hooks/commit-msg .git/hooks/commit-msg && chmod +x .git/hooks/commit-msg
cp scripts/hooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push
cp scripts/hooks/post-checkout .git/hooks/post-checkout && chmod +x .git/hooks/post-checkout

# 하네스 단위 테스트 실행 (Python 3.11 기준 — macOS system python3 는 3.9 일 수 있음)
python3.11 -m unittest discover -s tests -v
python3.11 -m unittest tests.test_signal_io -v   # 단일 모듈
node scripts/check_public_surface.mjs
```

> 빌드 / 런타임 명령어는 코드 도입 시 본 섹션에 추가 (별도 Task-ID).

## 커밋 / PR 절차

> 네이밍·메시지·PR 템플릿 상세: **[`docs/plugin/git-spec.md`](docs/plugin/git-spec.md)** (즉시 읽기 문서).

```
1. git checkout -b {브랜치명} main         # git-spec §1 패턴
2. (변경 작업)
3. git add {파일}
4. git commit -m "..."                      # hook 자동 게이트 (main-block + pytest)
5. git push -u origin {브랜치명}
6. gh pr create --title "..." --body "..."  # git-spec §4~§5 템플릿
7. bash scripts/pr-finalize.sh              # 머지 + CI 대기 + main sync 자동 (한 명령)
```

- **main 직접 commit/push 금지**. 항상 branch → PR → regular merge.
- **squash merge 금지** — 커밋별 히스토리 보존 목적.
- **branch 는 merge 후에도 삭제하지 않는다**.
- **pr-finalize 사용 권장** — 내부에서 peer merge guard(해당 시) + `gh pr merge --auto --merge` + `gh pr checks --watch` + auto-merge 완료 대기 + `git fetch origin main` ref 동기화 자동. 메인 Claude 가 main sync 까먹는 회귀 차단.
- **argument 없이 호출 시** current branch 의 open PR 자동 검출. 명시 시 `pr-finalize.sh <PR_NUMBER>`.
- **CI FAIL** 시 pr-finalize 가 exit 1 + 안내. 원인 수정 후 재시도.

## 환경변수

현재 없음. 도입 시 본 섹션에 (이름·용도·기본값·필수 여부) 추가.
