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

## 2026-07-13 UI 제품 journey pilot

기존 project-local 실행 계약에 `boundary=ui`와 단계별 화면 evidence만 추가해 active-project registry의 `source-5509daf5ed`에서 `finsight-underage-ui` journey로 실제 Next 앱과 Chromium을 실행했다. 랜딩의 `무료로 시작` CTA를 눌러 온보딩으로 이동하고, 미성년 생년월일과 이용 동의를 제출한 뒤 결과 화면으로 넘어가지 않으며 거부·미저장 안내가 표시되는지 `AC-001`과 대조했다. 외부 OAuth·DB 호출은 프로젝트의 acceptance 설정으로 차단했지만, 검증 경계인 실제 앱 기동·브라우저 클릭·Next server action·렌더 화면은 mock으로 대체하지 않았다.

```sh
python3.11 "$DCN"/harness/outcome_scorecard.py \
  --redact-paths \
  --measured-at 2026-07-13T03:00:00Z \
  --as-of 2026-07-13T03:00:00Z \
  --source-ref source-5509daf5ed \
  --json
```

| 영역 | 결과 | denominator / source | 실행 증거 | 사람 개입 | 해석 경계 |
|---|---|---|---|---:|---|
| product outcome | journey PASS 1/1, 제품 AC 1/1 | journey 1, AC 1, source 1 | `ui, screenshot, command, log` + sha256 receipt | 실행 중 사람 개입 0 | 단일 외부 활성 프로젝트의 단일 UI pilot이며 공개 우위 근거가 아님 |

receipt는 `landing` → `onboarding` → `underage-rejection` → final `profile-absent` 네 단계의 설명·대상 AC와 screenshot SHA-256을 연결한다. 브라우저 assertion log는 거부 안내, 입력 미저장 안내, 결과 미노출에 더해 거부 후 `/results`를 직접 열어도 profile-required 상태인 것을 모두 PASS로 남겼다. 증거는 해당 source 프로젝트의 ignored `.dcness-work/product-journey/ui-pilot-issue1080-20260713/`에 보존하며 공개 문서에는 절대경로를 기록하지 않는다. 화면 evidence가 사용자 관점에서 충분한지는 issue의 별도 human verification으로 남긴다.

## Agent effectiveness 입력 경계

- Cartography freshness에서 얻을 수 있는 것: 현재 SSOT·runtime entrypoint·capability owner 후보, affected route의 stale 여부와 갱신·재검증 기록.
- Codebase Sanity에서 얻을 수 있는 것: 감사 code revision, 실제 scope, 명령·warning·coverage 근거, dead-code 분류와 unknown.
- 아직 측정할 수 없는 것: 첫 올바른 대상 선택 정확도와 시간, 불필요한 read/tool 양, 오경로, 영향 범위 누락, context 기인 validator 재작업, cross-session 복구 성공의 paired before/after.

기능 또는 receipt가 존재한다는 사실은 마지막 항목들의 개선 증거가 아니다. 후속 trial이 생길 때까지 `측정 불가`를 실패나 개선으로 추정하지 않는다.

## 2026-07-12 Agent effectiveness deterministic screening

`agent-effectiveness-2026-07`은 frozen synthetic repository fixture 1개에서 cold-start 탐색과 refactor/replacement 검증 task 2개를 baseline/current로 replay했다. 새 agent나 공개 command를 추가하지 않고 기존 scorecard에 record 입력만 연결했다.

record의 tool/read/오경로/영향 집합 trace 값은 실제 agent 실행에서 유래하지 않고 record에 직접 저작된 synthetic 값이며, run ID·raw tool trace·생성 명령 같은 provenance가 없다. 따라서 본 절은 측정 계약과 계산이 fail-closed로 동작함을 검증하는 기록이지 실제 agent effectiveness의 관측이 아니다.

```sh
printf '{"version":1,"projects":[]}' > /tmp/dcness-empty-projects.json
python3.11 "$DCN"/harness/outcome_scorecard.py \
  --projects-file /tmp/dcness-empty-projects.json \
  --agent-effectiveness-record \
  "$DCN"/evals/agent-effectiveness/cartography-sanity-replay.json \
  --measured-at 2026-07-12T10:00:00Z \
  --json
```

측정 조건은 provider `deterministic-replay`, model `none`, frozen synthetic Python repo, baseline/current 두 variant다. 비교 trial 4, source fixture 1, task 2, 측정일 `2026-07-12T10:00:00Z`이며 input/output token `0/0`, cost `$0.00`이다. 모델을 호출하지 않는 저장 replay라 wall-clock은 agent 수행 시간이 아닌 fixture trace의 첫 정답 elapsed 값만 비교한다.

| task | 지표 | baseline | current | 판정 |
|---|---|---:|---:|---|
| cold-start | SSOT/entrypoint/owner/decision 정확도 | 4/4 | 4/4 | 비열화 없음 |
| cold-start | 첫 owner까지 tool / read bytes / elapsed | 5 / 3,100 / 50ms | 3 / 1,500 / 30ms | 감소 |
| cold-start | 전체 tool / read bytes / 오경로 | 6 / 3,400 / 2 | 4 / 1,800 / 0 | 감소 |
| refactor/replacement | stale/framework/seam 분류 | 1/3 | 3/3 | 개선 |
| refactor/replacement | 영향 누락 / 과다 포함 | 1 / 1 | 0 / 0 | 개선 |
| 두 task 합계 | context 기인 재작업 / cross-session 복구 | 2 / 0 | 0 / 2 | 개선 |
| 두 task 품질 | 제품 AC / MUST-FIX / 회귀 / 사람 복구 | 4/4 / 0 / 0 / 0 | 4/4 / 0 / 0 / 0 | 비열화 없음 |

탐색 tool은 `13→9`, read bytes는 `7,000→4,600`, 오경로는 `2→0`, 영향 누락은 `1→0`, context 기인 재작업은 `2→0`으로 계산됐고, 계산기는 핵심 품질 비열화가 없을 때만 결과를 기록했다. 이 수치는 저작된 record 값에 대한 측정 계약 검증 결과이며 실제 agent의 effectiveness 개선 관측이 아니다. 실제 agent effectiveness는 동일 frozen task의 실측 baseline/current 1+1 record가 남을 때까지 `측정 불가`로 유지했고, 그 실측 record는 아래 [2026-07-13 Agent effectiveness 실측 paired screening](#2026-07-13-agent-effectiveness-실측-paired-screening) 절에 남았다. 문서 수, map 크기, hook 수는 입력 설명일 뿐 effectiveness 대리값으로 사용하지 않았다.

당시 2026-07 epic 공통 추가 LLM trial 누계 `2/4`는 #1069 screening의 기존 2회뿐이며 이번 record의 새 LLM trial은 0회다. #1069와 같은 달 paired screening을 실행하지 않았다. 이 결과는 synthetic fixture 1개·task 2개와 저장 trace에 한정되고, live agent token/cost·실제 프로젝트 wall-clock·다중 model/provider·공개 우위는 측정 불가다.

## 2026-07-13 Agent effectiveness 실측 paired screening

`agent-effectiveness-real-2026-07`은 위 절과 동일한 frozen fixture·task 2개를 실제 headless agent로 실행한 baseline 1 trial + current 1 trial(1+1) 실측이다. provider `claude -p --safe-mode (headless)`, model `claude-sonnet-4-6`, 동일 task prompt·도구(Read/Glob/Grep)·격리 sandbox 조건에서 current에만 Cartography/Sanity contract preamble을 주입했다. record `evals/agent-effectiveness/cartography-sanity-real.json`의 provenance 블록에 각 run의 세션 ID(run ID), trace 파일·SHA-256, capture/rebuild 명령이 남아 있다. tool/read evidence trace는 `evals/agent-effectiveness/evidence/real-2026-07-attempt1/`과 `evals/agent-effectiveness/evidence/real-2026-07-attempt2/`에 보존한다. 각 trace는 init identity, tool call/result, elapsed time, final result를 유지하되 host 경로, account rate-limit 상태, plugin·skill·agent·slash-command·event UUID 같은 account/runtime inventory는 제외한다. CI는 hash만 확인하지 않고 attempt 2 trace에서 record를 다시 조립해 checked-in JSON과 동일한지 대조한다.

1차 시도(2026-07-13)는 두 variant 모두 refactor 영향 집합에 별도 framework 경로 2건(`config/handlers.json`, `src/runtime_handler.py`)을 과다 포함해 fail-closed 검증기가 record 등재를 거부했다. Cartography 계약에 영향 경계 규율(바뀌는 capability의 row 경계 유지, 별도 framework/manifest 등록 경로 미포함 — [`docs/plugin/deliverables-map.md`](../plugin/deliverables-map.md)에 동일 규율 반영)을 추가한 뒤 2차 paired run을 실행해 채택했다. 같은 설정의 재실행 선별은 하지 않았고 두 시도의 trace를 모두 보존했다. 2차의 baseline(계약 미주입)이 같은 과다 포함 2건을 재현하고 current(개정 계약)는 과다 0건이라, 이 규율이 해당 실패 모드를 실제로 제거했다는 paired 증거가 함께 남았다.

```sh
python3.11 "$DCN"/evals/agent_effectiveness_measure.py --from-traces \
  --output-dir "$DCN"/evals/agent-effectiveness/evidence/real-2026-07-attempt2 \
  --record-out "$DCN"/evals/agent-effectiveness/cartography-sanity-real.json
printf '{"version":1,"projects":[]}' > /tmp/dcness-empty-projects.json
python3.11 "$DCN"/harness/outcome_scorecard.py \
  --projects-file /tmp/dcness-empty-projects.json \
  --agent-effectiveness-record \
  "$DCN"/evals/agent-effectiveness/cartography-sanity-real.json \
  --measured-at 2026-07-12T15:17:58Z \
  --json
```

| task | 지표 | baseline | current | 판정 |
|---|---|---:|---:|---|
| cold-start | 좌표 정확도 | 4/4 | 4/4 | 비열화 없음 |
| cold-start | 전체 tool / read bytes / 오경로 | 6 / 1,072 / 1 | 4 / 923 / 0 | 감소 |
| cold-start | 첫 owner까지 tool / read bytes / elapsed | 4 / 923 / 11,189ms | 3 / 629 / 9,444ms | 감소 |
| refactor/replacement | stale/framework/seam 분류 | 3/3 | 3/3 | 비열화 없음 |
| refactor/replacement | 영향 누락 / 과다 포함 | 0 / 2 | 0 / 0 | 개선 |
| 두 task 품질 | fixture task AC | 7/8 | 8/8 | 개선 |
| downstream 품질 | MUST-FIX / 회귀 / 사람 복구 / context 재작업 / cross-session | 측정 불가 | 측정 불가 | 본 read-only fixture에서 미실행 |

합계는 전체 탐색 tool `15→13`, read bytes `2,260→2,156`, 오경로 `1→0`, 영향 과다 포함 `2→0`이고 측정된 fixture task AC가 `7/8→8/8`로 악화되지 않아 계산기가 개선 관측을 기록했다. MUST-FIX·회귀·사람 복구·context 재작업·cross-session은 실행하지 않았으므로 0으로 대체하지 않고 `측정 불가`로 둔다. result-event usage 기준 input/output token `18/4,519`(cache 토큰 제외), cost `$0.14`다. 실행 월 `2026-07`, 새 LLM trial 2회, 2026-07-13 사용자 결정으로 개정된 한시 상한 6회 기준 epic 공통 누계 `6/6`이다. validator는 기본 상한 4와 이 월의 6회 예외만 허용하고 record가 선언한 임의 cap은 거부한다. 단일 frozen fixture의 1회 paired 실측이므로 통계적 일반화와 공개 우위 주장에는 사용할 수 없다.

## 사용 가능한 주장

이 snapshot은 source 2개와 finished run 26개라는 cross-project process baseline 조건은 충족한다. 그러나 비교 variant별 반복 trial과 실제 product outcome이 없으므로 공개 우위 주장은 할 수 없다. 같은 fixture의 1+1 paired screening은 개인 경량화 `keep` / `remove` / `hold` 판단에만 사용할 수 있다. 2026-07-13 Agent effectiveness 실측 paired screening도 같은 경계를 따른다: 단일 frozen fixture 1회 실측이므로 개인 effectiveness 신호로만 쓰고 공개 우위 주장에는 쓰지 않는다.

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
`2026-07`, 당시 epic 공통 추가 LLM trial 누계 `2/4`, 당시 #1070 같은 달 screening 없음이다(이후 2026-07-13 사용자 결정으로 월 배분 분리 규칙 폐지·상한 한시 증액 — Agent effectiveness 실측 절 참조).
단일 frozen fixture 결과이므로 공개 superiority 근거가 아니다. 재현 계약, fixture
hash, evidence와 한계는 [`lean-ablation-2026-07.md`](lean-ablation-2026-07.md)에 있다.
