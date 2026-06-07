---
name: product-plan
description: 새 기능 / PRD 변경 / 큰 기획을 받아 메인 Claude 가 사용자와 직접 그릴미 대화하며 `docs/prd.md` + `docs/stories.md` + `docs/tech-review.md` *스켈레톤* 작성 → 사용자 1차 OK → `product-acceptance:SPEC_ACCEPTANCE` → PR 머지 + 이슈 등록 → `/tech-review` (선행 기술 검증) 권고 → 사용자 2차 OK 후 `/design` (`/architect-loop` 호환) 진입 시퀀스로 진행하는 스킬. 사용자가 "기획자야", "새 기능", "피쳐 추가", "이런 기능이 필요할 것 같아", "기획해줘", "스펙 작성", "PRD 작성", "프로덕트 플랜", "/spec", "/product-plan" 등을 말할 때 반드시 이 스킬을 사용한다. 구현 진입은 `/impl` 이 lane 을 판정하고, story/epic 구현 완료 후 `/acceptance` 로 제품 검수한다.
---

# Product Plan Skill — 메인 직접 인터랙션 + tech-review 단계 분리

> **본 스킬 = 메인 Claude 가 사용자와 *직접* 대화하며 PRD/stories.md + tech-review.md *스켈레톤* 작성**. product-planner sub-agent 폐기 (컨텍스트 손실 회피). 기술 검증은 별도 스킬 `/tech-review` 단계로 분리 (선행 기술 검증 전문 — tech-reviewer agent). `/spec` 는 본 스킬의 호환 alias 다.

> 🔴 **라우팅 SSOT** — skill 간 시퀀스 (PRD → `product-acceptance:SPEC_ACCEPTANCE` → `/tech-review` → `/design` (`/architect-loop` 호환) → `/impl` → `/acceptance`) / 재진입 / escalate / 단방향 관례 / 비대상 추천은 [`product-plan-routing.md`](product-plan-routing.md) 가 본 skill 의 단일 진본. 본 파일은 *진행 절차(Step)* 만 담는다. 분기·다음 단계 판단이 필요하면 그 파일을 읽는다. 본 skill 은 메인 직접 작업이지만, `/spec` 이행 기준 검수로 `product-acceptance:SPEC_ACCEPTANCE` 를 1회 호출한다.

## 그릴미 패턴 (PRD 작성 시 의무)

메인은 `/grill-me` 원문 지시를 *번역 없이 그대로* 적용해 그릴 대화를 진행한다 (절차형으로 번역하면 `relentlessly`·종료조건 같은 강도·동기가 손실됨 — 단독 `/grill-me` 가 강한 이유는 원문이 그대로 들어가기 때문):

> Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.
>
> Ask the questions one at a time.
>
> If a question can be answered by exploring the codebase, explore the codebase instead.

**product-plan 맥락 (위 원문에 더해 못박는 것)**:

- **이해 도달이 1차, PRD 작성은 그 기록** — 그릴의 목표는 `shared understanding` 도달이고, 아래 *PRD 산출물 체크리스트* 는 그 대화의 *부산물(기록)* 이다. 산출물 칸 채우기가 캐묻기를 잡아먹지 않게 한다.
- **체크리스트 충족 ≠ 종료** — 종료조건은 핵심 분기에서 사용자가 납득(shared understanding)했을 때다. 빈칸이 다 차도 핵심(목적·실제 페인·규모·엣지)에서 사용자가 납득 못 했으면 계속 캐묻는다.
- **why 부터, how 로 직행 금지** — 권장안 picking 만 시키지 말고 반례·엣지를 던져 사용자 사고를 압박한다. 형식(how) 보다 목적·실제 페인·규모(why) 를 먼저 판다.

(원문 출처: `~/.claude/skills/grill-me/SKILL.md`. 사용자 user skill 이라 외부 활성 프로젝트엔 없음 — 의존하지 않고 본 스킬에 원문 그대로 inline.)

## PRD 산출물 의무 (체크리스트 — 채우는 순서 자유)

그릴 대화 진행하며 `docs/prd.md` 에 다음 정보 다 채워졌는지 메인이 check:

- **서비스 개요** — 핵심 목적 (한 문장) + 타겟 유저 + 사용 상황 + 핵심 가치/차별점
- **기능 범위** — MVP 핵심 3~5 개 + 있으면 좋은 기능 + 명시적 제외 (NOT in scope)
- **기능별 스펙** — 각 기능마다 동작 명세 (유저 행동 → 시스템 반응) + 유저 시나리오 (Happy + 예외) + **수용 기준 (Given/When/Then, 검증 가능한 binary)** + 우선순위 (MoSCoW)
- **화면 인벤토리 + 대략적 플로우** — 텍스트 다이어그램 (기획 관점). UI 없는 기능은 `(UI 없음)` 표시
- **비즈니스 모델** — 수익 구조 + 과금 주체 + 성공 지표
- **외부 의존 보호** — PRD Must 기능 직결되는 외부 의존 (SDK / API / 모델 / 외부 라이브러리 / 다른 시스템) 각각:
  - (1) **product 요구사항 1줄** — 이 의존이 사용자에게 *무엇* 을 제공하는지 (= WHY). 구현 방식 표현 금지.
  - (2) **대체 불가 이유 1줄** — 왜 *이* 의존이 핵심인지. **금지 단어**: "그대로 / 1:1 동등 / 동일하게 / 이식 / port / parity / 마이그레이션 그대로" 같은 *HOW 단어* 가 등장하면 PRD 자체 거부 대상 (메인 그릴미 단계에서 catch). 이 단어들은 *기존 시스템의 구현* 을 product 요구사항으로 위장하는 신호 — "기존이 X 로 한다 → 새 시스템도 X" anti-pattern. *결과* 만 명시.
  - 외부 의존 0 개면 본 항목 "해당 없음" 명시 후 skip.
  - 근거: 실측 사단 사례 — "기존 시스템 X 기능 mobile parity" 류 framing 이 자기-부과 제약으로 굳어 다수 대안 path (라이브러리 합성 / 자체 native / 요구사항 강등 + UX 보강 등) 검토 0건. 원시 데이터 산술로 충분했던 사실 PRD/architecture/spike 전부 통과 후 발견.
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

**AC-ID 부여 (provenance origin)**: 모든 수용 기준에 안정 ID `AC-NNN` 을 박는다 (001부터 PRD 전역 순번, 한번 부여하면 불변). 이 AC-ID 가 검증 체인의 *origin* — impl 의 `REQ-NNN` 이 `(from AC-NNN)` 으로 인용하고, architecture-validator 가 "모든 Must AC 가 ≥1 REQ 로 커버되는가 + impl 리터럴이 PRD AC 와 일치하는가" 를 대조한다. 경로·디렉토리 이름·파일 포맷 같은 *리터럴 규약* 도 별도 AC 항목으로 명시 — impl 끼리만 일치하고 PRD 와 어긋나는 self-consistently wrong 을 막는다.

## stories.md 산출물 (단순화 — user story 만)

PRD 작성 완료 후 메인이 epic 단위 `docs/milestones/vNN/epics/epic-NN-<slug>/stories.md` Write — 1 epic + N story 구조 (1 stories.md = 1 epic 영역). **본문은 `As a / I want / So that` 만**. `대상 화면·컴포넌트` / `동작 명세` / `수용 기준 (Story 단위)` 같은 섹션은 *쓰지 않는다*:

- 대상 화면 / 동작 명세 = root `docs/architecture.md` (큰 그림) + epic 단위 architecture.md (세부 모듈 구조) + impl 파일 (`docs/milestones/vNN/epics/epic-NN-*/impl/NN-*.md`) 이 책임
- 수용 기준 (task 단위) = impl 파일의 REQ-NNN 표 (실행 가능 커맨드 의무)
- 수용 기준 (epic 단위) = stories.md 의 `## Epic` 섹션 `완료 기준` (사용자 검증 조건 크게)

### Story 크기 가이드 (이슈 [#511](https://github.com/alruminum/dcNess/issues/511) 보강)

module-architect 한 호출 = 한 Story 단위 = N 개 impl 파일 작성이라, Story 크기가 module-architect 한 호출의 산출 부담을 결정한다.

- **Story 1 개당 예상 task ≤ 5 권장** — module-architect 한 호출에 5 개 이하 impl 파일 산출
- **Story 가 큰 경우 분할 권고** — 예: "결제 + 환불 + 정산" 같은 Story 는 *결제 / 환불 / 정산* 세 Story 로 분할
- **cross-cutting Story 표시** — Story 본문 끝에 `**영향 모듈**: <목록>` 명시. module-architect 가 한 호출에 어떤 모듈을 다루는지 명시적으로 받을 수 있도록

epic 단위 `stories.md` 형식:

```markdown
# Story Backlog

## Epic — <epic 한 줄 요약>

**목표**: <epic 의 비즈니스 목적 한 단락>
**선행 조건**: <있으면>
**완료 기준** (epic 단위 수용 기준):
1. <검증 가능한 조건 1>
2. <검증 가능한 조건 2>
3. ...

**GitHub Epic Issue:** (이슈 등록 후 채워짐)

---

### Story 1 — <story 한 줄 요약>

**GitHub Issue:** (이슈 등록 후 채워짐)

**As a** <user>,
**I want** <action>,
**So that** <benefit>.

---

### Story 2 — ...
```

**구버전 호환성 (마이그레이션 정책)**:
- 기존 외부 활성 프로젝트의 옛 양식 stories.md (`대상 화면·컴포넌트` / `동작 명세` / `수용 기준 (Story 단위)` 섹션 포함) 는 *그대로 허용* — backfill 강제 X
- **새 작성** 시만 본 단순화 룰 적용
- read 시 두 양식 모두 인식 가능 (parser 가 `As a / I want / So that` 매치만 의무)

task-level 세부 진행 추적 X (PR + GitHub Issue close 시스템 SSOT — [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#이슈-계층)).

## 작성 절차 (메인 직접)

### Step 0 — 사전 read (lazy — 필요시만, #400)

정상 흐름은 본 skill 본문 + 인용된 docs 섹션 링크 만으로 진행. *룰 모호 / 분기 발생* 시에만 [`product-plan-routing.md`](product-plan-routing.md) (라우팅) / `docs/plugin/loop-procedure.md` / `skills/architect-loop/SKILL.md` / `issue-lifecycle.md` 부분 read (grep + offset/limit). 통째 read 폐기 — 메인 cache_read 기준치 감축.

### Step 1 — 사용자와 그릴 대화

위 *그릴미 패턴* (원문 그대로) 따라 진행. **종료조건은 핵심 분기에서 `shared understanding` 도달** — 아래 *PRD 산출물 체크리스트* 는 그 대화의 부산물(기록)이며, 칸이 다 찼다는 이유만으로 멈추지 않는다.

### Step 2 — PRD 작성

메인이 `docs/prd.md` Write/Edit. 새 작성 = `Write`, 변경 = `Edit` 도구 *섹션 단위 patch* 의무. **Write 통째 호출 금지** (기존 PRD 의 모르는 부분 silent 변경 위험).

### Step 3 — stories.md 작성

메인이 epic 단위 `docs/milestones/vNN/epics/epic-NN-<slug>/stories.md` Write. 1 epic + N story 구조 (위 형식). epic 디렉토리 부재 시 신규 생성. vNN 결정 — 신규 milestone 이면 가장 높은 vNN + 1 (예: v01 있으면 v02), 기존 milestone 추가면 같은 vNN.

### Step 4 — tech-review.md 스켈레톤 작성

메인이 `docs/tech-review.md` Write — *스켈레톤* 만 (본문 채우기 = 후속 `/tech-review` 단계의 tech-reviewer 책임).

**스켈레톤 형식**:

```markdown
# Tech Review — <PRD 한 줄 요약>

> 본 문서 = `/tech-review` 단계에서 tech-reviewer 가 본문을 채울 *스켈레톤*.
> 메인 작성 영역 = 필요 검토 사항 + PRD 항목 ref + 기술 이름 만.
> tech-reviewer 가 4 항목 (사용 가능 / 비용 / 라이선스 / 불가 시 대안 2개) + 증거물 + HTML 리포트 산출.

## 검토 대상 — 정식 항목

| # | 기술 이름 | PRD 항목 ref | 필요 검토 사항 |
|---|---|---|---|
| 1 | <예: OpenAI gpt-image-2> | PRD §3.2 이미지 생성 | 한국어 텍스트 렌더 정확도 ≥ 80% / 16:9 native / 비용 |
| 2 | <예: edge-tts InJoonNeural> | PRD §3.5 음성 합성 | 한국어 voice 동작 / latency / 라이선스 |
| ... | ... | ... | ... |

## 자체 발굴 후보 (사용자 확인 필요)

(tech-reviewer 가 PRD 본문 보고 자명 필요 발견 시 채움. 메인 작성 시 비워둠)

## 분기 — MVP / 고도화

본 PRD 의 빌드 단계 (스펙 깎기 분기 기준): <MVP 또는 고도화 명시>
```

PRD 의 모든 외부 의존 1 개당 1 행 의무. 외부 의존 0 개면 본 step skip 가능 + 본문 "외부 의존 없음 — `/tech-review` skip" 명시 (후속 `/tech-review` 도 skip).

### Step 5 — 사용자 1차 OK 체크포인트

PRD + stories.md + tech-review.md 스켈레톤 작성 완료 후 메인이 사용자에게 confirm:

```
📄 작성 완료:
- `docs/prd.md` — PRD 본문
- `docs/stories.md` — Epic + N Story
- `docs/tech-review.md` — 기술 검토 스켈레톤 (N 개 정식 항목)

검토 후 결정:
- OK → Step 5.5 (`product-acceptance:SPEC_ACCEPTANCE`) 진입
- patch 필요 → 어떤 섹션 / 어떤 내용 알려주세요
```

사용자 patch 요청 시 → 메인이 `docs/prd.md` / `docs/stories.md` / `docs/tech-review.md` 해당 섹션 Edit → 다시 본 Step 진입.

### Step 5.5 — product-acceptance:SPEC_ACCEPTANCE

사용자 1차 OK 후, branch 만들기 *전* 메인이 `product-acceptance` agent 를 `SPEC_ACCEPTANCE` mode 로 호출한다.

```
Agent(subagent_type="product-acceptance", prompt="""
mode: SPEC_ACCEPTANCE
검수 단위: 현재 /spec 또는 /product-plan 산출물
기준 문서:
- docs/prd.md
- docs/milestones/vNN/epics/epic-NN-<slug>/stories.md
- docs/tech-review.md

목적:
이 spec 이 이후 설계/구현/검수에 충분히 닫혔는지 확인한다.
좋은 아이디어인지 평가하지 말고, AC binary 여부, 검수 증거 기준,
외부 의존/보안/권한/데이터 질문 누락, Story/Epic 분할 명확성을 본다.
full E2E 검증은 MVP /spec 이행 범위 밖이다.
""")
```

결론 처리:

- `PASS` → Step 6 (통합 브랜치 그릴) 진입
- `FAIL` → gap 을 사용자에게 보고하고, 메인이 해당 섹션을 patch 한 뒤 Step 5 재진입
- `ESCALATE` → 기준 문서/권한/사용자 결정 부족을 보고하고 사용자 위임

### Step 6 — 통합 브랜치 그릴 (메인 → 사용자)

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
1. git checkout -b docs/<slug> main          # git-spec 의 브랜치 패턴
2. git add docs/prd.md docs/stories.md
3. git commit -m "[docs] PRD 신규 / 변경 요약"   # git-spec 의 커밋 제목 패턴
4. git push -u origin docs/<slug>
5. gh pr create --base main --title "..." --body "..."   # git-spec 의 PR 제목~PR 본문
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
   # (PRD sub-PR 은 이슈 등록 *전* 단계 — 별도 추적 이슈 만들지 X, 추적 이슈 폭주 회피)
8. bash "$PLUGIN_ROOT/scripts/pr-finalize.sh" <PR_NUMBER>
   # PRD sub-PR 머지 후에도 통합 브랜치는 살아있음 (sub-PR 더 누적 예정)
```

### Step 8 — 이슈 등록 trigger (선택)

PR 머지 완료 후 메인이 사용자에게 confirm:

```
PRD + stories.md 머지 완료. 이제 GitHub epic + story 이슈를 등록할까요? (Y/n)
```

> 통합 브랜치 케이스 (Step 6 (b)) 인 경우 — stories.md 의 `**Base Branch:**` 마커가 `scripts/create_epic_story_issues.sh` 에 의해 epic issue body 첫 줄로 *자동 미러링* 됨. GitHub UI 에서 #epic 만 봐도 통합 브랜치 모드임을 즉시 인지 가능.

사용자 Y → 메인이 `scripts/create_epic_story_issues.sh` 호출 (자동화 스크립트):

```bash
bash scripts/create_epic_story_issues.sh docs/milestones/vNN/epics/epic-NN-<slug>/stories.md
```

스크립트 동작:
1. stories.md parse — epic + Story N 추출
2. milestone number 조회 (Epics / Story)
3. epic 이슈 1 생성 → stories.md 에 번호 씀
4. story 이슈 N 순차 생성 → stories.md 에 번호 + 하단 표 씀
5. sub-issue API 호출 (epic ↔ story N 연결, GitHub native sub-issue API)
6. 결과 prose 출력

상세 SSOT = [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#sub-issue-연결-epic-story-gh-api-메커니즘).

스크립트 실패 시 메인이 사용자에게 보고 + [`docs/plugin/issue-lifecycle.md` Sub-issue 연결](../../docs/plugin/issue-lifecycle.md#sub-issue-연결-epic-story-gh-api-메커니즘) 따라 수동 처리 가능 (`mcp__github__create_issue` + `gh api` 직접 호출).

이슈 등록 후 stories.md 변경분은 별도 commit + PR 또는 사용자 자율 (스크립트 자체는 git mutation X — stories.md 만 수정).

### Step 9 — `/tech-review` 권고 (선행 기술 검증)

이슈 등록 완료 후 메인이 사용자에게 confirm — *기술 검증 단계 진입*:

```
PRD + stories.md + tech-review.md 스켈레톤 + 이슈 등록 완료.

다음 단계 — 선행 기술 검증:
→ `/tech-review` 호출 시 tech-reviewer 가 `docs/tech-review.md` 본문 채움
  + 증거물 (docs/tech-review/evidence/**) + 통합 HTML 리포트 (`docs/tech-review/report.html`)

⚠️ 단방향 관례 — `/design` (`/architect-loop` 호환) 진입 후 tech-reviewer 재호출은 비권장 (코드 강제 아님).
   기술 NO_GO 발견은 본 `/tech-review` 단계에서 확정하는 게 좋음.

진행할까요? (Y/n)
```

후속 분기 (외부 의존 0개 skip / 사용자 Y / `/design` 권고 echo) = [`product-plan-routing.md`](product-plan-routing.md). 자세히 = [`tech-review SKILL.md`](../tech-review/SKILL.md).

## 워크트리 (X)

`/product-plan` 은 워크트리 자동 진입 안 함. 기획·설계는 동시 다중 batch 충돌 회피 목적 부재. 메인 working tree 에서 별 branch 따고 직접 진행. 자세히 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정).

## 참조

- 라우팅 (skill 시퀀스 / 재진입 / escalate / catastrophic / 비대상): [`product-plan-routing.md`](product-plan-routing.md) — 본 skill 라우팅 SSOT
- 그릴미 원형: `~/.claude/skills/grill-me/SKILL.md` (사용자 user skill)
- 이슈 등록 SSOT: [`docs/plugin/issue-lifecycle.md`](../../docs/plugin/issue-lifecycle.md#sub-issue-연결-epic-story-gh-api-메커니즘)
- 브랜치·커밋·PR 네이밍: [`docs/plugin/git-spec.md`](../../docs/plugin/git-spec.md)
- 선행 기술 검증 (후속 스킬): [`skills/tech-review/SKILL.md`](../tech-review/SKILL.md), [`agents/tech-reviewer.md`](../../agents/tech-reviewer.md)
