---
name: efficiency
description: Claude Code 세션 JSONL 로그를 읽어 레포 단위 토큰, 캐시 효율, 비용을 JSON과 짧은 stdout 요약으로 보여주는 read-only 분석 명령. 사용자가 "토큰 효율", "비용 분석", "캐시 히트율", "/efficiency" 등을 말할 때 사용한다.
---

# Efficiency — 세션 토큰/비용 요약

`/spec -> /design -> /impl -> /acceptance` lifecycle과 독립된 read-only 운영 도구다.

## 목적

`~/.claude/projects/<encoded-repo>/*.jsonl`의 실제 usage를 읽어 세션별 토큰·캐시·비용과 전체 합계를 재현한다. hook runtime은 이 분석을 import하거나 dashboard를 만들지 않는다.

## 실행

```bash
DCEFF="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)/scripts/dcness-efficiency"
"$DCEFF" analyze --repo "$(pwd)" --out /tmp/dcness-efficiency.json
```

명령은 다음을 출력한다.

- 분석한 session 수
- 합산 비용
- cache hit 비율
- 원자료 `/tmp/dcness-efficiency.json`

사용자에게는 stdout 합계와 JSON에서 비용 상위 세션을 확인해 2~3줄로 보고한다. 추정 dashboard·ROI·thrash heuristic을 runtime에서 만들지 않는다.

## 계약

- read-only이며 프로젝트 파일을 변경하지 않는다.
- 세션 디렉터리나 usage가 없으면 exit 2와 명시적 오류를 반환한다.
- 옛 `dashboard`·`patterns`·`patterns-dashboard`·`full` subcommand는 runtime 분석 제거에 따라 exit 2와 `analyze`/`summary` migration 안내를 반환한다.
- 미등록 모델은 알려진 model prefix를 먼저 비교하고, 그래도 모르면 보수적인 Opus 단가를 사용하며 stderr에 경고한다.
- `/run-review`의 단일 run 분석과 달리 `/efficiency`는 레포의 Claude Code session usage 전체를 본다.

## 구현

- `harness/efficiency/analyze_sessions.py` — JSONL parse, 가격 계산, 세션/전체 집계
- `scripts/dcness-efficiency` — `analyze`/`summary` wrapper
