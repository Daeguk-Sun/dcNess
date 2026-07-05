---
name: run-review
description: dcness loop run (begin-run / end-run 사이클) 사후 분석 스킬. 각 step 의 비용·낭비 finding·재발 개선 후보를 추출해서 메타-하네스 self-improvement 루프 시작점 제공. 사용자가 "/run-review", "리뷰", "이번 run 어땠어", "낭비 분석", "잘못한 점 찾아", "사후 분석" 등을 말할 때 사용한다.
---

# Run Review Skill — 사후 분석 + 메타-하네스 self-improvement

> dcness loop run (`/impl-loop`, `/spec` 등) 의 산출물을 사후 분석.

## 언제 사용

- 사용자 발화: "/run-review", "리뷰", "이번 run 어땠어", "낭비 분석", "잘못한 점 찾아", "사후 분석", "복기"
- impl-loop / spec 등 큰 사이클 종료 후 자동 회고
- 대표 workflow 종료 시 CLAUDE.md/AGENTS.md 현행화 후보를 read-only 로 확인
- 현재 run 의 waste pattern 이 같은 sessions root 에서 몇 번째 반복인지 확인

## 언제 사용하지 않음

- 진행 중 run 분석 → 끝난 run 만 (`ledger.jsonl` 의 `run_finished` 후)
- 토큰 / 캐시 효율 전체 측정 → `/efficiency` (세션 단위 집계)
- 단일 PR 코드 리뷰 → `pr-reviewer` agent

## 핵심 동작

`.sessions/{sid}/runs/{rid}/ledger.jsonl` (step_completed event) + 단계별 prose + CC session JSONL 을 cross-correlation 해서:

1. **단계별 비용** — run 시작/종료 timestamp 내 assistant turn cost 합산 (price_for util 재사용)
2. **잘못한 점** (WASTE findings) — `run_review.py` 의 현재 waste detector 결과
3. **재발 기반 개선 후보** — 현재 run 의 waste pattern 이 같은 sessions root 에서 임계(기본 3회) 이상 반복되면 표면화. 룰 추가, skill 박제, 기존 룰 제거 중 무엇을 할지는 사용자가 결정한다.
4. **CLAUDE.md/AGENTS.md 현행화 후보** — context 문서 존재, AGENTS.md 의 CLAUDE.md SSOT 참조, CLAUDE.md 공식 구조·6축 rubric·dcNess cold-start 앵커, run-review finding 기반 세션 학습 환류 후보. 자동 수정하지 않고 제안만 출력한다.
5. **프로젝트-로컬 lesson 생성 입력** — helper `end-run` 시점에 같은 sessions root 의 recurrent WasteFinding 을 `.claude/loop-lessons/<agent>[-<mode>].md` 로 자동 축적한다. NoteFinding 은 lesson 입력이 아니다.

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

# (d) run 없이 context 문서 audit 만
"$HELPER" --context-audit --repo "$PROJECT_ROOT"
```

사용자 발화에 run_id 가 명시되면 (b), 없으면 (a) 실행. 사용자가 "어떤 run?" 식 모호 질문이면 (c) 로 list 출력 후 선택 받음.

### Step 1 — 리포트 출력 (그대로 character-for-character 복사)

⚠️ **출력 룰 절대 준수 **:

Bash stdout 의 마크다운 리포트를 **한 글자도 바꾸지 않고 그대로** Claude 텍스트 응답에 복사. 마크다운 테이블을 ASCII 박스로 변환 X. 섹션 생략 / 축약 / 재배치 X. "핵심은~" / "정리하면~" 같은 자체 해석 삽입 X.

근거: dcness echo 룰 MUST (DCN-30-15) — 압축 본능 차단. 본 skill 도 동일 정신.

### Step 2 — 후속 분기 권고 (선택, prose 끝에 1~3 줄)

리포트 출력 *후* 메인 Claude 가 추가 1~3 줄로 후속 액션 권고 가능 (별도 줄 — 리포트 본문에 삽입 X):
- HIGH waste 1+ → 해당 agent prompt 고치는 PR 권유
- HIGH waste 0 + 재발 후보 없음 → "이번 run clean 정합. 다음 task 진행 가능"
- MUST_FIX_GHOST 발견 → 주의사항 멈춤 룰 강화 검토
- context audit 후보 있음 → 사용자 승인 후 CLAUDE.md/AGENTS.md docs PR 또는 loop insight / agent prompt 수정으로 분리

## 잘못한 점 패턴 매트릭스

GOOD 자동 finding 은 폐기됐다. 잘한 사례 누적은 baseline noise 가 커서 학습 신호로 쓰지 않는다.

### 잘못한 점 (WASTE)

패턴 목록의 SSOT 는 `harness/run_review.py` 의 `ACTIVE_WASTE_PATTERNS` 와
`detect_wastes()` 구현이다. 이 문서는 목록 사본을 박제하지 않는다. detector 추가·삭제
시 lesson archive 여부도 이 코드 SSOT 를 따른다.

`THINKING_LOOP` / `TOOL_USE_OVERFLOW` 같은 `detect_notes()` 결과는 severity 없는
raw 알림이다. run-review 리포트에는 "측정 noted" 로 표시되지만, 재발 lesson 입력에는
포함하지 않는다.

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
- **단일 run 중심** — `/run-review` 의 재발 후보는 현재 run 의 waste pattern 만 같은 sessions root 에서 카운트한다. 전체 fleet 후보는 `harness/benchmark_aggregate.py` 를 사용한다.
- **자동 트리거 범위 제한** — helper 기반 `/design`·`/impl` run 은 `end-run` 의 review.md 안에 context audit 섹션이 자동 포함된다. helper run 이 없는 `/spec`·standalone `/acceptance` 는 skill 종료 절차에서 `dcness-review --context-audit` 를 명시 호출한다.
- **lesson 생성 시점** — helper `end-run` 이 `run_finished` 를 기록한 직후 recurrent WasteFinding 을 동기화한다. 따라서 review.md 에 표시되는 후보와 별개로, 다음 `begin-step` 의 `[LESSONS]` 주입은 finished run 기준으로 계산된다.

## 참조

- `harness/run_review.py` — 본 skill 의 실 구현
- `harness/loop_lessons.py` — recurrent WasteFinding 기반 프로젝트-로컬 lesson 저장·주입
- `commands/efficiency.md` — 세션 단위 토큰/캐시 효율 (보완 관계)
- 선행 하네스 review skill 패턴 — 본 skill 출처
