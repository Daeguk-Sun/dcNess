# dcNess benchmark — 재현 가능한 공개 evidence

이 문서는 설치 runtime이 보존하는 최소 receipt와 dcNess source checkout에서 실행하는 검증을 구분한다. process, agent effectiveness, 제품 outcome, 비용을 하나의 성공 점수로 합치지 않는다.

## 현재 공개 evidence snapshot

<!-- public-evidence-snapshot {"plugin_version":"0.29.0","measured_at":"2026-07-25","unit_tests":{"passed":1216,"total":1216},"guard":{"passed":50,"total":50},"source_project_count":2} -->

현재 plugin version은 **v0.29.0**, 측정일은 **2026-07-24**이다. unit과 guard 수치는 dcNess source checkout의 기계적 계약 evidence이며 보안 증명이나 제품 성공률이 아니다.

| evidence | 관측값 | 재현 명령 | 한계 |
|---|---:|---|---|
| 전체 unit 계약 | 1,216/1,216 PASS | `python3.11 -m unittest discover -s tests -v` | source checkout 1개의 코드·문서 계약 |
| guard fixture | 50/50 PASS | `python3.11 evals/guard_efficacy.py --json` | deterministic payload의 allow/block/exit/stdout 계약 |
| 공개 snapshot drift | README/benchmark 일치 | `node scripts/check_public_evidence.mjs` | 위 두 명령 결과와 문서 marker만 대조 |

최종 test 수가 바뀌면 실제 전체 unit과 guard efficacy를 먼저 실행한 뒤 README와 이 문서의 marker를 같은 값으로 갱신한다.

## 설치 runtime evidence 경계

runtime hook과 helper는 workflow 복구에 필요한 최소 state와 receipt만 남긴다.

- session/run/step lifecycle state와 validator prose
- 실제 policy block의 guard/category/source receipt
- 판정하지 못하고 통과한 fail-open reason receipt
- public `/run-review`가 읽는 ledger와 run timeframe

runtime은 per-tool 입력 trace, tool histogram, dashboard, benchmark aggregation, agent effectiveness 판정, 자동 insight/lesson을 수집하거나 import하지 않는다. guard receipt 기록 실패도 원래 allow/block 판정을 바꾸지 않는다.

## 공개 재현 명령

release 후보의 검증·merge를 확정한 뒤에는 활성 프로젝트의 local checkout이 아니라 plugin 설치본을 기준으로 `$PLUGIN_ROOT/scripts/pr-finalize.sh`를 호출한다.

### 단일 run 복기

```bash
scripts/dcness-review --latest
scripts/dcness-review --run-id <RID>
```

`/run-review`는 완료된 단일 run의 step, conclusion, coarse token/cost, 관측 가능한 failure mode, context 문서 상태를 read-only로 출력한다.

### repository session token/cost

```bash
scripts/dcness-efficiency analyze --repo "$(pwd)" --out /tmp/dcness-efficiency.json
scripts/dcness-efficiency summary --repo "$(pwd)"
```

`/efficiency`는 Claude Code session JSONL의 usage를 합산한다. dashboard와 heuristic pattern 판정은 만들지 않는다.

### maintainer Flow Health

```bash
python3.11 scripts/measure_main_turns.py <session-jsonl-or-project-session-directory> \
  --flow-health --plugin-version <audited-plugin-version> --json
```

dcNess source checkout의 이 모드는 활성 프로젝트 세션 안 `/impl`·`/impl-loop` 호출마다 첫 구현 action(메인 직접 구현 edit 또는 headless worker launch)까지의 시간, blocking main request, 실제 tool 시간, 비도구 경과 비율, 첫 progress와 tool 후 최장 무응답을 다시 계산한다. 비도구 경과에는 모델 생성·오케스트레이션·사용자 판단 시간이 함께 들어갈 수 있으므로 낭비나 idle 시간으로 해석하지 않는다.

단일 `Flow Health` 등급으로 서로 다른 사실을 합치지 않고 네 축을 따로 보고한다.

| 축 | 판정 |
|---|---|
| Startup SLO | 첫 action `<60초`·blocking request `≤2회`. 위반 표본이 있으면 `MISS`, 위반 없이 현행 버전 표본 3개 이상이면 `PASS`, 그 전에는 `UNVERIFIED` |
| Flow Visibility | 첫 progress와 tool 후 다음 progress가 각각 `<60초`. 위반 표본이 있으면 `DEGRADED`, 위반 없이 표본 3개 이상이면 `CLEAR`, 그 전에는 `UNVERIFIED` |
| Agent Activity | 60초 이상 무응답 뒤 같은 assistant request에 thinking block이 관측되면 `ACTIVE_REASONING_OBSERVED`; thinking 근거가 없는 구간이 있으면 `UNATTRIBUTED_WAIT_OBSERVED`. 이는 활동 증거이지 reasoning의 생산성 증명이 아니다 |
| Relative Speed | 이 command-only 측정에서는 항상 `UNPROVEN`. 같은 fixture·model·effort·provider의 반복 paired trial과 품질 비회귀가 있어야 상대 속도를 주장한다 |

Startup SLO는 Workflow, Flow Visibility는 Legibility, 이 네 축을 자동 산출하는 능력은 Observability 근거로 쓴다. release artifact `GO`/`HOLD`와는 합치지 않으며 사용자 prompt·session ID·절대경로는 감사 보고서에 노출하지 않는다.

### guard 공개 계약

```bash
python3.11 evals/guard_efficacy.py --json
```

결과의 `total.passed`, `total.failed`, category별 결과, command exit/stdout/stderr를 함께 확인한다. fixture 수는 기능 수가 아니라 공개 guard 경로의 대표 입력 수다.

## dcNess 저장소 전용 분석

fleet benchmark, historical outcome scorecard, main-turn measurement, cross-project diagnose, lean ablation은 dcNess maintainers가 source checkout에서 명시적으로 실행하는 연구·운영 도구다. release artifact와 사용자 프로젝트 runtime에는 배포하지 않는다. 이 도구들의 결과는 provenance, denominator, source 수, 측정 불가 항목을 함께 기록할 때만 공개 evidence 후보가 된다.

## 해석 원칙

- 테스트 감소는 제거된 내부 구현 표현과 함께 줄었을 때만 다이어트 evidence다.
- LOC 감소만으로 품질 우위를 주장하지 않는다. public command, state compatibility, guard failure mode, release smoke가 먼저다.
- 단일 fixture나 paired run은 pilot이며 일반적인 비용·생산성 우위가 아니다.
- runtime receipt는 복구와 판정 근거이며 사람/agent 성과 점수가 아니다.
