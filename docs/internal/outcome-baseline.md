# 제품 outcome scorecard 운영 baseline

> 측정 시점 snapshot. 값은 계속 쌓이는 runtime ledger의 영구 headline이 아니며, 재현 명령과 원천 범위를 함께 읽는다.

## 재현 명령

plugin checkout 또는 활성 plugin root를 `DCN`으로 지정한 뒤 실행한다.

```sh
python3 "$DCN"/harness/outcome_scorecard.py \
  --redact-paths \
  --measured-at 2026-07-11T13:46:46Z \
  --as-of 2026-07-11T13:46:46Z \
  --source-ref source-1242b5d736 \
  --source-ref source-d640b1b95d

python3 "$DCN"/harness/outcome_scorecard.py \
  --redact-paths \
  --measured-at 2026-07-11T13:46:46Z \
  --as-of 2026-07-11T13:46:46Z \
  --source-ref source-1242b5d736 \
  --source-ref source-d640b1b95d \
  --json
```

기본 원천은 active-project registry다. snapshot 시점 registry 5개 항목 중 완료 run 근거가 있는 source 프로젝트 2개만 분모에 들어갔다. 절대경로와 프로젝트 이름은 공개 snapshot에서 가리고, registry 위치와 경로 digest로 만든 stable source ref를 남긴다. 재현 명령은 이 두 ref를 명시적으로 고정하므로 registry 재정렬이나 새 프로젝트 추가가 source 집합을 바꾸지 않는다. 고정한 ref가 사라지거나 해당 runtime ledger를 읽을 수 없으면 재현기는 분모를 조용히 줄이는 대신 오류로 종료한다.

| source ref | 원천 위치 | finished/candidate run |
|---|---|---:|
| `source-1242b5d736` | active-project registry entry #3의 `.claude/harness-state/.sessions` | 12/13 |
| `source-d640b1b95d` | active-project registry entry #5의 `.claude/harness-state/.sessions` | 14/15 |

## 2026-07-11 snapshot

측정 시각과 관측 cutoff는 `2026-07-11T13:46:46Z`다. source 프로젝트 2, cutoff 전에 시작한 candidate run directory 28, cutoff 전에 receipt로 닫힌 finished run 26이다. 이후 추가된 run은 같은 snapshot 재현에서 제외된다.

| 영역 | 지표 | 값 | 분자/분모 | source 수 | 해석 경계 |
|---|---|---:|---:|---:|---|
| process | finished run 포함 | 92.9% | 26/28 | 2 | 불완전 run 2개는 집계에서 제외 |
| process | PR merge | 100.0% | 7/7 | 2 | `pr_created`가 있는 measurable PR만 분모; 제품 성공률 아님 |
| process | blocked event | 0.0% | 0/26 finished run | 2 | cutoff 이하의 명시적 `blocked` event만 집계 |
| process | guard 결과 | 측정 불가 | 0/0 | 2 | 선택한 legacy ledger baseline에 일관된 guard telemetry가 없음 |
| process | regression | 측정 불가 | 0/0 | 2 | 같은 조건의 반복 제품 journey 증거가 없음 |
| process | impl-validator 재작업 | 100.0% | 2/2 | 2 | 해당 agent의 판정 가능한 verdict만 분모; 다른 validator 역할과 합치지 않음 |
| process | validator verdict | 33건 | 33/26 finished run | 2 | architecture-validator FAIL 10/PASS 6, code-validator FAIL 7/PASS 8, impl-validator FAIL 2 |
| process | waste finding | 57건 | 57/26 finished run | 2 | `TOOL_REPEAT_HIGH` 42, `MISSING_CONCLUSION_ENUM` 7, `MUST_FIX_LEAK` 7, `END_STEP_SKIP` 1 |
| Agent effectiveness | 탐색 정확도·비용·오경로·영향 누락·context 재작업·복구 | 측정 불가 | 0/0 | 2 | 현재 ledger에 comparable paired trial이 없음 |
| product outcome | 실제 제품 AC와 사용자 journey | 측정 불가 | 0/0 | 2 | 앱/API/CLI/UI journey 실행 결과가 현재 ledger에 없음 |
| trial metadata | task/repo 유형, model/provider, variant, trial, token/wall-clock, 사람 개입 | 측정 불가 | 0/0 | 2 | legacy run 전체에 일관된 한 record가 없음 |

`7/7` merge는 PR 운영 결과다. guard PASS나 validator FAIL도 과정 evidence다. 세 값 중 어느 것도 실제 제품 AC 성공률로 바꾸지 않으며, merge 비율을 제품 전체 성공으로 해석하는 결론을 두지 않는다.

## Agent effectiveness 입력 경계

- Cartography freshness에서 얻을 수 있는 것: 현재 SSOT·runtime entrypoint·capability owner 후보, affected route의 stale 여부와 갱신·재검증 기록.
- Codebase Sanity에서 얻을 수 있는 것: 감사 code revision, 실제 scope, 명령·warning·coverage 근거, dead-code 분류와 unknown.
- 아직 측정할 수 없는 것: 첫 올바른 대상 선택 정확도와 시간, 불필요한 read/tool 양, 오경로, 영향 범위 누락, context 기인 validator 재작업, cross-session 복구 성공의 paired before/after.

기능 또는 receipt가 존재한다는 사실은 마지막 항목들의 개선 증거가 아니다. 후속 trial이 생길 때까지 `측정 불가`를 실패나 개선으로 추정하지 않는다.

## 사용 가능한 주장

이 snapshot은 source 2개와 finished run 26개라는 cross-project process baseline 조건은 충족한다. 그러나 비교 variant별 반복 trial과 실제 product outcome이 없으므로 공개 우위 주장은 할 수 없다. 같은 fixture의 1+1 paired screening은 개인 경량화 `keep` / `remove` / `hold` 판단에만 사용할 수 있다.
