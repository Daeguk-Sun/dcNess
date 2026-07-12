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

## 2026-07-12 non-UI 제품 journey pilot

2026-07-11 process snapshot은 그대로 고정하고, 이후 처음 생성된 product outcome 표본을 별도 slice로 추가한다. active-project registry의 `source-d640b1b95d`에서 `yt-make-intake-cli`를 실제 CLI entrypoint와 filesystem session 경계로 실행했다. helper가 start, health, journey assertion, cleanup을 순서대로 실행했고 `2026-07-12T07:36:43Z` receipt를 남겼다.

```sh
python3.11 "$DCN"/harness/outcome_scorecard.py \
  --redact-paths \
  --measured-at 2026-07-12T07:37:00Z \
  --as-of 2026-07-12T07:37:00Z \
  --source-ref source-d640b1b95d \
  --json
```

| 영역 | 결과 | denominator / source | 실행 증거 | 사람 개입 | 해석 경계 |
|---|---|---|---|---:|---|
| product outcome | journey PASS 1/1, 제품 AC 1/1 | journey 1, AC 1, source 1 | `cli, command, log` + sha256 receipt | 사람 개입 0 | 단일 외부 활성 프로젝트의 단일 non-UI pilot이며 공개 우위 근거가 아님 |

대상 AC는 `AC-421`이고 assertion은 자연어 prompt intake가 실제 session 파일을 만들며 선택한 `history_culture` category와 원문 prompt를 보존하는지 확인했다. `mock` adapter를 쓰지 않았고 실행 후 생성 상태는 cleanup했다. receipt와 log는 해당 source 프로젝트의 ignored `.dcness-work/product-journey/yt-make-intake-pilot-20260712/`에 남아 있으며 공개 문서에는 절대경로를 기록하지 않는다.

## Agent effectiveness 입력 경계

- Cartography freshness에서 얻을 수 있는 것: 현재 SSOT·runtime entrypoint·capability owner 후보, affected route의 stale 여부와 갱신·재검증 기록.
- Codebase Sanity에서 얻을 수 있는 것: 감사 code revision, 실제 scope, 명령·warning·coverage 근거, dead-code 분류와 unknown.
- 아직 측정할 수 없는 것: 첫 올바른 대상 선택 정확도와 시간, 불필요한 read/tool 양, 오경로, 영향 범위 누락, context 기인 validator 재작업, cross-session 복구 성공의 paired before/after.

기능 또는 receipt가 존재한다는 사실은 마지막 항목들의 개선 증거가 아니다. 후속 trial이 생길 때까지 `측정 불가`를 실패나 개선으로 추정하지 않는다.

## 2026-07-12 Agent effectiveness deterministic screening

`agent-effectiveness-2026-07`은 cold-start 탐색과 refactor/replacement 검증의 frozen synthetic fixture 2개를 baseline/current로 replay했다. 새 agent나 공개 command를 추가하지 않고 기존 scorecard에 record 입력만 연결했다.

```sh
printf '{"version":1,"projects":[]}' > /tmp/dcness-empty-projects.json
python3.11 "$DCN"/harness/outcome_scorecard.py \
  --projects-file /tmp/dcness-empty-projects.json \
  --agent-effectiveness-record \
  "$DCN"/evals/agent-effectiveness/cartography-sanity-replay.json \
  --measured-at 2026-07-12T10:00:00Z \
  --json
```

측정 조건은 provider `deterministic-replay`, model `none`, frozen synthetic Python repo, baseline/current 두 variant다. 비교 trial 4, source fixture 2, 측정일 `2026-07-12T10:00:00Z`이며 input/output token `0/0`, cost `$0.00`이다. 모델을 호출하지 않는 저장 replay라 wall-clock은 agent 수행 시간이 아닌 fixture trace의 첫 정답 elapsed 값만 비교한다.

| task | 지표 | baseline | current | 판정 |
|---|---|---:|---:|---|
| cold-start | SSOT/entrypoint/owner/decision 정확도 | 4/4 | 4/4 | 비열화 없음 |
| cold-start | 첫 owner까지 tool / read bytes / elapsed | 5 / 3,100 / 50ms | 3 / 1,500 / 30ms | 감소 |
| cold-start | 전체 tool / read bytes / 오경로 | 6 / 3,400 / 2 | 4 / 1,800 / 0 | 감소 |
| refactor/replacement | stale/framework/seam 분류 | 1/3 | 3/3 | 개선 |
| refactor/replacement | 영향 누락 / 과다 포함 | 1 / 1 | 0 / 0 | 개선 |
| 두 task 합계 | context 기인 재작업 / cross-session 복구 | 2 / 0 | 0 / 2 | 개선 |
| 두 task 품질 | 제품 AC / MUST-FIX / 회귀 / 사람 복구 | 4/4 / 0 / 0 / 0 | 4/4 / 0 / 0 / 0 | 비열화 없음 |

탐색 tool은 `13→9`, read bytes는 `7,000→4,600`, 오경로는 `2→0`, 영향 누락은 `1→0`, context 기인 재작업은 `2→0`으로 줄었고 핵심 품질은 악화되지 않았다. 따라서 이 결정적 screening에서는 개선을 관측했다. 문서 수, map 크기, hook 수는 입력 설명일 뿐 effectiveness 대리값으로 사용하지 않았다.

2026-07 epic 공통 추가 LLM trial 누계 `2/4`는 #1069 screening의 기존 2회뿐이며 이번 record의 새 LLM trial은 0회다. #1069와 같은 달 paired screening을 실행하지 않았다. 이 결과는 synthetic fixture 2개와 저장 trace에 한정되고, live agent token/cost·실제 프로젝트 wall-clock·다중 model/provider·공개 우위는 측정 불가다.

## 사용 가능한 주장

이 snapshot은 source 2개와 finished run 26개라는 cross-project process baseline 조건은 충족한다. 그러나 비교 variant별 반복 trial과 실제 product outcome이 없으므로 공개 우위 주장은 할 수 없다. 같은 fixture의 1+1 paired screening은 개인 경량화 `keep` / `remove` / `hold` 판단에만 사용할 수 있다.

## 2026-07 lean ablation pilot

`TOOL_REPEAT_HIGH` 42건/finished run 26개/source 2곳과 직접 연결된 선택형
`[LESSONS]`의 `hits/last/evidence` prompt metadata 축소를 평가했다. hard safety
guard는 live disable하지 않았고 frozen read-only fixture의 deterministic 비교,
shadow prompt 비교, 동일 `openai-codex` / `gpt-5.6-sol` 조건의 1+1 screening 순서를
지켰다.

| variant | trial | 제품 AC | MUST-FIX / 회귀 / 사람 개입 | input/output token | wall-clock | 결정 입력 |
|---|---:|---:|---:|---:|---:|---|
| baseline | 1 | 2/2 | 0 / 0 / 0 | 38,874 / 355 | 15.36s | full lesson metadata |
| metadata 축소 | 1 | 2/2 | 0 / 0 / 0 | 40,659 / 366 | 13.81s | prompt 107 bytes 감소 |

주지표 input token이 감소하지 않아 첫 pair에서 **keep**으로 종료했다. 실행 월
`2026-07`, epic 공통 추가 LLM trial 누계 `2/4`, #1070 같은 달 screening 없음이다.
단일 frozen fixture 결과이므로 공개 superiority 근거가 아니다. 재현 계약, fixture
hash, evidence와 한계는 [`lean-ablation-2026-07.md`](lean-ablation-2026-07.md)에 있다.
