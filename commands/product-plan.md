---
name: product-plan
description: 새 기능 / PRD 변경 / 큰 기획을 받아 메인 Claude 가 사용자와 직접 그릴미 대화하며 `docs/prd.md` + `docs/stories.md` 작성 → plan-reviewer 외부 검증 → 사용자 피드백 confirm → 후속 단계 (이슈 등록 / `/architect-loop` / `/impl-loop`) 시퀀스로 진행하는 스킬. 사용자가 "기획자야", "새 기능", "피쳐 추가", "이런 기능이 필요할 것 같아", "기획해줘", "프로덕트 플랜", "/product-plan" 등을 말할 때 반드시 이 스킬을 사용한다. 구현 진입은 별도 (`/impl` / `/impl-loop`).
---

# Product Plan Skill — 메인 직접 인터랙션 + plan-reviewer 외부 검증

> **본 스킬 = 메인 Claude 가 사용자와 *직접* 대화하며 PRD/stories.md 작성**. product-planner sub-agent 폐기 (컨텍스트 손실 회피). 외부 검증은 plan-reviewer sub-agent.

## 그릴미 패턴 (PRD 작성 시 의무)

메인은 다음 패턴으로 진행:

1. **한 번에 한 질문** — 5 항목 한꺼번에 받지 말고 분기 따라 1개씩
2. **가설 + 권장안 제시** — 질문할 때 *추측 답안 1+ 포함*. 사용자가 picking 받기 쉽게
3. **추측 금지** — 코드/문서로 답 가능하면 *탐색 우선*. 모르면 모른다 명시
4. **결정 나무 가지치기** — 분기 따라 의존성 1 개씩 해결

(영감: `~/.claude/skills/grill-me/SKILL.md` 4 줄 룰. 사용자 user skill 외부 의존 X — 본 스킬 안 inline 흡수.)

## PRD 산출물 의무 (체크리스트 — 채우는 순서 자유)

그릴 대화 진행하며 `docs/prd.md` 에 다음 정보 다 채워졌는지 메인이 check:

- **서비스 개요** — 핵심 목적 (한 문장) + 타겟 유저 + 사용 상황 + 핵심 가치/차별점
- **기능 범위** — MVP 핵심 3~5 개 + 있으면 좋은 기능 + 명시적 제외 (NOT in scope)
- **기능별 스펙** — 각 기능마다 동작 명세 (유저 행동 → 시스템 반응) + 유저 시나리오 (Happy + 예외) + **수용 기준 (Given/When/Then, 검증 가능한 binary)** + 우선순위 (MoSCoW)
- **화면 인벤토리 + 대략적 플로우** — 텍스트 다이어그램 (기획 관점). UI 없는 기능은 `(UI 없음)` 표시
- **비즈니스 모델** — 수익 구조 + 과금 주체 + 성공 지표
- **외부 의존 보호** — PRD Must 기능 직결되는 외부 의존 (SDK / API / 모델 / 외부 라이브러리 / 다른 시스템) 각각:
  - (1) **product 요구사항 1줄** — 이 의존이 사용자에게 *무엇* 을 제공하는지 (= WHY). 구현 방식 표현 금지.
  - (2) **대체 불가 이유 1줄** — 왜 *이* 의존이 핵심인지. **금지 단어**: "그대로 / 1:1 동등 / 동일하게 / 이식 / port / parity / 마이그레이션 그대로" 같은 *HOW 단어* 가 등장하면 PRD 자체 거부 대상 (plan-reviewer §8.X 가 자동 catch). 이 단어들은 *기존 시스템의 구현* 을 product 요구사항으로 위장하는 신호 — "기존이 X 로 한다 → 새 시스템도 X" anti-pattern. *결과* 만 명시.
  - 외부 의존 0 개면 본 항목 "해당 없음" 명시 후 skip.
  - 근거: jajang Epic 19 사단 (2026-05) — "서버 ffmpeg 4 필터 mobile parity" framing 이 자기-부과 제약으로 굳어 *7개 대안 path* (RN-audio-api 합성 / pure-JS DSP / 단일-목적 native module / 요구사항 강등 + UX 보강 등) 검토 0건. WAV byte buffer 산술로 충분했던 사실 PRD/architecture/spike 전부 통과 후 발견.
- **스코프 결정** — 4 옵션 제시 의무 (사용자 명시 선택 받음):
  - **A Expansion** (MVP + 자연스럽게 추가)
  - **B Selective** (MVP + BM 직결 고영향, 균형)
  - **C Hold Scope** (요구사항 정확히)
  - **D Reduction** (가장 빠른 핵심 검증만)

미충족 영역 발견 시 메인이 그릴로 추가 질문 → 사용자 답 받고 채움.

### 수용 기준 작성 — 검증 가능 binary 의무

"잘 동작" / "사용자 친화적" 같은 모호 표현 X. 통과 조건이 binary 로 판단 가능해야:

| 약한 표현 | 강한 표현 |
|---|---|
| "검색이 빠르다" | "검색 결과 p95 < 200ms 응답" |
| "에러를 처리한다" | "Given 잘못된 입력, When 제출, Then 에러 메시지 X 표시 + 폼 유지" |
| "잘 보인다" | "각 카드 제목 1줄 + 메타 2줄 + 썸네일 16:9 비율" |

Given/When/Then 자체가 goal-driven 패턴 — 모든 수용 기준에 적용.

## stories.md 산출물 (단순화 — user story 만)

PRD 작성 완료 후 메인이 `docs/stories.md` Write — epic + N story 구조. **본문은 `As a / I want / So that` 만**. `대상 화면·컴포넌트` / `동작 명세` / `수용 기준 (Story 단위)` 같은 섹션은 *박지 않는다*:

- 대상 화면 / 동작 명세 = `docs/architecture.md` (큰 모듈 흐름 + 인터페이스) + impl 파일 (`docs/impl/NN-*.md`) 이 책임
- 수용 기준 (task 단위) = impl 파일의 REQ-NNN 표 (실행 가능 커맨드 의무)
- 수용 기준 (epic 단위) = stories.md 의 `## Epic` 섹션 `완료 기준` (사용자 검증 조건 크게)

`docs/stories.md` 형식:

```markdown
# Story Backlog

## Epic — <epic 한 줄 요약>

**목표**: <epic 의 비즈니스 목적 한 단락>
**선행 조건**: <있으면>
**완료 기준** (epic 단위 수용 기준):
1. <검증 가능한 조건 1>
2. <검증 가능한 조건 2>
3. ...

**GitHub Epic Issue:** (이슈 등록 후 박힘)

---

### Story 1 — <story 한 줄 요약>

**GitHub Issue:** (이슈 등록 후 박힘)

**As a** <user>,
**I want** <action>,
**So that** <benefit>.

---

### Story 2 — ...
```

**구버전 호환성 (마이그레이션 정책)**:
- 기존 외부 활성 프로젝트 (jajang Epic 11/12 등) 의 옛 양식 stories.md (`대상 화면·컴포넌트` / `동작 명세` / `수용 기준 (Story 단위)` 섹션 포함) 는 *그대로 허용* — backfill 강제 X
- **새 작성** 시만 본 단순화 룰 적용
- read 시 두 양식 모두 인식 가능 (parser 가 `As a / I want / So that` 매치만 의무)

task-level 세부 진행 추적 X (PR + GitHub Issue close 시스템 SSOT — [`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §0).

## 작성 절차 (메인 직접)

### Step 0 — 사전 read (lazy — 필요시만, #400)

정상 흐름은 본 skill 본문 + 인용된 docs §번호 만으로 진행. *룰 모호 / 분기 발생* 시에만 `docs/plugin/loop-procedure.md` / `orchestration.md` §2~§3 + §4.2 / `handoff-matrix.md` / `issue-lifecycle.md` 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

### Step 1 — 사용자와 그릴 대화

위 *그릴미 패턴* + *PRD 산출물 체크리스트* 따라 진행. 메인이 한 번에 한 질문씩, 분기 따라 가지치기. 모호 시 가설 + 옵션 제시. 코드/문서 read 가능한 부분은 탐색 우선.

### Step 2 — Spike Pre-Check (조건부)

사용자 입력 또는 1차 정형화 결과에 다음 *spike 의심 신호* 1+ 포함 시 PRD 작성 *전* plan-reviewer 를 `PRE_CHECK` 모드로 1회 호출 (`agents/plan-reviewer.md` "호출 모드" 섹션):

- **외부 의존 명시**: 외부 모델 / API / SDK 이름 (예: "OpenVoice", "ElevenLabs", "Replicate API")
- **조건부 약속 패턴**: "M0 에서 검증" / "후보 N개 비교 후 선정" / "X 안 되면 Y 로 fallback"
- **사용자 의문문**: "이거 진짜 되나?", "X 가 Y 를 지원하는지"

플로우:
- `PASS` → PRD 작성 진입. 검증 결과 (`EXTERNAL_VERIFIED` 섹션) 를 PRD 본문에 박음
- `FAIL` → 사용자에게 결과 보고 + 입력 재정리 요청
- `ESCALATE` → 사용자 위임

신호 없으면 skip — 바로 Step 3.

### Step 3 — PRD 작성

메인이 `docs/prd.md` Write/Edit. 새 작성 = `Write`, 변경 = `Edit` 도구 *섹션 단위 patch* 의무. **Write 통째 호출 금지** (기존 PRD 의 모르는 부분 silent 변경 위험).

### Step 4 — stories.md 작성

메인이 `docs/stories.md` Write. epic + N story 구조 (위 형식).

### Step 5 — plan-reviewer 외부 검증

PRD + stories.md 완성 후 plan-reviewer 호출 (`FULL` 모드 default):

```
Agent(subagent_type="plan-reviewer", prompt="""
PRD: docs/prd.md
Stories: docs/stories.md
Pre-Check 결과 (있으면): ...
""")
```

plan-reviewer 가 8 차원 심사 후 prose 결론 + findings emit.

### Step 6 — 피드백 항목별 수용 (β 패턴)

plan-reviewer findings 각 항목마다 메인이 *"수용 권장 / 거절 권장"* 의견 박아 사용자에게 출력 → 사용자 한 줄로 confirm:

```
[plan-reviewer finding 1] <내용>
  메인 의견: 수용 권장 — <이유>
  → 사용자 confirm: Y/n?

[plan-reviewer finding 2] <내용>
  메인 의견: 거절 권장 — <이유>
  → 사용자 confirm: Y/n?
```

- 사용자 *수용* 항목 → 메인이 `docs/prd.md` / `docs/stories.md` Edit 으로 patch
- 사용자 *거절* 항목 → 변경 X. PRD 본문에 *거절 사유* 1 줄 박음 (다음 review 재발화 방지)
- patch 완료 후 → 사용자 OK 시 Step 6.5. 다시 review 필요하면 Step 5 재진입 (cycle 한도 2)

### Step 6.5 — 통합 브랜치 그릴 (메인 → 사용자)

PRD/stories.md 검증 완료 후 branch 만들기 *전* 메인이 1회 그릴 — 작업 전략 결정:

```
이 epic 작업량 어떻게 가시죠?

(a) 일반 — sub-PR 마다 main 으로 머지. 가장 단순. 작업 중 main 에 중간 결과 점진 노출.
(b) 통합 브랜치 — `feature/<slug>` 따고 *모든 sub-PR (PRD/stories.md 포함)* base = 통합 브랜치.
    마지막에 통째 main 머지. main 보호 + spike NO_GO 시 통째 폐기 자유. drift 비용 있음.

→ slug 후보 (메인 추정 — epic 제목 기반): `<auto-suggest>`
→ 응답: a / b + (b 응답 시 slug 확인)
```

- 사용자 (a) → 마커 X. 평소대로 Step 7 (a) 흐름.
- 사용자 (b) → 메인이 stories.md 상단에 `**Base Branch:** feature/<slug>` 1줄 추가 (`**GitHub Epic Issue:**` 줄과 인접). Step 7 (b) 흐름 진입.

> 마커 1 줄의 효과 — 이후 architect-loop / impl-loop / impl 가 매 sub-PR 만들 때 stories.md 의 `**Base Branch:**` 매치 → `gh pr create --base <매치 값>`. 매치 없음 → `--base main` (default).

### Step 7 — branch + commit + PR + 머지

**(a) 일반 (default, trunk)**:

```
1. git checkout -b docs/<slug> main          # git-naming-spec §1 패턴
2. git add docs/prd.md docs/stories.md
3. git commit -m "[docs] PRD 신규 / 변경 요약"   # git-naming-spec §3 패턴
4. git push -u origin docs/<slug>
5. gh pr create --base main --title "..." --body "..."   # git-naming-spec §4~§5
6. bash "$PLUGIN_ROOT/scripts/pr-finalize.sh" <PR_NUMBER>   # auto-merge + CI watch + main sync
```

**(b) 통합 브랜치 (integration)**:

```
1. git checkout -b feature/<slug> main       # 통합 브랜치 생성
2. git push -u origin feature/<slug>          # 원격 push (sub-PR base 로 쓸 수 있게)
3. git checkout -b docs/<slug>_prd feature/<slug>   # PRD sub-PR 브랜치
4. git add docs/prd.md docs/stories.md
5. git commit -m "[docs] PRD 신규 / 변경 요약"
6. git push -u origin docs/<slug>_prd
7. gh pr create --base feature/<slug> --title "[docs] ..." \
     --body "... \nDocument-Exception-PR-Close: PRD/stories.md 머지 — 이슈 없음"
   # PR body 의 `Document-Exception-PR-Close` 마커 = check_pr_body.mjs 게이트 우회
   # (PRD sub-PR 은 이슈 등록 *전* 단계 — 별도 추적 이슈 만들지 X, jajang #261 카오스 회피)
8. bash "$PLUGIN_ROOT/scripts/pr-finalize.sh" <PR_NUMBER>
   # PRD sub-PR 머지 후에도 통합 브랜치는 살아있음 (sub-PR 더 누적 예정)
```

### Step 8 — 이슈 등록 trigger (선택)

PR 머지 완료 후 메인이 사용자에게 confirm:

```
PRD + stories.md 머지 완료. 이제 GitHub epic + story 이슈를 등록할까요? (Y/n)
```

> 통합 브랜치 케이스 (Step 6.5 (b)) 인 경우 — stories.md 의 `**Base Branch:**` 마커가 `scripts/create_epic_story_issues.sh` 에 의해 epic issue body 첫 줄로 *자동 미러링* 됨. GitHub UI 에서 #epic 만 봐도 통합 브랜치 모드임을 즉시 인지 가능.

사용자 Y → 메인이 `scripts/create_epic_story_issues.sh` 호출 (자동화 스크립트):

```bash
bash scripts/create_epic_story_issues.sh docs/stories.md
```

스크립트 동작:
1. stories.md parse — epic + Story N 추출
2. milestone number 조회 (Epics / Story)
3. epic 이슈 1 생성 → stories.md 에 번호 박음
4. story 이슈 N 순차 생성 → stories.md 에 번호 + 하단 표 박음
5. sub-issue API 호출 (epic ↔ story N 연결, GitHub native sub-issue API)
6. 결과 prose 출력

상세 SSOT = [`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §1.

스크립트 실패 시 메인이 사용자에게 보고 + `docs/plugin/issue-lifecycle.md` §1 따라 수동 처리 가능 (`mcp__github__create_issue` + `gh api` 직접 호출).

이슈 등록 후 stories.md 변경분은 별도 commit + PR 또는 사용자 자율 (스크립트 자체는 git mutation X — stories.md 만 수정).

### Step 9 — `/architect-loop` 진입 권장 (사용자 결정)

이슈 등록 완료 후 메인이 사용자에게 confirm:

```
PRD + stories.md + 이슈 등록 완료. 이제 설계 루프 진입할까요?
→ `/architect-loop <epic-path>` 호출 시 ux-architect / system-architect / architecture-validator / module-architect × K 순차 진행 + 1 PR 머지. (Y/n)
```

사용자 Y → `/architect-loop` 진입. N → 사용자가 나중에 직접 호출 (자동 진입 X — `commands/architect-loop.md` §전제 조건 정합).

## 비대상 (다른 skill 추천)

- 버그 → `/issue-report` (`qa-triage`)
- 한 줄 수정 / 버그픽스 → `/issue-report` (분류 후 impl-task-loop fallback)
- 디자인만 → designer 직접 (Pencil 또는 `design-variants/*.html`)

## 후속 라우팅

- PRD/stories 완성 + 머지 + 이슈 등록 후 → `/architect-loop` (설계 루프 — 권장) → 그 후 `/impl-loop` / `/impl` (구현 루프)
- 기존 PRD 변경 → 본 스킬 재진입 (`Edit` 도구 섹션 단위 patch 의무, Write 통째 X)
- `UX_REFINE_READY` 후속 — ux-architect REFINE → designer

## 워크트리 (X)

`/product-plan` 은 워크트리 자동 진입 안 함. 기획·설계는 동시 다중 batch 충돌 회피 목적 부재. 메인 working tree 에서 별 branch 따고 직접 진행. 자세히 = [`docs/plugin/loop-procedure.md`](../docs/plugin/loop-procedure.md) §1.1.

## 참조

- 시퀀스 / 핸드오프 / 권한: [`docs/plugin/orchestration.md`](../docs/plugin/orchestration.md) §2~§3, [`docs/plugin/handoff-matrix.md`](../docs/plugin/handoff-matrix.md)
- 그릴미 원형: `~/.claude/skills/grill-me/SKILL.md` (사용자 user skill)
- 이슈 등록 SSOT: [`docs/plugin/issue-lifecycle.md`](../docs/plugin/issue-lifecycle.md) §1
- 브랜치·커밋·PR 네이밍: [`docs/plugin/git-naming-spec.md`](../docs/plugin/git-naming-spec.md)
- plan-reviewer 8 차원 심사: [`agents/plan-reviewer.md`](../agents/plan-reviewer.md)
