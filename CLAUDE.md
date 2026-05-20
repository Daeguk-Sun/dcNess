# CLAUDE.md — dcNess 프로젝트 작업 지침

> 본 파일은 메인 Claude (Claude Code) 가 dcNess 저장소에서 작업할 때의 지침이다. 작업 규칙 SSOT.

> 🔴 **[세션 시작 시 즉시 읽기 의무 — §3 문서 지도 참조]**

## 0. 프로젝트 정체성

> 🔴 **메인 Claude 가 자주 까먹는 핵심 — 매번 작업 전 반드시 인지**

### 0.1 본 프로젝트 = 하네스 인프라 (plug-in 배포물)

- 본 프로젝트(dcness)는 **Claude Code 용 plug-in 으로 배포**된다.
- 사용자(외부 프로젝트)는 **`/init-dcness` 스킬을 통해 활성화**한다.
- 본 프로젝트에 추가하는 모든 기능은 **dcness 자체를 위한 것이 아니라**, **활성화한 외부 프로젝트에 적용되기 위한 것**이다.
- 따라서 "이 프로젝트에서 잘 작동하는가" 가 아니라 **"활성화한 외부 프로젝트에서 잘 작동하는가"** 가 기준.

### 0.2 dcness 자체는 init-dcness 미적용 — 자기 규격 미얽매임

- 본 dcness 저장소는 자기 자신에 `/init-dcness` 를 실행하지 **않는다**.
- 따라서 dcness plug-in 의 규격(`stories.md` 강제 / `issue-lifecycle.md §1.1` 흐름 / `product-planner` 시퀀스 등) 에 **얽매이지 않는다**.
- dcness 자체의 작업은 다음 3개만 따른다:
  - 본 `CLAUDE.md` (작업 절차 + 게이트)
  - `docs/plugin/git-naming-spec.md` (브랜치·커밋·PR 네이밍)
  - GitHub 이슈 (필요 시 자유 형식, 메타-스토리·stories.md 불필요)
  - 본 CLAUDE.md
- **헷갈리지 마라**: plug-in 규격은 *외부 활성화 프로젝트* 용이지, dcness 자기 자신용이 아니다.

### 0.3 내부 ID 를 외부 배포물에 박지 마라

- **외부에 배포되는 파일** (= plug-in 사용자가 보게 되는 파일: `agents/**`, `commands/**`, `hooks/**`, 그리고 plug-in 사용자가 따라야 하는 SSOT 인 `docs/plugin/issue-lifecycle.md` 등) 안에는 **내부 ID / 내부 추적 표현을 본문으로 박지 않는다**.
- 외부 사용자에게 내부 추적용 표현은 **잡음**이다. 그 변경 이유 / 작동 룰만 자연어로 설명하면 충분.

### 0.4 작성 스타일 — 쉬운 한글 + § 표시 명확히

- 외래어 (Caveats / Disclaimer / Note / TBD 등) 보다는 **명확한 한글** 사용. (예: "Caveats" → "주의사항" / "TBD" → "추후 결정")
- 영어 약어가 더 정확한 곳(API / SDK / SSOT / PR / CI 등 산업 표준어)은 그대로 사용.
- **영어 명사구·줄임말 함부로 사용 금지** — 사용자 응답 / PR 본문 / 커밋 메시지 / 문서 본문 모두 적용. 예시 대체:
  - "cheap lever" → "저비용 절감 수단" / "가벼운 개선책"
  - "knob" → "조작 지점" / "조정값"
  - "follow-up" → "후속" / "후속 작업"
  - "wrap-up" → "마무리"
  - "polish" → "다듬기" (일반 문맥)
  - "fallback" → "대체 경로" / "후보 경로"
  - "fresh" → "새 / 갓 시작한"
  - "in-session" → "한 세션 안에서" / "세션 내"
  - "digest" → "요약" / "요약본" / "압축 요약"
  - "override" → "재정의" / "덮어쓰기"
  - "digest override" / "review echo override" 같은 합성 영어 명사구 → "review 출력 재정의" / "요약본으로 재정의" 등 한글 풀이
  - "caveat" / "Caveat" → "주의사항" / "주의 신호"
  - "baseline" → "기준선" / "기준치" / "측정 기준"
  - "substance" → "실증 근거" / "근거 내용"
  - "cap" (한도 의미) → "상한" / "한도" (`<머리>cap` 모자류 / `cap_*` 코드 식별자는 그대로)
  - "rebuild" → "다시 그리기" / "재생성"
  - "collapse" → "접기" / "한 줄로 모음"
  - "narration" → "서술"
  - "per-task" → "task별"
  - "spawn" (자식 프로세스 생성 의미) → "생성" / "자식 프로세스 띄움"
  - "verbatim" → "원본 그대로"
  - "rigor" → "엄정성" / "엄격성"
  - "hard constraint" → "엄격 제약"
  - 일반: 영어 명사구가 떠오르면 *우선 한글 풀이*, 정확도 위해 영어 병기 필요 시 `한글(영어)` 형식.
- **예외 — 그대로 사용**:
  - 산업 표준 약어 (API / SDK / SSOT / PR / CI / TDD / DRY / OWASP / MUST / IMPL / OAuth 등)
  - dcness 코드 식별자·spec 키워드 (`POLISH` / `IMPL` / `SPEC_GAP_FOUND` / `PASS` / `FAIL` / `ESCALATE` / `Hybrid A` 등 agent·orchestration 에 박힌 정형 이름)
  - 도구·라이브러리·인물 이름 (Claude / Anthropic / GitHub / vitest 등)
  - 이슈·PR 본문 직접 인용
- **`§` 기호는 명확하게 사용** — `§N`, `§N.M` 형식. 어디서 인용했는지 **반드시 명시** (예: `CLAUDE.md §2` / `orchestration.md §2.1`).
- 단순히 "위 섹션" / "아래 참조" 같은 모호한 표현 X — 항상 `파일명 §번호` 박을 것.

### 0.5 추가한 기능은 반드시 배포 경로에도 포함

- 본 저장소(dcness self) 에만 추가하면 **외부 활성화 프로젝트에서는 작동하지 않는다** — 과거 사례: 기능을 dcness 자체에 추가했는데 정작 설치한 외부 프로젝트(jajang)는 그 기능이 없어 작동 안 함.
- 모든 기능 추가 작업은 **배포 경로 검증 의무** 가 동반된다. 다음 중 *해당하는 모든 경로* 가 갱신돼야 작업 완료:
  1. **plug-in 본체 파일** (`agents/**`, `commands/**`, `hooks/**`) — 사용자가 plug-in 업데이트 시 자동 적용. 본 저장소의 같은 경로에 변경 = plug-in 도 자동 갱신 (단 사용자가 plug-in 버전 업 받은 후).
  2. **`/init-dcness` 스킬이 사용자 프로젝트로 *복사·배포* 하는 파일** (예: `scripts/check_*.mjs`, `scripts/hooks/commit-msg`, `.github/workflows/*.yml`) — 본 저장소에만 추가하면 신규 프로젝트는 받지만 *기존 활성화 프로젝트* 는 못 받음. **`commands/init-dcness.md` 의 deploy 스텝에 반드시 추가** + 기존 사용자가 재배포받을 방법 고지.
  3. **사용자가 따라야 하는 SSOT 문서** (예: `docs/plugin/issue-lifecycle.md`, `docs/plugin/git-naming-spec.md` 중 사용자용 부분) — 본 저장소 docs 만 갱신하면 사용자는 못 봄. plug-in 배포물 쪽으로 옮기거나 init-dcness 가 복사하도록 처리.
- 기능 추가 PR 본문에 **"배포 경로 검증"** 항목 명시 — 어떤 경로(1/2/3) 로 사용자 환경에 도달하는지, 누락 없는지.
- **검증 안 된 변경은 dcness 자체에서만 작동하는 환상**. 사용자에게 안 닿으면 기능 추가 의미 없음.

---

### 0.6 모드 (위 0.1~0.5 정체성 위에서)

- **목적**: RWHarness fork-and-refactor — Prose-Only 원칙 결정론 + 4 기둥 정합 + 함정 회피 5원칙.
- **모드**: **메인 Claude 직접 작업** (`docs/archive/status-json-mutate-pattern.md` §10 / §11.4 정합).
  - architect / code-validator / engineer 위임 강제 **없음**.
  - RWHarness 가드 미적용 환경. **단** Document Sync 거버넌스만 강제.
  - 글로벌 `~/.claude/CLAUDE.md` 의 RWHarness 위임 룰(에이전트 분기 / 인프라 프로젝트 분기)은 본 프로젝트에 **미적용**. 본 파일이 우선한다.

## 1. 작업 절차 (모든 변경 공통)

0. **워크트리 (impl 류 루프 한정)**
   - **진입 조건**: 코드 변경 batch (`/impl` / `/impl-loop` / `/auto-loop`) 진입 시 자동 `EnterWorktree(name="<목적>-{ts_short}")`. 목적: 메인 working tree 보호 + 동시 다중 세션 충돌 회피.
   - **제외**: `/product-plan` / 모듈 설계 / 문서·시드 작업은 워크트리 X — 충돌 회피 목적 부재.
   - **수동 우회**: 사용자 발화에 정규식 `워크트리\s*(빼|없|말)` 매치 (예: "워크트리 빼고") 시에만 건너뜀.
   - **금지**: 수동 `git worktree add` 우회 — CC permission 시스템이 `EnterWorktree` 만 sub-agent 권한 자동 처리.
1. **수정 작업**.
2. **commit 직전**: git pre-commit hook 자동 게이트 (main-block + pytest).
3. **branch → PR → regular merge** (직접 `main` push 금지). CI PASS 후 메인이 즉시 머지 — *사용자 수동 승인 대기 X*.
4. **종료 시 ExitWorktree** — squash 흡수 검사 후 자동 `keep`/`remove` (`docs/plugin/loop-procedure.md §1.1`).

## 2. 게이트 요약

- **main-block**: `scripts/hooks/pre-commit` — main 직접 commit 차단
- **git-naming**: `scripts/hooks/commit-msg` (로컬) + `git-naming-validation.yml` (CI) — 브랜치·커밋·PR 제목 형식 강제
- **pytest**: `scripts/check_python_tests.sh` — harness/tests/agents 변경 시만
- **plugin-manifest**: `scripts/check_plugin_manifest.mjs` (CI `plugin-manifest.yml`) — `.claude-plugin/plugin.json` version / manifest 정합 검증
- **pr-body**: `scripts/check_pr_body.mjs` (CI `pr-body-validation.yml`) — PR 본문 템플릿 충족 검증

> ⚠️ **금지**: `--no-verify` 등 hook 우회. main 직접 push.

## 3. 문서 지도

### 즉시 읽기 (세션 시작 시 항상)

| 파일 | 역할 |
|---|---|
| [`docs/plugin/orchestration.md`](docs/plugin/orchestration.md) §0~§2.1 | **대원칙 + catastrophic** — harness 강제 2가지 + catastrophic 시퀀스 |
| [`docs/plugin/git-naming-spec.md`](docs/plugin/git-naming-spec.md) | 브랜치·커밋·PR 네이밍 규칙 SSOT — 모든 커밋 작업에 적용 |

### 작업 시 읽기 (lazy — 해당 작업 직전에만)

| 파일 | 언제 읽나 |
|---|---|
| [`docs/plugin/design.md`](docs/plugin/design.md) | 디자인 시스템 SSOT 변경 / plug-in agent 디자인 룰 영향 작업 시 |
| [`docs/archive/status-json-mutate-pattern.md`](docs/archive/status-json-mutate-pattern.md) | 하네스 Phase 분할 / 전환 절차 원전 참조 시 (역사 자료) |
| [`docs/plugin/orchestration.md`](docs/plugin/orchestration.md) | 시퀀스 mini-graph + 8 loop 풀스펙 — 루프 진입 경로·분기 수정 시 |
| [`docs/plugin/handoff-matrix.md`](docs/plugin/handoff-matrix.md) | agent 호출 분기 / retry / escalate 한도 / 접근 권한 경계 수정 시 |
| [`docs/plugin/loop-procedure.md`](docs/plugin/loop-procedure.md) | Step 0~8 mechanics (begin-run → begin-step → Agent → end-step → finalize-run) 수정 시 |
| [`docs/plugin/hooks.md`](docs/plugin/hooks.md) | hook 시스템 (PreToolUse / SessionStart / cc-pre-commit) 수정 시 SSOT |
| [`docs/plugin/issue-lifecycle.md`](docs/plugin/issue-lifecycle.md) | 외부 활성 프로젝트의 epic / story / impl 흐름 변경 시 SSOT (본 저장소 자체엔 미적용 — §0.2 참조) |
| [`PROGRESS.md`](PROGRESS.md) | 현재 상태·TODO·Blockers 확인 시 |
| [`AGENTS.md`](AGENTS.md) | 외부 에이전트(Codex 등) 지침 수정 시 |
| [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) | PR 체크리스트 확인 시 |
| [`scripts/check_python_tests.sh`](scripts/check_python_tests.sh) | pytest 게이트 구현 참조 시 |
| [`scripts/hooks/pre-commit`](scripts/hooks/pre-commit) | git pre-commit hook 수정 시 |
| [`scripts/hooks/cc-pre-commit.sh`](scripts/hooks/cc-pre-commit.sh) | Claude Code PreToolUse hook 수정 시 |
| [`docs/internal/plugin-release.md`](docs/internal/plugin-release.md) | 플러그인 릴리즈·버전 배포 요청 시 — 순서·태그·주의사항 |
| [`docs/internal/release-notes.md`](docs/internal/release-notes.md) | 릴리즈 노트 기록 — 버전별 커밋 범위·변경 요약 |

## 4. 개발 명령어

```sh
# git hook 설치 (clone 후 1회)
cp scripts/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
cp scripts/hooks/commit-msg .git/hooks/commit-msg && chmod +x .git/hooks/commit-msg
cp scripts/hooks/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push
cp scripts/hooks/post-checkout .git/hooks/post-checkout && chmod +x .git/hooks/post-checkout

# 하네스 단위 테스트 실행
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_signal_io -v   # 단일 모듈
```

> 빌드 / 런타임 명령어는 코드 도입 시 본 섹션에 추가 (별도 Task-ID).

## 5. 커밋 / PR 절차

> 네이밍·메시지·PR 템플릿 상세: **[`docs/plugin/git-naming-spec.md`](docs/plugin/git-naming-spec.md)** (즉시 읽기 문서).

```
1. git checkout -b {브랜치명} main         # git-naming-spec §1 패턴
2. (변경 작업)
3. git add {파일}
4. git commit -m "..."                      # hook 자동 게이트 (main-block + pytest)
5. git push -u origin {브랜치명}
6. gh pr create --title "..." --body "..."  # git-naming-spec §4~§5 템플릿
7. bash scripts/pr-finalize.sh              # 머지 + CI 대기 + main sync 자동 (한 명령)
```

- **main 직접 commit/push 금지**. 항상 branch → PR → regular merge.
- **squash merge 금지** — 커밋별 히스토리 보존 목적.
- **branch 는 merge 후에도 삭제하지 않는다**.
- **pr-finalize 사용 권장** — 내부에서 `gh pr merge --auto --merge` + `gh pr checks --watch` + auto-merge 완료 대기 + `git checkout main && git pull` 자동. 메인 Claude 가 main sync 까먹는 회귀 차단.
- **argument 없이 호출 시** current branch 의 open PR 자동 검출. 명시 시 `pr-finalize.sh <PR_NUMBER>`.
- **CI FAIL** 시 pr-finalize 가 exit 1 + 안내. 원인 수정 후 재시도.

## 6. 환경변수

현재 없음. 도입 시 본 섹션에 (이름·용도·기본값·필수 여부) 추가.
