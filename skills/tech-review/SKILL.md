---
name: tech-review
description: >
  PRD 초안 작성 + 사용자 초안 OK 후, PRD의 기술 검토 필요 영역을 바탕으로 *기술 검토* 단계를
  진행하는 스킬. tech-reviewer 서브에이전트 호출 + return 결과 사용자에 echo + 사용자
  2차 OK 체크포인트 + 재호출 cycle 관리. `/design` 진입 후 본 스킬 재호출은 비권장
  (단방향 관례 — 코드 강제 아님). 사용자가 "tech-review", "기술 검토 가자", "이거 진짜 되는지
  확인", "/tech-review" 등을 말할 때 반드시 이 스킬을 사용한다.
---

# Tech Review Skill — 선행 기술 검증 + 사용자 2 차 OK 게이트

> 본 스킬 = `/spec` 도중 PRD 최종화 전에 호출되는 전역 기술 검증 게이트이자, `/design` 중 `NEW_DEP_ESCALATE` option 4 로 호출되는 epic 단위 기술 검증 경로다. tech-reviewer 가 지정된 검토 입력을 읽고 root 또는 epic `tech-review.md` 본문을 생성/갱신하며, 증거물과 HTML 리포트는 `.dcness-work/reviews/` 에 남긴다. 메인이 cycle 을 관리하고 사용자가 최종 OK 한다.

> 🔴 **분기 규칙 SSOT** — tech-reviewer 결론 (PASS / FAIL / ESCALATE) → 다음 호출 / 사용자 2차 OK 분기 / cycle 재진입 / 단방향 관례 / 비대상 / 후속은 [`tech-review-routing.md`](tech-review-routing.md) 가 본 skill 의 단일 진본. 본 파일은 *진행 절차(Step)* 만 담는다. 분기 판단이 필요하면 그 파일을 읽는다. 용어·공개 진입점·분기 표현을 수정하거나 리뷰할 때만 [`terms.md`](../../docs/plugin/terms.md) 를 확인한다.

## 전제 조건

본 스킬은 두 모드 중 하나로 진입한다.

**전역 preflight 모드** (`/spec` 내부):
1. `docs/prd.md` 존재 + PRD 초안 작성 완료 (`/spec` Step 2 결과)
2. `docs/prd.md` 에 **기술 검토 필요 영역** 존재 + 검토 질문 / PRD 근거 / 성공·실패 시 PRD 영향이 명시됨
3. 사용자 PRD 초안 OK 완료 (`/spec` Step 3 — PRD 초안 검토 후 진행 결정)

**epic option 4 모드** (`/design` 중 `NEW_DEP_ESCALATE` option 4):
1. `docs/prd.md` 존재
2. `docs/epics/<epic>/stories.md` 존재
3. 미검증 외부 의존 질문, 대상 epic 경로, 성공·실패 시 epic 설계 영향이 호출 prompt 에 명시됨

전역 preflight 모드 미충족 시 → `/spec` 권고 후 종료. epic option 4 모드 미충족 시 → `/design` 호출자로 ESCALATE 한다.

## 작성 절차 (메인 직접)

### Step 0 — 전제 확인

```bash
ls docs/prd.md
```

부재 파일 발견 시:
```
docs/prd.md 부재.
→ /spec 진행 후 재진입하세요.
```

`docs/prd.md` 안에 기술 검토 필요 영역이 없거나 "해당 없음"이면 `/tech-review` 를 진행하지 않고 `/spec` Step 5 PRD 최종화로 되돌린다.

### Step 1 — tech-reviewer 호출

전역 preflight 모드:
```
Agent(subagent_type="tech-reviewer", prompt="""
PRD: docs/prd.md
검토 입력: docs/prd.md 의 "기술 검토 필요 영역"

[이전 cycle 있으면 추가]
이전 cycle 컨텍스트:
- 이전 cycle 에서 PRD 항목 X 가 Y 로 patch 됨 (이유: ...)
- 이전 cycle 에서 검토 질문 Z 가 추가됨

docs/tech-review.md 를 생성/갱신하고, raw evidence 와 HTML report 는 .dcness-work/reviews/ 에 저장하세요.
각 정식 항목은 사용 가능성 / 비용 / 라이선스 / 대안 필요 여부 / 목적 적합성 / evidence 를 포함해야 합니다.
""")
```

epic option 4 모드:
```
Agent(subagent_type="tech-reviewer", prompt="""
PRD: docs/prd.md
Epic stories: docs/epics/<epic>/stories.md
검토 입력: 대상 epic `stories.md` 와 미검증 외부 의존 질문

[design 호출자가 전달한 NEW_DEP_ESCALATE 맥락]
- 새 외부 의존 / API / SDK / model:
- 왜 이 epic 범위에서 필요한지:
- 성공·실패 시 epic architecture / impl task 영향:

docs/epics/<epic>/tech-review.md 를 생성/갱신하고, raw evidence 와 HTML report 는 .dcness-work/reviews/ 에 저장하세요.
각 정식 항목은 사용 가능성 / 비용 / 라이선스 / 대안 필요 여부 / 목적 적합성 / evidence 를 포함해야 합니다.
""")
```

이전 cycle 컨텍스트 = *메인이 prompt 에 명시* (tech-reviewer 가 stateless 이므로). 첫 cycle 은 컨텍스트 생략.

### Step 2 — return prose 받기 + 산출 경로 echo

tech-reviewer 가 prose 결론 + 모드별 본문(`docs/tech-review.md` 또는 `docs/epics/<epic>/tech-review.md`) + `.dcness-work/reviews/**` evidence/report 완료 후 return.

메인이 사용자에게 echo — **백틱 + 클릭 가능 형태**:

```
tech-review 본문 + HTML 리포트 + 증거물 산출 완료.

📄 본문: `docs/tech-review.md` — 항목별 verdict + 4 항목 + 권고
🌐 통합 HTML: `.dcness-work/reviews/<report>.html` — 증거 (음성/이미지/로그) 한 페이지 통합
   → `open .dcness-work/reviews/<report>.html` 로 직접 확인
📁 증거 디렉토리: `.dcness-work/reviews/` — 개별 파일 보존

요약:
- 정식 항목 N 개 중 M PASS / K FAIL
- 자체 발굴 후보 J 개 (사용자 확인 대상)
- 스펙 깎기 권고 L 개
```

**옛 frustration 패턴 금지**:
- raw 경로 5 개 별개 명령 나열 X (예: `open /tmp/.../sunhi.mp3 — 여성 ... × 5 줄`)
- 워크트리 절대경로 매 줄 반복 X (처음 1 회만 + 이후 상대경로)
- markdown 링크 없는 텍스트 경로 X

### Step 3 — 사용자 2 차 OK 체크포인트

사용자에게 다음 옵션 제시 (메인이 prose 로):

```
PRD 초안(`docs/prd.md`), tech-review 본문(`docs/tech-review.md` 또는 `docs/epics/<epic>/tech-review.md`), `.dcness-work/reviews/` HTML 리포트 확인 후 결정:

1. **OK** → `/spec` Step 5 로 복귀해 PRD 최종화
2. **PRD 재기술 필요** → 어떤 항목 어떻게 patch 할지 알려주세요
3. **검토 범위 추가** → 어떤 질문을 PRD의 기술 검토 필요 영역에 추가할지 알려주세요
4. **항목 polish** → 어떤 항목 더 깊이 검증할지 알려주세요
```

### Step 4 — 분기 (분기 규칙 진본 = [`tech-review-routing.md`](tech-review-routing.md))

**4-1. 사용자 OK** → 종료 + `/spec` Step 5 (PRD 최종화) 로 복귀.

**4-2. PRD 재기술 필요** →
- 메인이 사용자와 patch 항목 토론 (그릴미 — 어디를 / 어떻게)
- 메인이 `docs/prd.md` Edit (섹션 단위 patch)
- 기술 검토 필요 영역이 바뀌면 cycle 컨텍스트에 명시
- **Step 1 재진입** (cycle 컨텍스트 prompt 명시 — "이전 cycle 에서 X 가 Y 로 patch 됨")

**4-3. 검토 범위 추가** →
- 메인이 사용자와 추가 검토 질문 결정
- 메인이 `docs/prd.md` 의 기술 검토 필요 영역을 갱신
- **Step 1 재진입** (cycle 컨텍스트 명시 — "검토 질문 Z 가 추가됨")

**4-4. 항목 polish** →
- 메인이 사용자와 polish 요구 정리 (어떤 항목 / 어떤 검증 방법 추가)
- 메인이 재호출 prompt 에 polish 요구 명시 (예: "이 항목은 Bash 실측 1 회 추가 의무")
- **Step 1 재진입**

### Step 5 — `/spec` 복귀 (사용자 OK 종료)

사용자 2 차 OK 후 메인이 echo:

```
tech-review 통과 완료.
→ `/spec` Step 5 로 돌아가 `docs/prd.md` 를 최종 PRD 로 업데이트합니다.
```

이후 stories.md 작성, `SPEC_ACCEPTANCE`, PR 머지, 이슈 등록, `/design` 권고는 `/spec` 이 계속 진행한다.

## 단방향 관례 (재진입 비권장)

`/design` 진입 *후* 본 스킬 재호출은 **관례상 비권장** (코드 강제 아닌 자연어 관례 — 메인/사용자 자율 판단). 정합 룰 SSOT = [`docs/plugin/hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) 의 tech-review 자연어 관례. tech-reviewer 단계 = PRD 최종화 전 기술 검증 기회다. /design 도중 미검증 새 외부 의존 발견 시 처리 = [`../design/design-routing.md`](../design/design-routing.md#escalate-처리) option 4 포함 경로를 따른다.

## 워크트리 (X)

`/tech-review` 는 워크트리 자동 진입 안 함. 기획·검증 단계는 동시 다중 batch 충돌 회피 목적 부재. 메인 working tree 에서 직접 진행. 자세히 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정).

## 참조

- 분기 규칙 (결론→다음 / cycle / 중대 차단 / 비대상 / 후속): [`tech-review-routing.md`](tech-review-routing.md) — 본 skill 분기 규칙 SSOT
- tech-reviewer agent SSOT: [`agents/tech-reviewer.md`](../../agents/tech-reviewer.md)
- PRD 작성 (선행 스킬): [`skills/spec/SKILL.md`](../spec/SKILL.md)
- 설계 단계 (후속 스킬): [`skills/design/SKILL.md`](../design/SKILL.md)
- 옛 plan-reviewer 폐기 배경 (이슈 [#515](https://github.com/alruminum/dcNess/issues/515))
