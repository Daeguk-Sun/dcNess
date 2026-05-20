# PROGRESS

## 현재 상태

- **📐 측정 스크립트 + #345 흡수 권고 (#446 트랙 보조)**: `scripts/measure_main_turns.py` 신규 — Claude Code 세션 JSONL (`~/.claude/projects/<project-id>/<sid>.jsonl`) 파싱 → 메인 assistant turn 분포 (tool / text-only / thinking-only) + tool histogram + Agent (sub-agent) 호출 분포 출력. text/JSON 출력 + 디렉토리 일괄 처리. #446 본문 baseline (8af5fb4d=203 / 1518caa0=349) 정확 재현 검증. Step 3 프로토타입 gate 측정 + Step 6 사후 검증에 재사용. 동시에 #345 (`/impl-loop` 메인 컨텍스트 누적 — fresh-process-per-task driver 필요) 코멘트로 #446 트랙 흡수 권고 — fresh-process 제안은 6/15 Agent SDK 과금 분리로 폐기 (#438), 본질 문제는 #446 Hybrid A 가 in-session 안에서 흡수.

- **🏗️ /impl-loop Hybrid A 설계 — build-worker agent + 2-step (#446 Step 2)**: `/impl-loop` 한정 신규 agent `build-worker` (test+impl+self-validate 3 phase 통합, helper Bash self-call, TDD GUARD 정합, git/PR 메인 위임). impl-task-loop 진입 모드에 Hybrid A (2-step) 추가 — default (4-step, `/impl` 단발) / fallback (5-step, impl 부재) 옆. `commands/impl-loop.md` 절차 5 단계 재작성 + 진행 뷰 sub-step 4→2 + digest 형식 worker 어휘 + 세션 청킹 권장 (15-20 task/세션). `docs/plugin/{handoff-matrix,orchestration,loop-procedure}.md` 동기 — §1.12 build-worker 결론, §4.3 진입 모드 3분기, §4.8 모드 분기, §3.2.1 worker phase prose 자체 Write 규약 (`build-{test,impl,validate}.md`). `/impl` 단발은 4-agent 그대로 (rigor 우선 의도된 티어링). 코드 미동작 (설계만) — Step 3 jajang 1-task 프로토타입 실측 (gate ≤ 50 turn) 통과 후 Step 4 multi-PR + Step 5 릴리즈 0.2.27 진행. PR #448.

- **✂️ /impl-loop cheap levers — agent 5종 return 가이드 구체화 + impl-loop digest override (#446 Step 1)**: jajang 실측 baseline ~280 turn/task 의 post-Agent ~47 turn 누적 주범 중 하나가 review.md verbatim echo + agent 본문 narration. 5 agent (`test-engineer` / `engineer` / `code-validator` / `pr-reviewer` / `module-architect`) 기존 generic return-terseness 가이드 (#440) 옆에 산출물 구조별 구체화 단락 추가 — 테스트 케이스 표 전수 입력 금지 (test-engineer), 파일별 narration → `M files +X -Y` 통계 (engineer), A/B/C 통과 항목 열거 금지 (code-validator), A~F 체크리스트 본문 재진술 금지 (pr-reviewer), impl 본문 재진술 금지 (module-architect), 공통 워크트리 절대경로 반복 금지. `commands/impl-loop.md` driver-scope **review echo override** 절 추가 — verbatim review.md 는 디스크 (`<run_dir>/review.md`) 그대로, 메인 컨텍스트는 5줄 digest (task 결론 / agent 결과 / finding / PR·이슈 / next). `/impl` 단발 verbatim MUST 그대로 (`commands/impl.md` 무변경 — hard constraint 준수). PR #447.

- **🔧 /impl-loop run 격리 복원 + 사람 친화 진행 뷰 (#443)**: #438 in-session 복귀 시 `commands/impl-loop.md` 절차가 `loop-procedure.md` 옛 `b<i>.` 한-run 모델 잔재를 베껴 `begin-run impl-loop` 1회 + 모든 task 를 한 run 에 묶음 → `run_review` 가 run 단위라 거대 review.md 1개 (헤드리스는 task=자식세션=run 격리됐던 것 깨짐). **작업 1 (run 격리)**: `orchestration.md §4.1` 카탈로그에 `impl-loop` 행 없음 = 정설 `impl-loop = impl-task-loop × N, 각 task 독립 impl run`. `commands/impl-loop.md` 절차를 "각 task = 독립 `begin-run impl` … `end-run` = N run = N review.md" 로 수정. `loop-procedure.md` §1.2 (entry_point 예시 `impl-loop` 제거 + driver note) / §2 (`/impl-loop` 아래 impl run 은 TaskCreate skip) / §3.1 (`<task-id>` `b<i>.` 제거). `orchestration.md §4.8` 재작성 (outer `impl-<i>` + inner `b<i>.` → 각 task 독립 run). `harness/`·`tests/` `b<i>.` 참조 0건 — 순수 문서/스킬. **작업 2 (진행 뷰, Model Q)**: Task 시스템 = 평탄 리스트(부모/자식 필드 X) + 생성순 표시 (샘플 task 렌더 실측 검증). `commands/impl-loop.md` `## 진행 뷰` 섹션 신규 — outer 헤더 + 현재 task sub-step `ㄴ` 들여쓰기 중첩, 예정 task 대기 줄, task 전환마다 [현재 헤더 + sub + 남은 헤더] rebuild (중간삽입 불가 우회). 릴리즈 0.2.26.

- **✂️ impl-loop agent return 간결성 규율 — 메인 컨텍스트 누적 감축 (#438 lever A, #440)**: #438 로 `/impl-loop` 이 메인 in-session 오케스트레이션 복귀 → 매 task 의 sub-agent return prose 가 메인 컨텍스트에 누적 (#345 근본 원인). impl-task-loop 5 agent (`engineer` / `test-engineer` / `code-validator` / `pr-reviewer` / `module-architect`) 정의의 "결론 + 권장 다음 단계" 섹션에 **return 간결성 가이드** 1블록 추가 — return prose 는 메인이 다음 행동을 결정하는 데 필요한 것만 (결론 + 핵심 변경·발견 + 권장 다음 단계), 과정 narration / impl 계획·컨텍스트 재진술 / 파일별 장황한 설명 제거, 단 결론 근거 substance (실측 명령·수치 / 발견 항목 / 미완 작업) 유지. 형식 강제(라인 cap) 아닌 *내용 선택* 가이드 — prose-only 철학 정합. 부수 효과: prose_file → review.md 신호 중심 간결화로 `/run-review` 노이즈 감소. 432 unittest PASS.

- **🗑️ /impl-loop·/impl 헤드리스 폐기 — in-session 오케스트레이터 복귀 (#438)**: Anthropic 이 2026-06-15 부터 구독 플랜의 `claude -p` / Agent SDK 사용량을 별도 "Agent SDK 크레딧" 풀로 분리 + full API rate 과금. dcness `/impl-loop`·`/impl`(헤드리스 옵션) 의 `claude -p` 자식 세션 spawn 이 정확히 그 풀에 진입 → 헤드리스 경로 완전 폐기. `/impl-loop` 을 메인 Claude in-session flat 오케스트레이터로 복귀 (`orchestration.md §4.8` 의 `impl-task-loop × N` 모델 — 헤드리스는 그 위 얇은 override 층이었음). **변경**: `scripts/impl_loop_headless.py` (563줄) + `tests/test_impl_loop_headless.py` (478줄) 삭제. `commands/impl-loop.md` 재작성 — 헤드리스 spawn 제거 + in-session per-task 절차 복원 (보존: 워크트리 1회 + base-ref #424 / Pre-flight gate / 진입 직전 1회 확인 #346 / 1 task = 1 PR / 4-step 모두 호출 MUST #431, 신규: false-clean 차단 메인 직접 확인 + compaction 복구 절, 스테일 `§4.9 → §4.8` 수정). `commands/impl.md` — `## 헤드리스 실행 옵션 (#422)` 섹션 삭제 + #431 false-clean 검출 서술(헤드리스 parser 의존)을 메인 직접 확인으로 재작성 + #375 헤드리스 framing 정리. `orchestration.md §4.8` / `loop-procedure.md` = 메커니즘 중립이라 무변경. in-session = 구독 interactive 한도 — Agent SDK 크레딧 풀 미진입. 후속 (별 PR): agent 정의 terse-return 규율 (잔여분 최소화 lever A).

- **🗑️ /quick 스킬 폐기 — TDD Guard 강제로 light path 무력화**: `hooks/tdd-guard.sh` PreToolUse hook (release 0.2.16 / PR #339·#340) 이 src 편집 시 매칭 test 파일 존재 검사 + deny 강제. `quick-bugfix-loop` 는 test-engineer 단계 부재 → engineer:IMPL 가 *test 없는* src 편집 시도 시 catastrophic deny → loop stuck. quick 본질 (light path = test-engineer 없음) 이 TDD Guard 와 충돌. quick-bugfix-loop bugfix-specific 기능 (`fix/`/`chore/` branch prefix / code-validator bugfix scope 자동 분기 / module-architect 버그픽스 케이스) 은 이미 `impl-task-loop` / `code-validator` / `module-architect` 본문에 흡수되어 추가 작업 불필요. **변경**: `commands/quick.md` 삭제. `agents/qa.md` 라우팅 가이드 `impl-task-loop fallback path` 로 통일. `commands/qa.md` 후속 라우팅 `FUNCTIONAL_BUG`/`CLEANUP` → `impl-task-loop (/impl) fallback path`. `commands/impl.md` / `commands/impl-loop.md` / `commands/product-plan.md` / `commands/run-review.md` / `commands/efficiency.md` / `commands/init-dcness.md` 비대상·후속·skill 목록 정리. `docs/plugin/orchestration.md` §3.5 quick-bugfix-loop mini-graph + §4.5 풀스펙 삭제 + §3.6 qa-triage → §3.5 / §4.6 → §4.5 재번호 + §4.7~§4.10 → §4.6~§4.9 재번호 + qa-triage CLEANUP 라우팅 `engineer 직접` 폐기 (HARNESS_ONLY_AGENTS 위반). `loop-procedure.md` / `handoff-matrix.md` / `dcness-rules.md` quick 언급 정리. `harness/hooks.py` / `session_state.py` / `scripts/dcness-helper` docstring. `tests/eval_*.py` quick_bugfix_loop reference 폐기. `tests/test_*.py` entry_point fixture `quick` → `impl`/`qa`. `CLAUDE.md` / `README.md` skill 목록 10 → 9.

- **🔄 plan-reviewer 그릴미 개편 — enum 3 통일 + ESCALATE 트리거 + opus 승격 4 + Spike Pre-Check**: `agents/plan-reviewer.md` 본문 전면 갱신 — 결론 enum 2개 (`PLAN_REVIEW_PASS` / `PLAN_REVIEW_CHANGES_REQUESTED`) → 3개 (`PLAN_REVIEW_PASS` / `PLAN_REVIEW_FAIL` / `PLAN_REVIEW_ESCALATE`) 통일. ESCALATE 트리거 4 케이스 명시 (외부 검증 실행 불가 / 권한 경계 밖 정보 / cycle 한도 직전 동일 finding 반복 / `EXTERNAL_VERIFIED` URL 부재 PASS 시도). 호출 모드 2개 (`FULL` default / `PRE_CHECK` Spike Pre-Check) 명시. opus 승격 4 (plan-reviewer / security-reviewer / system-architect / product-planner) — 손실 비용 + 판단 깊이 + 호출 빈도 ROI. `commands/product-plan.md` Pre-Check Trigger 섹션 추가 — 사용자 입력에 spike 키워드 (외부 모델/API/SDK / 조건부 약속 패턴 / 의문문) 발견 시 product-planner 호출 *전* plan-reviewer `PRE_CHECK` 모드 1회 호출. `PRODUCT_PLAN_UPDATED` plan-reviewer skip 분기 폐기 — 변경의 성격 무관 항상 호출. `docs/plugin/orchestration.md` mermaid + mode-step 표 + 분기표 일괄 갱신. `loop-procedure.md` enum 분기 갱신. `handoff-matrix.md` plan-reviewer 섹션 3 결과로 갱신. `scripts/research/enum_roi_baseline.mjs` classify CHANGES_REQUESTED → FAIL. `tests/eval_*.py` allowed enums ESCALATE 추가.

- **♻️ Validator 단순화 — 5 sub-doc → 2 평탄 에이전트 + enum 통일**: `agents/validator.md` + `agents/validator/` 폴더 통째 폐기. 두 평탄 에이전트로 평탄화 — `agents/code-validator.md` (impl ↔ 구현 일치, full/bugfix scope 자동 분기 — `docs/impl/NN-*.md` vs `docs/bugfix/#N-slug.md`) + `agents/architecture-validator.md` (Placeholder Leak + Spike Gate 2 항목 — 자가검증 사각지대만). UX_VALIDATION 폐기 → ux-architect 에 5 카테고리 self-check 흡수 (FAIL → 재고려 2 cycle). DESIGN_VALIDATION 의 자가검증 가능 항목 (인터페이스/에러/엣지케이스/리스크/성능) → architect SYSTEM_DESIGN 에 5 항목 self-check 흡수. PLAN_VALIDATION 폐기 (issue #247 drift 회복). 결론 enum 13개 → 3개 통일 (`PASS / FAIL / ESCALATE` — `SPEC_MISSING` 은 `ESCALATE` 사유로 흡수). harness 정합: HARNESS_ONLY_AGENTS (`engineer` + `code-validator`), §2.3.5 게이트 (architect MODULE_PLAN SD 후속 직전 architecture-validator PASS 필수), ALLOW_MATRIX. 28 파일 갱신. 437 unittest 모두 PASS. PR 진행 중.

- **✅ Epic 3 Story 3.4 (#165) 완료 — marketplace.json source.ref → release 전환 + 0.2.0 bump**: `.claude-plugin/marketplace.json` plugin source 를 `{ "source": "github", "repo": "alruminum/dcNess", "ref": "release" }` 로 전환 (로컬 `./` 제거). `plugin.json` + `marketplace.json` metadata.version `0.1.0-alpha` → `0.2.0`. Epic 3 코드 작업 완료 — PR 머지 후 release-sync.yml 자동 발화로 release 브랜치 갱신. 외부 dry-run (jajang `/plugin update dcness`) 은 PR 머지 후 별도 진행. DCN-CHG-20260506-16.

- **✅ Epic 3 Story 3.3 (#164) 완료 — release-sync.yml + branch protection 가이드**: `.github/workflows/release-sync.yml` 신규 (main push 시 자동 release sync, concurrency 그룹으로 중복 실행 방지). `docs/internal/branch-protection-setup.md` 신규 (release 브랜치 보호 설정 절차). PR #205.

- **✅ Epic 3 Story 3.2 (#163) 완료 — release 브랜치 + sync_release.sh**: `scripts/sync_release.sh` 신규. origin/main → release 동기화 (dcness self 경로 제거 후 force-with-lease push). release 브랜치 초기화 완료. 검증: docs/internal|archive 0 hit / docs/plugin 9 파일 / tests|harness 0 hit. 부수 수정: pytest 게이트 삭제 트리거 버그(`--diff-filter=ACM`). PR #202.

- **✅ Epic 3 Story 3.1 (#162) 완료 — source.ref GREEN**: `marketplace.json` plugin source 의 `{ "source": "github", "repo": "alruminum/dcNess", "ref": "release-dryrun" }` 실측. docs/internal/ + docs/archive/ cache 미존재 확인. Epic 3 Story 3.2~3.4 진행 가능. 결과: `docs/internal/story-3-1-source-ref-verification.md`.

- **🗑️ 거버넌스 슬림화 PR-1 진행 중 (#182)** (`DCN-CHG-20260506-15`): Task-ID + 동반 갱신 게이트 시스템 폐기. check_task_id.mjs / check_document_sync.mjs 삭제, CI 워크플로우 2개 삭제, hooks 호출 제거. PR-2(문서 정리)·PR-3(Epic3 재평가) 후속. (PR-3 #193 가 먼저 머지되며 `Closes #182` 가 잘못 발동해 이슈가 close 된 것을 reopen 후 PR-1/PR-2 정상 진행 중.)

- **🔧 #151 후속 — 옛 경로 잔존 7건 정리** (`DCN-CHG-20260506-14`): Epic 2 검증 정규식이 `(../docs/X.md)` 만 잡아 `(../X.md)` 형태 마크다운 링크 누수. `harness/agent_boundary.py` docstring + `docs/internal/main-claude-rules.md` (5건+4링크) + `docs/internal/self-guidelines.md` (2건) + `docs/plugin/handoff-matrix.md` §4.4 (1건) + `commands/init-dcness.md` §4 (dcness self repo 명시 라인) 일괄 갱신.

- **🔧 harness/ docstring archive 경로 정리 (#179)** (`DCN-CHG-20260506-08`): Story 1.3 인용처 갱신 누락분. `harness/session_state.py` + `harness/hooks.py` 의 `docs/conveyor-design.md` 인용 → `docs/archive/conveyor-design.md`.

- **🔒 main 직접 commit 차단 hook 게이트 신설 (#173)** (`DCN-CHG-20260506-07`): `scripts/hooks/pre-commit` + `scripts/hooks/cc-pre-commit.sh` 양쪽에 main 브랜치 차단 추가. 자연어 룰만 있던 카테고리 mechanical 강제 (Story 1.3 회귀 방지). governance §2.7 게이트 매트릭스에 row 추가.

- **📂 Epic 2 — docs 폴더 분리 (#151)** (**완료**):
  - **Story 2.5** (`DCN-CHG-20260506-13`): 전체 저장소 구 경로 참조 일괄 갱신. agents/ 16개 (orchestration/issue-lifecycle/known-hallucinations 경로), commands/ 5개, docs/internal cross-ref, `harness/agent_boundary.py` DCNESS_INFRA_PATTERNS 갱신 (삭제된 loop-catalog 제거 포함), `tests/test_agent_boundary.py` 4건, CLAUDE.md/README.md/AGENTS.md, scripts/hooks/.github 주석 경로 전수 갱신. `docs/process/` 참조 0건 확인.
  - **Story 2.4** (`DCN-CHG-20260506-12`): dcness self 거버넌스 7개를 `docs/process/` → `docs/internal/` git mv. `check_document_sync.mjs` RECORD/RATIONALE 상수 경로 갱신. `docs/process/` 폴더 비움 완료.
  - **Story 2.3** (`DCN-CHG-20260506-10`): 외부 배포 SSOT 7개 → `docs/plugin/` git mv.
  - **Story 2.2** (`DCN-CHG-20260506-09`): `docs/status-json-mutate-pattern.md` (444줄) 핵심 추출 → `docs/plugin/prose-only-principle.md` (58줄 SSOT) 신규 + 원본 `docs/archive/` 이동. agents/ 12개 footer + 기타 인용처 25곳 갱신.
  - **Story 2.1** (`DCN-CHG-20260506-06`): `docs/process/dcness-guidelines.md` 분할 → `docs/plugin/dcness-rules.md` (skill 룰) + `docs/internal/self-guidelines.md` (self 룰). §8/§9 TBD → 이슈 #174/#175. 인용처 17곳 갱신. harness INFRA_PATTERNS 경로 갱신 + 신규 테스트 2케이스.

- **🧹 Epic 1 — 외부 배포물 정리 (#150)** (`DCN-CHG-20260506-02` ~ `-05`):
  - **Story 1.1** (`-02`): `.claude-plugin/`, `commands/`, `README.md` RWHarness 고유명사 13건 제거 (표기 "선행 하네스" 통일)
  - **Story 1.2** (`-03`): 외부 배포 경로 (agents/ 21개 / commands/ 3개 / docs/ 5개 / CLAUDE.md) DCN-CHG 내부 ID 92건 스크럽
  - **Story 1.3** (`-04`): `docs/archive/` 신설 + 역사 자료 5개 이동 (conveyor-design / epic-index / manual-smoke-guide / migration-decisions / plugin-dryrun-guide) + 인용처 전수 갱신
  - **Story 1.4** (`-05`): `README.md` / `PROGRESS.md` 현행화 — DCN-CHG 잔여 5건 제거, Status 헤더 갱신, Skill 목록 8→10개, 다음 단계 정리

- **🔧 Task-ID format gate fix — subject-only 검사** (`DCN-CHG-20260505-04`):
  - `scripts/check_task_id.mjs` — `validateMessage` → `validateSubject`. subject 1 줄째에서만 정확히 1 개 검사. body 안 역사 참조 / Document-Exception-Task / 후속 link 자유 허용.
  - `docs/process/governance.md` §2.1 — commit message 위치 룰 명문화 (subject canonical 1 개 / body 자유).
  - **회귀 사유**: DCN-CHG-20260505-03 (#144) 커밋 body 의 역사 참조 (`DCN-CHG-20260430-32` handoff-matrix split 사례 비유) 가 게이트 over-strict 매칭 → fail. 룰 본질 = "본 작업 canonical 1 개" 이지 텍스트 토큰 갯수 X.

- **🧹 SSOT 슬림화 1 차 — orchestration ↔ loop-catalog 통합** (`DCN-CHG-20260505-03`, #144):
  - `docs/loop-catalog.md` (249 줄) → `docs/orchestration.md` 흡수 통합 + git rm. **8 → 7 SSOT** (5 코어 → 4 코어).
  - 신 `orchestration.md` 구조: §0 정체성 / §1 적용 모드 / §2 게이트 시퀀스 / §3 진입 경로 mini-graph / §4 8 loop 행별 풀스펙 (구 loop-catalog 흡수) / §5 catastrophic vs 자율 / §6 코드 driver / §7 참조. 최종 464 줄.
  - **cap 완화**: `orchestration.md` 만 500 줄 cap 예외. 다른 4 SSOT (handoff-matrix / loop-procedure / dcness-guidelines / main-claude-rules) 는 300 cap 유지.
  - **ref churn 최소화**: agents/ 13 개 footer 변경 0 (orchestration.md 만 ref 했던 패턴). commands/ 5 개 § 번호 patch + docs/ 5 개 ref update + hooks/ 1 곳.
  - **Follow-up**: `harness/agent_boundary.py` DCNESS_INFRA_PATTERNS 의 `loop-catalog\.md` regex 1 줄 제거 = 별도 PR (harness change-type 회피 위해 본 PR 범위 외).

- **🔒 Task-ID 게이트 PR title 검사 제거 + branch protection 설정** (`DCN-CHG-20260504-05`):
  - `scripts/check_task_id.mjs` — `--pr-title` 모드 제거 (커밋 메시지 검사만 유지).
  - `.github/workflows/task-id-validation.yml` — `Validate PR title` step 제거.
  - GitHub main branch protection required status checks 설정 (3개 게이트 강제화).

- **🏷️ git-naming-spec CI/hook 강제** (`DCN-CHG-20260503-04`):
  - `scripts/check_git_naming.mjs` 신규 — 브랜치명·커밋/PR 제목 형식 검증 스크립트.
  - `scripts/hooks/commit-msg` 신규 — 로컬 commit-msg hook (커밋 제목 즉시 차단).
  - `.github/workflows/git-naming-validation.yml` 신규 — CI 브랜치명·PR 제목 게이트.
  - `CLAUDE.md` §3 문서 지도 즉시읽기/lazy 분리. §5 squash→regular merge 수정.

- **📦 PR/Commit/Issue 구조화 강제** (`DCN-CHG-20260502-05`):
  - **3-commit 구조** (impl-task-loop 계열): docs(MODULE_PLAN 후) → tests(TESTS_WRITTEN 후) → src+PR(CODE_VALIDATION 후). `loop-procedure.md §3.4` 신설.
  - **catastrophic gate 3개**: §2.3.6(test-engineer=docs commit), §2.3.7(engineer IMPL=tests commit), §2.3.8(pr-reviewer=src commit). impl loop(entry_point=impl) 계열에만 적용.
  - **record-stage-commit** 서브커맨드 신규 — `$HELPER record-stage-commit <docs|tests|src>` → live.json.stage_commits 기록.
  - **이슈 레이블 체계**: 정적(BugFix/UI/Docs, `scripts/setup_labels.sh`) + 동적(V0N/EPIC0N/Story0N, agent 자동 생성).
  - **docs/epic-index.md** 신규 — EPIC번호 ↔ GitHub이슈번호 매핑 SSOT.
  - **PR merge**: squash → regular merge (3 commit 히스토리 보존). `§5.4` 주석 추가.
  - **agent 갱신**: product-planner(epic 이슈 의무), task-decompose(story 이슈 의무), qa(BugFix 레이블), designer(UI 레이블).
  - **374 tests OK** (신규 10 case: StageCommit*GateTests 3클래스).

- **📚 loop-insights 누적·주입** (`DCN-CHG-20260502-02`):
  - `harness/loop_insights.py` 신규 — agent별 insights 파일 read/write (`.claude/loop-insights/<agent>[-<mode>].md`).
  - `finalize-run --accumulate` — redo-log REDO_* + WASTE/GOOD findings → agent별 파일 append.
  - `begin-step` stdout 주입 — 해당 agent insights 있으면 `[INSIGHTS: <agent>/<mode>]` 섹션 출력.
  - `loop-procedure.md` §3.1 강제 문구 추가.
  - 게이트(sentinel 체크) 없음 — AI 신뢰 원칙 적용.

- **🐛 session-start 절대 경로 버그 수정** (`DCN-CHG-20260502-03`):
  - DCN-01 inject에서 상대 경로 사용 → Read 도구 실패 버그.
  - `CLAUDE_PROJECT_DIR`로 동적 절대 경로 구성, Python에 `sys.argv[1]`로 전달.

- **🔒 session-start BLOCKING 게이트 강화** (`DCN-CHG-20260502-01`):
  - inject 3원칙 적용: (1) 출력 금지 조건 — Read 완료 전 텍스트 출력 금지. (2) 검증 토큰 — 첫 응답 첫 줄에 `[dcness-guidelines 로드 완료 — §13 감시자 Hat 장착]` 의무. (3) 예외 없음 명시 — "안녕"/"hi"/"hello"/짧은 질문 전부 포함.
  - 배경: 단순 인사에서 inject 무시 확인. "인사 → 짧은 응답" 패턴 매칭이 system-reminder를 후순위로 밀어냄.

- **🦥 session-start lazy-load v2** (`DCN-CHG-20260501-18`):
  - inject lazy 섹션 파일경로 완전 제거 — 경로 나열 자체가 read 트리거였음.
  - dcness-guidelines.md §0 마크다운 링크 비활성 텍스트로 교체.
  - 경로는 skill 파일 `## 사전 read` 섹션에만 존재하여 skill 진입 시에만 노출.

- **🦥 session-start lazy-load 최적화** (`DCN-CHG-20260501-17`):
  - session-start inject: 5 docs 즉시 read → `dcness-guidelines.md` 1개만 즉시, 나머지 4개 lazy.
  - `dcness-guidelines.md` §0: "매 세션 의무 read" → "loop 시작 전 read" 변경.
  - `dcness-guidelines.md` §13 신규: 감시자 Hat 전문 이전 (inject에서 제거).
  - skill 파일 5개(`impl`/`quick`/`product-plan`/`impl-loop`/`qa`): `## 사전 read` 섹션 추가.
  - 예상 절감: skill 미호출 세션 ~13K 토큰, skill 호출 세션 ~5-8K 토큰.

- **🪄 PostToolUse prose auto-staging** (`DCN-CHG-20260501-15`):
  - `handle_posttooluse_agent` — `tool_response.text` 추출 → `write_prose` → `live.json.current_step.prose_file` 기록.
  - `end-step --prose-file` optional로 변경 — 미제공 시 `current_step.prose_file` 자동 읽기.
  - 메인 Claude 의 Write/Bash heredoc prose-staging 작업 제거 가능 (매 step 1~2회 절감).
  - `_count_step_occurrences` `base_dir` 파라미터 추가 (hook test 정합).
  - 351 tests OK.

- **🔗 prose_file 직결 + `_resolve_prose_path()` 삭제** (`DCN-CHG-20260501-14`):
  - `.prose-staging/` 파일명 패턴 불일치로 같은 (agent, mode) 반복 시 두번째가 outer prose 덮어씌워 run-review 분실 버그 수정.
  - `write_prose(occurrence=N)` 추가 — N>0 시 `<agent>[-mode]-N.md` 고유 파일명.
  - `_append_step_status(prose_path)` → `.steps.jsonl`에 `prose_file` 절대 경로 저장.
  - `parse_steps()`: `prose_file` 직접 read, legacy fallback 보존. `_resolve_prose_path()` 삭제.
  - 342 tests OK.

- **📡 PostToolUse Agent surface push (PR-3)** (`DCN-CHG-20260501-13`):
  - jajang 운영 1 cycle 발견 — 권고 어휘로 메인 능동 retrieval 행동 강제 불가. trace 는 read 함, redo-log 0 entry. jajang 메인 자기 진단 ROI 표 ("룰 추가 < surface 개선") 그대로 반영.
  - **PostToolUse Agent hook 가 push 채널로** — sub 종료 후 `additionalContext` 로 메인 다음 turn Agent tool result 옆에 system reminder 자동 inject. 공식 docs 확정 메커니즘.
  - **`harness/sub_eval.py`** 신규 — 보수적 anomaly 룰 (tool_uses<2 / 같은 tool 5회+ / Write 약속+0건 prose-only). 자동 결정 PASS / REDO_SUSPECT.
  - **`agent_trace.histogram` + `last_agent_id`** helper 추가.
  - **`handle_posttooluse_agent`** 확장 — sub trace 집계 → histogram 계산 → anomaly 검출 → stdout JSON inject + redo_log 자동 append (`auto:true` 마커).
  - 정상 메시지 1줄: `[감시자 hook] sub=engineer tool histogram: Bash:2 Read:4 (PASS)`. anomaly 강조: `⚠️ anomaly 감지: prompt 에 Write/Edit 약속, 실제 0건 (prose-only 의심) + REDO 권고`.
  - **트레이드오프 §0 정합** — 정보 inject 만, 강제 X. 메인 자율 판단 보존 (룰 침해 0).
  - 회귀 0 — 신규 21 case (sub_eval 10 + agent_trace 6 + hooks 5), 전체 345 tests OK.
- **🎩 감시자 Hat + audit-redo skill (PR-2)** (`DCN-CHG-20260501-12`):
  - PR-1 인프라 위에 운영 layer. 사용자 비전 4축 중 (1) 결과 평가 + (4) 학습 진화 (2-layer) 가동.
  - **`hooks/session-start.sh`** additionalContext 에 "감시자 Hat (권고)" 섹션 추가 — builder + 감시자 두 hat / sub completion 깐깐 평가 / `redo-log` 1줄 append / 루프 재구성 자유. 대원칙 §0 정합 — 권고 어휘만, 형식 강제 X.
  - **`commands/audit-redo.md`** 신규 skill — `(sub, mode)` 별 redo 분포 + REDO 사유 클러스터 + trace 공통 패턴 → Layer 1 (현 프로젝트 1차 prompt 첨가) + Layer 2 (`agents/*.md` 영구 patch) 후보 제안. `/run-review` 와 직교 (waste vs redo 학습).
  - **운영 시나리오** — 메인이 매 sub completion 시 권고에 따라 `redo-log.append()` → 1-2 주 누적 후 `/audit-redo` 호출 → 패턴 발견 → Layer 1 즉시 첨가 → N 회 검증 → Layer 2 PR (별도 Task-ID).
  - **한계** — hook trace = 행동만 (thinking X, P7 미래). 권고 어휘라 메인이 *안 따르면* 효과 0 → 운영 데이터로 강제 escalation 검토.
- **🪝 sub 행동 사후 추적 인프라 (PR-1)** (`DCN-CHG-20260501-11`):
  - 사용자 비전 — 정적 룰 추가 게임 → 추론 기반 judgment 로 패러다임 전환. 4축: 결과 평가 / 행동 추적 / audit log / 학습 진화 (2-layer). PR-1 은 (2)+(3) 코드 인프라만.
  - **`harness/redo_log.py`** 신규 — `redo-log.jsonl` append/read/tail. 메인이 sub completion 평가 후 PASS/REDO_SAME/REDO_BACK/REDO_DIFF 1줄 기록. POSIX O_APPEND atomic, 4096 bytes 이내 entry. 15 tests.
  - **`harness/agent_trace.py`** 신규 — `agent-trace.jsonl` append/read/tail. PreToolUse/PostToolUse hook 가 sub 내부 도구 호출마다 1줄 기록. 11 tests.
  - **`harness/hooks.py` 확장** — `handle_pretooluse_file_op` boundary 통과 시 trace pre append + 신규 `handle_posttooluse_file_op` (PostToolUse Edit/Write/Read/Bash) + CLI subcommand. tool_input 200 bytes truncate (POSIX atomic 보장).
  - **`hooks/post-file-op-trace.sh`** 신규 wrapper + `hooks/hooks.json` PostToolUse `Edit|Write|Read|Bash` matcher 등록.
  - **한계 명시**: hook trace = sub *행동* 만. thinking / 중간 message X (`.output` 가공은 P7 미래). 도구 0번 쓰는 sub turn = trace 텅 빔.
  - **PR-2 (DCN-CHG-20260501-12)** 후속 — SessionStart 감시자 hat 메시지 + `commands/audit-redo.md` skill (Layer 1+2 학습 진화).
  - 회귀 0 — 신규 35 case (15+11+9), 전체 324 tests OK. 토큰 비용 0 (hook LLM context 외부).
- **♻️ /run-review must_fix retro 재계산** (`DCN-CHG-20260501-10`):
  - DCN-CHG-20260501-09 forward-only 보강 — 이전 run 의 `.steps.jsonl` stale `must_fix` 무력화. parser `parse_steps()` 가 prose_full 보유 시 `_has_positive_must_fix` 재계산, 부재 시 jsonl fallback.
  - 자장 run-ef6c2c00 (이전 PR 머지 *전* 작성된 stale jsonl) retro 검증 — MUST_FIX_GHOST 6 → 0.
  - source 분리 자각: finalize-run (session_state) 은 jsonl 사용 (실시간 fresh, 정확). parser (run_review) 는 prose 재계산 (retro 정확). 의도적 분리.
  - 신규 2 테스트 (recompute / fallback). 288 → 290 ran / all PASS.
- **🔧 /run-review 4 false positive 동시 fix (자장 run-ef6c2c00)** (`DCN-CHG-20260501-09`):
  - 자장 40 step / $118.73 run /run-review 결과 28 waste finding 검증 — 4 이슈 한 번에 fix.
  - **#1 prose_path bug** (가장 결정적): skill DCN-30-21 부터 `<run_dir>/.prose-staging/<bN.agent-mode>.md` 에 prose 작성, 그러나 parser 가 legacy `<run_dir>/<agent>-<mode>.md` 만 읽음 → 9 engineer step 모두 같은 1 파일 매칭 → MISSING_SELF_VERIFY 9건 false positive. `_resolve_prose_path()` 신규 — Nth occurrence 매칭 + fallback. 자장 실 데이터로 b1~b3 anchor=True 회복 확인.
  - **#2 MUST_FIX_GHOST regex bug**: `_MUST_FIX_RE` 단순 단어경계 → "MUST FIX 0, NICE TO HAVE 6" 부정문 매칭. `_has_positive_must_fix()` 신규 — 라인 단위 negation 검사. 6 pr-reviewer 케이스 false positive 0.
  - **#3 engineer banner**: agents/engineer.md H1 직후 `⚠️ CRITICAL — extended thinking 본문 드래프트 금지` 추가. architect sub-mode 7 + product-planner (DCN-30-39) 패턴 동일. 자장 4 stall 실측 (614/1102/429/670s) 명시.
  - **#4 prose_excerpt cap 4 → 12**: `_append_step_status` cap 5~12 룰 정합. ECHO 임계 `< 3` 유지.
  - **신규 7 테스트** (ResolveProsePath 5 + must_fix negation/positive 2). 281 → 288 ran / all PASS / 회귀 0.
  - **다른 patterns** (PLACEHOLDER_LEAK / INFRA_READ / READONLY_BASH / EXTERNAL_VERIFIED_*) — path fix 로 정확도 자동 회복.
- **🧪 pytest pre-commit 게이트 (paths 분기)** (`DCN-CHG-20260501-07`):
  - 직전 task (`-06`) 로 protection 폐기 → CI `unittest discover` 표시 레벨로 떨어짐. 사용자 — doc-sync 동급 mechanical 차단 원함.
  - **`scripts/check_python_tests.sh`** 신규 — staged `harness/` / `tests/` / `agents/` / `python-tests.yml` 매칭 시만 `python3 -m unittest discover -s tests`. 비매칭 0초, 매칭 ~3초. `GITHUB_ACTIONS` skip.
  - **pre-commit chain 화** — `scripts/hooks/pre-commit` + `scripts/hooks/cc-pre-commit.sh` 둘 다 doc-sync 통과 후 pytest 호출.
  - **governance.md §2.7** — 게이트 매트릭스 표 신설 (doc-sync = 모든 commit / pytest = paths 분기). 우회 = `--no-verify` (룰 위반).
  - 사용자 PICK 옵션 B (paths 분기) — 사용자 의도 정합. 옵션 A (무조건) / C (branch protection 재활성) 기각.
- **🔄 branch protection 폐기 + paths 필터 복구 (DCN-CHG-20260501-04 revert)** (`DCN-CHG-20260501-06`):
  - 사용자 의도 재확인 — "doc-sync 정도의 제어" 였음. 이전 세션 ("CI 강제해서 실패 못하게") 과해석으로 protection ON + paths 필터 OFF 동반 결정. 본 task 로 둘 다 revert.
  - **branch protection live 폐기** — `gh api -X DELETE repos/alruminum/dcNess/branches/main/protection` 200. 재호출 → 404 "Branch not protected" 확인.
  - **paths 필터 복구** — `python-tests.yml` (harness/tests/agents/yml) + `plugin-manifest.yml` (plugin/script/yml). docs-only PR 불필요 실행 회피.
  - **governance.md §2.8** — "Branch Protection (현재 비활성)" 으로 재작성. doc-sync §2.7 3중 hook 만 실질 강제. 나머지 CI 게이트는 표시 레벨.
  - **`gh pr merge --squash --auto` 의무 룰 폐기** — protection 없으면 작동 X. 일반 `--squash` 머지.
  - `setup_branch_protection.mjs` / `branch-protection-setup.md` — header 에 ⚠️ OFF 명시. 재활성용 보존.
- **🚥 branch protection — CI 4 checks 강제** (`DCN-CHG-20260501-04`) — ⚠️ DCN-CHG-20260501-06 으로 revert. 아래 기록 유지 (히스토리):
  - DCN-30-37 ~ DCN-30-40 7+ PR 동안 CI fail 누적 머지 회귀 차단. 사용자 명령 과해석.
  - PR #84 실측 — 머지 15:28:21 / CI 완료 15:28:32~39 = 11~18초 일찍 머지. 우연 success.
  - `setup_branch_protection.mjs` review 1 → null (1인 운영 self-approve 불가) + governance §2.8 갱신.
  - **live 적용** — 4 contexts 강제 (`Document Sync gate` / `unittest discover` / `validate manifest` / `Task-ID format gate`) + strict + linear history.
  - **`gh pr merge --squash --auto` 의무** 룰 추가 — CI 통과 후 자동 머지.
  - **workflow paths 필터 폐기** (`python-tests.yml` / `plugin-manifest.yml`) — paths 미스매치 시 required check 발화 X → PR BLOCKED 영원 회피.
- **📕 main-claude-rules.md SSOT — CLAUDE.md 동일 레벨 강제 read** (`DCN-CHG-20260501-02`):
  - DCN-30-40 (SessionStart inject 처음부터 작동 0회 회귀) 후속. inject 깨져도 룰 인지 보장하는 *backup 메커니즘*.
  - `docs/process/main-claude-rules.md` 신규 (204줄, 300 cap 안):
    - §1 **실존 검증 강제** — 글로벌 `~/.claude/CLAUDE.md` 제1룰 + dcness §12 self-verify 통합. 안티패턴 7건 (DCN-30-37 sed / DCN-30-40 inject / CI 미확인 등).
    - §2 **dcness 인프라** — 300줄 cap (DCN-30-30) / 5 SSOT 표 / 거버넌스 / 핵심 강제 룰 4 / sub-agent path 보호 (DCN-CHG-20260501-01).
    - §3 **Karpathy 4 원칙 전문** — `forrestchang/andrej-karpathy-skills/skills/karpathy-guidelines/SKILL.md` (MIT) 인용. dcness agent 별 적용 매핑.
  - `CLAUDE.md` 상단 🔴 reference 박스 + 문서 지도 추가 — CC 가 CLAUDE.md 자동 로드 → 본 문서 read 자연 유도.
  - 사용자 요청 3 항목 (실존 검증 강제 / dcness-guide 인프라 / Karpathy 전문) 정확 정합.
- **🛡️ sub-agent path 보호 hook (handoff-matrix §4 코드 SSOT)** (`DCN-CHG-20260501-01`):
  - DCN-30-39 5번 follow-up — `DCNESS_INFRA_PATTERNS` 가 spec only, 코드 enforcement 0. sub-agent 가 인프라 path Edit/Write/Bash 자유.
  - **첫 원칙 정합** — "강제 = 작업 순서 + 접근 영역" — 접근 영역 강제는 spec only ↔ 코드 drift 해소.
  - **`harness/agent_boundary.py`** 신규 — `DCNESS_INFRA_PATTERNS` (9) / `ALLOW_MATRIX` (12 agent) / `READ_DENY_MATRIX` / `is_infra_project()` 4 OR / `is_opt_out()` / `check_write/read_allowed()` / `extract_bash_paths()` heuristic.
  - **`harness/hooks.py` 핸들러 3개** — `handle_pretooluse_agent` 끝 `update_live(active_agent=...)` 등록 + `handle_pretooluse_file_op()` (Edit/Write/Read/Bash) + `handle_posttooluse_agent()` (clear). CLI 2 subcommand 추가.
  - **hooks/hooks.json** — PreToolUse `Edit|Write|NotebookEdit|Read|Bash` matcher + PostToolUse `Agent` matcher 추가. `hooks/file-guard.sh` + `hooks/post-agent-clear.sh` 신규.
  - **메인 vs sub-agent 분기** — live.json.active_agent 공유 상태로 식별. 메인 = 통과 (governance Document Sync 가 보호).
  - **dcness 자체 = 해제** — `is_infra_project()` True 시 모든 룰 우회. user 프로젝트 (자장 등) 만 enforce.
  - **opt-out** — `.no-dcness-guard` 마커 + `DCNESS_INFRA=1` env + `CLAUDE_PLUGIN_ROOT` env + cwd 화이트리스트 (4 OR).
  - 38 신규 테스트 (`test_agent_boundary` 27 + `test_hooks` 11). 281 ran / 279 PASS / 2 pre-existing flaky 무관.
  - `docs/handoff-matrix.md` §4.4 코드 SSOT cross-ref + INFRA pattern 리스트 코드와 동기.
- **🚨 SessionStart inject 처음부터 작동 0회 — schema fix + 압축** (`DCN-CHG-20260430-40`):
  - 자장 사용자 보고 — `/product-plan` 진입 시 메인이 dcness 룰 미인지. system-reminder = "OK" 만, 본문 부재. 본 dcness 세션 jsonl `grep` = 0 직접 검증.
  - 2 bug 동시: (1) JSON schema 잘못 (`{continue, additionalContext}` top-level → CC honor X). 정확 = `{hookSpecificOutput: {hookEventName, additionalContext}}` nested wrapper. (2) 12K char (CC 10K cap 초과).
  - **fix**: schema `hookSpecificOutput` wrapper + content directive only (~1.2K) — 5 SSOT path + 핵심 강제 룰 4 (가시성 / Step 기록 / self-verify / --auto-review). 글로벌 `~/.claude/CLAUDE.md` 와 동일 레벨 강제.
  - **검증 의무 (NEXT 세션)** — 머지 후 새 dcness 세션 시작 시 jsonl `grep "DCN-30-40 자동 로드"` ≥ 1 확인. 자장 plugin reinstall + 동일 검증.
  - **DCN-30-27 ~ -39 의존성 재검증 필요** — inject 작동 후 5 slim skill 메인이 SSOT 만 보고 동작 가능 self-test.
- **🪶 /run-review 후속 cleanup 3건** (`DCN-CHG-20260430-39`):
  - DCN-30-38 follow-up — 사용자 우선순위 4-3-1 한 PR 묶음 (5번 catastrophic-gate path 보호는 별도).
  - **(4) cross-ref sweep** — DCN-30-32 split 잔재 1줄 정정. `agents/pr-reviewer.md:86 "(orchestration.md §7 정합)"` → `"(handoff-matrix.md §4 정합)"`. agent prompt grep 매칭 = 단 1줄.
  - **(3) `tool_uses` 컬럼** — `harness/run_review.py:render_report` 단계별 상세 표 13 컬럼 확장. `≥ 100` 시 `**bold**` 강조 (TOOL_USE_OVERFLOW 임계 정합). 미매칭은 `-`. TOOL_USE_OVERFLOW 회귀 측정 가시성 ↑.
  - **(1) sub-mode banner** — `agents/architect/{system-design,task-decompose,module-plan,tech-epic,light-plan,docs-sync,spec-gap}.md` 7 파일 H1 직후 `> ⚠️ CRITICAL — extended thinking 본문 드래프트 금지` 1 블록 추가. master 룰 (`agents/architect.md` §자기규율 lines 98-103) 의 sub-mode 가시화. THINKING_LOOP 회귀 회피 (DCN-30-20 jajang 6분 stall).
  - 테스트 3 신규 (`ToolUsesColumnTests`). 45 ran / 45 PASS. sub-mode 7 파일 모두 300줄 cap 미충돌 (최대 254줄).
- **🪶 self-verify echo anchor 자율화 + §12 sed 안티패턴** (`DCN-CHG-20260430-38`):
  - DCN-30-34 self-verify `## 자가 검증` 단일 형식 강제 → first-principle ("출력 형식 자유") 회색 영역. anchor 자율화 (다중 옵션) + substance 만 의무.
  - `agents/engineer.md` 양 섹션 (자가 검증 + IMPL_PARTIAL 남은 작업) anchor 자율 명시.
  - 4 anchor 옵션: `## 자가 검증` / `## Verification` / `## 검증` / `## Self-Verify`.
  - `harness/run_review.py:SELF_VERIFY_ANCHORS` 패턴 4 + `_has_self_verify_anchor` helper.
  - `MISSING_SELF_VERIFY` 패턴 (MEDIUM) — engineer step (IMPL_DONE / IMPL_PARTIAL / POLISH_DONE) 에 anchor 부재 시 emit.
  - `dcness-guidelines.md` §12 안티패턴 1줄 추가 — Bash sed/awk 후 *전·후* 실측 의무 (방법 자율).
  - 8 신규 테스트. 240 ran / 238 PASS / 2 pre-existing flaky 무관.
- **📊 /run-review 회귀 4 패턴 자동 검출** (`DCN-CHG-20260430-37`):
  - DCN-30-36 prior count hint 의 *사후 측정* 인프라 + 자장 실 패턴 4종 자동 검출.
  - `harness/run_review.py:StepRecord.tool_use_count` 필드 + `assign_invocations_to_steps` propagate.
  - `_scan_main_sed_misdiagnosis` 신규 — CC JSONL 안 메인 self-correction 패턴 검출.
  - `detect_wastes` signature 확장 (invocations / repo_path / window). 4 신규 패턴:
    - `TOOL_USE_OVERFLOW` (≥ 100, 자장 실측 임계)
    - `PARTIAL_LOOP` (IMPL_PARTIAL ≥ 3 in run)
    - `END_STEP_SKIP` (invocations > steps + margin 1)
    - `MAIN_SED_MISDIAGNOSIS` (메인 self-correction 텍스트 패턴)
  - 자장 실 데이터 검증 — run-c0ef57e0 에서 `tool_use_count=153` 즉시 검출 ✓.
  - 8 신규 테스트. 34 ran / all PASS.
  - 자율 침해 0 (사후 분석만). MISSING_SELF_VERIFY 는 PR3 (DCN-30-38) 의 anchor 자율화 후 추가.
- **🎯 engineer prior tool_use_count hint** (`DCN-CHG-20260430-36`):
  - jajang epic-08/09 회고 추가 분석 — engineer overflow 5회 (102/119/153/170/223 tool uses) 자장 오후 실측. DCN-30-34 IMPL_PARTIAL enum 만으론 LLM self-monitor 불가능 (CC API 미노출 본질 한계) → 실효 부족.
  - `harness/run_review.py:extract_agent_invocations` 에 `tool_use_count` 필드 (`totalToolUseCount`) 추가.
  - `harness/session_state.py:_prior_engineer_tool_use_count(sid)` 신규 + `_cli_begin_step` 가 `agent="engineer"` 시 stderr hint (`[hint] prior engineer tool_use_count=N — IMPL_PARTIAL 분할 자율 판단 권고. 강제 X (정보만).`).
  - 자율 침해 0 — 측정 정보 보충만, 판단은 agent/메인 자율. 측정 source = `toolUseResult.totalToolUseCount` (CC session JSONL).
  - 신규 3 테스트 (engineer hint / no prior silent / non-engineer silent). 224 ran / 222 PASS / 2 pre-existing flaky 무관.
- **🛡️ 진단/제안 self-verify 원칙 SSOT** (`DCN-CHG-20260430-35`):
  - jajang impl-loop epic-08 회고 I5 (메인 sed misdiagnosis "130개 fix" → 실제 0개) 회귀 방지.
  - `docs/process/dcness-guidelines.md` §12 신설 — 글로벌 `~/.claude/CLAUDE.md` "제1 룰" (실존 검증 강제) 을 dcness skill 진행 컨텍스트에 SessionStart 훅 자동 inject 로 재인용.
  - 룰 (MUST): 추측 금지 + 실측 후 단언. 검증 방법은 자율 (grep / ls / Read / Bash / WebFetch).
  - engineer.md §자가 검증 echo (DCN-30-34) 와 짝 — agent 인용 + 메인 실행 verify 양방향.
- **🛡️ engineer IMPL_PARTIAL + self-verify echo + hallucination catalog** (`DCN-CHG-20260430-34`):
  - jajang impl-loop epic-08 회고 I1/I2/I3 (engineer context overflow 3회) + I5 (메인 sed misdiagnosis) 회귀 방지.
  - **`IMPL_PARTIAL` enum 신설** — 단일 호출 무리 인지 시 자율 분할. handoff-matrix.md §1.5 + §2 (split ≤ 3) / loop-catalog.md §3 §5 (allowed_enums) / dcness-guidelines.md §5 (yolo 매트릭스) 박힘.
  - **engineer.md 3 신규 섹션** — 작업 분할 (IMPL_PARTIAL) / 대량 동일 변환 도구 자율 선택 / 자가 검증 echo 의무. 174줄 (300 cap 안).
  - **`docs/known-hallucinations.md` 신설 SSOT** — 외부 도구 config 키 학습 데이터 노이즈 카탈로그. architect 3개 + validator 1개 cross-ref 1줄.
  - **자율 정합** — 숫자 cap 강제 X, 도구 자율, 카탈로그 정보 제공 only.
- **🛡️ begin-step 시 stale current_step WARN** (`DCN-CHG-20260430-33`):
  - jajang impl-loop epic-08 회고 I4 (e08 batch 2 `.steps.jsonl` engineer 누락) 회귀 방지.
  - `STALE_STEP_TTL_SEC = 30 * 60` (30분) 신설. `update_current_step` 에 stale 검사 — 기존 current_step 의 `last_confirmed_at` 이 30분 초과면 stderr `STALE STEP WARN`.
  - 자동 보정 X (DCN-30-25 정책 정합 — 안전). end-step 누락 + 다음 begin-step 패턴 (DCN-30-25 미커버) 만 cover.
  - 테스트 2 케이스 추가 (stale WARN / fresh no-WARN).
- **✂️ orchestration.md split (handoff-matrix 분리)** (`DCN-CHG-20260430-32`):
  - PR4 의 follow-up — orchestration.md (540줄) 300줄 cap 위반 해소.
  - **`docs/handoff-matrix.md` 신규** (256줄) — agent 측 강제 영역 SSOT. §4 결정표 (12 agent enum) + §5 retry 한도 + §6 escalate 카탈로그 + §7 권한 매트릭스 (호출 / Write / Read / 인프라) 통째 이전.
  - **`docs/orchestration.md` 슬림** (540 → 298줄) — 시퀀스 SSOT 만 보존 (§0 정체성, §1 모드, §2 게이트 시퀀스, §3 진입 경로 mini-graph 6, §4 cross-ref to handoff-matrix, §5 catastrophic vs 자율 영역, §6 driver 결정, §7 proposal cross-ref, §8 참조).
  - 책임 축: 시퀀스 spec ↔ agent 결정/권한. 모든 cross-ref 양방향 + dcness-guidelines.md §0.1 "현재 알려진 위반" 항목 해소 (없음).
- **🪶 4 skill bulk slim (quick/impl/impl-loop/product-plan)** (`DCN-CHG-20260430-31`):
  - 4 PR migration 의 마지막 PR. 5 skill 합계 660 → 132줄 (80% 절감).
  - `commands/quick.md` 215 → 32줄 — `quick-bugfix-loop` cross-ref + Inputs (이슈 / 영향 파일 / 재현 / 원하는 방향).
  - `commands/impl.md` 205 → 32줄 — `impl-batch-loop` + UI 감지 시 `impl-ui-design-loop` 자동 전환 명시. State-aware skip / Step 4.5 / catalog §3 cross-ref.
  - `commands/impl-loop.md` 127 → 36줄 — `impl-batch-loop × N` chain. outer `impl-<i>` / inner `b<i>.<agent>` 컨벤션 (DCN-30-12). catalog §3 + §10 cross-ref.
  - `commands/product-plan.md` 113 → 32줄 — `feature-build-loop`. Inputs 정형화 (요구사항 / 시나리오 / 제약 / 우선순위 / 변경 vs 신규) — `CLARITY_INSUFFICIENT` 사전 회피.
  - 모든 mechanics 제거 — `loop-procedure.md` (Step 0~8) + `loop-catalog.md` (loop spec) 단일 source.
- **✂️ loop-procedure.md split + 300줄 cap 룰 신설** (`DCN-CHG-20260430-30`):
  - 사용자 지시 — "loop-procedure.md 쪼개자 가급적 300라인 넘기지 말랬잖아 행동지침 md는 이것도 룰로 적어놔줘". loop-procedure.md (436줄) cap 위반.
  - **`docs/loop-catalog.md` 신규** (239줄) — 8 loop 행별 풀스펙 (allowed_enums / 분기 / sub_cycles / branch_prefix). loop-procedure.md §7.0 인덱스 + §7.1~§7.10 풀스펙 모두 이전.
  - **`docs/loop-procedure.md` 슬림** (436 → 242줄) — Step 0~8 mechanics 만 보존. §7 = catalog cross-ref + catastrophic 룰 정합 1 항목.
  - **`docs/process/dcness-guidelines.md` §0 갱신** — 2 SSOT 분담 (procedure + catalog) 명시. §0.1 신설 — **행동지침 md 300줄 cap 룰** (대상 / 대상 외 / Why / How to apply / 현재 알려진 위반).
  - **`docs/orchestration.md` §3 헤더** — loop-catalog.md cross-ref 추가.
  - **알려진 위반**: orchestration.md (540줄). split 후속 별도 Task-ID 예정.
- **🔌 helper finalize-run --auto-review + qa.md slim pilot** (`DCN-CHG-20260430-29`):
  - 4 PR migration (skill 슬림화 + procedure SSOT) 의 PR3.
  - `harness/session_state.py:_cli_finalize_run` 에 `--auto-review` flag 추가. STATUS JSON 출력 직후 in-process 로 `harness.run_review.main(["--run-id", rid, "--repo", cwd])` 호출. 메인 Claude 가 finalize-run 부르면 review 자동 piggy-back — 의도적 skip 불가.
  - 실패 케이스 (review_main 예외) 안전망 — `AUTO_REVIEW_FAIL` stderr WARN + STATUS JSON 자체는 정상 출력 + exit 0.
  - `commands/qa.md` slim pilot — 127줄 → 28줄 (78% 절감). `qa-triage` loop / Inputs / 후속 라우팅 추천만. 절차는 [`docs/loop-procedure.md`](docs/loop-procedure.md) §1~§6 + §7.5 cross-ref.
  - `tests/test_session_state.py` 3 신규 (`auto_review_chains_report` / `skip_on_failure` / `off_no_chain`) PASS. 219 ran / 217 PASS / 2 pre-existing flaky 무관.
  - PR4 후속 — 4 skill (quick / impl / impl-loop / product-plan) bulk slim.
- **📐 loop-procedure.md §7 매트릭스 행별 풀스펙 보강** (`DCN-CHG-20260430-28`):
  - PR1 (DCN-30-27) self-test gap 반영. §7.0 한눈 인덱스 + §7.1~§7.8 행별 풀스펙 sub-section. 각 행 = `branch_prefix` decision rule / `Step 4.5 적용` / Step 별 `allowed_enums` 표 / 분기 표 / sub_cycles. 252줄 → 436줄.
  - feature-build-loop 분기 (PRODUCT_PLAN_UPDATED skip / UX_REFINE_READY / CLARITY_INSUFFICIENT 등) 명시.
  - impl-ui-design-loop design-critic 별도 step 분리 + DESIGN_LOOP_ESCALATE / VARIANTS_ALL_REJECTED 분기.
  - ux-design-stage / ux-refine-stage designer mode (THREE_WAY 권장) + 사용자 PICK / Step 2.5 사용자 승인.
  - sub_cycle agent (architect:SPEC_GAP / engineer:POLISH-<n> / engineer:IMPL-RETRY-<n> / designer:SCREEN-ROUND-<n>) allowed_enums 명시.
- **📑 loop-procedure.md SSOT 신설 + cross-ref** (`DCN-CHG-20260430-27`):
  - skill 5종 Step 0~7 *실행 절차* 중복 (100~215줄/skill) 풀어내는 4 PR migration 의 1단계.
  - `docs/loop-procedure.md` (252줄) — 8 loop 공통 실행 절차 SSOT (Step 0 worktree+begin-run / Step 1 TaskCreate / Step 2~N agent 호출 / Step 4.5 stories sync / Step 7 finalize-run+clean+commit-PR / Step 8 review).
  - 8 loop name 확정: `feature-build-loop` / `impl-batch-loop` / `impl-ui-design-loop` / `quick-bugfix-loop` / `qa-triage` / `ux-design-stage` / `ux-refine-stage` / `direct-impl-loop`.
  - `docs/process/dcness-guidelines.md` §0 cross-ref + 의무 read 명시. `docs/orchestration.md` §3 헤더 8 loop name 매핑.
- **📜 dcness-guidelines.md SSOT + SessionStart 훅 inject** (`DCN-CHG-20260430-26`):
  - 사용자 지적 — quick.md (light path 전용) 에 범용 룰 다 박혀 책임 혼재. + 미래 추가 룰 (Epic/Story 분할, 커스텀 루프) SSOT 필요.
  - `docs/process/dcness-guidelines.md` (신규) — 11 섹션 (가시성 / Step 기록 / **/run-review 의무 (신규)** / **결과 출력 룰 (신규)** / yolo / AMBIGUOUS / worktree / TBD 분할 기준 / TBD 커스텀 루프 / 권한 요청 / Karpathy 참조).
  - `hooks/session-start.sh` — 활성 프로젝트 게이트 통과 후 guidelines.md 내용을 system-reminder 로 inject (RWHarness review-inject 패턴 정합). CC 매 세션 자동 인지 + plugin 비활성 시 발화 X.
  - `commands/quick.md` — 380줄 → 215줄 슬림화. 범용 룰 cross-ref 만.
  - 미래 룰 추가 = 본 SSOT 1 파일에만 append.
- **🛡️ Step 기록 안전망 — drift/count WARN + skill SSOT 강화** (`DCN-CHG-20260430-25`):
  - jajang DCN-30-23 사후 분석 — engineer 자체 PR 만든 후 메인이 end-step skip → .steps.jsonl 누락 사단.
  - helper 측: `_cli_end_step` drift detector (current_step ≠ args.agent → stderr WARN) + `finalize-run --expected-steps N` row count 검증.
  - `commands/quick.md` SSOT: `## Step 기록 룰` 절 신규 — Agent ↔ begin/end-step 1:1 의무 + POLISH 네이밍 컨벤션 + 안티패턴 4건 + helper 안전망 cross-ref.
  - `commands/impl.md` Step 7 — `--expected-steps 5` 박음.
  - 신규 4 테스트. 자동 보정 X (안전) — WARN 으로 메인 사후 인지.
- **🕐 /run-review 단계별 표에 local time 시각 컬럼** (`DCN-CHG-20260430-24`):
  - 사용자 디버그 시 UTC `04:xx` 가 헷갈려 보고. `.steps.jsonl` 은 UTC ISO 저장 (시스템 표준), render 측만 `astimezone()` 변환해서 KST 표시.
- **🩹 /run-review 매칭 fix + skill prompt 의 prose-file 격리** (`DCN-CHG-20260430-23`):
  - jajang 실측 (run-657d86fc, 9 step) 발견 2 결함 동시 fix.
  - **(1) 매칭 cascade 결함**: step 0 invocation 부재 시 후속 step 모두 어긋남 (9 중 2 매칭). timestamp-proximity 기반 매칭 (inv.ts < step.ts AND step.ts - inv.ts ≤ 600s, closest before) 으로 해결 → 9 중 8 매칭 (step 0 정당 미매칭).
  - **(2) prose-file 세션 격리 X**: skill prompt 가 `/tmp/dcness-*.md` 고정 path 사용 → 멀티세션 race / stale prose 잔여로 helper 가 옛 enum 추출. `dcness-helper run-dir` subcommand 신규 + skill prompt 4개 (`quick` / `product-plan` / `impl` / `qa`) 가 `<run_dir>/.prose-staging/<step>.md` 사용. multisession 자동 격리.
  - 신규 5 테스트 (AssignInvocationsTests timestamp / missing-first / unmatched-after-step + run-dir CLI). 209/211 PASS (2 pre-existing flaky 무관).
- **🌀 /run-review Phase 2 — THINKING_LOOP 검출 + per-Agent metrics** (`DCN-CHG-20260430-20`):
  - 사용자 jajang 실측 사례 (product-planner 6분 elapsed + ↓624 tokens stall) 자동 검출.
  - CC session JSONL `toolUseResult.usage.output_tokens` + `totalDurationMs` per-Agent 매칭 (순서 + agent name).
  - `EXPECTED_AGENT_BUDGETS` 12 agent 표 (elapsed_s + min_output_tokens).
  - THINKING_LOOP — duration > budget × 1.5 + output < budget × 0.3 (또는 5분 + 1k 절대 한도).
  - StepRecord 필드 4 추가 (duration_ms / output_tokens / total_tokens / cost_usd / matched_invocation).
  - 단계별 표 컬럼 5 추가 (duration / out_tok / total_tok / cost / matched).
  - 신규 8 테스트 (NormalizeAgentTypeTests / AssignInvocationsTests / ThinkingLoopDetectionTests). 23/23 PASS.
- **🔍 /run-review skill — 메타-하네스 self-improvement Phase 1** (`DCN-CHG-20260430-19`):
  - RWHarness `harness-review.py` 의 dcness 변환. dcness conveyor run 사후 분석.
  - `harness/run_review.py` (~370 LOC) — `.steps.jsonl` + per-agent prose 파싱 → 잘한 점 5 패턴 + 잘못한 점 8 패턴 detection + run-level cost (CC session JSONL 합산).
  - 잘한 점: `ENUM_CLEAN` / `PROSE_ECHO_OK` (DCN-30-15) / `DDD_PHASE_A` (DCN-30-16) / `DEPENDENCY_CAUSAL` / `EXTERNAL_VERIFIED_PRESENT` (DCN-30-18).
  - 잘못한 점: `RETRY_SAME_FAIL` / `ECHO_VIOLATION` / `PLACEHOLDER_LEAK` / `MUST_FIX_GHOST` / `SPEC_GAP_LOOP` / `INFRA_READ` / `READONLY_BASH` / `EXTERNAL_VERIFIED_MISSING`. 오늘 박은 룰 자동 회귀 검출.
  - `commands/run-review.md` skill prompt — character-for-character 출력 룰 (RW 패턴 정합).
  - 신규 15 테스트 PASS. dcness skill 9 개.
  - Phase 2 후속: per-Agent cost 매칭 (`toolUseResult.totalCost`), finalize-run 자동 트리거, 30일 누적 분석.
- **🪄 MODULE_PLAN_READY 마커 → state-aware skip** (`DCN-CHG-20260430-13`):
  - 사용자 통찰 — RWHarness plan_loop 의 원래 의도 (산출물 있으면 통과 / 없으면 다시 호출) 복원.
  - `agents/architect/task-decompose.md` — 각 batch 산출 시 ## 생성/수정 파일 / ## 인터페이스 / ## 의사코드 / ## 결정 근거 + `MODULE_PLAN_READY` 마커 박는 컨벤션.
  - `commands/impl.md` Step 2.0 — batch 파일 마커 grep → SKIP_MODULE_PLAN 시 batch 파일을 architect-MODULE_PLAN.md 자리에 cp + test-engineer 직진. catastrophic §2.3.3 정합.
  - 분기 추가 = 1 (grep 1줄). branch-surface-tracking warning 임계 미달.
  - 옵션 D — 컨벤션 + 메인 자율. dcness 철학 정합.
- **🧷 /impl-loop inner sub-task 의무 + `b<i>.<agent>` prefix 컨벤션** (`DCN-CHG-20260430-12`):
  - 사용자 smoke 발견 — 메인이 inner 5 sub-task TaskCreate inline skip → outer 5 batch entry 만 보임.
  - `commands/impl-loop.md` Step 2 에 ⚠️ "skip 금지" 경고 + `b<i>.<agent>` prefix 컨벤션 박음.
  - `commands/impl.md` Step 1 도 같은 강도 강조.
  - 사용자 가시성 기대 형식 (◼ b1.architect: MODULE_PLAN 등) 그대로 default 화.
- **👀 가시성 보강 — 결론 섹션 우선 + 메인 text echo** (`DCN-CHG-20260430-11`):
  - `_extract_prose_summary` 가 `## 결론` / `## Summary` / `## 변경 요약` 섹션 우선 추출. cap 12줄/1200char.
  - 5 skill (qa / quick / product-plan / impl / impl-loop) 에 "가시성 룰" 신규 — 매 Agent 후 메인 text reply 로 prose 핵심 5~12줄 echo (CC collapsed 회피).
  - 사용자 manual smoke 피드백 (ctrl+o 의존) 에 두 채널 동시 보강. 신규 5 테스트. 185/185 PASS.
  - PR split (#51 PROGRESS fragment + #52 본체) — commit 분할 사고. 두 PR 합쳐 -11 완성.
- **💰 /efficiency skill — jha0313/skills_repo 흡수** (`DCN-CHG-20260430-08`):
  - `harness/efficiency/` 패키지 (4 script fork from `improve-token-efficiency`) + `scripts/dcness-efficiency` wrapper + `commands/efficiency.md` skill prompt.
  - dcness fix 2건: encode_repo_path 의 `.` → `-` (CC 실 인코딩 룰 정합), price_for prefix 매칭 (dated suffix / variant tag 흡수).
  - 4 지표 점수화 (Cache utilization 40% + Output density 20% + Read redundancy 20% + Tool economy 20%) + Pareto + 6 절감 휴리스틱.
  - 신규 10 테스트 (`test_efficiency.py`). 181/181 PASS.
  - dcness skill 8 개: /init-dcness /qa /quick /product-plan /impl /impl-loop /smart-compact /efficiency.
- **🔁 /impl + /impl-loop skill 신규** (`DCN-CHG-20260430-06`):
  - `/impl` — per-batch 정식 impl 루프 (architect MODULE_PLAN → test-engineer → engineer IMPL → validator CODE_VALIDATION → pr-reviewer + clean 자동 commit/PR + yolo + worktree).
  - `/impl-loop` — multi-batch sequential auto chain (각 batch 마다 /impl 호출 + clean 자동 진행 + caveat 멈춤).
  - /product-plan TASK_DECOMPOSE 산출 batch list 의 후속 진입점. 5 sub-task per batch 가시화 — 사용자 manual smoke 지적 정합.
  - dcNess plugin skill 7개 됨: /qa /quick /product-plan /smart-compact /init-dcness /impl /impl-loop.
- **🔍 DESIGN_VALIDATION step 추가** (`DCN-CHG-20260430-05`):
  - orchestration §3.1 mermaid + §2.3.5 catastrophic 룰 + §4.9 결정표 갱신.
  - /product-plan Step 6.5 신규 (validator DESIGN_VALIDATION) + cycle 한도 2.
  - hooks.py §2.3.5 검사 (architect TASK_DECOMPOSE + SYSTEM_DESIGN.md 존재 시 DESIGN_REVIEW_PASS 필수).
  - 신규 5 테스트 (`CatastrophicDesignValidationTests`). 171/171 PASS.
  - 사용자 manual smoke 발견 — validator/design-validation.md agent 정의는 있는데 orchestration 시퀀스에서 호출 자리 빠져있던 갭 메움.
- **🧹 heuristic-only 정착 + dead code 제거** (`DCN-CHG-20260430-04`):
  - `harness/llm_interpreter.py` + `tests/test_llm_interpreter.py` 삭제 (dead code, 호출 경로 0).
  - `interpret_with_fallback` 의 `llm_interpreter=` 인자 제거 — heuristic-only.
  - `signal_io.py` docstring 정정 ("프로덕션 = haiku" → "프로덕션 = heuristic-only").
  - `docs/status-json-mutate-pattern.md` §0 정착 박스 추가 (heuristic-only 4 이유 + 트렌드 위치).
  - 트렌드 위치 재정의: RWH [2024 regex] → proposal 원안 [2025 메타 LLM] → **dcness 정착 [2025+ heuristic-only + 메인 cascade]** → [2026 structured output].
  - anthropic SDK 의존 0, 도그푸딩 API_KEY 불필요.
  - 166/166 PASS (이전 184 - 18 = LLM 관련 테스트 삭제).
- **🤖 Helper-side automation foundation** (`DCN-CHG-20260430-02`):
  - `dcness-helper end-step` 이 enum 추출 후 prose 첫 5~8줄 stderr 자동 출력 — CC collapsed 회피, 모든 skill 가시성 자동 ↑.
  - `dcness-helper finalize-run` 신규 — `.steps.jsonl` append-only 로그 집계 → JSON status (has_ambiguous / has_must_fix / step enum 매트릭스). skill 이 clean 판정용으로 소비.
  - `dcness-helper auto-resolve` 신규 — yolo 모드 폴백 매트릭스. UX_FLOW_ESCALATE → UX_FLOW_PATCHED 등 권장 액션 JSON.
  - `/quick` Step 7 = 7a clean 자동 commit/PR (graceful degrade) + 7b caveat 확인. worktree squash 흡수 자동 검사 (`git diff main..wt-branch -- :^.claude` 빈 줄이면 discard_changes=true).
  - yolo keyword (yolo / auto / 끝까지 / 막힘 없이 / 다 알아서) — `/quick` `/product-plan` 둘 다 적용. catastrophic 훅 (§2.3) 은 hard safety 보존.
  - 신규 9 테스트 (`HelperAutomationTests`). 184/184 PASS.
  - PR2 후속: validator DESIGN_VALIDATION 추가 + `/impl` `/impl-loop` skill.
- **🔧 Skill bash PYTHONPATH wrapper** (`DCN-CHG-20260429-41`):
  - `scripts/dcness-helper` 신규 — BASH_SOURCE 기반 자기위치 추출 → PYTHONPATH 자동 설정. CLAUDE_PLUGIN_ROOT 의존 0.
  - 4 skill (`qa` / `quick` / `product-plan` / `init-dcness`) 의 helper 호출 일괄 wrapper 경유로 변경.
  - Manual smoke (`/qa`) 첫 helper 호출 ModuleNotFoundError 해결.
- **🚪 Plugin 활성화 게이트 + cross-project PYTHONPATH** (`DCN-CHG-20260429-40`):
  - `harness/session_state.py` — `is_project_active` / `enable_project` / `disable_project` + 4 CLI subcommand. plugin-scoped whitelist (`~/.claude/plugins/data/dcness-dcness/projects.json`) — CC `data/` 컨벤션 정합 + 글로벌 `~/.claude/` 오염 0.
  - hook 양쪽 (`hooks/session-start.sh` `hooks/catastrophic-gate.sh`) — PYTHONPATH=$CLAUDE_PLUGIN_ROOT prepend + `is-active` 게이트 (inactive 프로젝트 즉시 exit 0). hook 자체는 모든 프로젝트에서 호출되지만 dcness 미활성 프로젝트는 import 비용도 0.
  - `commands/init-dcness.md` 신규 — `/init-dcness` skill (현재 cwd 활성화 + 안내).
  - 신규 10 테스트 (`ProjectActivationTests`). 175/175 PASS.
  - manual smoke 사용자 발견에서 출발 — dcness install 후 hook 미발화 + cross-project ModuleNotFoundError. 두 문제 동반 해결.
- **🌲 Worktree 격리 옵션 C** (`DCN-CHG-20260429-39`):
  - `harness/session_state.py` `_default_base()` γ 설계 — `git rev-parse --git-common-dir` 로 main repo `.claude/harness-state/` 를 단일 source. cwd 별 캐시. 비-git 폴백 보존.
  - `commands/quick.md` / `commands/product-plan.md` Step 0a — keyword (`worktree` / `wt` / `격리` / `isolate`) 트리거 시 EnterWorktree, 종료 step 에 ExitWorktree 옵션.
  - `docs/conveyor-design.md` §13 신규 — 옵션 검토 (A/B/C/D) + γ 설계 + skill protocol + EnterWorktree 룰 정합.
  - 신규 5 테스트 (전체 165/165 PASS).
  - v2 후속: 자동 cleanup / PR merge 감지 / 옵션 D 디폴트 마이그레이션.
- **🧪 Conveyor 인프라 Step 4 — multi-session e2e smoke** (`DCN-CHG-20260429-35`):
  - `tests/test_multisession_smoke.py` 신규 (11 케이스):
    - bash 훅 파이프라인 (4) — 실 subprocess 호출 + 부수효과 검증
    - 멀티세션 격리 (3) — 두 cc_pid by-pid / live.json 격리 + 동시 Popen race 검증
    - catastrophic 룰 e2e (4) — engineer/pr-reviewer/HARNESS_ONLY 차단 + 통과 매트릭스
  - 신규 11 테스트 (전체 160/160 PASS).
  - 한계: 실 Claude Code 환경의 PPID 신뢰성 / stdin payload 형식 = 별도 manual smoke follow-up.
- **🚀 Conveyor 인프라 Step 3 — 훅 인프라** (`DCN-CHG-20260429-34`):
  - `harness/hooks.py` (~280 LOC) — Python 훅 핸들러 (SessionStart + PreToolUse Agent)
  - `hooks/session-start.sh` + `hooks/catastrophic-gate.sh` — bash 래퍼 (PPID 캡처 + python 호출)
  - `hooks/hooks.json` — plugin 활성 시 자동 등록 (RWHarness 패턴 정합)
  - HARNESS_ONLY_AGENTS (engineer / validator-PLAN/CODE/BUGFIX_VALIDATION) + §2.3 4룰 (1/3/4) 강제
  - 신규 28 테스트 (전체 149/149 PASS).
- **🚀 Conveyor 인프라 Step 2 — `session_state.py` 확장 (by-pid 레지스트리 + CLI)** (`DCN-CHG-20260429-33`):
  - by-pid 레지스트리 함수 8개 (`.by-pid/{cc_pid}` sid 매핑 + `.by-pid-current-run/{cc_pid}` rid 매핑) — 멀티세션 정합 핵심.
  - PPID chain walker (`os.getppid()` → bash → `ps` → CC main pid) — 환경변수 휘발성 우회.
  - CLI subcommand 5개 (`init-session/begin-run/end-run/begin-step/end-step`) — argparse 진입점.
  - 신규 20 테스트 (전체 121/121 PASS).
- **📐 Conveyor 디자인 v2 — `docs/conveyor-design.md` rewrite** (`DCN-CHG-20260429-32`, PR #31 머지):
  - PR #29 v1 (Python `run_conveyor`) 폐기 후 Task tool + Agent + helper + 훅 패턴 채택.
  - 12 절 모두 갱신. 멀티세션 by-pid 레지스트리 layout 명시.
  - 폐기 사유 = subagent 호출이 Python 안에서 일어나면 PreToolUse 훅 미발화 + 사용자 가시성 0 + 메인 자율도 0.
- **🚀 Conveyor 인프라 Step 1 — `harness/session_state.py` 신규** (`DCN-CHG-20260429-30`):
  - OMC `SkillActiveStateV2` (active_runs map, soft tombstone, heartbeat) + RWH `_meta` envelope + 3-tier resolution (글로벌 폴백 제외) + atomic write (O_EXCL+fsync+rename+dir fsync, 0o600) 차용.
  - 14 함수 export — session_id 검증/추출/resolution, session pointer R/W, run_id 생성, atomic_write, session_dir/run_dir/live_path, read_live/update_live, start_run/update_current_step/complete_run, cleanup_stale_runs.
  - 49 신규 테스트 (전체 101/101 PASS).
  - **컨베이어 spec** (`docs/conveyor-design.md` PR #29) 의 첫 코드 구현. 후속 Task 들 (-31 impl_driver / -32 SessionStart hook / -33 catastrophic-gate hook) 의 인프라 기반.
- **🎯 Conveyor 디자인 spec — `docs/conveyor-design.md`** (`DCN-CHG-20260429-29`, PR #29 머지):
  - 메인 클로드 = 시퀀스 결정자, 컨베이어 = 멍청한 순회기, catastrophic = PreToolUse 훅. 12 절 660 줄.
  - PR #28 (옵션 c JSON 결정자) close 후 새 spec. proposal §2.5 (prose-only) 정합.
- 거버넌스 시스템 부트스트랩 완료 (`DCN-CHG-20260429-01`, PR #1 머지)
- 프로젝트 루트 `CLAUDE.md` + 루트 정책 파일 게이트 분류 추가 (`DCN-CHG-20260429-02`)
- **Plugin 배포 인프라**: `.claude-plugin/{plugin,marketplace}.json` (`DCN-CHG-20260429-04`)
  - 이름 = `dcness`, 버전 = `0.1.0-alpha`. RWHarness 와 공존 가능 설계.
- **모듈 분류 framework 적용**: `docs/migration-decisions.md` (`DCN-CHG-20260429-05`)
- **CI 게이트 3종**: Document Sync (`-08`) / Python tests (`-09`) / Plugin manifest (`-10`)
- **README + AGENTS 보강**: `-11`, `-12`
- **🎉 Phase 2 iter 5 (FINAL) — ux-architect + product-planner prose-only** (`DCN-CHG-20260429-19`):
  - `agents/ux-architect.md` (UX_FLOW_READY / UX_FLOW_PATCHED / UX_REFINE_READY / UX_FLOW_ESCALATE) — UX_FLOW + UX_SYNC + UX_SYNC_INCREMENTAL + UX_REFINE 4 모드 inline + Anti-AI-Smell + 카테고리 클리셰 회피 + 라이트/다크 두 모드 의무 + Outline-First
  - `agents/product-planner.md` (PRODUCT_PLAN_READY / CLARITY_INSUFFICIENT / PRODUCT_PLAN_CHANGE_DIFF / PRODUCT_PLAN_UPDATED / ISSUES_SYNCED) — Phase 1 (요구사항) + Phase 2 (기능 스펙) + Phase 3 (4 옵션 스코프) + Diff-First 변경 처리 + ISSUE_SYNC
  - **Phase 2 종결**: 13 agent docs 모두 prose-only 변환 완료 (validator iter 0 + 4 read-only iter 1 + 8 architect iter 2 + 2 engineer/test-engineer iter 3 + 2 designer/critic iter 4 + 2 ux/planner iter 5)
- **🚀 Phase 2 iter 4 — designer + design-critic prose-only** (`DCN-CHG-20260429-18`):
  - `agents/designer.md` (DESIGN_READY_FOR_REVIEW / DESIGN_LOOP_ESCALATE) — 2×2 매트릭스 (SCREEN/COMPONENT × ONE_WAY/THREE_WAY) 4 모드 + Phase 0 (이슈 생성, Pencil 캔버스) + Phase 1 (variant 생성) + Phase 4 (DESIGN_HANDOFF, outline-first) + 차별화 의무 + View 전용 원칙
  - `agents/design-critic.md` (VARIANTS_APPROVED / VARIANTS_ALL_REJECTED / UX_REDESIGN_SHORTLIST) — 4 기준 (UX 명료성·미적 독창성·컨텍스트 적합성·구현 실현성) 각 10점, 총 40점, PASS 28+ 기준
- **🚀 Phase 2 iter 3 — engineer + test-engineer prose-only** (`DCN-CHG-20260429-17`):
  - `agents/engineer.md` (IMPL_DONE / SPEC_GAP_FOUND / IMPLEMENTATION_ESCALATE / TESTS_FAIL / POLISH_DONE) — Phase 1 스펙 검토 + Phase 2 구현 + 듀얼 모드 + DESIGN_HANDOFF + 재시도 한도 + 커밋 단위 룰
  - `agents/test-engineer.md` (TESTS_WRITTEN / SPEC_GAP_FOUND) — TDD attempt 0 전용, src/ 읽기 금지 (catastrophic-prevention), impl `## 생성/수정 파일` 경로만 사용
- **🚀 Phase 2 iter 2 — architect 8 docs prose-only** (`DCN-CHG-20260429-16`):
  - `agents/architect.md` (마스터, 7 모드 인덱스 + Outline-First 자기규율 + TRD 현행화 룰)
  - `agents/architect/system-design.md` (SYSTEM_DESIGN_READY)
  - `agents/architect/module-plan.md` (READY_FOR_IMPL — depth/design frontmatter, DB 영향도 분석, 듀얼 모드 가드레일)
  - `agents/architect/spec-gap.md` (SPEC_GAP_RESOLVED / PRODUCT_PLANNER_ESCALATION_NEEDED / TECH_CONSTRAINT_CONFLICT)
  - `agents/architect/task-decompose.md` (READY_FOR_IMPL — Outline-First, 듀얼 모드 가드레일)
  - `agents/architect/tech-epic.md` (SYSTEM_DESIGN_READY)
  - `agents/architect/light-plan.md` (LIGHT_PLAN_READY — bugfix / DESIGN_HANDOFF / REVIEW_FIX / DOCS_UPDATE)
  - `agents/architect/docs-sync.md` (DOCS_SYNCED / SPEC_GAP_FOUND / TECH_CONSTRAINT_CONFLICT)
  - 모두 prose writing guide. `---MARKER:X---` 텍스트 마커 + `@OUTPUT` JSON schema + preamble / agent-config 별 layer 의존 폐기.
- **🚀 Phase 2 iter 1 — 4 read-only agents prose-only** (`DCN-CHG-20260429-15`):
  - `agents/pr-reviewer.md` (LGTM / CHANGES_REQUESTED) — validator 와 역할 분리, 스코프 매트릭스, 레거시 처리
  - `agents/plan-reviewer.md` (PLAN_REVIEW_PASS / PLAN_REVIEW_CHANGES_REQUESTED) — 8 차원 (현실성·MVP·제약·UX·숨은가정·경쟁·BM·기술실현)
  - `agents/qa.md` (FUNCTIONAL_BUG / CLEANUP / DESIGN_ISSUE / KNOWN_ISSUE / SCOPE_ESCALATE) — 역질문 루프, MCP+tracker CLI 폴백
  - `agents/security-reviewer.md` (SECURE / VULNERABILITIES_FOUND) — OWASP Top 10 + WebView 특화
  - 모두 prose writing guide 형식. `---MARKER:X---` 텍스트 마커 + `@OUTPUT_*` JSON schema + preamble 자동주입 / agent-config 별 layer 의존 모두 폐기.
- **🧹 stale 참조 sweep** (`DCN-CHG-20260429-14`): CLAUDE.md test 명령어 + python-tests.yml 헤더 + marketplace.json description/tags + .gitignore 코멘트 + migration-decisions framework 표현을 prose-only 로 정정. history record 항목은 governance §2.4 스코핑 정합으로 미수정.
- **🔄 Phase 1 재정렬 — Prose-Only Pattern** (`DCN-CHG-20260429-13`):
  - **proposal 갱신**: `docs/status-json-mutate-pattern.md` 가 *Prose-Only Pattern* 으로 정정. 형식 강제 자체가 사다리를 부른다는 자각 — JSON schema 도 형식 사다리의 한 형태. harness 강제 = 작업 순서 + 접근 영역만, 그 외는 agent 자율.
  - **폐기**: `harness/state_io.py` (~290 LOC) + `tests/test_state_io.py` (32) + `tests/test_validator_schemas.py` (9). JSON schema 강제 자체가 형식 사다리 잠재.
  - **신규**: `harness/signal_io.py` (~290 LOC) — `write_prose` / `read_prose` / `interpret_signal` (휴리스틱 + DI swap) / `MissingSignal` (3 reason).
  - **테스트**: `tests/test_signal_io.py` 29 PASS — round-trip / path 화이트리스트 / 휴리스틱 (단어경계·case-insensitive·다중매칭) / DI / clear_run_state.
  - **validator agent docs 6 재작성**: `@OUTPUT_*` 형식 강제 제거 → prose writing guide. 각 모드별 결론 enum 만 명시 (PASS / FAIL / SPEC_MISSING / ESCALATE 등).
  - 메타 LLM (haiku) 통합은 `interpreter=` DI swap point 로 남김 — 후속 Task-ID.

## TODO

### Phase 1 — Foundation (prose-only) ✅
모든 acceptance 항목 완료. dcNess 메인 작업 모드(`status-json-mutate-pattern.md` §11.4) 정합으로 RWHarness `harness/core.py` 의 parse_marker 호출지 / agent-boundary hook ALLOW_MATRIX / `_AGENT_DISALLOWED` 변경은 본 저장소엔 미도입 (plugin 배포 시점 사용자 프로젝트 가드용).

### Phase 2 — 메타 LLM 통합 + 다른 12 agent docs (진행 중)

**다음 iteration 시작점**: `git log --oneline` + 본 PROGRESS 의 진행도 확인 후 다음 묶음 picker.

- [ ] Anthropic SDK 통합 — `interpret_signal` 의 메타 LLM interpreter 구현 (haiku, cycle 당 비용 측정 — proposal R8)
- [ ] ambiguous prose 카탈로그 — `MissingSignal(ambiguous)` raise 시 `.metrics/ambiguous-prose.jsonl` 누적 (proposal R1 acceptance)
- [ ] 다른 agent docs 를 prose writing guide 로 변환:
  - [x] **iter 1 완료** (DCN-CHG-20260429-15): `agents/pr-reviewer.md`, `agents/plan-reviewer.md`, `agents/qa.md`, `agents/security-reviewer.md`
  - [x] **iter 2 완료** (DCN-CHG-20260429-16): `agents/architect.md` + 7 mode sub-doc
  - [x] **iter 3 완료** (DCN-CHG-20260429-17): `agents/engineer.md` + `agents/test-engineer.md`
  - [x] **iter 4 완료** (DCN-CHG-20260429-18): `agents/designer.md` (4 모드 inline) + `agents/design-critic.md`
  - [x] **iter 5 완료** (DCN-CHG-20260429-19): `agents/ux-architect.md` + `agents/product-planner.md` — Phase 2 13 agents 종결 🎉

### Phase 3 — GitHub 외부화 + Sweep ✅ (종결, 5/5 iter)

> proposal §5 Phase 3 정합 — RWHarness `commit-gate.py` Gate 1/4/5 → GitHub Actions 외부화.
> dcNess 는 commit-gate.py 미도입(migration-decisions §2.2 DISCARD)이라 *자연 외부화* — 신규 워크플로우만 추가.
> proposal §6 의 4 acceptance 모두 PASS (자연 만족 2 + 신규 1 + 비대상 1) + dcNess 한정 추가 5 항목 모두 PASS.

- [x] **iter 1 완료** (DCN-CHG-20260429-20): Task-ID 형식 검증 워크플로 + 스크립트 — `scripts/check_task_id.mjs` + `.github/workflows/task-id-validation.yml`. 모든 비-머지 커밋이 `DCN-CHG-YYYYMMDD-NN` 토큰 정확히 1개 포함하는지 PR/push 단위로 차단. PR title 도 동시 검증. 머지 커밋 면제(squash 합본). proposal §11 4-pillar #2 (CI 최후 차단) 정합.
- [x] **iter 2 완료** (DCN-CHG-20260429-21): branch protection 적용 스크립트 + 가이드 — `scripts/setup_branch_protection.mjs` (멱등 PUT, dry-run 지원) + `docs/process/branch-protection-setup.md` (자동/수동/검증) + `governance.md` §2.8 신설. proposal §5 Phase 3 "Gate 5 (LGTM flag) → branch protection required reviewers" 외부화. RWHarness `class Flag` LGTM in-process 메커니즘은 dcNess 자연 폐기 (migration-decisions §2.2 DISCARD), GitHub branch protection 이 동일 역할 외부 강제. 4 status check (`Document Sync gate` / `unittest discover` / `validate manifest` / `Task-ID format gate`) + 1 approving review + force-push/삭제 차단 + linear history.
- [x] **iter 3 완료** (DCN-CHG-20260429-22): Anthropic SDK haiku interpreter 통합 — `harness/llm_interpreter.py` (신규, `make_haiku_interpreter()` 팩토리, mock client DI 지원, telemetry `.metrics/meta-llm-calls.jsonl`, ambiguous fallback) + `tests/test_llm_interpreter.py` (16 케이스, 실 SDK 호출 0). `harness/signal_io.py` 의 `interpret_signal(..., interpreter=)` swap point 가 프로덕션 가능 상태. proposal §3 비용 (~$0.0001/호출) + R8 telemetry 누적.
- [x] **iter 4 완료** (DCN-CHG-20260429-23): heuristic-first + LLM-fallback 합성 전략 + telemetry 분석기 — `harness/interpret_strategy.py` (신규, `interpret_with_fallback()` 합성, outcome 5종 telemetry) + `tests/test_interpret_strategy.py` (7 케이스) + `scripts/analyze_metrics.mjs` (heuristic + LLM JSONL 집계, outcome 분포 / 비용 / 모델별 / allowed enum 별 / 최근 ambiguous 샘플 5개 / Phase 4 fitness 목표 자동 판정). `tests/test_llm_interpreter.py` 의 telemetry_dir 누락 3 케이스 fix (cwd `.metrics/` 오염 회피). 52/52 PASS. proposal R1 (ambiguous 카탈로그) + R8 (cycle 당 비용 측정) + §5 Phase 4 fitness 측정 인프라 완성.
- [x] **iter 5 완료** (DCN-CHG-20260429-24): Phase 3 종결 + `docs/process/plugin-dryrun-guide.md` (신규 — proposal §12 절차 풀어쓴 운영 가이드, 11 섹션: 사전검증 → manifest → marketplace → 충돌회피 → smoke test → 1 cycle 도그푸딩 → 완전 제거/롤백 → acceptance → Phase 4 후속). `docs/status-json-mutate-pattern.md` §6 Phase 3 acceptance 4 항목 모두 PASS 표시 (자연 만족 2 + 신규 워크플로 1 + RWHarness 외 1) + dcNess 한정 5 항목 추가 PASS.
- [x] **사후 보강** (DCN-CHG-20260429-25): **오케스트레이션 SSOT** — `docs/orchestration.md` 신규 작성. RWHarness `harness-spec.md` §4.2 (게이트 시퀀스) + §4.3 (진입 경로) + `harness-architecture.md` §3 (호출 권한 + Write/Read 가드 + INFRA_PATTERNS) 통합. 11 섹션 (정체성·적용모드·게이트시퀀스 mermaid·진입경로 mini graph 6개·결론 enum 결정표·retry 한도·escalate 카탈로그·핸드오프 매트릭스·catastrophic vs 자율·코드 driver 보류 옵션 a/b/c·proposal 인용). 형식 강제 어휘 (`---MARKER---` / `_handoffs/` / `class Flag`) 모두 dcNess prose + signal_io 표현으로 변환. proposal §2.5 원칙 4 + §11.4 직접 인용. Phase 1~3 작업 (agents/*.md / signal_io / 거버넌스) 의 *시퀀스 정의 spec* 부재를 보강 — 사용자 지적 정합. 옵션 (c) Orchestration Agent + 동적 시퀀스 (parameter-driven, 메타 LLM 동적 갱신, catastrophic backbone 강제) 신규 발상으로 §9 에 박음.
- [x] **사후 보강** (DCN-CHG-20260429-26): **agents/*.md 형식 어휘 일괄 폐기** — 외부 review 지적 반영. `@MODE:X:Y` 헤더 메타 / `@PARAMS:` JSON 블록 / `@CONCLUSION_ENUM:` 라인 / `@OUTPUT JSON schema` 본문 메모를 24 파일 모두에서 자연어로 변환. 177 → 0 hit. 헤더 메타 블록 → "**모드** / **결론** / **호출자가 prompt 로 전달하는 정보**" 자연어 3 라인. 표 안 `@MODE:` 접두사 → mode 이름만 남김. "폐기된 컨벤션 (참고)" 본문은 *원리 보존* + 형식 어휘 제거 (proposal §2.5 정합 명시). 형식 사다리 부활 risk 차단.
- [x] **사후 보강** (DCN-CHG-20260429-27): **agents/*.md 자율성 강화 일괄 정리** — proposal §2.5 정신 (작업 순서 + 접근 영역만 강제, 그 외 agent 자율) 정합으로 24 파일 압축. **4350 → 1683 줄 (61% 감소)**, 모든 파일 ≤ 150 줄. 변환 6 원칙: (A) frontmatter = 자기인식 → "🔴 정체성" 강박 섹션 + "절대 출력 금지 패턴" list 폐기 → 1 줄 메타. (B) 원칙 1 줄 + 자율 판단. (C) Phase/Step 강박 → "수행 흐름 (자율 조정 가능)" 1 단락. (D) 산출물 마크다운 템플릿 → "정보 의무 (형식 자유)" 권고만. (E) 결론 enum 예시 반복 → 헤더 1 회. (F) 다중 체크리스트 → catastrophic 1~2 + 권고 prose. 페르소나 1~2 줄 압축. Anti-AI-Smell 가치 메타는 1 단락 압축. 폐기된 컨벤션 섹션 제거 (orchestration.md / status-doc 참조로 대체). 모든 파일 끝에 cross-link 1 단락. 코드 변경 0, 회귀 0.

### Phase 3 acceptance 매핑 표

| proposal §6 Phase 3 항목 | dcNess 결과 | 근거 |
|---|---|---|
| commit-gate.py Gate 1/4/5 코드 0 | ✅ 자연 만족 | migration-decisions §2.2 — commit-gate.py DISCARD |
| `.github/workflows/*` 3+ 신설 | ✅ **4 워크플로** | document-sync(`-08`) + python-tests(`-09`) + plugin-manifest(`-10`) + task-id-validation(`-20`) + branch protection 룰(`-21`) |
| ENV 게이트 (`HARNESS_PROSE_*`) 모두 제거 | ✅ 자연 만족 | dcNess 도입 0 |
| CHG-14.1 폐기 정정 | ✅ 비대상 | RWHarness 영역 |
| (dcNess 추가) Task-ID 형식 검증 | ✅ | `DCN-CHG-20260429-20` |
| (dcNess 추가) LGTM 외부화 | ✅ | `-21` (branch protection) |
| (dcNess 추가) haiku interpreter | ✅ | `-22` |
| (dcNess 추가) heuristic-fallback + analyzer | ✅ | `-23` |
| (dcNess 추가) plugin dry-run 가이드 | ✅ | `-24` |

### Phase 4 — 4 기둥 fitness 측정 (다음)

> proposal §5 Phase 4 진입 전제: Phase 1~3 모두 PASS (✅ 본 PR 머지 후 충족).

- [ ] 컨텍스트 layer 5 → 2 측정 (CLAUDE.md + agents/*.md + AGENTS.md + ...)
- [ ] hook 갯수 7 → 3 (catastrophic 만) — dcNess 자연 만족 (hooks/ 디렉토리 0)
- [ ] LOC 순감소 5000 → 2500~3000 (RWHarness baseline 비교)
- [ ] 형식 강제 호출지 0 (parse_marker / flag_touch / write_handoff) — dcNess 자연 만족
- [ ] poor_cache_util 비용 $507 → $200 미만 (improve-token-efficiency 측정)
- [ ] 메타 LLM cycle 당 < $0.10 (analyzer fitness PASS — 본 Phase 3 인프라 완성)
- [ ] catastrophic 가드 무손실 (의도적 src/ 외 수정 → 차단 검증)
- [ ] **plugin 배포 dry-run** (`docs/archive/plugin-dryrun-guide.md` §1~§9 절차 실행)

### 인프라 / CI 보강
- [ ] branch protection 룰 추가 (사용자 수동, GitHub Settings)
- [ ] CLAUDE.md §6 환경변수 — 도입 시 갱신

## Blockers
- 없음
