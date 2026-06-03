# 릴리즈 노트

> 버전별 변경 요약. 상세 커밋은 `git log {prev_tag}..{tag}` 참조.

---

## v0.4.0 (2026-06-04)

**커밋 범위**: `v0.3.0..v0.4.0`
**핵심 변경**: `commands/*.md` → `skills/<name>/SKILL.md` 승격 (7 skill) + 라우팅을 각 skill 옆 `<name>-routing.md` 단일 진본으로 분산 + 전역 SSOT (`orchestration.md` / `handoff-matrix.md` / 전역 `routing.md`) 폐기. 부수 — Codex read-only validator skills 3종 신설 + harness 코드 다이어트 + agent 기능 강화 + 문서 컨벤션 SSOT 신설.

### 무엇이 바뀌나

1. **commands → skills 전환 (7 skill)** — `architect-loop` / `impl-loop` / `impl` / `issue-report` / `product-plan` / `tech-review` / `ux` 를 `commands/<name>.md` 단일 파일에서 `skills/<name>/SKILL.md` (진행 절차) + `skills/<name>/<name>-routing.md` (라우팅 SSOT — mermaid + 결론→다음 매핑 + retry 한도 + escalate) 디렉토리로 승격. SKILL.md 경량화. frontmatter `name` 동일 → 사용자 호출 방식 (`/architect-loop`·`/impl` 등) 그대로. plugin.json 무변경 (skills/ 자동 스캔, namespace `dcness:<name>`). 옛 `commands/<name>.md` 삭제 (동일 name 중복 등록 충돌 회피). 남은 commands = `efficiency` / `init-dcness` / `run-review` / `smart-compact`.

2. **라우팅 SSOT 분산 + 전역 집계 파일 폐기** — `docs/plugin/orchestration.md` + `handoff-matrix.md` + 전역 `routing.md` 폐기. 통찰 = "라우팅은 skill 이 소유, agent 는 결론(enum)만 낸다". 런타임에 안 읽히던 전역 집계 view(중복)를 각 skill 옆 `<name>-routing.md` 단일 진본으로 이전.

3. **Codex read-only validator skills 신설** — `code-validator` / `architecture-validator` / `pr-reviewer` 3종을 Codex read-only 실행으로 route 가능. `codex/skills/dcness-*/SKILL.md` + `scripts/dcness-codex-validator` wrapper (Codex read-only sandbox + prose 수집 + end-step 저장 + mutation guard) + `harness/agent_routing.py` (local routing). **사용자 repo 에 파일 안 만듦** — `~/.claude/plugins/data/dcness-dcness/routing.json` + `$CODEX_HOME/skills/` 에만. read-only 3종 한정(mutation agent migration 차단).

4. **harness 코드 다이어트** — `harness/interpret_strategy.py` + `scripts/analyze_metrics.mjs` + `tests/eval_{deepeval,agentevals}.py` 삭제 (enum 추출 / 전략 해석 / 외부 eval 의존 제거). `harness/agent_routing.py` + `harness/prev_tasks.py` 신규.

5. **agent 기능 강화** — architecture-validator premortem 시뮬레이션 + origin anchor provenance 검증 / tech-reviewer → system-architect signal 전달 / 신규 의존 경량 escalate (G3) / tech-stack grill checkpoint / UI-less 화면 ux skip gate / impl-loop prev-tasks 컨텍스트 inject + dry-run preview.

6. **문서 컨벤션 SSOT + 정리** — `docs/internal/doc-conventions.md` 신규 (문서 작성 규약 단일 진본). anchor-ref 마이그레이션 (§N 참조 → 제목 자연어), codeblock/주석 stale-ref 자연어화, routing/loop 중복 다이어트, README·manifest sync, loop-procedure 단일 목적 슬림화.

### 사용자 영향

- **외부 활성 프로젝트: `claude plugin update dcness@dcness` 로 skills 전환 자동 반영** — 호출 방식 (`/architect-loop`·`/impl-loop`·`/impl`·`/issue-report`·`/product-plan`·`/tech-review`) 그대로. 옛 `commands/<name>.md` 는 삭제됐지만 같은 namespace 로 skills 가 등록돼 동작 동형. (런타임 트리거 100% 확인은 사용자 환경에서 한 번 호출.)
- **Codex validator 쓰려면 `/init-dcness` 재실행** — plugin update 후 `/init-dcness` 재실행 시 Step 2.10 에서 `$CODEX_HOME/skills/dcness-*` 복사 + routing opt-in (Y/n). 끄기 = `dcness-helper routing disable-codex-validation`. opt-in 안 하면 기존 (메인 Claude in-session) validator 그대로.
- **옛 전역 SSOT 앵커 참조** — `orchestration.md` / `handoff-matrix.md` / 전역 `routing.md` 의 §N 앵커 참조는 전부 각 skill routing.md 또는 제목 자연어로 마이그레이션됨. 외부 사용자가 직접 참조하던 링크 없으면 영향 없음.

### 업데이트

```sh
claude plugin update dcness@dcness
# Codex validator 까지 쓰려면:
/init-dcness   # 재실행 → Step 2.10 routing opt-in
```

---

## v0.3.0 (2026-05-26)

**커밋 범위**: `v0.2.34..v0.3.0`
**핵심 변경**: `/architect-loop` 의 책임 구조 재설계 — system-architect 책임 좁힘 + module-architect 책임 확장 + Story 묶음 단위 호출 + architecture-validator 영역 갱신 (Spike Gate 폐기 + Cross-Story Interface + 공통 SSOT 룰 위반) + 모듈 설계 원칙 공통 SSOT 신설 ([#511](https://github.com/alruminum/dcNess/issues/511)). plug-in major bump — 옛 구조 epic 의 architect-loop 재진입은 자율, 새 epic 부터는 새 구조 강제.

### 무엇이 바뀌나

1. **system-architect 책임 좁힘** — 옛 구조에서는 도메인 모델 + 모듈 구조 + 기술 스택 + Story → impl 매핑 표 + Spike Gate 까지 다 책임 (한 호출에 task 27 개 outline 부담). 새 구조 = 전체 시스템 그림만 — root `docs/architecture.md` (기술 스택 + 외부 의존 + 전체 모듈 토폴로지) + root `docs/adr.md` (전체 시스템 수준 의사결정) + epic 단위 architecture.md (모듈 목록 + 의존 그래프 + 공통 task 목록 + Story → 모듈 매핑) + epic 단위 adr.md + epic 단위 domain-model.md. 페르소나 한 줄 정의 폐기 + 작업 명세 (What / When / DoD) 형식 ([#515](https://github.com/alruminum/dcNess/issues/515) 의 tech-reviewer 패턴 정합). `## impl 목차` 표 폐기. Spike Gate 별도 phase 폐기 (tech-reviewer 가 PRD 단계 cover, 차단 패턴 한 줄만 자기 규율로 흡수).

2. **module-architect 책임 확장 — Story 묶음 단위** — 한 호출 = 한 Story 단위 = N 개 impl 파일 작성 + 단위 안 task 식별 + 의존 순서 결정 + cross-task interface 정합 검증 + 도메인 sync. Story → 작업 매핑 + task 분할 책임 (옛 system-architect 영역) 흡수. K (호출 수) = Story 수 + 공통 호출 1 회 (공통 task 있으면) 또는 0 회. 옛 task 단위 K (~27) 와 다르게 새 K 는 Story 묶음 단위라 ~5+α 영역.

3. **architecture-validator 영역 갱신** — 3 영역 검증 — **Placeholder Leak (유지) + Cross-Story Interface 정합성 (옛 Cross-Task Interface 에서 변경 — Story 안은 module-architect self-check 가 cover, Story 간만 validator 영역) + 공통 SSOT 룰 위반 (신규 — 순환 의존 / 미허가 의존 / public API contract 위반 자동 영역 + Deep Modules / 부작용 없는 반환 수동 review 권고 영역 분리)**. Spike Gate 폐기. `/architect-loop` 안에서 두 시점 호출 — Step 3.5 (system-architect 직후, Placeholder + 공통 SSOT) + Step 5 (module 다 끝난 후, Cross-Story Interface).

4. **공통 SSOT 신설 — [`docs/plugin/module-design-principles.md`](../plugin/module-design-principles.md)** — 세 영역 룰을 한 곳에 모음 — Deep Modules (John Ousterhout, "A Philosophy of Software Design") + Interface Design for Testability ([mattpocock skills](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/interface-design.md)) + 의존성 강제 세 영역 (순환 의존 / 미허가 의존 빌드 시점 차단 / 모듈 공개·비공개 영역 구분 강제 / DI 강제). system / module / engineer / test-engineer 의 호출 시 read 의무. drift 차단 + agent 본문 분량 ↓.

5. **batch 모드 폐기** — 옛 `/architect-loop` 의 batch 모드 (K ≥ 8 시 Story 단위 묶음 1 호출) 폐기. Story 묶음 자체가 batch 의 본질 해결.

6. **폴더 구조 SSOT 명확화 — system-wide + epic 단위 분리** — 옛 구조에서는 stories.md 위치 영역이 product-plan.md 와 architect-loop.md 사이 drift 가 있어 외부 사용자 프로젝트마다 메인 Claude 가 임의로 위치 결정 (jajang 은 epic 폴더 안 / youtube-gen 은 docs root). 새 구조 = root (`docs/prd.md` + `docs/tech-review.md` + `docs/architecture.md` + `docs/adr.md`) + epic 단위 (`docs/milestones/vNN/epics/epic-NN-*/stories.md` + architecture.md + adr.md + domain-model.md + ux-flow.md + impl/). PRD 는 root 단일 (제품 1 개 = PRD 1 개), milestone 진화는 같은 파일 안 영역 갱신.

### 사용자 영향

- **옛 epic 의 architect-loop 재진입은 자율** — architecture.md 의 `## impl 목차` 표가 들어있는 epic 은 새 구조와 충돌. 메인 Claude 가 강제 차단은 안 하되 옛 표 영역 의미가 사라짐 (`task_index` 의미 = 그 Story 안 task 순번으로 변경). 옛 epic 영역에서 새 architect-loop 호출 시 system-architect 가 epic 단위 architecture.md 신규 작성 영역으로 진행.
- **새 epic 부터는 새 구조 강제** — `/product-plan` 진입 시 epic 단위 stories.md 위치 (`docs/milestones/vNN/epics/epic-NN-<slug>/stories.md`) 영역으로 자동 작성. `/architect-loop` 영역도 같은 epic 경로 위에서 진행.
- **옛 batch 호출 코드 즉시 실패** — `/architect-loop` 의 batch 모드 명시 호출 영역은 v0.3.0 후 작동 안 함. 자연 폐기 (Story 묶음으로 갈음).
- **외부 사용자 dcness plug-in 갱신 명령** — `claude plugin update dcness@dcness`. 문제 발생 시 uninstall → install fallback (`claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness`).

### 옛 root 단위 stories.md (youtube-gen 패턴) 마이그레이션 가이드

옛 `docs/stories.md` (root) 영역을 새 구조로 옮길 때:

1. 기존 `docs/stories.md` 안 epic 헤더 영역 식별 (예: `## Epic — <설명>`)
2. 새 디렉토리 생성 — `docs/milestones/vNN/epics/epic-NN-<slug>/`
3. `docs/stories.md` 내용을 새 디렉토리 안 `stories.md` 로 이동
4. 같은 디렉토리에 architecture.md / adr.md / domain-model.md 신규 작성 (`/architect-loop` 호출 시 system-architect 가 자동 신규 작성)
5. `docs/stories.md` (root) 영역은 archive 또는 삭제 (`git rm`)
6. GitHub 이슈 등록 영역은 그대로 유지 (재등록 불필요) — 이슈 본문의 stories.md 경로 영역만 새 경로로 patch

### 옛 epic 단위 stories.md (jajang 패턴) 영역의 변화

기존 epic 단위 stories.md 영역 (예: `docs/milestones/v1/epics/epic-08-*/stories.md`) 은 위치 영역이 새 구조와 정합. 단 옛 architecture.md / adr.md 가 root 단일 영역 (예: `docs/ARCHITECTURE.md`) 인 경우 — root architecture.md / adr.md 영역으로 갱신 (대문자 → 소문자) + epic 단위 architecture.md / adr.md / domain-model.md 신규 작성. `/architect-loop` 재호출 시 system-architect 가 자동 처리.

### 모노레포 영역 (별도 issue 예정)

모노레포 (workspace 여러 개) 대응은 본 v0.3.0 영역 외. `CONTEXT-MAP.md` / `package.json` 의 `workspaces` / `pnpm-workspace.yaml` / `turbo.json` / `nx.json` 마커 detect 시 메인 Claude 가 사용자에게 안내 + 본 영역 별도 GitHub issue 등록.

### 보강 영역 (출시 후 측정 + 후속)

- **Story 크기 가이드 추가** (`commands/product-plan.md` 영역, 현 [`skills/product-plan/SKILL.md`](../../skills/product-plan/SKILL.md)) — Story 1 개당 예상 task ≤ 5 권장 / Story 큰 경우 분할 권고 / cross-cutting Story 표시. module-architect 한 호출의 산출 부담 통제.
- **cross-cutting Story 빈도 측정** — 외부 활성 프로젝트의 epic 1-2 개를 새 구조로 수동 시뮬레이션. 빈도 ≥ 30% 면 Architecture Mode opt-in (stories.md 마커로 모듈 묶음 / Story 묶음 선택) 재검토.
- **module-architect 모델 검토** — 새 구조에서 한 호출의 판단 차원이 깊어짐. sonnet 으로 누락 / 회전 발생 시 opus 승격 검토.
- **validator 자동 / 수동 영역 분리 운영** — 자동 검증 통과 영역 + 수동 review 권고 영역 분리 명시. 사용자가 수동 review 권고 영역에 PASS 주면 완료.

---

## v0.2.34 (2026-05-26)

**커밋 범위**: `v0.2.33..v0.2.34`
**핵심 변경**: `plan-reviewer` agent 폐기 + `tech-reviewer` 신설 + `/tech-review` 스킬 분리 + 단방향 catastrophic 룰 ([#516](https://github.com/alruminum/dcNess/pull/516)). 부수 — impl-loop 강화 (review 5줄 / SPEC_GAP 예외 / 세션 분할 / phase prose lint) + architect-loop batch + interface 정합성 검증 + SSOT cross-ref CI 게이트 + PR/git 인프라 다듬기 + CLAUDE.md 사용자 정체성 최상단 승격.

### 무엇이 바뀌나

1. **`plan-reviewer` 폐기 → `tech-reviewer` 신설 + `/tech-review` 스킬 분리** ([#516](https://github.com/alruminum/dcNess/pull/516)) — 옛 8 차원 (현실성 / MVP / 제약 / UX / 숨은가정 / 경쟁 / 과금 / 기술실현) reviewer 가 메인 그릴미와 §1~§5 중복 + 사후 self-check 의미 약함 (이슈 [#515](https://github.com/alruminum/dcNess/issues/515)). 새 정체성 = 페르소나 폐기 + 작업 명세 (What / When / DoD) 형식 + 책임 2 축 (기술 제약 검토 4 항목 / 용도별 스펙 깎기). Bash + Write 권한 부여 (`docs/tech-review.md` + `docs/tech-review/**` 한정) — 실측 + 증거물 (음성 / 이미지 / 로그) + 통합 HTML 리포트 (`docs/tech-review/report.html`) 산출. 워크플로우 = `/product-plan` (PRD + 스켈레톤) → 사용자 1 차 OK → `/tech-review` (본문 + evidence + HTML) → 사용자 2 차 OK → `/architect-loop`. **단방향 catastrophic** — `/architect-loop` 진입 후 tech-reviewer 재호출 금지 (회귀 사고 패턴 차단). 옛 plan-reviewer 호출 코드 (`Agent(subagent_type="plan-reviewer", ...)`) 는 plug-in update 후 즉시 실패 — 외부 활성 프로젝트는 `/tech-review` 로 이행 필요. `system-architect.md:101` ADR 4 카테고리 사후 self-check 룰도 같이 폐기 (선행 검증 = tech-reviewer 가 cover). 사용자 환경 `.gitignore` 에 `docs/tech-review/evidence/` + `docs/tech-review/report.html` 수동 추가 권고 (init-dcness 자동 추가 X — overwrite 위험).

2. **impl-loop 강화 — review 5줄 강제 + SPEC_GAP 예외 + 세션 분할** ([#513](https://github.com/alruminum/dcNess/pull/513) / [#514](https://github.com/alruminum/dcNess/pull/514)) — pr-reviewer return prose 5 줄 강제 + 다시 그리기 trade-off 명시 + 세션 분할 권장 (F8+F9+F13). build-worker 의 경량 SPEC_GAP 예외 + phase prose path 명시 + lint 강제 (F4+F7+F12). 매 task return 누적이 메인 컨텍스트 부풀게 하던 회귀 차단.

3. **architect-loop batch 모드 + cross-task interface 정합성 검증** ([#512](https://github.com/alruminum/dcNess/pull/512)) — architect-loop §4.2 module-architect × K 가 batch 호출 가능 (개별 호출 누적 비용 절감). architecture-validator 가 cross-task interface 정합성 검증 책임 추가 (F6+F11). handoff-matrix + orchestration §4.2 drift 동시 갱신 룰 박음 ([#505](https://github.com/alruminum/dcNess/issues/505)).

4. **SSOT 정리 — cross-ref CI 게이트 + dead link / 옛 명칭 회귀 차단** ([#495](https://github.com/alruminum/dcNess/pull/495) / [#496](https://github.com/alruminum/dcNess/pull/496) / [#497](https://github.com/alruminum/dcNess/pull/497) / [#498](https://github.com/alruminum/dcNess/pull/498) / [#499](https://github.com/alruminum/dcNess/pull/499) / [#500](https://github.com/alruminum/dcNess/pull/500)) — `scripts/check_cross_refs.mjs` + CI workflow `cross-ref-validation.yml` 신규 (dead link / dead anchor / 옛 명칭 deny-list 자동 catch). SSOT M1 (archive 인용 9건 본문 자족화) + M2 (handoff-matrix §1 ↔ orchestration §4 양방향 drift 룰) + N (옛 명칭 정리 — auto-loop / direct-impl-loop / §1.4 / §3.5 / §3.1.5 / §7.5) + agent ↔ SSOT 정합 (HIGH 5건 + drift 룰 callout).

5. **PR / git 인프라 다듬기** ([#502](https://github.com/alruminum/dcNess/pull/502) / [#509](https://github.com/alruminum/dcNess/pull/509) / [#510](https://github.com/alruminum/dcNess/pull/510)) — `scripts/create_epic_story_issues.sh` 의 milestone title 추출 정정 (gh CLI 정합). `pr-finalize.sh` 의 auto-merge 토글이 clean status PR 에서 거부되는 케이스 즉시 머지 fallback + `origin/main` ref-only fetch 정석 패턴 (F1+F3+F14). `check_pr_body.mjs` 의 task-index trailer + Story 마지막 task `Closes` 강제 가드 (F10) + build-worker / git-spec 에 task-index trailer 의무 명시 (F10 보강).

6. **`CLAUDE.md` 사용자 정체성 최상단 승격 + 헤더 영역 정리** ([#493](https://github.com/alruminum/dcNess/pull/493)) — 사용자 정체성 (한국어 시니어 엔지니어 / 자연스러운 표준어 / 결론부터 / 클릭 가능 링크) 을 §0 프로젝트 정체성 옆으로 승격. 매 세션 시작 시 메인 Claude 가 즉시 인지하는 두 영역만 최상단.

### 사용자 영향

- **외부 활성 프로젝트의 옛 `plan-reviewer` 호출 코드 즉시 실패** — `/tech-review` 로 이행 필요. `/product-plan` 재진입 시 새 워크플로우 (PRD + 스켈레톤 → 사용자 1 차 OK → `/tech-review` → 사용자 2 차 OK → `/architect-loop`) 따라 진행.
- **외부 환경 `.gitignore` 수동 추가 권고** — `docs/tech-review/evidence/` + `docs/tech-review/report.html` (로컬 보존, repo 부풀음 차단).
- **옛 `commands/run-review.md` 의 `EXTERNAL_VERIFIED_PRESENT/MISSING` baseline 폐기** — 새 baseline 신설 X (과거 측정 데이터는 보존). plan-reviewer 산출물 패턴 사라짐.

---

## v0.2.33 (2026-05-23)

**커밋 범위**: `v0.2.32..v0.2.33`
**핵심 변경**: `docs/plugin/git-spec.md` 단일 SSOT 신설 (PR + commit + 이슈 등록 룰 통합) + PR body 게이트 over-firing 해소 + review heuristic 강화 (TOOL_REPEAT_HIGH 신규 / must_fix 부정 한국어 라벨 흡수) + helper 진단성 + pr-reviewer 권한 경계 명확화 + 한국어 톤 표준화.

### 무엇이 바뀌나

1. **`docs/plugin/git-spec.md` 신설 + `git-naming-spec.md` 폐기 + `issue-lifecycle.md` 축소** ([#491](https://github.com/alruminum/dcNess/pull/491)) — 브랜치·커밋·PR 네이밍 (§1~§6) + 이슈 등록 양식 (§7) + PR 트레일러 룰 (§8) + 이슈 완료 룰 (§9) 단일 SSOT. `issue-lifecycle.md` 는 흐름·메커니즘 (sub-issue API / 멱등성 / 마일스톤 조회 / pre-flight gate) 만 남김 (202 → 78줄). `.github/PULL_REQUEST_TEMPLATE.md` 신 양식 (관련 이슈 번호 / 배경 및 문제 / 원인 / 작업내용 / 결정 근거 / Test Plan / 참고). dcness self 전용 `## 배포 경로 검증` 섹션 = self 만 (외부 SSOT 누출 X — CLAUDE.md §0.3 정합).

2. **PR body 게이트 over-firing 해소** ([#492](https://github.com/alruminum/dcNess/pull/492)) — `scripts/check_pr_body.mjs` 의 정규식 확장 (`CLOSE_RE` → `TRAILER_RE`). `Part of #N` 트레일러도 valid 로 인정 (close 키워드 단독 강제 폐기). 중간 task PR 마다 fail 발화하던 룰 모순 해소. 외부 활성 프로젝트의 다음 PR 부터 즉시 적용 (composite action 상대경로 호출 — 재배포 불필요).

3. **pr-reviewer 권한 경계 명확화** ([#485](https://github.com/alruminum/dcNess/pull/485)) — `commands/impl.md` + `commands/impl-loop.md` 정상 흐름 표현 정정. pr-reviewer 의 `tools: Read, Glob, Grep` 명시 + commit/push/PR 생성·머지는 *메인 Claude 전담* 분리. 외부 활성 프로젝트 CC 가 "pr-reviewer 가 PR 만들어야 하는데 권한이 없다" 호소하던 회귀 차단.

4. **review heuristic — TOOL_REPEAT_HIGH 신규** ([#487](https://github.com/alruminum/dcNess/pull/487)) — `harness/run_review.py` 의 `_detect_tool_repeat_findings`. agent-trace.jsonl 의 (tool, input) 카운트 임계 (Bash 5+ / Read 4+ / 기타 5+) 초과 시 `TOOL_REPEAT_HIGH` MEDIUM finding emit. build-worker 가 같은 명령 반복 호출하는 안티패턴 catch.

5. **review heuristic — must_fix 부정 한국어 라벨 흡수** ([#486](https://github.com/alruminum/dcNess/pull/486)) — `_MUST_FIX_NEGATION_RE` 의 between 영역 일반화 (`[\s:=]*` → `[^\n]{0,30}?`). pr-reviewer prose 의 `**MUST FIX 항목**: 없음` 같은 한국어 라벨 형태 흡수. `MUST_FIX_LEAK` HIGH false positive 차단.

6. **helper sid/rid 진단성 강화** ([#488](https://github.com/alruminum/dcNess/pull/488)) — `harness/session_state.py` 의 `diagnose_sid_rid_resolution`. 3 layer (env / PPID / active_runs scan) 상태 + escape hatch (`DCNESS_SESSION_ID/RUN_ID` export 명령) stderr 출력. 사용자 자가 해결 영역 확보.

7. **한국어 톤 표준화 — '박-' 동사 회귀 전수 보정** ([#490](https://github.com/alruminum/dcNess/pull/490)) — `agents/` + `commands/` + `hooks/` + `harness/` + `scripts/` + `docs/plugin/` 영역의 비표준 동사 변형 약 137건 (37 파일) 을 자연스러운 한국어 표준 동사로 통일.

### 왜 바뀌나

본 release 의 두 핵심 변경 (#491 SSOT 통합 / #492 게이트 해소) 은 같은 뿌리:

- **#491 SSOT 통합**: 직전 release (v0.2.32) 까지 PR / commit / 이슈 등록 룰이 5곳 (PR template / git-naming-spec / issue-lifecycle / build-worker inline / create_epic_story_issues inline) 에 분산. PR #485 작성 시 commit message 와 PR body 가 같은 정보를 다른 양식으로 *중복 작성* 하는 패턴 노출. 외부 활성 프로젝트 CC 의 *어디 룰 따를지* 추적 비용 제거 목적.

- **#492 게이트 해소**: SSOT 통합 작업 중 사용자가 반복 발생하는 fail 메일 보고 → 게이트 룰 (`close 키워드 1+ 강제`) 와 dcness 룰 (`중간 task PR = Part of #N`) 정면 모순 발견. 정규식 의미 진화 (\"close 키워드\" → \"트레일러\") 로 해소.

나머지 #485 / #486 / #487 / #488 / #490 은 외부 활성 프로젝트 (jajang) 의 실측 회귀 사례 받아 부수 보강.

### 사용자 행동

- **외부 활성 프로젝트는 plug-in 업데이트만 받으면 즉시 적용** (CLAUDE.md §0.5 경로 1·3):
  - `pr-body-validation` 게이트가 `Part of #N` 도 통과 → 우회 마커 (`Document-Exception-PR-Close:`) 빈도 급감
  - 새 SSOT `docs/plugin/git-spec.md` 가 plug-in 본체 경로로 자동 read
- **외부용 PR template 자동 배포는 본 release 에 포함 X** — 외부 사용자가 자기 `.github/PULL_REQUEST_TEMPLATE.md` 작성 또는 메인 CC 가 spec §5 본문 직접 read 후 PR body 작성

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.2.32 (2026-05-23)

**커밋 범위**: `v0.2.31..v0.2.32`
**핵심 변경**: `/impl-loop` 분기 룰을 "양식별 분기" → "impl 파일 존재 여부" 1차원으로 단순화. build-worker 가 모든 input (정식 양식 / bugfix / 자유 형식) 받음. impl 파일 부재 시 module-architect 자동 선두 진입.

### 무엇이 바뀌나

1. **`commands/impl-loop.md` 분기 룰** — 정규식 양식 매치 (`docs/milestones/.../impl/NN-*.md`) 폐기. **impl 파일 존재 여부 1차원**만 본다:
   - 있음 → build-worker 직진 (2-step: build-worker + pr-reviewer)
   - 없음 → module-architect 가 먼저 impl 파일 생성 → build-worker 진입 (3-step)
2. **`commands/impl-loop.md` 후보 경로 (4-agent + module-architect 선두 5-step) 섹션 폐기** — build-worker capability 활용 100%. code-validator 독립 호출 X (build-worker 안 self-validate 로 흡수 — #446 정합).
3. **`commands/impl-loop.md` 자동 폴백 룰 명시** — build-worker 가 진행 중 `SPEC_GAP_FOUND` 던지면 메인이 module-architect 호출 → impl 파일 보강 → build-worker 재시도 (cycle ≤ 2). attempt 한도 초과 시 사용자 위임.
4. **`commands/impl-loop.md` 진행 뷰 단계 수 표기 정정** — sub-step 수 = 2 (impl 있음) / 3 (impl 없음). 옛 후보 경로 5-step 표기 폐기.
5. **`agents/build-worker.md` phase 1 read 의무 톤 다운** — `## 인터페이스 / ## 수용 기준 / ## 핵심 로직 / ## 생성·수정 파일` 4 섹션 강제 → "양식 자유. 어디 건드릴지 + 어떻게 검증할지 박혀있으면 진행, 의문 시 `SPEC_GAP_FOUND`" 자율 판단. 1줄 fix 같은 가벼운 task 에 4 섹션 다 강제하는 빡빡함 제거.

### 왜 바뀌나

본 세션 외부 사용자 케이스 — bugfix 3건 (`docs/bugfix/#N-*.md`) 을 `/impl-loop` 으로 진행했는데 build-worker 가 *능력은 있지만* skill 분기 룰이 정식 양식만 허용해서 4-agent 후보 경로로 강제 분기. build-worker 본인 명세서 (`agents/build-worker.md:25`) 에는 "정식 양식 또는 bugfix 양식 둘 다 받음" 박혀있는데 매니저 (skill) 가 그 능력을 활용 안 함 = 모순.

근본 단순화로 양식별 분기 자체 폐기. 분기 기준 = "impl 파일 있나 없나" 단 하나. build-worker 가 내용 보고 자율 판단하는 구조 (정보 부족 시 `SPEC_GAP_FOUND` → 자동 폴백). `/impl` 단발 호출은 4-agent 모델 유지 (단발은 누적 위기 없음, 엄정성 우선 의도된 티어링).

### 사용자 행동

`/impl-loop` 진입 시 자동 적용. 다음부터 모든 양식 (정식 / bugfix / 자유 형식) 이 build-worker 한 번에 처리 → 메인 토큰 절약 + 사용자 입장 단계 안 쪼개짐.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.2.31 (2026-05-22)

**커밋 범위**: `v0.2.30..v0.2.31`
**핵심 변경**: `/impl` + `/impl-loop` skill prose 에 TaskCreate / TaskUpdate 호출 강제 룰 (`## 강제 사전` 섹션) 박음. 메인 Claude 가 dcness helper `begin-step` 트래킹으로 충분하다 자율 판단해서 TaskCreate skip 하는 회귀 차단.

### 무엇이 바뀌나

1. **`commands/impl-loop.md`** — `## 절차` 직전에 `## 강제 사전 — TaskCreate / TaskUpdate (사용자 가시성, MUST)` 섹션 신설. WHY 명시 (`begin-step` = 내부 트래킹 / TaskCreate = 사용자 UI 가시) + catastrophic 안티패턴 명시 + 호출 시점 4개 (진입 / task 전환 / sub-step 전환 / 완료) 명시.
2. **`commands/impl-loop.md` `## 진행 뷰`** — "진입 시 / task i 진행 중" 두 줄에 **(MUST — §강제 사전 정합)** 라벨 추가 — 자율 영역 인식 차단.
3. **`commands/impl-loop.md` `## 안티패턴`** — "TaskCreate / TaskUpdate skip — begin-step 트래킹으로 충분 자율 판단" catastrophic 1줄 추가.
4. **`commands/impl.md`** — `## 절차` 직전에 동일 `## 강제 사전` 섹션 신설. inner loop 4-step (`test-engineer` / `engineer:IMPL` / `code-validator` / `pr-reviewer`) 에 task list 1개 + sub-step 4개 (fallback 시 5개) 생성 의무 명시.

### 왜 바뀌나

jajang 외부 작업 세션 중 메인 Claude 가 dcness helper `begin-step` / `end-step` 으로 트래킹된다는 이유로 Claude Code 의 TaskCreate 를 자율 skip 하는 회귀 발생. 사용자가 *Claude Code UI* 를 보는데 진행 상태 표시가 없어 "왜 task 안 만들고 셀프로 돌려?" 지적. 두 트래킹은 **다른 layer** — helper = 내부 state 파일 (사용자 UI 불가시), TaskCreate = 사용자 가시. 둘 다 호출 의무. skill prose 가 자연어 룰 중 가장 강한 위치 (메인이 skill 진입 시 반드시 inject) 라 거기 명시적으로 박음.

### 사용자 행동

`/impl` / `/impl-loop` 진입 시 자동 적용 — 메인 Claude 가 진입 직후 TaskCreate 호출 의무. 사용자는 Claude Code UI 에서 task 진행 상태 직접 확인 가능.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.2.30 (2026-05-22)

**커밋 범위**: `v0.2.29..v0.2.30`
**핵심 변경**: #457 산출물 양식 단순화 + CLAUDE.md 자기 검열 룰 제거. 메인 Claude 응답 속도 / 자연스러운 대화 톤 회복 + impl.md 에 사용자 review 영역 (What/Why/ADR) 분리 + sub-agent return 산출물 경로 백틱 의무.

### 무엇이 바뀌나

1. **impl.md 양식에 What/Why/ADR 3 섹션 추가** (PR #464) — 사용자가 module-architect 산출물을 보고 *뭘 만들지 / 왜 / 결정 근거* 한눈에 잡을 수 있게 평이한 한국어 서사로 분리. engineer 가 보는 영역 (`Scope` / `인터페이스` / `수용 기준`) 은 효율 양식 그대로. 경량 케이스 (버그픽스 등) 는 What/Why 1~2 줄 압축 + ADR 생략 가능.
2. **4 agent return prose 에 산출물 경로 백틱 의무** (PR #465) — `engineer` / `pr-reviewer` / `code-validator` / `test-engineer` 가 자기 산출물 (impl.md / 코드 / PR / 이슈 / review.md) 경로를 백틱으로 감싼 형태로 박는다. 메인 Claude 가 그대로 사용자 응답에 echo 하므로 사용자가 한 번 클릭으로 도달.
3. **CLAUDE.md §0.4 자기 검열 룰 제거** (PR #462, dcness self) — 외래어 / 영어 명사구 / 줄임말 금지 + 매 turn 자가 검열 + § 표시 강제 룰이 메인 응답 속도 ↓ + 톤 부자연 + *룰 만족 자체에 인지 자원 소모* 의 직접 원인. 사용자 프로필 각인 한 줄로 단순화 (`사용자는 한국어가 가장 익숙한 시니어 엔지니어`).

### 왜 바뀌나

jajang 2026-05-21 product-plan 세션에서 사용자가 며칠 헛수고한 사단이 있었다 — "허밍한 사람 목소리와 음악 합성이 가능한가" 라는 *가능성 확인* 질문을 했는데, 며칠간 Claude 가 한 작업은 "허밍 보컬 어떻게 튜닝할까" 였다. 가능성을 묻는 질문이 어떻게 좁은 디테일 작업으로 바뀌었는지 추적해보니, 사용자가 산출물 본문 (PRD / stories.md / impl/*.md) 을 *읽지 않고 넘긴* 게 핵심 원인.

안 읽은 이유 둘:
- 양식이 어려워 부담 (서사 부재, 데이터 / 약어 폭격)
- 산출물 경로가 클릭 가능 형태로 안 박혀 Finder 로 직접 찾아가야 했음

본 릴리즈는 이 두 마찰을 동시에 줄인다.

### 외부 활성 프로젝트 영향

- **agents/ 변경** (PR #464 / #465) 은 plug-in 본체 → `claude plugin update dcness@dcness` 시 자동 적용
- **CLAUDE.md §0.4 변경** (PR #462) 은 dcness self 작업 지침. 외부 활성 프로젝트의 CLAUDE.md 는 `/init-dcness` 가 만드는 별도 파일이라 자동 변경 X. 외부 프로젝트에서도 같은 결로 정리 원하면 사용자가 자기 CLAUDE.md 의 자기 검열 섹션 직접 갱신 (각인 한 줄로 단순화 권장)

### 보류 항목

- **처방 2-(2) 메인 출력 훅 강제** — sub-agent 거치지 않고 메인이 직접 가공한 정보 (이슈 # / PR # / 파일 경로) 의 백틱 강제. 위험도 / 오탐 평가 더 필요. PR #465 (처방 2-(1)) 만으로 실효 부족 시 별 이슈로 재진입.
- **메인 대화 톤 감사** (별 트랙) — 메인 응답 *대화 톤 자체* 도 정보 나열 방향으로 기울어진 부작용. 룰 시스템 누적 추정. 룰 추가 자체가 코끼리 함정일 수 있어 신중. 본 릴리즈 PR #462 가 부분 처방.

### #446 Hybrid A 트랙

v0.2.29 (build-worker 가드 + git 통합 스크립트) 적용 후 외부 활성 프로젝트 재측정 미완. 본 릴리즈는 build-worker 본문 직접 변경 없음. 단 return 경로 백틱 의무는 build-worker 도 같은 결 (engineer + pr-reviewer 흡수) 이라 *간접* 적용됨.

### 머지된 PR

- [PR #462](https://github.com/alruminum/dcNess/pull/462) — CLAUDE.md §0.4 자기 검열 룰 제거 (메타 처방)
- [PR #464](https://github.com/alruminum/dcNess/pull/464) — module-architect impl.md What/Why/ADR 3 섹션
- [PR #465](https://github.com/alruminum/dcNess/pull/465) — 4 agent return prose 경로 백틱 의무
- [#457 close + 요약 코멘트](https://github.com/alruminum/dcNess/issues/457)

---

## v0.2.29 (2026-05-21)

**커밋 범위**: `v0.2.28..v0.2.29`
**핵심 변경**: #446 Step 3 1-task 측정 결과 반영 — build-worker prompt 가드 3건 + 메인 git 통합 스크립트. 재측정 진입용.

### 1. 1-task 측정 결과 (#446 Step 3, 외부 활성 프로젝트)

v0.2.28 발행 후 외부 활성 프로젝트에서 1-task 측정 진입. 결과:

- 메인 turn = 121 (기준 ≤ 100 +21 미달)
- 기준선 ~280 turn/task 대비 ~57% 감소 (큰 절감 자체는 인정)
- 사후 보정 ~10 turn 중 ~8 turn = build-worker 의 3 결함 회수 가능
- 권장 보강 적용 시 ~110 turn 예상 (여전히 ≤ 100 미달 가능성)

분석: thinking-only + text-only = 50.7% / Agent 호출 = 3.1% / git+gh 분리 호출 = 13.8%. Hybrid A 가 sub-agent 안 작업 흡수해도 메인 *대화 + 관리* 자체 base load 는 ~80-100 turn.

### 2. build-worker prompt 가드 3건 (PR #458)

`agents/build-worker.md` 에 3 가드 절 신규:

- **§Scope 가드 (MUST)** — impl `## Scope` 의미적 경계 강조. ALLOW_MATRIX 형식적 경계 통과해도 의미 위반은 catastrophic. viability mock / `__DEV__` 분기 / 다른 화면 mock / 종단간 bridge 코드 본 task PR 안 박지 말 것. 필요 시 `IMPLEMENTATION_ESCALATE`
- **§stub / 회피 코드 금지 (MUST)** — TDD GUARD 회피 stub 안티패턴 차단. phase 2 build-impl 의 GREEN 의무 = 진짜 GREEN. 필요해 보이면 `SPEC_GAP_FOUND`
- **§PR body 초안 close-keyword 정확성 (MUST)** — impl frontmatter task_index + 부모 이슈 본문 + invocation prompt 만 source. task_index 매핑 (M/M = Closes / N<M = Part of / epic 마지막 둘 다)

### 3. 메인 git 통합 스크립트 (PR #460)

`scripts/pr-create.sh` 신규 — branch + add + commit + push + gh pr create 통합. 인자: `--branch / --base / --title / --body-file / --commit-msg-file`. 분리 5 호출 → 통합 3 turn (Write × 2 + Bash 1) = ~2 turn 회수.

`commands/impl-loop.md` 절차 §2.iii — 분리 명령 → `scripts/pr-create.sh` 통합 호출 예시. 분리 호출 비권장 명시.

### 4. 재측정 진입

본 릴리즈 적용 후 외부 활성 프로젝트에서 2번째 task 측정:

1. `claude plugin update dcness@dcness` → v0.2.29 적용
2. `/impl-loop <task>` 호출
3. 측정: `python3 scripts/measure_main_turns.py <new-sid>.jsonl`
4. 결과 비교:
   - ≤ 100 turn → 통과 → #446 Step 6 사후 검증
   - 100-150 turn → 본문 기준 재조정 (~150 현실적) + Hybrid A 유지
   - > 150 turn → 후보 경로 (4-agent) 복귀 PR + 단념

### 5. /impl 무변경

`commands/impl.md` 손 안 댐 (#446 엄격 제약). `/impl` 단발 호출 = 4-agent 모델 그대로.

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.29 적용
- 외부 활성 프로젝트에서 2번째 task 측정 진입

---

## v0.2.28 (2026-05-21)

**커밋 범위**: `v0.2.27..v0.2.28`
**핵심 변경**: `/impl-loop` Hybrid A 모드 활성화 — build-worker 2-step 진입점 전환 (#446 Step 4, 측정 진입용).

### 1. Hybrid A 활성화 (#446 Step 4, PR #455)

v0.2.27 까지 spec docs (agents/build-worker.md + docs/plugin/{handoff-matrix,orchestration,loop-procedure}.md) 머지된 채 진입점 보류 상태였던 Hybrid A 를 `commands/impl-loop.md` 진입점 활성화로 실측 진입:

- **§절차** — 4-agent 시퀀스 → Hybrid A 5 단계 재작성: ① 진입 직전 1회 확인 → ② begin-run + build-worker step (Agent 호출) → ③ git/PR 생성 (메인) → ④ pr-reviewer step + 머지 (`scripts/pr-finalize.sh` 호출) → ⑤ end-run + 5줄 요약 출력
- **§진행 뷰** — sub-step 4건 → 2건 (build-worker / pr-reviewer). 후보 경로 (정식 위치 impl 부재 시) sub-step 5건 (module-architect + 4-agent)
- **§review 출력 재정의 5줄 요약** — Hybrid A 기본 형식 (build-worker · pr-reviewer). 후보 경로 4-agent 형식 별도 1줄
- **§git 권한** — engineer / build-worker / test-engineer 등 sub-agent git/PR 호출 금지 명시. worker 는 PR 본문 + commit message 초안만 prose return
- **§안티패턴** — build-worker 항목 3건 추가 (phase prose 자체 Write 확인 / sub-sub 호출 금지)

### 2. 실측 진입 — 사용자 협력 측정

본 릴리즈가 #446 Step 3 통과 기준 (메인 turn ≤ 100, 엄정성 유지) 의 실측 진입용. 사용자가 자기 활성 프로젝트에서:

1. `/impl-loop <task-path>` 1회 호출 → build-worker 자동 진입 → 새 세션 JSONL 생성
2. `python3 scripts/measure_main_turns.py ~/.claude/projects/<encoded>/<sid>.jsonl` 측정
3. 결과 비교:
   - 기준선 ~280 turn/task (jajang 옛 세션, scripts/measure_main_turns.py 정확 재현 검증)
   - 통과 기준 ≤ 100 turn (목표 ~30)
4. 결과에 따라:
   - 통과 → 그대로 유지 → #446 Step 6 사후 검증 (2-3 task 추가 측정)
   - 미달 → 후보 경로 (4-agent) 로 복귀 PR + 0.2.29 hotfix + #446 Step 4-5 단념

### 3. /impl 무변경

`commands/impl.md` 손 안 댐 (#446 엄격 제약). `/impl` 단발 호출 = 4-agent 모델 그대로 (엄정성 우선 의도된 티어링).

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.28 적용
- 사용자 활성 프로젝트에서 `/impl-loop` 호출 시 build-worker 자동 진입. 측정 후 결과 보고

---

## v0.2.27 (2026-05-20)

**커밋 범위**: `v0.2.26..v0.2.27`
**핵심 변경**: `/impl-loop` 메인 컨텍스트 누적 감축 — 저비용 개선 (#446 Step 1) + 측정 자동화 도구. Hybrid A 설계 (#446 Step 2) 머지되었으나 본 릴리즈 한정 *활성화 보류* (실측 미완).

### 1. 저비용 개선 — agent 5종 return 가이드 구체화 + impl-loop review 출력 재정의 (#446 Step 1, PR #447)

jajang 실측 기준선 ~280 turn/task 의 post-Agent 누적 주범 = review.md 원본 그대로 출력 + agent 본문 장황한 서술. 두 갈래로 즉시 절감:

- **agent 5종 return 가이드 구체화** — `agents/{test-engineer,engineer,code-validator,pr-reviewer,module-architect}.md` 의 기존 generic return-terseness (#440) 옆에 산출물 구조별 *구체화* 단락 추가
  - test-engineer: 테스트 케이스 표 전수 입력 금지 (케이스 수 + 카테고리 + RED/GREEN + SPEC_GAP 만)
  - engineer: 파일별 변경 서술 → `M files +X -Y` 통계 + 의도 1-2 문장
  - code-validator: A/B/C 통과 항목 열거 금지 ("A/B/C 통과" 1줄)
  - pr-reviewer: A~F 체크리스트 본문 재진술 금지 (카테고리 라벨 + (파일:라인) + 1-2 문장)
  - module-architect: impl 본문 재진술 금지 (섹션 라벨 + 의도)
  - 공통: 워크트리 절대경로 반복 echo 금지
- **`commands/impl-loop.md` driver 범위 review 출력 재정의** — 원본 review.md 는 디스크 (`<run_dir>/review.md`) 그대로, 메인 컨텍스트는 5줄 요약 (task 결론 / agent 결과 / finding / PR·이슈 / next)
- `/impl` 단발 호출은 review.md 원본 그대로 출력 MUST 유지 — 엄정성 우선 (`commands/impl.md` 무변경)

### 2. 측정 스크립트 — scripts/measure_main_turns.py (PR #449)

Claude Code 세션 JSONL 파싱 → 메인 assistant turn 분포 (tool / text-only / thinking-only) + tool histogram + Agent 호출 분포 출력. Python 표준 라이브러리만, text/JSON 출력 + 디렉토리 일괄. #446 본문 기준선 (8af5fb4d=203 / 1518caa0=349) 정확 재현 검증. Step 3 프로토타입 통과 기준 + Step 6 사후 검증에 재사용.

### 3. Hybrid A 설계 — build-worker + 2-step (#446 Step 2, PR #448) — *본 릴리즈 한정 활성화 보류*

`/impl-loop` 메인 turn ~85-90% 감축 목적의 Hybrid A 모드 설계 완료:
- `agents/build-worker.md` 신규 — `/impl-loop` 한정 통합 worker (test + impl + self-validate 3 phase, helper Bash self-call, TDD GUARD 정합, git/PR/pr-reviewer 호출 메인 위임)
- `docs/plugin/{handoff-matrix,orchestration,loop-procedure}.md` 동기 (§4.3 진입 모드 3분기 / §4.8 Hybrid A 모드 / §3.2.1 worker phase prose 자체 Write)

**본 릴리즈 한정 활성화 보류 — `commands/impl-loop.md` 의 `/impl-loop` 진입점은 4-agent 시퀀스 유지**. 이유 = #446 Step 3 프로토타입 (jajang 1-task 실측 통과 기준) 미완. 실측 검증 후 별 PR 로 활성화. spec 은 머지된 채 (활성화 대기). 자세히 = `commands/impl-loop.md` §"Hybrid A 모드 (활성화 대기, #446)" (당시 기준 — 현 `skills/impl-loop/SKILL.md` 로 통합).

### 4. #345 흡수 권고

[#345](https://github.com/alruminum/dcNess/issues/345) (`/impl-loop` 메인 컨텍스트 누적 — task별 새 프로세스 driver 필요) 코멘트 박음 — 새 프로세스 제안은 6/15 Agent SDK 과금 분리로 폐기 (#438 정합), 본질 문제는 #446 트랙이 한 세션 안에서 Hybrid A 로 흡수. close 권고.

### 5. /impl 무변경 보장

전 릴리즈에서 `commands/impl.md` 손 안 댐 (#446 엄격 제약). `/impl` 단발 호출 = 4-agent 모델 그대로 (엄정성 우선 의도된 티어링).

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.27 적용
- 저비용 개선 + 측정 스크립트 즉시 효과. Hybrid A 활성화 = Step 3 통과 기준 충족 후 별 PR (예상 v0.2.28+)

---

## v0.2.26 (2026-05-19)

**커밋 범위**: `v0.2.25..v0.2.26`
**핵심 변경**: `/impl-loop` run 격리 복원 + 사람 친화 진행 뷰 (#443)

### 1. run 격리 복원 (#443 작업 1)

v0.2.25 의 in-session `/impl-loop` 이 모든 task 를 한 run 에 묶어 `run_review` 가 거대 review.md 1개를 내던 결함 수정. (`run_review` 는 run 단위 `--run-id` 동작 — 헤드리스 시절엔 task=자식세션=run 이라 자연 격리됐던 것이 in-session 복귀 시 옛 `b<i>.` 한-run 모델 잔재를 베껴 깨졌음.)

- `commands/impl-loop.md` — 각 task = 독립 `begin-run impl` … `end-run` run. **N task = N run = N run dir = N review.md** (task별 로그·`/run-review` 격리)
- `loop-procedure.md` §1.2 / §2 / §3.1 + `orchestration.md §4.8` — 옛 `b<i>.` 한-run 모델 잔재 정리
- `/impl-loop` 은 자기 run 이 없는 `impl-task-loop × N` driver — `orchestration.md §4.1` 카탈로그 정설 정합

### 2. 사람 친화 진행 뷰 (#443 작업 2)

`commands/impl-loop.md` `## 진행 뷰` 섹션 신규 — task 리스트가 주욱 펼쳐져 현재 페이즈 식별이 어렵던 문제 해소:

- 완료 task 는 한 줄 / 현재 task 만 sub-step 을 `ㄴ` 들여쓰기로 펼침 / 예정 task 는 대기 줄
- Task 시스템 = 평탄 리스트 (부모/자식 필드 X) + 생성순 표시 (샘플 task 렌더 실측 검증) → 중간삽입 불가 우회로 task 전환마다 [현재 헤더 + sub-step + 남은 헤더] rebuild

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.26 적용

---

## v0.2.25 (2026-05-19)

**커밋 범위**: `v0.2.24..v0.2.25`
**핵심 변경**: `/impl-loop`·`/impl` 헤드리스 (`claude -p`) 폐기 → 메인 in-session 오케스트레이터 복귀 (#438 + #440)

### 배경 — Anthropic Agent SDK 과금 변경

2026-06-15 부터 구독 플랜의 `claude -p` / Claude Agent SDK / GitHub Actions 사용량이 별도 "Agent SDK 크레딧" 풀로 분리 + full API rate 과금 (Pro $20 / Max 5x $100 / Max 20x $200, per-user, 미사용분 cycle 말 소멸). dcness 헤드리스 자식 세션 spawn 이 정확히 이 풀에 진입 → 구독 사용자 비용 폭증.

공식: https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan

### 1. 헤드리스 경로 완전 폐기 (#438, PR #439)

- `scripts/impl_loop_headless.py` (563줄) + `tests/test_impl_loop_headless.py` (478줄) 삭제
- `commands/impl-loop.md` 재작성 — `claude -p` 자식 spawn 제거, 메인 in-session per-task 오케스트레이션 복원. `orchestration.md §4.8` 의 `impl-task-loop × N` 모델이 이미 in-session 이라 헤드리스는 그 위 얇은 override 층이었음
- `commands/impl.md` — `## 헤드리스 실행 옵션 (#422)` 섹션 삭제
- 보존: 워크트리 1회 + base-ref(#424) / Pre-flight gate / 진입 직전 1회 확인(#346) / 1 task = 1 PR / 4-step 모두 호출 MUST(#431)
- 신규: false-clean 차단(메인 직접 확인) + compaction 복구 절 (루프 상태 = conveyor state 파일 SSOT)
- in-session = 구독 interactive 한도 — Agent SDK 크레딧 풀 미진입

### 2. impl-loop agent return 간결성 규율 (#440, PR #441)

- impl-task-loop 5 agent (engineer / test-engineer / code-validator / pr-reviewer / module-architect) "결론 + 권장 다음 단계" 섹션에 return 간결성 가이드 1블록 추가
- return prose = 결론 + 핵심 변경·발견 + 권장 다음 단계만. 과정 narration / 계획 재진술 / 파일별 장황한 설명 제거. 결론 근거 substance (실측 명령·수치 / 발견 항목 / 미완 작업)는 유지
- 형식 강제(라인 cap) 아닌 내용 선택 가이드 — prose-only 철학 정합
- in-session 복귀로 매 task return 이 메인 컨텍스트에 누적 → 큰 epic(15~30 task) 대비 잔여분 감축

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.25 적용

## v0.2.24 (2026-05-14)

**커밋 범위**: `v0.2.23..v0.2.24`
**핵심 변경**: 헤드리스 자식 stream-json 파서 — 사람 친화 progress view (#431 follow-up → PR #434)

### 1. 자식 spawn `--output-format stream-json --verbose` 전환

`scripts/impl_loop_headless.py:spawn_child`:
- 옛 `--output-format text` (raw line stream = verbose noise) → `stream-json --verbose` 로 교체
- `format_progress_event(ev)` 신규 — JSON event → 사람 친화 1 line per marker:
  - `tool_use.name == "Task"` → `  ㄴ <subagent_type> — <description>`
  - `tool_use.name == "Bash"` + conveyor 키워드 (begin-run/begin-step/end-step/end-run) → `  ㄴ <cmd>`
  - `type == "result"` → `  [result] <첫 줄>`
  - 그 외 도구 (Edit/Read/Glob 등) 는 skip — noise 차단
- `extract_event_text(ev)` 신규 — parse_result + 4-step keyword 검사용 text 추출

배경 (사용자 시연): jajang epic 19 헤드리스 진행 시 외부 progress (`Running... 11m 42s · ↓ 8.8k tokens`) 만 보이고 자식 sub-agent 흐름 안 보임. v0.2.23 의 `[child] <raw line>` stream 은 verbose noise 가 너무 많음. 사용자가 원한 형태:
```
xxxxx task
  ㄴ test-engineer — 테스트 작성중
  ㄴ engineer — 구현중
  ㄴ code-validator — 검증중
  ㄴ pr-reviewer — 리뷰중
```

stream-json + JSON 파서 + filter 후 1 line per marker 박으면 CC Bash foreground 의 ⎿ 들여쓰기에 자식 진행 자연 표시.

### 2. `commands/impl-loop.md` / `commands/impl.md` §절차 갱신

- stream-json + 사람 친화 progress 동작 명시
- Bash background + Monitor 패턴 폐기 (Monitor notification 이 메인 Claude 해석 layer 거쳐 효과 X)
- Bash foreground 호출 시 CC UI ⎿ 자연 표시 명시

### 사용자 업데이트 가이드

```sh
claude plugin update dcness@dcness
```

---

## v0.2.23 (2026-05-14)

**커밋 범위**: `v0.2.22..v0.2.23`
**핵심 변경**: 헤드리스 자식 실시간 가시화 + conveyor + inner 4-step 안전망 (#430 + #432)

### 1. 헤드리스 자식 stdout 실시간 line stream (#422 follow-up → PR #430)

`scripts/impl_loop_headless.py:spawn_child()`:
- `subprocess.run(capture_output=True)` → `subprocess.Popen + threading drain` 으로 교체 (line-buffered stream)
- 자식 line 마다 `[child] <line>` / `[child:err] <line>` 접두 박아 stream_to (default sys.stderr) 로 즉시 echo

`commands/impl-loop.md` / `commands/impl.md` 절차 — Bash tool `run_in_background=true` + Monitor stream MUST 명시.

배경: 메인 세션 헤드리스 진행 시 외부 progress (`11m 42s · ↓ 8.8k tokens`) 만 보이고 자식 sub-agent 흐름 안 보임 → 자식 line stream + Monitor 로 인터랙티브 `/impl` 과 동일 가시화.

### 2. 헤드리스 자식 conveyor + inner 4-step 안전망 (#431 → PR #432)

`scripts/impl_loop_headless.py:build_invocation`:
- `--append-system-prompt` 에 의무 4 항목 inject (commands/impl.md 본문보다 우선):
  1. 진입 즉시 begin-run 호출
  2. inner 4-step 모두 호출 (test-engineer → engineer → code-validator → pr-reviewer)
  3. PR merge 직후 end-run 호출
  4. 종료 prose enum (PASS/FAIL/ESCALATE)

`scripts/impl_loop_headless.py:process_task`:
- 자식 stdout 에 `code-validator` / `pr-reviewer` 흔적 부재 시 → blocked 강등 (parent text fragility 검사)

`commands/impl.md` §Inner loop 4-step 모두 호출 (MUST) 섹션 신규.

배경: jajang epic 19 task 06 자식이 test-engineer + engineer 만 호출하고 commit/push/PR 안 만들고 PASS 박고 종료 → headless parent false-clean 판정 → 메인 수동 수습. 자식 cost \$15~20/1회 실측인데 dcness-review 에 \$0 표시 = 측정 거버넌스 catastrophic 결함.

결함 1 (`dcness-review --latest` 가 자식 run 못 찾음) 은 결함 2 (자식 begin-run 미호출 → `.steps.jsonl` 부재) fix 로 자동 해소.

### 사용자 업데이트 가이드

```sh
claude plugin update dcness@dcness
```

---

## v0.2.22 (2026-05-14)

**커밋 범위**: `v0.2.21..v0.2.22`
**핵심 변경**: jajang Epic 19 followup 4 묶음 — 헤드리스 자식 정합 + TDD GUARD entry-file + worktree base-ref

### 1. impl-loop 자식 conveyor cycle 안전망 (#422 → PR #425)

`scripts/impl_loop_headless.py`:
- `[E]` 자연어 단락에 명시 `begin-run impl / begin-step / end-step / end-run` 호출 박음 (옛 indirect chain 위임 → silent-fail 회귀 차단)
- `process_task()`: `confirm_issue_closed is False` → `clean → blocked` 강등 (false-clean 안전망). 이슈 번호 부재 시 cwd `git status --porcelain` fallback 검사

배경: jajang Epic 19 NS2 자식이 사용자 위임 자연어 + enum 누락 + exit 0 종료 시 헤드리스 parent 가 `ALL CLEAN` 잘못 보고. `.steps.jsonl` 미작성 → `/run-review` 사후 분석 불가.

### 2. 헤드리스 자식 슬래시 직호출 리팩토링 (#422 follow-up → PR #426)

`scripts/impl_loop_headless.py`:
- 자식 prompt = `/dcness:impl <task-path>` 슬래시 직호출로 단순화 (chain 깊이 3 → 0)
- retry context → `--append-system-prompt` 로 inject
- 옛 `build_command()` ([A]~[E] 5 묶음 자연어) → `build_invocation()` 으로 폐기

`commands/impl.md`:
- §사전 read 의무 5번 항목 추가 (같은 epic 형제 머지 PR 환기)
- §헤드리스 실행 옵션 추가 — 단발 task 도 사용자 발화 `헤드리스|headless` 매치 시 헤드리스로 위임

배경: 자식이 슬래시 호출 받으면 `commands/impl.md` 본문이 system-reminder 로 자동 inject → 인터랙티브 `/impl` 과 동일 정확도. `.steps.jsonl` 정상 작성 → `/run-review` 가능.

### 3. TDD GUARD entry-file false-positive 해소 (#423 → PR #427)

`hooks/tdd-guard.sh`:
- entry-file path heuristic 추가: `App.{ts,tsx,js,jsx}` / `_layout.{ts,tsx,js,jsx}` / `apps/*/index.{ts,tsx,js,jsx}` / `src/main.{ts,tsx,js,jsx}`
- 파일 내용 시그니처 grep 추가: `registerRootComponent\(` / `AppRegistry\.registerComponent\(` (Edit 케이스 cover)

배경: Expo `apps/mobile/index.js` / RN `App.tsx` / expo-router `_layout.tsx` 가 boilerplate (비즈니스 로직 X) 인데 TDD GUARD 가 차단. engineer agent 의 빈 stub 회피 안티패턴 강화 위험.

회귀 방지: 일반 비즈니스 로직 (`src/business-logic.ts`) + 테스트 부재 → 여전히 deny.

### 4. outer worktree base-ref 분기 SSOT (#424 → PR #428)

`docs/plugin/loop-procedure.md` §1.1.1 신규:
- `**Base Branch:**` 마커 매치 시 outer worktree base 도 integration branch 정합 (`git worktree add -b <new> <path> origin/<integration>` + `EnterWorktree(path=)` 우회 패턴)
- §1.1 의 "수동 git worktree add 우회 금지" 룰에 §1.1.1 예외 명시

`commands/impl-loop.md` / `commands/impl.md` / `commands/architect-loop.md` §워크트리 섹션 + §1.1.1 참조 1줄 추가. `commands/architect-loop.md:57` 모호 표현 (`동일 base 에서 따야 함`) 구체화.

배경: jajang Epic 19 ADR-19E 통합 브랜치 패턴에서 outer worktree (origin/main 기반) vs sub-PR base (`feature/local-dsp`) mismatch → sub-PR diff 거대화 ("삭제 변경" false). 사용자 자율 회피 + 자식 자체 sub-worktree 패턴으로 NS1/NS2 머지 성공 — 룰 부재 우회 사례.

### 사용자 업데이트 가이드

```sh
claude plugin update dcness@dcness
```

---

## v0.2.21 (2026-05-13)

**커밋 범위**: `v0.2.20..v0.2.21`
**핵심 변경**: 통합 브랜치 패턴 지원 — git-naming + product-plan + scripts auto-detect (#413 + #414)

### 1. git-naming regex 완화 (#413)

`scripts/check_git_naming.mjs`:
- BRANCH_RE 에 `feature/<desc>` 패턴 추가 (자유 feature / 통합 브랜치 — 예: `feature/local_dsp`)
- 4 패턴 통일 기본 제약: 소문자 + `[a-z0-9_-]` + 최소 3자
- TITLE_RE 에 `[epic{N}]` (epic-only, 통합 → main 머지) + `[feature]` (자유 feature) 추가

`docs/plugin/git-naming-spec.md` §1 / §2 / §4 / §6 표 갱신 + base 분기 룰 명시.

배경: jajang Epic 19 (#262) 통합 브랜치 `feature/local-dsp` push 시 hook 차단 → `--no-verify` 우회. 본 release 로 차단 해소.

### 2. 통합 브랜치 모드 (`commands/product-plan.md`) (#414 problem A)

- §Step 6.5 신설 — 메인 → 사용자 그릴 (a) 일반 / (b) 통합 브랜치
- §Step 7 (a) trunk / (b) integration 분기
- (b) 흐름: `stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 + 통합 브랜치 생성 + PRD sub-PR (`docs/<slug>_prd` from `feature/<slug>`)

mode 코드 분기 도입 X — 자연어 마커만으로 분기 (메인 Claude 의 stories.md grep 인식).

### 3. scripts/create_epic_story_issues.sh 헤더 양식 auto-detect + 마커 미러링 (#414 problem B)

- 헤더 양식 auto-detect: `## Epic — ...` (h2+h3, product-plan 양식) / `# Epic NN — ...` (h1+h2, jajang 양식)
- `**Base Branch:**` 마커 자동 epic issue body 미러링

배경: jajang stories.md (h1+h2) parse 실패 → 메인이 4 직접 호출로 우회. 본 release 로 양식 통일 흡수.

### 4. commands × 3 base 분기 체크리스트

`commands/impl.md` / `commands/impl-loop.md` / `commands/architect-loop.md` 의 PR 생성 직전 절차에 stories.md `**Base Branch:**` grep → `--base` 박는 룰 1줄 추가.

### 5. docs/plugin/issue-lifecycle.md §1.4 명문화

통합 브랜치 케이스 — base ≠ main sub-PR 의 GitHub auto-close 한계 + 마지막 통합 → main 머지 PR body 에 bulk close (`Closes #<story1...N>` + `Closes #<epic>`) 패턴 명문화. GitHub default branch 제약 (linking-a-pull-request-to-an-issue) 인용.

### 사용자 업데이트 가이드

```sh
claude plugin update dcness@dcness
```

문제 발생 시:
```sh
claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness
```

업데이트 후 `feature/<desc>` 같은 자유 슬러그 브랜치명 + `[feature] / [epic{N}]` PR 제목 형식이 즉시 통과한다.

---

## v0.2.20 (2026-05-13)

**커밋 범위**: `v0.2.19..v0.2.20`
**핵심 변경**: `_summarize_input` cwd 기준 relative path 단축 (#408)

### v0.2.19 실증 결과 (본 세션 dcness self repo)

#401 (skill 진입 docs 통째 read 폐기) 처방 효과 강력 확인:
- 이전 (처방 전 jajang): `orchestration.md` 24.7k + `loop-procedure.md` 17.8k *통째 read*
- 현재 (처방 후 본 세션): `docs/plugin/*` 6회 모두 *부분 read* (max 1.5k chars). 통째 read 0회.
- → 메인이 lazy read 가이드 정합 행동 채택. 처방 작동.

cache_read 추이 (본 세션 967 turns):
- 초반 14k → 중반 497k → 후반 172k (감소)
- 메인 행동에 따라 cumulative cache_read 가 ↓ 가능 — cost-aware 의 효과 정합.

### path 단축 hotfix (PR #409, #408)

`harness/hooks.py:_summarize_input` 의 file_path/path 영역에 cwd 기준 relative 단축:

이전:
```
같은 input 반복: /Users/dc.kim/project/jajang/.claude/worktrees/impl-issue259/src/foo.ts ×3
```

후:
```
같은 input 반복: src/foo.ts ×3
```

- `_shorten_path` 함수 신규
- `_summarize_input` Read/Edit/Write/NotebookEdit 의 file_path/path 영역만 적용
- Bash command 는 단축 X (command 전체 의미 보존)
- cwd 외부 path 는 그대로 (절대 path 보존)

효과: ~6k chars / 세션 cache_read 감축 (~1.5k tok). 의미 손실 X.

### 테스트
- 6 신규 (`tests.test_hooks.ShortenPathTests`)
- 410 / 410 tests PASS

### 활성 사용자 권장
- `claude plugin update` 한 번 → v0.2.20 적용
- v0.2.19 까지 미적용 사용자는 한 번 update 로 #400 + #402 + #404 + #408 누적 처방 모두 받음

---

## v0.2.19 (2026-05-13)

**커밋 범위**: `v0.2.18..v0.2.19`
**핵심 변경**: cost / cache_read leak 감축 3종 처방 누적 (#400 / #402 / #404)

### 배경 — cost 분석

세션 분석 결과 (jajang 1106 events / dcness self 4989 events):
- 후반 turn cache_read 평균 267k~507k (초반 32k~57k 의 4.7~16배)
- cache hit 95% 인데도 cost 폭증 ($15~71 / run) = **컨텍스트 양** 자체가 본질
- 메인 turn cost 비중 98% (sub-agent 격리는 잘 작동 중)

### skill 진입 docs 통째 read 폐기 (PR #401, #400)

5 commands 의 "사전 read (skill 진입 즉시)" 룰 → "lazy — 필요시만":

- 이전: `docs/plugin/loop-procedure.md` + `orchestration.md` + `handoff-matrix.md` + `issue-lifecycle.md` read 후 진행 (~65.9k chars / ~16.5k tok 통째 read)
- 후: 본 skill 본문 + 인용된 §번호 만으로 진행. 룰 모호 / 분기 발생 시에만 grep + offset/limit 부분 read.
- 영향: `architect-loop.md` / `impl-loop.md` / `impl.md` / `issue-report.md` / `product-plan.md`
- 효과: skill 진입 시 메인 cache_read baseline 약 16.5k tok 한 번에 절감.

### SessionStart inject 다이어트 + cost-aware 가이드 (PR #403, #402)

`hooks/session-start.sh` 의 inject 본문 1425 → 1106 chars (-22%):

- 각 섹션 제목 단축 / verbose 부분 축약
- **cost-aware 행동 룰 1줄 신규**:
  > 큰 plan/docs 통째 read 회피 → grep + offset/limit. Bash output 길면 `| head` 잘라내기. sub-agent 위임 우선 (메인 직접 도구 ↓ → 메인 cache_read 누적 ↓)
- 직접: 매 turn cache_read ~-80 tok / 세션 turn 수만큼 누적 감축
- 간접: 메인이 cost-aware 행동 채택 → 큰 도구 결과 누적 회피 → cumulative cache_read 더 큰 감소

### hook 정상 통과 시 suppressOutput 시도 (PR #405, #404)

CC 본체 알려진 버그 (`anthropics/claude-code#34859`, `#34713` 등 9+ open) 회피 가설:

- hook exit 0 + 빈 stdout 정석 따라도 transcript 에 `Output truncated (0KB total)` 165자 wrapper attachment 박힘
- 3 PreToolUse hook (`catastrophic-gate.sh` / `file-guard.sh` / `tdd-guard.sh`) 정상 통과 path 에서 `{"suppressOutput": true, ...}` JSON emit
- 차단 path (deny / exit 1) 는 기존 동작 유지
- 실증 필요 — 다음 /impl 1 회 transcript 비교

### 알려진 한계 (Anthropic 영역)

- CC 본체가 모든 도구 호출에 165자 wrapper attachment 박는 패턴 = dcness 비활성 환경에서도 동일
- 회피 = 본체 fix 대기 또는 suppressOutput 시도 (#405)
- dcness 영역 처방 = 메인 행동 가이드 + skill 진입 docs lazy + hook output suppress

### 테스트
- 404 / 404 tests PASS (변경 X)

### 활성 사용자 권장
- `claude plugin update` 한 번 → 다음 세션부터 cost-aware 룰 + lazy docs read 자동 적용
- 사용자 실증: 다음 /impl 1 회 transcript 비교 (특히 attachment leak 감소 여부)

---

## v0.2.18 (2026-05-12)

**커밋 범위**: `v0.2.17..v0.2.18`
**핵심 변경**: review.md 다이어트 + 메인 자율 인사이트 매커니즘 (#392 / #394 / #396)

### review.md 폐기 통합 (PR #393, #392)

dcness 정신 정합 X 패턴 통합 폐기:

- **잘한점 5 패턴 전체 폐기**: ENUM_CLEAN / PROSE_ECHO_OK / DDD_PHASE_A / DEPENDENCY_CAUSAL / EXTERNAL_VERIFIED_PRESENT. jajang 실측 loop-insights 100% PROSE_ECHO_OK baseline 노이즈가 직접 동기.
- **6 정신 위반 waste 패턴 폐기**: ECHO_VIOLATION / PLACEHOLDER_LEAK / EXTERNAL_VERIFIED_MISSING / MISSING_SELF_VERIFY / MAIN_SED_MISDIAGNOSIS / PARTIAL_LOOP. agent 자율 영역 침해 + hardcoded 임계 = sub_eval.py:6~10 정신 위반.
- **redo_log + routing_telemetry 폐기**: jajang "하지 말 것" 0건 + record_cascade 0건 = 매커니즘 죽음.
- **`commands/audit-redo.md` skill 폐기**: redo_log 의존 매커니즘 죽음.
- 약 -800 lines (코드 + 테스트 + docs).

### review.md 측정 noted + 도구 분포 표 (PR #395, #394)

- **TOOL_USE_OVERFLOW + THINKING_LOOP → "측정 noted" 섹션**: severity 폐기, raw 알림. 사용자 요청에 따라 hardcoded 임계 유지하되 "결정" 형식 폐기.
- **도구 사용 분포 표 신규**: `agent-trace.jsonl` 의 PreToolUse pre entry 집계. step 별 윈도우 Read/Write/Edit/Bash/Glob/Grep 카운트. raw 측정 — 임계 X.
- `NoteFinding` dataclass 신규.

### 메인 자율 인사이트 매커니즘 (PR #397, #396)

자동 누적 폐기 후 대체:

- **`$HELPER insight <agent>[-<mode>] "<자연어 한 줄>"` CLI 신규**: 메인 자율 평가.
- **FIFO 10 cap 누적**: agent+mode 별 `.claude/loop-insights/<agent>[-<mode>].md`. 100 run 돌려도 ≤10줄 (200 tokens / agent inject).
- **agent+mode 분리 파일**: `engineer-IMPL.md` / `engineer-POLISH.md` 따로. 다음 run 의 같은 agent+mode begin-step 만 정확 inject.
- **review.md 끝 prompt 임베드**: REVIEW_READY 시 메인 시야 진입 — `## 📝 메인 인사이트 (1줄 자율 평가)`.

### end-run 단일화 (PR #397, #396)

- 옛 2개 명령 (`finalize-run --expected-steps <N> --auto-review` + `end-run`) → 1개 (`end-run`) 단순화.
- end-run 안전망 (`session_state.py:1001`) 이 finalize-run --auto-review 자동 발사.
- `commands/impl.md` §종료 조건 + `loop-procedure.md` §5.1 명시 갱신.

### 테스트
- 456 → 404 tests (폐기 -58 + 신규 +6)
- jajang run-459cce99 실데이터 검증: 다이어트 후 양식 정상 + 새 매커니즘 정상 작동

### 배경

이번 변경의 *원래 의도* = #321 의 본래 핵심: "단순 룰 정합 표시는 학습 가치 0. dcness self-improvement = 메인 LLM 자율 평가". sub_eval.py:6~10 자율 친화 재설계 (#272 W1) 정신을 review.md / loop-insights 영역까지 확장 적용.

---

## v0.2.17 (2026-05-12)

**커밋 범위**: `v0.2.16..v0.2.17`
**핵심 변경**: agent 다이어트 + 기획·설계 루프 재편 + **SSOT 다이어트 (9→7, 28% 감소)**

### 폐기된 agent (4)

- `security-reviewer` (PR #348) — `pr-reviewer §F-Security` + architect 위협 모델 가정·invariant 흡수
- `design-critic` (PR #351) — designer 1 시안 + 사용자 직접 PICK
- `product-planner` (PR #352) — 메인 Claude 가 사용자와 *직접 그릴미 대화* 로 PRD/stories.md 작성. 외부 검증은 `plan-reviewer` (잔존)
- (옛 단일 `architect` agent — 이미 system-architect / module-architect 로 분리 완료)

agent 13 → 9.

### stories.md 양식 단순화 + impl 파일 7 원칙 (PR #355)

- stories.md = user story (`As a / I want / So that`) 만. 옛 3 섹션 (`대상 화면·컴포넌트` / `동작 명세` / `수용 기준 (Story 단위)`) 폐기
- impl 파일 7 원칙 (Scope / 자기완결성 / 사전 준비 / 시그니처 / AC 실행커맨드 / 주의사항 / 네이밍)
- impl 파일 진입 prompt 의무 (architecture.md + adr.md + 의존 PR read)
- ADR 룰 + architecture.md 비대화 방지 (300줄 cap)

### `feature-build-loop` 폐기 + `/architect-loop` 신설 (본 PR — PR3-B)

- 옛 `feature-build-loop` (Step 2~6.N 통째 commit X 후 첫 task PR commit3 에 누적) → `/product-plan` (Step 2~3, PRD+stories PR1) + `/architect-loop` (Step 4~6.N, 설계 PR2) 분리
- `/architect-loop` 진입 = 사용자 명시 호출 (자동 X). 워크트리 ON 자동
- commit 단위: ux-flow → commit1 / architecture.md+adr.md → commit2 / impl/NN-*.md K 개 → commit 3..K+2 / PR 1개 + 머지
- 본 변경 SSOT = `commands/architect-loop.md`, `orchestration.md §3.1.5 / §4.2` (당시 기준 — 현 `skills/architect-loop/` + loop-procedure §7.0 으로 해체)

### `Step 4.5 sync` + `backlog.md` 폐기 (본 PR)

- 옛 룰: engineer IMPL_DONE 후 메인이 stories.md `[x]` 체크 + backlog.md epic `[x]` 체크
- 폐기 사유: 새 stories.md 양식 = task `[ ]` 자체 없음 (user story 만, PR #355) + 진행 추적 SSOT 단일화 (GitHub issue close 시스템 + PR body `Closes`/`Part of` 트레일러)
- impl-task-loop commit3 = src/** **only** (옛 `src/**, stories.md 등` 룰 폐기)

### PR body `Closes` 판정 메커니즘 변경 (본 PR)

- 옛 룰: stories.md 부모 Story 섹션 `[ ]` 카운트 (awk one-liner)
- 새 룰: impl 파일 frontmatter `task_index: <i>/<total>` + `story: <N>` grep
- module-architect 가 frontmatter 박음 (호출자 prompt 의 `task_index` 그대로). epic 마지막 story 판정 = gh API 1 회 호출

### 이슈 등록 자동화 (PR #353)

- `scripts/create_epic_story_issues.sh` 신설 — stories.md parse + epic/story 이슈 생성 + sub-issue API 연결 한 명령
- `/impl` / `/impl-loop` 진입 직전 task 진행 상태 확인 룰 (issue #346 옵션 C — `git log --grep` + plan tail read)

### 마이그레이션 정책

- **활성 프로젝트 (jajang 등) 진행 중 working tree** — 옛 룰 그대로 종료. 신규 epic 만 새 룰 (`/architect-loop`) 적용
- **옛 양식 stories.md (task `[ ]` 박힌)** — 잔재 허용. backfill 강제 X. 새 작성만 새 양식
- **자동 변환 원하는 사용자용** — `scripts/migrate_stories_to_new_format.sh` (report-only, 자동 변환 X)

### Breaking Change 호환 깨짐 알림

다음 sub-agent 직접 호출자 = 깨짐:
- `subagent_type: "dcness:product-planner"` → 메인 Claude 가 사용자와 직접 그릴미 대화 + `plan-reviewer` 외부 검증
- `subagent_type: "dcness:design-critic"` → designer 1 시안 + 사용자 PICK
- `subagent_type: "dcness:security-reviewer"` → `pr-reviewer §F-Security` 흡수

해당 호출자 = `/issue-report` / `/impl` / `/product-plan` / `/architect-loop` skill 진입으로 자동 라우팅.

### `harness/hooks.py` catastrophic gate 단순화 (본 PR)

- §2.3.4 / §2.3.5 = 옛 단일 `architect` agent + mode 시절 잔재. prerequisite 검증은 메인 영역 (architect-loop skill §Pre-flight gate / 전제 조건) 으로 이전 — 코드 강제 폐기
- §2.3.1 / §2.3.3 / §2.3.6~§2.3.8 = 유지
- `_has_plan_ready` 갱신: `module-architect.md` + occurrence (`module-architect-N.md`) 우선, legacy 호환 유지

### 배포 경로 (CLAUDE.md §0.5)

- (1) plug-in 본체 — `commands/architect-loop.md` 신설 + `agents/{module-architect,system-architect,engineer,pr-reviewer,qa}.md` 갱신 + `harness/hooks.py` 갱신
- (2) init-dcness 배포 — `scripts/migrate_stories_to_new_format.sh` (선택 사용)
- (3) SSOT 문서 — `docs/plugin/{orchestration,loop-procedure,issue-lifecycle,handoff-matrix}.md` 갱신

**사용자 적용**:
```sh
claude plugin update dcness@dcness
```

기존 활성 프로젝트의 진행 중 epic 은 옛 룰 그대로 종료. 신규 epic 부터 `/product-plan` → `/architect-loop` → `/impl-loop` 시퀀스 적용.

### SSOT 다이어트 5 PR (#366~#371)

자연어 SSOT 9개 → **7개**, 총 2,388줄 → **1,714줄** (28% 감소). 외부 사용자 시야 5 SSOT (orchestration / loop-procedure / handoff-matrix / hooks / issue-lifecycle).

#### PR-0 (#366) — enum 현행화 잔재 정리
- `agents/architecture-validator.md` `system-architect READY` → `PASS` (3곳)
- `docs/plugin/handoff-matrix.md` §1.4b/§1.9 Note (옛 6 mode / 옛 validator 5 모드 폐기 알림) → 제거
- `docs/plugin/orchestration.md` + `commands/impl.md` 옛 `MODULE_PLAN_READY` 마커 표현 제거

#### PR-1 (#367) — `known-hallucinations.md` 폐기
- 39줄, entry 1건 (jest) — SSOT 별도 파일 ROI △. agent body 의 *공식 docs WebFetch* 가이드가 진본
- 3 agent (code-validator / module-architect / system-architect) cross-ref 제거

#### PR-2 (#368) — `orchestration.md` 다이어트 + 시퀀스 재구성
- 463 → 351줄 (24% 감소)
- §2 시퀀스 재편: §2.1 catastrophic (원칙) / §2.2 기획 mermaid / §2.3 설계 mermaid / §2.4 구현 mermaid
- §3 mini-graph 6개 폐기 (§4 풀스펙 표가 진본). §4.8 direct-impl-loop 폐기 (§4.3 와 100% 동일)
- **§2.3 catastrophic → §2.1** cross-ref 갱신 (코드/테스트/문서 ~25 곳, stderr 메시지 + 테스트 매치 정합)

#### PR-4 (#369) — 작은 SSOT 4개 다이어트
- `hooks.md` (281→239): 미사용 event 압축 / 외부 사용자 영향 반복 단락 폐기 / 우회 표 통합 / 한눈요약 폐기
- `handoff-matrix.md` (225→201): §1.2 번호 정렬 / §1.4 "기술 에픽" 단락 폐기 / §4.3 코드 인용 → link
- `issue-lifecycle.md` (191→181): §1.3.1 sub-issue 절차 압축 / §2.3 1줄 압축
- `design.md` §5.4 작성 스타일 폐기 (글로벌 메모리 중복)

#### PR-3 (#371) — `dcness-rules.md` 폐기 + 슬림 inject + loop-procedure 흡수
- `dcness-rules.md` (263줄) 폐기
- **SessionStart inject**: 263줄 BLOCKING GATE Read 강제 → **~30줄 슬림 본문 직접 inject** (92% 감소)
- 토큰: `[dcness-rules 로드 완료]` → `[dcness 활성 확인]`
- §1 강제 영역 2가지 + 안티패턴 4건 → `CLAUDE.md §0.7` 본문 흡수
- §3 mechanics + 행동지침 (echo 5~12줄 / REDO 분류 / 자가점검 / AMBIGUOUS / step 명명) → `loop-procedure.md §3.1/§3.2` 흡수
- §4 리뷰 출력 + 개선점 코멘트 → `loop-procedure.md §6` 흡수
- 10 agent cross-ref redirect + 코드 SSOT (`agent_boundary.py`, `hooks.py`, etc.) 갱신

### 사용자 영향 — SSOT 다이어트

**외부 활성 프로젝트** (jajang 등):
- 매 세션 SessionStart inject: 263줄 → ~30줄 (**92% 감소**)
- 새 토큰 `[dcness 활성 확인]` (옛 `[dcness-rules 로드 완료]` 대체)
- catastrophic 룰 번호 `§2.3.x` → `§2.1.x` (코드 stderr 메시지 자동)
- agent body cross-ref redirect 완료 — agent 동작 변경 0

**plug-in update 시 자동 적용** — 사용자 수동 작업 0.

---

## v0.2.16 (2026-05-11)

**커밋 범위**: `v0.2.15..(다음 태그)`
**핵심 변경**: TDD 게이트 design pivot — CI 게이트 + commit-msg chain 전체 rollback, PreToolUse tdd-guard 도입

- **이슈 #320 design pivot (PR #339)** — v0.2.10~v0.2.13 의 CI 게이트 (composite
  action) + commit-msg TDD chain 이 monorepo lifecycle hook / pm 다양성 / missing
  test script 등 함정 누적. 사용자 의도 ("구현보다 테스트 먼저") 는 사후 검증
  아니라 *작성 전 차단*. PreToolUse hook 시점 차단으로 전환.
  - **Rollback**:
    - `.github/actions/tdd-gate/action.yml` 삭제
    - `scripts/check_tdd_staged.mjs` 삭제
    - `scripts/hooks/commit-msg` TDD chain 제거 (git-naming 만 남김)
    - `commands/init-dcness.md` Step 2.9 (CI 게이트) + Step 2.10 (commit-msg TDD) 제거
    - **유지**: `scripts/pr-finalize.sh` (사용자 명시 의도)
  - **신규**:
    - `hooks/tdd-guard.sh` — PreToolUse[Edit|Write|NotebookEdit] hook
    - `hooks/hooks.json` matcher 등록
    - `commands/init-dcness.md` Step 2.9 (신규 안내문)
  - **영감**: jha0313/codex-live-demo `.codex/hooks/tdd-guard.sh`
  - **동작**: agent 가 src 파일 Edit/Write 시도 시 매칭 test 파일 존재 검사 →
    없으면 deny + 한국어 안내. TS/JS 한정. 자동 skip (설정/타입/Next.js 특수/비-코드)
    풍부. 다른 언어 영향 0.

**차이** (이전 v0.2.13 commit-msg vs 본 PR PreToolUse):

| | v0.2.13 commit-msg | v0.2.16 PreToolUse |
|---|---|---|
| 시점 | commit 직전 | 코드 작성 *직전* |
| 진짜 TDD | △ 사후 검증 | ✅ 작성 전 차단 |
| 실행 | O test 실행 | ❌ 존재만 |
| 함정 | jajang 사단 (lifecycle / pm) | 적음 (자동 skip 풍부) |
| 범위 | 4 언어 | TS/JS |
| 옵트인 | 마커 파일 | 자동 (TS/JS 검출) |

**실증 검증 8 케이스**:
- test 없는 src → DENY
- test 있는 src → PASS
- 설정 / Next.js / .py / test 자체 / empty → silent skip

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `hooks/tdd-guard.sh` + `hooks/hooks.json` plug-in 업데이트 자동
- (2) init-dcness 배포 — Step 2.9 안내문. tdd-guard 사용자 repo cp X (plug-in hook 직접 발화)
- (3) SSOT 문서 — N/A

**한계 (v0.2.16)**:
- TS/JS 한정 — 다른 언어 후속
- *test 실행 X* — 존재만 확인 (실행은 사용자 vitest watch / CI 등 개별)
- agent 가 `Bash` 으로 직접 파일 작성 시 차단 X (단 catastrophic-gate 등 다른 hook 이 잡음)

**사용자 적용**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트 (jajang — 이전 TDD 인프라 정리):
```sh
cd ~/project/jajang
git rm .github/workflows/tdd-gate.yml
git rm -f .dcness/tdd-gate-enabled
git commit -m "..."
```

이후 agent Edit/Write 시 tdd-guard 자동 발화. 사용자 추가 설정 0.

---

## v0.2.15 (2026-05-11)

**커밋 범위**: `v0.2.14..(다음 태그)`
**핵심 변경**: TDD 게이트 polish — `ignore_scripts` input + `pr-finalize.sh` 한 명령 머지

- **이슈 #320 jajang prepare hook self-block (PR #336)** — composite action 에
  `ignore_scripts` input 추가. monorepo workspace `"prepare": "npm run build"`
  같은 hook 이 root `npm ci` 시 발화 → 빌드 실패 → tdd-gate self-block 회피.
  - `with: { ignore_scripts: true }` 옵트인 시 `--ignore-scripts` flag 적용
  - pnpm / yarn / bun / npm 모두 지원
  - 디폴트 false (기존 행동 유지)
  - thin yml 템플릿에 `fetch-depth: 0` + 옵트인 주석 추가

- **이슈 #320 pr-finalize helper (PR #337)** — 머지 절차 5 명령 → 1 명령.
  사용자 피드백 "머지되면 main 으로 다시 되돌아가고 pull 까지 했으면" 대응.
  - `scripts/pr-finalize.sh` 신규
  - 흐름: gh pr merge --auto → gh pr checks --watch → auto-merge 완료 대기 → checkout main + pull
  - argument 없으면 current branch 의 open PR 자동 검출
  - working tree dirty 시 사용자 확인 후 sync skip
  - CI FAIL / 머지 안 됨 시 exit 1 + 안내
  - `git-naming-spec.md §6` + `CLAUDE.md §5` 머지 절차 갱신 — 1 명령으로 통합

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `.github/actions/tdd-gate/action.yml` + `scripts/pr-finalize.sh`
- (2) init-dcness 배포 — Step 2.9 thin yml 갱신 (옵트인 주석 + fetch-depth)
- (3) SSOT 문서 — `git-naming-spec.md` §6 + `CLAUDE.md` §5

**jajang 즉시 적용**:
```sh
claude plugin update dcness@dcness
/init-dcness   # 새 thin yml 받음
# .github/workflows/tdd-gate.yml 에서 with: ignore_scripts: true 박음 (monorepo prepare hook self-block 회피 시)
bash scripts/pr-finalize.sh   # 머지 + main sync 자동
```

---

## v0.2.14 (2026-05-11)

**커밋 범위**: `v0.2.13..(다음 태그)`
**핵심 변경**: init-dcness Step 2.11 — 인프라 머지 자동화 (사용자 부담 0)

- **이슈 #320 (사용자 피드백) (PR #334)** — `/init-dcness` 가 cp 만 하고 git
  add/commit/PR 사용자 부담. 까먹으면 workflow yml 이 main 미반영 → CI 게이트
  dead code. 본 release 가 자동 commit + PR 까지 끝까지 진행.
  - `commands/init-dcness.md` Step 2.11 신규
  - 변경 파일 검출: `.github/workflows/` + `.dcness/` 명시 path
  - branch 검사: main 일 때만 자동 진행 (사용자 작업 보호)
  - 사용자 동의 (Y/n) 후: branch → stage → commit → push → PR
  - branch 패턴: `docs/dcness_init_{timestamp}` (git-naming-spec 정합)
  - 자동 머지 X — 인프라 PR 은 사용자 검토 후 머지 권장

**jajang 사단 (실측)**:
- 기존: `git-naming-validation.yml` 만 main 등록. `tdd-gate.yml` + `pr-body-validation.yml` working tree 잔존
- 본 release 후 `/init-dcness` 재실행 → Step 2.11 발화 → 자동 PR → 머지하면 모든 workflow 정상

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `commands/init-dcness.md` plug-in 업데이트 자동
- (2) init-dcness 배포 — Step 2.11 신규. 기존 활성 프로젝트는 `/init-dcness` 재실행 시 발화
- (3) SSOT 문서 — N/A

**한계**:
- 사용자가 이미 PR 만든 인프라 변경 있을 때 중복 시도 가능 (메인 Claude 가 사전 `gh pr list --search` 검사 권장)
- `gh` CLI 미설치 환경 → push 까지만 + 사용자 수동 PR 권유

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트:
```sh
/init-dcness   # Step 2.11 발화 — working tree 인프라 변경 검출 시 자동 PR 제안
```

---

## v0.2.13 (2026-05-11)

**커밋 범위**: `v0.2.12..(다음 태그)`
**핵심 변경**: TDD 게이트 phase 4 — pre-commit (commit 단 차단, 자체완결 wall)

- **이슈 #320 #1 phase 4 (PR #332)** — commit-msg hook chain 에 TDD 게이트 추가.
  staged src 변경 = test 변경 함께 + 변경분 test 실행 PASS 강제. branch protection
  의존성 0 → 진짜 자체완결 wall.
  - `scripts/check_tdd_staged.mjs` 신규 — 본체 (옵트인 마커 + skip marker + 분기 + 실행)
  - `scripts/hooks/commit-msg` 갱신 — git-naming 후 TDD 게이트 chain
  - `commands/init-dcness.md` Step 2.10 신규 — 옵트인 + 3-commit 구조 정합 안내
- **옵트인 메커니즘**: `.dcness/tdd-gate-enabled` 마커 파일 활성화 신호. 부재 시 silent pass.
  다른 프로젝트 영향 0 (외부 활성화 프로젝트가 옵트인 안 한 경우 자동 발화 X).
- **skip marker**: commit message 안 `[skip-test: <사유>]` 매치 시 우회 — 단순 typo /
  문서 변경 / refactor 무영향 케이스 정당 우회.
- **변경분만 실행**: test-engineer 작성 task 용 test (5~15개) 만 실행 = 수초. 풀
  스위트 아님.
- **4 언어 자동 검출**: jest / vitest (deps 검사) / pytest / cargo test / go test.

**3-commit 구조 정합** (loop-procedure §3.4):

| commit | stage | TDD 게이트 |
|---|---|---|
| commit1 (docs) | `docs/impl/NN.md` | PASS (src 0) |
| commit2 (tests) | `src/__tests__/**` | PASS (test 만) |
| commit3 (src) | `src/**` + stories.md | PASS (branch diff test 인지) |
| 위반: src 만 | `src/bar.ts` | BLOCK |

**6 케이스 실측 검증** 완료 (PR #332 body 참조).

**layered defense 완성**:

| 단 | 어디서 | dcness 도입 |
|---|---|---|
| 1 | **commit 단** (commit-msg hook) | **v0.2.13 phase 4 ← 본 release** |
| 2 | CI workflow (affected) | v0.2.12 phase 3 |
| 3 | Branch Protection | 사용자 수동 (안내문) |

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `scripts/check_tdd_staged.mjs` + `scripts/hooks/commit-msg`
  chain — plug-in 업데이트 자동 반영
- (2) init-dcness 배포 — Step 2.10 신규. 기존 활성 프로젝트는 `/init-dcness` 재실행
  시 발화. commit-msg shim 은 이미 chain 로직 박혀있어 사용자가 옵트인 마커만 작성하면
  즉시 동작.
- (3) SSOT 문서 — N/A

**한계 (phase 4)**:
- node test runner: jest / vitest 자동. 그 외 (mocha / ava 등) → `npm test` 폴백
- rust: 단순화 — `cargo test` 풀 폴백 (변경 test 파일만 native 한계)
- python: pytest 만 (unittest 만 쓰는 프로젝트면 `[skip-test]` 우회)
- `--watch` 룰 (git-naming-spec §6) 그대로 — commit 단 차단으로 CI 우회 위험 ↓
  단 룰 완화는 별도 결정

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트:
```sh
/init-dcness   # Step 2.10 발화 — 옵트인 (Y) 시 .dcness/tdd-gate-enabled 마커 작성
git add .dcness/tdd-gate-enabled  # 팀 공유
```

---

## v0.2.12 (2026-05-11)

**커밋 범위**: `v0.2.11..(다음 태그)`
**핵심 변경**: TDD 게이트 phase 3 — affected detection 자동 (CI 병목 해소, 사용자 설정 0)

- **이슈 #320 #1 phase 3 (PR #330)** — composite action 이 4 언어 변경분 affected
  만 자동 실행. v0.2.11 phase 2 풀 스위트의 CI watch 병목 (2~5분/PR × N task)
  해소.
  - **node**: nx.json / turbo.json / pnpm-workspace.yaml 자동 검출 →
    `nx affected` / `turbo run test --filter=...[<base>]` /
    `pnpm -F "...[<base>]" test`. dependency 그래프 자동 포함.
    - 미검출 (yarn classic / npm workspaces / bun / 단일) → 풀 폴백
  - **python**: 변경 .py 파일의 가장 가까운 상위 `pyproject.toml` / `setup.py` /
    `setup.cfg` 식별 → 그 root 별 pip install + pytest. 변경 0건 → skip.
  - **rust**: Cargo.toml `[workspace]` 검출 시 변경 파일 → member 매핑 →
    `cargo test -p <member>`. 단일 crate → `cargo test`. 변경 0건 → skip.
  - **go**: 변경 .go 의 dirname (유니크) → `go test ./<path>/...`. 변경 0건 → skip.
  - **PR base 자동 추출**: `github.event.pull_request.base.sha` 또는 origin/main 폴백

**jajang 효과**:
- apps/mobile (js + pnpm workspaces) 변경 → 해당 workspace + dependents 만 jest
- apps/api (python) 변경 → apps/api 안 pytest 만
- 둘 다 변경 안 됐으면 skip
- 사용자 작업 0 — `package.json["dcness"]["testCommand"]` override 박을 필요 없음

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `.github/actions/tdd-gate/action.yml` plug-in 업데이트 자동
- (2) init-dcness 배포 — Step 2.9 안내문 갱신. thin yml unchanged (composite action
  호출 1줄만 박힘 → 자동 phase 3 적용)
- (3) SSOT 문서 — N/A (capability 확장)

**한계 (phase 3)**:
- python/rust/go dependency 그래프 자동 포함 = phase 4 (현재 path 기반)
- yarn classic / npm workspaces / bun affected = 풀 폴백 (native filter 약함)
- 비-지원 언어 (Elixir/Ruby/Java/.NET/PHP/Swift) = phase 4

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트는 thin yml 그대로 — composite action 만 phase 3 자동 적용 (다음 PR 부터).

---

## v0.2.11 (2026-05-11)

**커밋 범위**: `v0.2.10..(다음 태그)`
**핵심 변경**: TDD 게이트 phase 1 → phase 2 — polyglot universal (#320 #1 확장)

- **이슈 #320 #1 phase 2 (PR #328)** — TDD 게이트가 node 한정에서 4 언어 universal
  로 확장. v0.2.10 phase 1 의 *node + root `scripts.test` 단일 명령* 가정이
  polyglot 모노레포 (jajang = apps/mobile=js + apps/api=python) 에 안 맞아 root fix.
  - `.github/actions/tdd-gate/action.yml` — 4 언어 검출 + 매트릭스 실행
    - node: package.json + pm 자동 (pnpm/yarn/bun/npm)
    - python: pyproject.toml / setup.py / setup.cfg / requirements*.txt + pytest (unittest 자동 cover)
    - rust: Cargo.toml + cargo test --all
    - go: go.mod + go test ./...
  - 검출된 *모든* 언어 PASS 필요 (polyglot matrix 결합)
  - 4 언어 모두 미검출 시 fail (비-지원 언어 phase 3 대기)
  - `commands/init-dcness.md` Step 2.9: 4 언어 안내문 + polyglot 가이드

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `.github/actions/tdd-gate/action.yml` plug-in 업데이트 자동 반영
- (2) init-dcness 배포 — Step 2.9 안내문 갱신. 기존 활성 프로젝트는 `/init-dcness`
  재실행 시 새 안내문 받음. thin yml 은 unchanged (외부 composite action 호출 1줄만
  박혀있어 자동 phase 2 적용)
- (3) SSOT 문서 — N/A (capability 확장)

**polyglot 적용 효과**:
- jajang (mobile=js + api=python): plugin update + `/init-dcness` 재실행만으로
  자동 cover. root `scripts.test` 위임 명령 / 별도 pytest workflow 작성 불필요.
- 향후 polyglot 활성 프로젝트들 모두 자동 혜택.

**한계 (phase 2)**:
- 지원 외 (Elixir / Ruby / Java / .NET / PHP / Swift) — phase 3 후속
- Python tooling = pip 만 (poetry / pdm / uv 는 phase 3)
- 풀 스위트만 — incremental 로컬 hook 은 phase 4

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트:
```sh
/init-dcness   # Step 2.9 발화 — TDD 게이트 옵트인 + 4 언어 안내문
```

---

## v0.2.10 (2026-05-10)

**커밋 범위**: `9a63e28..(다음 태그)`
**핵심 변경**: jajang Epic 12 회고 통합 — 진짜 bug 5건 root fix (이슈 #320 / #302 / #321 C / #292)

- **이슈 #320 #1 — TDD 게이트 3 단 (PR #322)**: jajang Epic 12 task 03 cascade 26
  cases 사단 root fix. engineer 의 prompt-level boundary 룰 (echo / grep) 은 차단력
  0 → mechanical wall 도입. 산업 표준 (incremental pre-commit → CI 풀 → branch
  protection) 중 *CI 풀* + *branch protection* 단을 dcness 가 배포.
  - `.github/actions/tdd-gate/action.yml` 신규 (node 전용, pm 자동 검출)
  - `commands/init-dcness.md` Step 2.9 추가 — 옵트인 thin yml + branch protection 안내

- **이슈 #320 #2 — PR body Closes pre-flight (PR #324)**: jajang Story 2 #239 OPEN
  영구 잔존 사단. `loop-procedure.md §3.4` 의 PR body 자동 판단 bash 가 stories.md
  *전체* `[ ]` 카운트 → 다른 Story 미완 task 와 섞임 → 본 task 가 부모 Story 마지막
  이라도 `Part of` 박힘. awk 으로 부모 Story 섹션 한정 카운트로 교체.
  - `docs/plugin/loop-procedure.md` §3.4 bash 골격 수정
  - `docs/plugin/issue-lifecycle.md` §1.4 적용 절차 4 step 명문화 추가

- **이슈 #302 #1 — RETRY_SAME_FAIL allow-list 보강 (PR #323)**: jajang run-cf83861d
  false positive 3건 — architect MODULE_PLAN × 4 task 정상 호출이 retry 오인 → review
  trust 저하. `harness/run_review.py` allow-list 에 `PROSE_LOGGED` (#284 prose-only
  mode 표준 sentinel) 추가 + prose 내용 다르면 다른 invocation 으로 판정 룰 추가.
  - 회귀 테스트 2 추가 (test_retry_same_fail_prose_logged_skip /
    test_retry_same_fail_different_prose_skip)

- **이슈 #321 C 1/4 — STRAY_DIR_LEAK detector (PR #325)**: jajang run-dbd49faf
  `.claire` × 3 회 연속 typo 사례. `harness/run_review.py:detect_wastes` 에 typo
  의심 디렉토리 검출 추가 (difflib similarity 0.70 threshold + KNOWN_INFRA_DIR_NAMES
  allow-list).
  - 회귀 테스트 3 추가. false positive 후보 9개 검증 (.vscode/.cargo/.cache 등
    모두 0.70 미만)

- **이슈 #292 partial — Step 4.5 범위 외 path 명문화 (PR #326)**: jajang main
  stories.md drift 177건의 root cause 일부 명문화. `loop-procedure.md §4` 본문에
  `quick-bugfix-loop` / engineer 직접 호출 / 메인 직접 commit / dcness 도입 이전
  잔재 — 사용자 책임 path 명시 + backfill 가이드 cross-link.

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `harness/`, `agents/` 변경은 plug-in 업데이트 자동 반영
- (2) init-dcness 배포 — Step 2.9 신규 (TDD 게이트). 기존 활성 프로젝트는
  `/init-dcness` 재실행 필요 — Step 2.9 자동 발화하여 thin yml 옵트인
- (3) SSOT 문서 — `loop-procedure.md` / `issue-lifecycle.md` plug-in cache 직접 read

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트는 추가로 `/init-dcness` 재실행 (Step 2.9 발화 + TDD 게이트
옵트인 + branch protection 안내). 멱등 — 다른 Step 들은 이미 적용된 경우 skip.

---

## v0.2.9 (2026-05-09)

**커밋 범위**: `156691f..(다음 태그)`
**핵심 변경**: init-dcness 신규 프로젝트 초기 docs 폼 시드 (이슈 #296)

- **이슈 #296** — `/init-dcness` 실행 시 `docs/PRD.md` / `docs/ARCHITECTURE.md` /
  `docs/ADR.md` 3개 파일 시드 (부재 시만, 멱등). 사용자가 PRD 논의 후 채워넣을
  표준 placeholder 제공 — 매 프로젝트마다 다른 형태로 시작하던 분산 해소.
  - `templates/project-init/{PRD,ARCHITECTURE,ADR}.md` 신규.
  - `commands/init-dcness.md` Step 2.8 추가 — 부재 시 사용자 동의 받고 cp.
  - 짧고 placeholder 위주 (한 화면 내 완결).

**배포 경로**: 본 변경은 init-dcness 가 사용자 repo 로 *복사·배포* 하는
인프라 (배포 경로 2). 기존 활성화 프로젝트는 자동 적용 안 됨 — `/init-dcness`
재실행 시 부재 파일만 시드 (멱등). 신규 프로젝트는 이번 release 부터 자동 시드.

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트에서 docs 폼 받고 싶으면 `/init-dcness` 재실행 (멱등).

---

## v0.2.8 (2026-05-09)

**커밋 범위**: `4926adf..(다음 태그)`
**핵심 변경**: helper picker semver 정렬 — 가장 오래된 cache 선택 회귀 수정 (이슈 #293)

- **이슈 #293** — helper 진입 패턴 `ls -d ${CLAUDE_PLUGIN_ROOT:-.../dcness/dcness/*} | head -1`
  이 알파벳 순 정렬로 *가장 오래된* cache (예: 6 버전 환경에서 0.2.2) 선택. v0.2.7
  의 prose-only mode (이슈 #284 정착) 에 도달 못 해 0.2.2 의 enum-required mode +
  옛 휴리스틱 강제. jajang run-f0c23053 실측에서 휴리스틱 FP 2건 발생 (validator
  prose "0 FAIL" → enum=FAIL 오추출 / pr-reviewer "MUST FIX 없음 + NICE TO HAVE
  4건" → must_fix=true 오판정). 4 파일 (총 9 occurrences) 의 picker glob 패턴
  `head -1` → `sort -V | tail -1` 교체:
  - `docs/plugin/loop-procedure.md` (1)
  - `commands/run-review.md` (1)
  - `commands/init-dcness.md` (5)
  - `commands/efficiency.md` (2)

**영향**:
- v0.2.7 의 prose-only mode 가 picker 가 옛 cache 강제로 도달 못 했던 회귀 수정.
- 본 v0.2.8 부터는 picker 가 항상 최신 semver 선택 → prose-only mode 자연 활용.
- cache 다중 버전 환경 (`claude plugin update` 누적) 에서 모두 영향.

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 cache 가 0.2.7 이 아닌 옛 버전을 picker 강제하던 환경 (jajang 실측 사례) 은
본 업데이트 후 정상화.

---

## v0.2.7 (2026-05-08)

**커밋 범위**: `1cff44a..(다음 태그)`
**핵심 변경**: enum 시스템 폐기 → prose-only routing 전환 (epic #280)

- **이슈 #281** — `harness/routing_telemetry.py` 신규. PostToolUse Agent 훅이
  매 sub 종료 시 prose tail (1200자 cap) 을 `.metrics/routing-decisions.jsonl`
  에 1줄 append. 메인이 사용자 위임할 때는 CLI `record-cascade --reason ...`.
  enum heuristic-calls.jsonl 의 prose-only 후속 — 회귀 검증용 raw baseline.
- **이슈 #282** — `docs/plugin/handoff-matrix.md §1` 의 enum 표 12 종을
  자연어 routing 가이드로 재포맷. agent 별 가능한 결론 *유형* + 권장 다음
  처리 흐름을 prose 로 서술. §2 retry / §3 escalate / §4 권한은 보존.
- **이슈 #283** — 22 agent 파일 (12 master + 5 architect sub-mode + 5
  validator sub-mode) 의 enum 표를 자연어 가이드로 환원. frontmatter
  description / leading prose / "## 결론 enum" 표 모두 "결론 + 권장 다음
  단계 자연어 명시" 로 통일. 기존 enum 단어는 *예시 권장 표현* 으로 보존.
- **이슈 #284** — `harness/interpret_strategy.py` telemetry write 코드
  제거 (`.metrics/heuristic-calls.jsonl` 신규 기록 0). `_cli_end_step` 의
  `--allowed-enums` optional. 미지정 시 prose-only mode (stdout
  `PROSE_LOGGED`). legacy `--allowed-enums` 호출은 호환 보존.
  `dcness-rules.md §3.3` / `loop-procedure.md §3.1` prose-only mode 권장
  으로 갱신.
- **이슈 #285** — 배포 경로 검증. 본 epic 모든 변경은 plug-in 본체 (배포
  경로 1) 안. `claude plugin update` 로 자동 전파. init-dcness 가 사용자
  repo 로 복사하는 인프라 (배포 경로 2) 변경 없음. 사용자용 SSOT 문서
  (배포 경로 3) 는 plug-in cache 안 — 자동 갱신.

**전환 모델 (정착 후)**:
1. agent 가 prose 마지막 단락에 *어떤 결과로 끝났는지 + 메인이 누구를
   부르는 게 적절한지* 자유 표현.
2. 메인 Claude 가 prose + handoff-matrix.md §1 자연어 가이드 보고 routing.
3. `routing-decisions.jsonl` raw 누적 → 회고 분석 (#281).
4. 결정 못 하면 `routing_telemetry record-cascade` 후 사용자 위임.

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트는 plug-in update 만으로 자동 적용. init-dcness 재실행
불필요. 외부 활성화 프로젝트 동작 확인은 사용자가 일반 작업 진행 중 자연스
럽게 검증 (특별한 검증 절차 없음).

---

## v0.2.6 (2026-05-08)

**커밋 범위**: `09e537f..c69e28a`
**핵심 변경**: engineer 권한 경계 강화 + POLISH self-verify 면제 + Step 7 회고 메모리 의무 + 워크트리 hook 정정 + DeepEval 마이그레이션

- `agents/engineer.md`: 자체 `git commit/push/branch` 호출 + `stories.md/backlog.md/batch-list.md` 직접 수정 사전 차단 (#148). §권한 경계 / §IMPL_PARTIAL / §커밋 단위 규칙 / §1 task = 1 PR 안티패턴 4 군데 정합. POLISH 자가 검증 anchor 면제 명시 (#252)
- `harness/run_review.py`: `MISSING_SELF_VERIFY` 검사에서 `POLISH_DONE` 제외 — POLISH prose 본문 자체가 검증 substance, anchor 강제는 잉여 (#252). 회귀 방지 unittest 추가
- `docs/plugin/loop-procedure.md §5.5`: 7b caveat 보고 양식에 "📝 메모리 candidate" 섹션 + 의무 룰 추가 (#149). 7a clean 도 review report waste finding 시 동일 적용
- `docs/plugin/dcness-rules.md`: "Step 7 회고 → 메모리 저장 의무" 룰 추가 — SessionStart inject 로 매 세션 자동 인지 (#149)
- `scripts/hooks/cc-pre-commit.sh`: cwd 결정 우선순위 뒤집기 — `git rev-parse --show-toplevel` 우선, fallback `CLAUDE_PROJECT_DIR` (#268). 워크트리 안 commit 이 메인 main 으로 오인 차단되던 회귀 수정
- `tests/eval_*.py` + 평가 인프라: AgentEvals → DeepEval 마이그레이션 (#263)

**업데이트**:
```sh
claude plugin update dcness@dcness
```

---

## v0.2.5 (2026-05-07)

**커밋 범위**: `8d097b4..6612db0`  
**핵심 변경**: 루프 종료 후 finalize-run 강제 안전망 + REVIEW_READY 신호

- `loop-procedure.md §3.3`: advance enum 마지막 step → 사용자 대기 없이 즉시 Step 7 명시 (issue-240)
- `loop-procedure.md §5.1`: 트리거 명시 + end-run 안전망 설명 추가
- `session_state.py _cli_finalize_run`: `finalized_at` 플래그 저장 + review → `review.md` 파일 저장 + stderr `[REVIEW_READY]` 신호
- `session_state.py _cli_end_run`: `finalized_at` 없으면 자동 `finalize-run --auto-review` 실행
- `dcness-rules.md`: 파일 경로 채널별 형식 분기 룰 추가 (CC 채팅 = 평문 백틱, 도큐 = 마크다운 링크)

**업데이트**:
```sh
claude plugin update dcness@dcness
```

---

## v0.2.4 (2026-05-07)

**커밋 범위**: `0fb69df..6038ceb`  
**핵심 변경**: PostToolUse prose 추출 전면 실패 수정

- PostToolUse hook 에서 tool_response 가 list 포맷일 때 prose 추출 전면 실패하던 버그 수정 (issue-232)
- `plugin-release.md` 'bump' → '버전 올리기' 표현 개선

---

## v0.2.3 (2026-05-07)

**커밋 범위**: `bfd500d..0fb69df`  
**핵심 변경**: `claude plugin update` 버그 수정

- `marketplace.json` `plugins[].source` 를 github object → `"./"` 로 복구
- 신규 install 은 두 포맷 모두 동작했으나, update 는 `"./"` 만 동작함을 확인 (`e68a440` 에서 잘못 변경된 것)
- git 태그 관리 시작 (이 버전부터 `v{버전}` 태그 병행)

---

## v0.2.2 (2026-05-07)

**커밋 범위**: `ff3ae5b..bfd500d`  
**핵심 변경**: 내부 문서 구조 정리 + dcness-rules 전면 재편

- `dcness-rules.md` 전면 재편 — 대원칙 신설, 루프 구조화, prose-only 통합 (issue-223)
- `main-claude-rules.md`, `self-guidelines.md`, `governance.md`, `branch-protection-setup.md` 삭제 — 역할 흡수 또는 중복 제거
- `CLAUDE.md §3` lazy 표 누락 파일 보완

---

## v0.2.1 (2026-05-07)

**커밋**: `ff3ae5bcdbd62c8f2240ca94f31d593133634101` (release branch HEAD)  
**핵심 변경**: marketplace 배포 경로 정비 + 로컬 게이트 강화

- release 브랜치에서 `marketplace.json` 제거 (sync_local_plugin.sh 폐기, issue-221)
- `dcness-rules.md` 로 rename + 정제 (issue-217)
- cc-pre-commit.sh 브랜치명·PR 제목 로컬 게이트 추가 (issue-171)
- run_review false positive 수정 (issue-171)
