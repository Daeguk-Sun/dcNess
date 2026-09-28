---
name: run-review
description: 완료된 dcNess run의 단계, 비용, 실패 모드, context 문서 상태를 read-only로 복기한다.
---

# Run Review

`/spec -> /design -> /impl -> /acceptance` 흐름에서 완료된 run을 분석한다. 단위는 run 하나 또는 story 하나다. runtime hook은 분석을 수행하지 않으며, 사용자가 `/run-review`를 요청하거나 helper가 run 종료 review를 만들 때만 실행한다.

## 범위

- `ledger.jsonl`의 `run_finished`와 `step_completed` receipt
- 단계별 validator prose
- run 시간대의 Claude Code session usage
- 현재 run의 waste/failure mode와 같은 sessions root 안의 반복 여부
- CLAUDE.md/AGENTS.md 연결, dcNess cold-start 앵커, context 문서 6축 rubric 품질
- `--story`를 쓰면 같은 story에 속한 run 전체와 그 story의 소요·토큰·비용 총계, 중복 제거한 finding 집계

per-tool 입력 trace, tool histogram, 자동 lesson/insight, cross-project dashboard는 수집하거나 생성하지 않는다. 저장소 개발자가 별도로 쓰는 benchmark 도구는 배포 runtime 계약이 아니다.

## 실행

```bash
HELPER="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)/scripts/dcness-review"

"$HELPER" --latest
"$HELPER" --run-id <RID>
"$HELPER" --story <STORY_ID>
"$HELPER" --list --limit 20
"$HELPER" --context-audit --repo "$(git rev-parse --show-toplevel)"
```

run id가 주어지면 `--run-id`, story 단위 복기 요청이면 `--story`, `list` 요청이면 `--list`, 그 밖에는 `--latest`를 사용한다. 진행 중 run은 implicit latest 후보에서 제외한다.

`--story`의 `STORY_ID`는 impl task frontmatter의 `story` 값이다. `/impl-loop`는 task마다 run을 따로 열고 각 run을 `begin-run impl --design-doc <impl task 경로>`로 시작하므로, run 기록의 `design_doc`과 그 impl task의 `story`가 run과 story를 잇는다. 별도 상태 파일을 만들거나 요구하지 않는다. 그 story에 속한 완료 run이 없으면 exit 1과 함께 그 사실을 보고한다.

## 출력 계약

helper stdout의 markdown report를 그대로 사용자에게 전달한다. report는 다음 핵심 정보를 포함한다.

- run/entry point/step 수와 coarse token·cost 합계
- 단계별 agent, mode, conclusion, elapsed, token/cost
- 재시도, 누락 conclusion, 경계 위반 흔적, 미해결 MUST FIX 같은 관측 가능한 finding
- 같은 sessions root 안의 반복 finding 후보
- context 문서 audit 결과

`--story` 리포트는 같은 섹션 구성을 story 단위로 재사용한다.

- story 요약(run 수, step 수, 소요·비용·token 총계, clean run 비율)
- run별 내역(run id, entry point, impl task 경로, step 수, 소요, 비용, 최종 enum)
- run 시작 순서대로 이은 호출 흐름
- story 전체에서 중복 제거한 finding과 그 발생 run 목록

분석 결과는 규칙을 자동 추가·삭제하거나 프로젝트 파일을 수정하지 않는다. 사용자가 후속 변경을 승인하면 별도 branch와 PR로 처리한다.

## 한계

- 비용은 run 시간대 session usage를 대응시킨 값이라 완전한 per-agent billing 증명이 아니다.
- prose finding은 정규식과 저장 receipt 기반이며 semantic judge가 아니다.
- helper run이 없는 `/spec`·standalone `/acceptance`는 필요할 때 `--context-audit`를 명시 호출한다.

## 구현

- `harness/run_review.py` — run parser, finding, 단일 run 및 story 단위 report
- `scripts/dcness-review` — 공개 wrapper
- `harness/efficiency/analyze_sessions.py` — 가격 계산 공유
- `commands/efficiency.md` — repository session 전체 token/cost 요약
