---
name: tech-review
description: >
  PRD + `docs/tech-review.md` 스켈레톤 작성 완료 + 사용자 1차 OK 후 *기술 검토* 단계를
  진행하는 스킬. tech-reviewer 서브에이전트 호출 + return 결과 사용자에 echo + 사용자
  2차 OK 체크포인트 + 재호출 cycle 관리. `/architect-loop` 진입 후 본 스킬 재호출 금지
  (단방향 catastrophic). 사용자가 "tech-review", "기술 검토 가자", "이거 진짜 되는지
  확인", "/tech-review" 등을 말할 때 반드시 이 스킬을 사용한다.
---

# Tech Review Skill — 선행 기술 검증 + 사용자 2 차 OK 게이트

> 본 스킬 = `/product-plan` 종료 후 *명시 호출* 되는 기술 검증 게이트. tech-reviewer 가 stateless 본문 채움 + 메인이 cycle 관리 + 사용자가 최종 OK.

> 🔴 **라우팅 SSOT** — tech-reviewer 결론 (PASS / FAIL / ESCALATE) → 다음 호출 / 사용자 2차 OK 분기 / cycle 재진입 / 단방향 catastrophic / 비대상 / 후속은 [`tech-review-routing.md`](tech-review-routing.md) 가 본 skill 의 단일 진본. 본 파일은 *진행 절차(Step)* 만 담는다. 분기 판단이 필요하면 그 파일을 읽는다.

## 전제 조건

본 스킬 진입 *전* 충족 의무:

1. `docs/prd.md` 존재 + 기능 명세 완료 (`/product-plan` Step 3 결과)
2. `docs/tech-review.md` 스켈레톤 존재 (`/product-plan` Step 4.5 결과 — 필요 검토 사항 + PRD 항목 ref + 기술 이름 만 채움)
3. 사용자 1차 OK 완료 (`/product-plan` Step 5 — PRD + 스켈레톤 검토 후 진행 결정)

미충족 시 → `/product-plan` 권고 후 종료.

## 작성 절차 (메인 직접)

### Step 0 — 전제 확인

```bash
ls docs/prd.md docs/tech-review.md
```

부재 파일 발견 시:
```
docs/prd.md 또는 docs/tech-review.md 스켈레톤 부재.
→ /product-plan 진행 후 재진입하세요.
```

### Step 1 — tech-reviewer 호출

```
Agent(subagent_type="tech-reviewer", prompt="""
PRD: docs/prd.md
스켈레톤: docs/tech-review.md

[이전 cycle 있으면 추가]
이전 cycle 컨텍스트:
- 이전 cycle 에서 PRD 항목 X 가 Y 로 patch 됨 (이유: ...)
- 이전 cycle 에서 격리 후보 Z 가 정식 항목으로 격상됨

본문 채워주세요 — 정식 항목 4 항목 충족 + 증거물 + report.html 생성.
""")
```

이전 cycle 컨텍스트 = *메인이 prompt 에 명시* (tech-reviewer 가 stateless 이므로). 첫 cycle 은 컨텍스트 생략.

### Step 2 — return prose 받기 + 산출 경로 echo

tech-reviewer 가 prose 결론 + 산출 3 종 (`docs/tech-review.md` + `docs/tech-review/evidence/**` + `docs/tech-review/report.html`) 완료 후 return.

메인이 사용자에게 echo — **백틱 + 클릭 가능 형태**:

```
tech-review 본문 + HTML 리포트 + 증거물 산출 완료.

📄 본문: `docs/tech-review.md` — 항목별 verdict + 4 항목 + 권고
🌐 통합 HTML: `docs/tech-review/report.html` — 증거 (음성/이미지/로그) 한 페이지 통합
   → `open docs/tech-review/report.html` 로 직접 확인
📁 증거 디렉토리: `docs/tech-review/evidence/` — 개별 파일 보존

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
HTML 리포트 (`docs/tech-review/report.html`) 확인 후 결정:

1. **OK** → 설계 단계 진입 (/architect-loop 권고)
2. **PRD 재기술 필요** → 어떤 항목 어떻게 patch 할지 알려주세요
3. **격리 후보 격상** → 어떤 후보 추가 검토할지 알려주세요
4. **항목 polish** → 어떤 항목 더 깊이 검증할지 알려주세요
```

### Step 4 — 분기 (라우팅 진본 = [`tech-review-routing.md`](tech-review-routing.md))

**4-1. 사용자 OK** → Step 5 (종료 + `/architect-loop` 권고).

**4-2. PRD 재기술 필요** →
- 메인이 사용자와 patch 항목 토론 (그릴미 — 어디를 / 어떻게)
- 메인이 `docs/prd.md` Edit (섹션 단위 patch)
- (필요 시) 스켈레톤 (`docs/tech-review.md`) 도 갱신 — 새 의존 추가 / 항목 제거
- **Step 1 재진입** (cycle 컨텍스트 prompt 명시 — "이전 cycle 에서 X 가 Y 로 patch 됨")

**4-3. 격리 후보 격상** →
- 메인이 사용자와 격상 후보 결정
- 메인이 `docs/tech-review.md` 스켈레톤 갱신 — 격리 후보 → 정식 항목으로 이동
- **Step 1 재진입** (cycle 컨텍스트 명시 — "격리 후보 Z 가 정식 항목으로 격상됨")

**4-4. 항목 polish** →
- 메인이 사용자와 polish 요구 정리 (어떤 항목 / 어떤 검증 방법 추가)
- 메인이 스켈레톤에 polish 메모 추가 (예: "이 항목은 Bash 실측 1 회 추가 의무")
- **Step 1 재진입**

### Step 5 — `/architect-loop` 권고 (사용자 OK 종료)

사용자 2 차 OK 후 메인이 echo:

```
tech-review 통과 완료. 다음 단계 — 설계 루프:

→ `/architect-loop <epic-path>` 호출 시 ux-architect / system-architect /
  architecture-validator / module-architect × K 순차 진행 + 1 PR 머지.

⚠️ 단방향 catastrophic — /architect-loop 진입 후 tech-reviewer 재호출 금지.
   설계 도중 tech-review 미검증 새 외부 의존 발견 시 → NEW_DEP_ESCALATE 3안
   (채택+수동검증 / 대안 기술 우회 / 전체 원점 회귀). 어느 옵션이든
   tech-reviewer 재호출은 없음 (단방향 보존). 전체 회귀는 3안 중 하나일 뿐.

진행할까요? (Y/n)
```

사용자 Y → `/architect-loop` 진입. N → 사용자가 나중에 직접 호출.

## 단방향 catastrophic (재진입 금지)

`/architect-loop` 진입 *후* 본 스킬 재호출 **금지**. 정합 룰 SSOT = [`docs/plugin/hooks.md`](../../docs/plugin/hooks.md#catastrophic-gatesh) (§2.1.4). tech-reviewer 단계 = *마지막 기술 검증 기회* — 그래서 증거물 / HTML 리포트 룰의 가치가 가중된다. architect-loop 도중 미검증 새 외부 의존 발견 시 처리 (NEW_DEP_ESCALATE 3안) = [`tech-review-routing.md`](tech-review-routing.md) — 어느 옵션이든 tech-reviewer 재호출 0 (단방향 보존).

## 워크트리 (X)

`/tech-review` 는 워크트리 자동 진입 안 함. 기획·검증 단계는 동시 다중 batch 충돌 회피 목적 부재. 메인 working tree 에서 직접 진행. 자세히 = [`docs/plugin/loop-procedure.md`](../../docs/plugin/loop-procedure.md#worktree-분기-action-루프-한정).

## 참조

- 라우팅 (결론→다음 / cycle / catastrophic / 비대상 / 후속): [`tech-review-routing.md`](tech-review-routing.md) — 본 skill 라우팅 SSOT
- tech-reviewer agent SSOT: [`agents/tech-reviewer.md`](../../agents/tech-reviewer.md)
- PRD 작성 (선행 스킬): [`skills/product-plan/SKILL.md`](../product-plan/SKILL.md)
- 설계 단계 (후속 스킬): [`skills/architect-loop/SKILL.md`](../architect-loop/SKILL.md)
- 옛 plan-reviewer 폐기 배경 (이슈 [#515](https://github.com/alruminum/dcNess/issues/515))
