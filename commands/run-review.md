---
name: run-review
description: dcness conveyor run (begin-run / end-run 사이클) 사후 분석 스킬. 각 step 의 잘한 점·잘못한 점·비용을 추출해서 메타-하네스 self-improvement 루프 시작점 제공. 사용자가 "/run-review", "리뷰", "이번 run 어땠어", "낭비 분석", "잘못한 점 찾아", "사후 분석" 등을 말할 때 사용한다.
---

# Run Review Skill — 사후 분석 + 메타-하네스 self-improvement

> dcness 컨베이어 run (`/impl-loop`, `/product-plan` 등) 의 산출물을 사후 분석.

## 언제 사용

- 사용자 발화: "/run-review", "리뷰", "이번 run 어땠어", "낭비 분석", "잘못한 점 찾아", "사후 분석", "복기"
- impl-loop / product-plan 등 큰 사이클 종료 후 자동 회고
- 30일 누적 위반 사례 수집 (별도 후속 — 본 skill 은 단일 run)

## 언제 사용하지 않음

- 진행 중 run 분석 → 끝난 run 만 (`.steps.jsonl` 마감 후)
- 토큰 / 캐시 효율 전체 측정 → `/efficiency` (세션 단위 집계)
- 단일 PR 코드 리뷰 → `pr-reviewer` agent

## 핵심 동작

`.sessions/{sid}/runs/{rid}/.steps.jsonl` + 단계별 prose + CC session JSONL 을 cross-correlation 해서:

1. **단계별 비용** — run 시작/종료 timestamp 내 assistant turn cost 합산 (price_for util 재사용)
2. **잘한 점** (GOOD findings) — ENUM_CLEAN / PROSE_ECHO_OK / DDD_PHASE_A / DEPENDENCY_CAUSAL / EXTERNAL_VERIFIED_PRESENT
3. **잘못한 점** (WASTE findings) — RETRY_SAME_FAIL / ECHO_VIOLATION / PLACEHOLDER_LEAK / MUST_FIX_GHOST / SPEC_GAP_LOOP / INFRA_READ / READONLY_BASH / EXTERNAL_VERIFIED_MISSING

## 절차

### Step 0 — run 식별

```bash
HELPER="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)/scripts/dcness-review"

# (a) 인자 없음 → 최신 run
"$HELPER" --latest

# (b) 인자 = run_id → 명시
"$HELPER" --run-id <RID>

# (c) 인자 = "list" → run 목록만
"$HELPER" --list --limit 20
```

사용자 발화에 run_id 가 명시되면 (b), 없으면 (a) 실행. 사용자가 "어떤 run?" 식 모호 질문이면 (c) 로 list 출력 후 선택 받음.

### Step 1 — 리포트 출력 (그대로 character-for-character 복사)

⚠️ **출력 룰 절대 준수 **:

Bash stdout 의 마크다운 리포트를 **한 글자도 바꾸지 않고 그대로** Claude 텍스트 응답에 복사. 마크다운 테이블을 ASCII 박스로 변환 X. 섹션 생략 / 축약 / 재배치 X. "핵심은~" / "정리하면~" 같은 자체 해석 삽입 X.

근거: dcness echo 룰 MUST (DCN-30-15) — 압축 본능 차단. 본 skill 도 동일 정신.

### Step 2 — 후속 라우팅 권고 (선택, prose 끝에 1~3 줄)

리포트 출력 *후* 메인 Claude 가 추가 1~3 줄로 후속 액션 권고 가능 (별도 줄 — 리포트 본문에 삽입 X):
- HIGH waste 1+ → 해당 agent prompt 고치는 PR 권유
- HIGH waste 0 + GOOD 다수 → "이번 run clean 정합. 다음 task 진행 가능"
- MUST_FIX_GHOST 발견 → 주의사항 멈춤 룰 강화 검토

## 잘한 점 / 잘못한 점 패턴 매트릭스

### 잘한 점 (GOOD)

| 패턴 | 검출 조건 | 정합 룰 |
|---|---|---|
| `ENUM_CLEAN` | step enum 이 expected 매트릭스 정합 + must_fix=False | loop-procedure §7.0 |
| `PROSE_ECHO_OK` | prose_excerpt 5~12줄 | DCN-30-15 |
| `DDD_PHASE_A` | architect SD prose 안 Domain Model / Phase A 섹션 | DCN-30-16 |
| `DEPENDENCY_CAUSAL` | architect SD prose 의존성 화살표에 인과관계 표기 | DCN-30-16 |

### 잘못한 점 (WASTE)

| 패턴 | 심각도 | 검출 조건 | 정합 룰 |
|---|---|---|---|
| `RETRY_SAME_FAIL` | MEDIUM | 연속 동일 FAIL enum | 각 skill `<skill>-routing.md` §retry |
| `ECHO_VIOLATION` | MEDIUM | prose_excerpt < 3줄 | DCN-30-15 |
| `PLACEHOLDER_LEAK` | HIGH (system-architect) / MEDIUM | prose 안 `[미기록]` / `M0 이후` / `NotImplementedError` | DCN-30-18 |
| `MUST_FIX_GHOST` | HIGH | must_fix=true 이후 다음 step 진행 | conveyor 주의사항 룰 |
| `SPEC_GAP_LOOP` | MEDIUM | module-architect 보강 cycle > 2회 | 각 skill `<skill>-routing.md` §retry |
| `INFRA_READ` | HIGH | prose 안 인프라 경로 흔적 | catastrophic 권한 경계 |
| `READONLY_BASH` | HIGH | read-only agent 가 Bash 호출 | catastrophic 권한 경계 |
| `THINKING_LOOP` (DCN-30-20) | HIGH | duration > budget × 1.5 + output_tokens < budget × 0.3 (또는 duration > 5분 + output < 1k) | product-planner 6분 stall 실측 사례 |

### Per-Agent 비용 / 토큰 (DCN-30-20, Phase 2)

각 step 의 sub-agent 호출에 대응하는 CC session JSONL `toolUseResult` 매칭으로 추출:
- `duration_ms` — sub-agent 실행 시간
- `total_tokens` — input + cache + output 합산
- `output_tokens` — sub-agent 가 emit 한 token (THINKING_LOOP 검출 핵심 시그널)
- `cost_usd` — `harness/efficiency/analyze_sessions.price_for()` 재사용

매칭 룰: 순서 (timestamp 오름차순) + agent name 정합 (`dcness:system-architect` / `dcness:module-architect` 그대로).

미매칭 시 (구버전 / 다른 agent / log 결손) per-step metric 표시 X (`-`). run-level cost 는 별도 합산.

## 한계 / 후속

- **per-Agent 정확 cost X (Phase 1)** — 현재는 run timeframe 합산 (coarse). Phase 2 = `toolUseResult.totalCost` 매칭 (Agent tool call 별).
- **prose 텍스트 분석 한계** — 한국어/영어 mixed regex 기반. semantic 분석 안 함.
- **한 run 만** — 30일 누적 / 다른 run 비교는 별도 skill 후속.
- **자동 트리거 X** — 현재는 사용자 명시 호출. 후속: finalize-run 직후 자동 trigger 옵션.

## 참조

- `harness/run_review.py` — 본 skill 의 실 구현
- `commands/efficiency.md` — 세션 단위 토큰/캐시 효율 (보완 관계)
- `agents/system-architect.md` §Spike Gate (DCN-30-18) — PLACEHOLDER_LEAK 룰 출처
- `skills/issue-report/SKILL.md` / `skills/impl-loop/SKILL.md` 가시성 룰 (DCN-30-15) — ECHO_VIOLATION 룰 출처
- 선행 하네스 review skill 패턴 — 본 skill 출처
