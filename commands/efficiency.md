---
name: efficiency
description: Claude Code 세션 JSONL 로그 (`~/.claude/projects/<encoded-repo>/*.jsonl`) 를 파싱해서 토큰 / 캐시 효율 / 비용 리포트 (HTML 대시보드 + ROI 절감안) 를 생성하는 분석 스킬. 사용자가 "토큰 효율", "비용 분석", "Claude 비용", "session report", "/efficiency", "효율 리포트", "캐시 히트율", "내 Claude 얼마 썼나", "absorb" 등을 말할 때 사용. 단발 세션 X — 레포 전체 N 세션 집계 + 4 지표 점수화 + Pareto 분석 + 6 절감 휴리스틱.
---

# Efficiency Skill — Claude Code 세션 토큰/비용 분석

> **출처 (attribution)**: `jha0313/skills_repo` 의 `improve-token-efficiency` skill. 4 script 보존, dcness 패턴 (helper protocol + skill prompt) 으로 wrap.

## 언제 사용

- "토큰 효율 분석", "세션 효율", "비용 분석"
- "Claude Code usage report", "show session cost"
- "효율 리포트", "캐시 히트율", "내 Claude 얼마 썼나"
- 레포 단위 (현 cwd 또는 명시 path) Claude Code 사용 패턴 / 비용 / 점수 알고 싶을 때
- 단발 세션 X — *여러 세션 집계 + 점수화 + 시각화* 가 필요한 모든 경우

## 언제 사용하지 않음

- 코드 작성 / 버그픽스 / 기획 → `/issue-report` `/impl` `/impl-loop` `/product-plan` 등 다른 skill
- AI-readiness 평가 (코드베이스 자체) → 본 skill 비대상 (별도 ai-readiness 도구 후보)

## 시퀀스

본 skill 은 **read-only 분석 도구** — agent 호출 X, prose 종이 X, catastrophic 룰 비대상. 단순 helper wrapper 호출 chain.

```
analyze_sessions (Python) → JSON 리포트
  → build_dashboard (Python) → HTML 대시보드
  → 사용자 보고 (Korean, 2~3줄 요약 + 상위 절감안 3가지)
```

## 절차

### Step 0 — run 시작 (선택)

본 skill 은 분석 도구라 *run 등록 의무 없음*. 단 `.steps.jsonl` 추적 원하면:

```bash
HELPER="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)/scripts/dcness-helper"
RUN_ID=$("$HELPER" begin-run efficiency)
echo "[efficiency] run started: $RUN_ID"
```

skip 해도 무방.

### Step 1 — 분석 + 대시보드 (단일 명령)

```bash
DCEFF="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)/scripts/dcness-efficiency"
"$DCEFF" full --repo "$(pwd)" --out-dir /tmp/dcness-efficiency
```

`full` subcommand = `analyze` → `dashboard` 자동 chain.

출력:
- `/tmp/dcness-efficiency/session_analysis.json` — raw 데이터 (다른 도구가 소비 가능)
- `/tmp/dcness-efficiency/efficiency_report.html` — 단일 HTML 대시보드 (Chart.js CDN)

### Step 2 — 사용자 보고 (Korean, 2~3줄)

JSON 의 `totals` + `top_sessions` + 개선안 list 에서 핵심 추출:

```
[efficiency] <session count> 세션 / $<total cost> / 평균 등급 <grade>
- 캐시 히트율: <ratio>%
- 상위 N 세션이 전체 비용의 <%> 차지
- 가장 큰 절감 후보 (3개):
  1. <개선안 1> — 예상 절감 $<amount>
  2. <개선안 2> — ...
  3. <개선안 3> — ...

대시보드: open /tmp/dcness-efficiency/efficiency_report.html
JSON: /tmp/dcness-efficiency/session_analysis.json
```

### Step 3 — run 종료 (Step 0 했으면)

```bash
"$HELPER" end-run
```

## 추가 명령 (advanced)

본 skill 의 wrapper (`scripts/dcness-efficiency`) 5 subcommand:

| subcommand | 역할 |
|---|---|
| `analyze` | JSON 리포트만 (dashboard X) |
| `dashboard` | analyze JSON → HTML 대시보드 |
| `patterns` | 패턴 분석 (`detect_patterns.py`) — 토큰 thrash / 반복 read 등 |
| `patterns-dashboard` | patterns JSON → HTML |
| `full` | analyze + dashboard chain (가장 흔한 사용) |

특정 user 가 이미 JSON 만 원하면 `analyze`, 패턴 탐지 (반복 read 등) 추가 원하면 `patterns` chain.

## 점수화 rubric (4 지표 가중)

`scripts/analyze_sessions.py` 가 각 세션을 0–100 점화:

| 지표 | 가중치 | 측정 |
|---|---|---|
| **Cache utilization** | 40% | `cache_read / total_input`. 0.85 이상 만점. |
| **Output density** | 20% | `output / total_input`. ~2% sweet spot. |
| **Read redundancy** | 20% | `redundant_reads / total_reads`. 같은 파일 반복 read = 감점. |
| **Tool economy** | 20% | 출력 1k 토큰당 툴 호출 수. 2–10 건강. |

등급: A+ ≥90, A ≥85, ..., D ≥40, F <40.

## 가격 기준 (per 1M tokens, USD)

`harness/efficiency/analyze_sessions.py` 의 `PRICING` dict:

| Model | Input | Output | Cache 5m | Cache 1h | Cache read |
|---|---|---|---|---|---|
| Opus 4.x | 15.0 | 75.0 | 18.75 | 30.0 | 1.50 |
| Sonnet 4.x | 3.0 | 15.0 | 3.75 | 6.0 | 0.30 |
| Haiku 4.x | 0.80 | 4.0 | 1.0 | 1.6 | 0.08 |

prefix 매칭 — `claude-haiku-4-5-20251001`, `claude-opus-4-7[1m]` 같은 variant suffix 자동 흡수. 새 모델은 PRICING dict 한 줄 추가.

## 6 절감 휴리스틱 (`build_dashboard.py`)

1. **Opus → Sonnet 라우팅** — 30% Sonnet 이관 가정. 5배 비용비.
2. **장시간 세션 `/compact`** — 상위 14 세션 cache_read 30% 감소 가정.
3. **이미지 세션 관리** — 이미지 포함 세션 컴팩션 50% 절감.
4. **Cache TTL 1h → 5m** — 1h 캐시의 40% 가 5m 충분 가정.
5. **세션 scope 축소** — 상위 외 세션 cache_read 15% 감소.
6. **중복 Read 제거** — `redundant_reads × 3000토큰 × (cache write + 10 re-read)` 비용 차단.

추정치 — 사용자 "실제 절감?" 물으면 "휴리스틱, 실행 후 재측정" 답.

## 한계 / 후속

- **세션 디렉터리 부재**: 레포가 Claude Code 로 한 번도 열린 적 없으면 "분석할 세션 없음" 안내 + 종료.
- **모든 세션 빈 usage**: 오래된 CLI 버전. 자동 제외 후 남은 게 없으면 종료.
- **가격 미등록 모델**: prefix 매칭 + Opus default fallback. `PRICING` 갱신 권장.
- **dcness telemetry 와 분리**: `.metrics/heuristic-calls.jsonl` (heuristic enum 추출 telemetry) ≠ 본 skill 의 CC 세션 비용 분석. 두 영역 별도.

## 참조

- `harness/efficiency/analyze_sessions.py` — 세션 JSONL 파싱 + 점수화
- `harness/efficiency/build_dashboard.py` — Chart.js HTML 대시보드
- `harness/efficiency/detect_patterns.py` — 토큰 thrash 패턴 탐지
- `harness/efficiency/build_patterns_dashboard.py` — 패턴 HTML
- `scripts/dcness-efficiency` — wrapper (analyze / dashboard / patterns / full)
- `jha0313/skills_repo/improve-token-efficiency` — 출처 skill
