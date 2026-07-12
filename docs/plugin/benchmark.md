# dcNess benchmark — 측정 재현 가이드 + 실측 샘플

> 이 문서는 "화려한 성능 자랑" 이 아니다. dcNess 가 실제로 어디서 비용을 줄이는지,
> 그 수치를 **누구나 자기 프로젝트에서 직접 재현**할 수 있게 하는 것이 목적이다.
> 공개된 표본은 작다. headline 숫자는 항상 표본 수, 출처 수, 한계를 같은 단락에 둔다.
> 표본이 작으면 일반 성능 주장이 아니라 pilot / anecdote 로만 다룬다.

## 현재 공개 Evidence snapshot

<!-- public-evidence-snapshot {"plugin_version":"0.21.0","measured_at":"2026-07-12","unit_tests":{"passed":1924,"total":1924},"guard":{"passed":39,"total":39},"source_project_count":2} -->

현재 plugin version은 **v0.21.0**, 측정일은 **2026-07-12**다. 아래 표의 최대
source 프로젝트 수는 2이며, 영역별 실제 source와 denominator는 각 행에 다시 적는다.
process, Agent effectiveness, product outcome, 비용을 합산한 단일 성공 점수는 만들지 않는다.

| evidence 영역 | 관측값 | denominator | source 수 | 재현 명령 | 한계 |
|---|---|---:|---:|---|---|
| 하네스 정의·기계적 guard | unittest 1,924/1,924 PASS; guard fixture 39/39 PASS | test 1,924; guard 39 | dcNess checkout 1 | `node scripts/check_public_evidence.mjs` | 테스트와 fixture 계약의 과정 evidence다. 보안 증명·제품 성공률이 아니다 |
| Agent effectiveness | tool 13→9; read 7,000→4,600 bytes; wrong path 2→0; missed impact 1→0; context rework 2→0 | baseline/current trial 4, task 2 | synthetic fixture 1 | `printf '{"version":1,"projects":[]}' > /tmp/dcness-empty-projects.json && python3.11 harness/outcome_scorecard.py --projects-file /tmp/dcness-empty-projects.json --agent-effectiveness-record evals/agent-effectiveness/cartography-sanity-replay.json --measured-at 2026-07-12T10:00:00Z --json` | deterministic 저장 replay다. live agent token/cost, 실제 프로젝트 wall-clock, 다중 model/provider는 측정 불가 |
| PR·validator 운영 | finished 26/28; PR merge 7/7; validator verdict 33/26 finished run | candidate run 28; measurable PR 7; finished run 26 | 외부 활성 프로젝트 2 | [`outcome-baseline.md`](../internal/outcome-baseline.md#재현-명령)의 두 source-ref 고정 명령 | merge·validator FAIL은 제품 성공률이 아니다. 선택한 legacy ledger의 guard와 regression은 측정 불가 |
| 실제 제품 outcome | non-UI journey 1/1 PASS; 제품 AC 1/1 | journey 1; AC 1 | 외부 활성 프로젝트 1 | [`outcome-baseline.md`](../internal/outcome-baseline.md#2026-07-12-non-ui-제품-journey-pilot)의 receipt 집계 명령 | 단일 CLI/filesystem pilot이다. UI·다른 제품·공개 우위로 일반화할 수 없다 |
| 비용·경량화 | prompt 107 bytes 감소; input token 38,874→40,659; 결정 `keep` | baseline/variant trial 2 | frozen fixture 1 | `python3.11 evals/lean_ablation.py evals/lean-ablation/tool-repeat-lesson-metadata.json --json` | billed cost 측정 불가. 단일 pair의 wall-clock 감소를 우위 근거로 쓰지 않는다 |

### 구현 전 결정 pilot과 행동 eval 보정

| evidence | 관측값 | denominator / source | 재현·원천 | 한계 |
|---|---|---|---|---|
| 결정 완전성 회고 | 실제 작업 2건 모두에서 이미 정해진 선택은 재질문하지 않고 구현 방향을 바꾸는 미결정 1건씩 표면화; 사람 확인 완료 | 회고 2 / 실제 작업 source 2 | [`decision-completeness-pilots.md`](../internal/decision-completeness-pilots.md)의 원본 hash와 대조 위치 | 회고 표본이며 제품 성공률·질문 절감률을 산출하지 않는다 |
| 행동 eval judge 보정 | 사람 golden과 저장 judge 판정 9/9 일치 | 비교 9, report 2 / 고정 calibration set 1 | `python3 evals/calibrate_judge.py evals/calibration/core-incidents-v1 --golden evals/golden/core-incidents-v1.json --expect-golden-version core-incidents-v1-human-v1 --expect-subset-version core-incidents-v1` | 2026-07-05 Sonnet report 2건의 고정 재채점이다. 현재 모든 agent 행동이나 제품 outcome을 뜻하지 않는다 |

### freshness와 drift 검출

기본 검증 명령은 실제로 `python3.11 -m unittest discover -s tests -v`와
`python3.11 evals/guard_efficacy.py --json`을 실행한다. 그 결과를 README와 이 문서의
동일 snapshot marker, `.claude-plugin/plugin.json` version과 비교하므로 version·test·guard
중 하나라도 현재 checkout과 달라지면 exit 1이다.

```sh
node scripts/check_public_evidence.mjs
```

이 gate는 source-ref runtime ledger나 ignored journey receipt를 공개 저장소에 복제하지
않는다. 운영·제품·effectiveness 숫자의 원천과 고정 cutoff는
[`outcome-baseline.md`](../internal/outcome-baseline.md)가 소유하며, 원천이 없는 환경에서는
기록된 snapshot을 재현한 것처럼 가장하지 않고 `측정 불가`로 남긴다.

## 무엇을 측정하나

dcNess 는 측정 인프라를 plug-in 본체에 같이 배포한다.

| 측정 도구 | 무엇을 보나 | 진입점 |
|---|---|---|
| [`scripts/measure_main_turns.py`](../../scripts/measure_main_turns.py) | Claude Code 세션의 메인 assistant turn 분포 (tool / text-only / thinking-only) + tool histogram + sub-agent 호출 분포 | 직접 실행 |
| [`harness/run_review.py`](../../harness/run_review.py) | run 1개의 step별 비용·토큰 + 낭비(waste) finding | `/run-review` skill |
| [`harness/benchmark_aggregate.py`](../../harness/benchmark_aggregate.py) | 여러 run 가로질러 fleet 집계 (PR 머지 성공률 / review rejection / escalate / blocked / waste top-N / 재발 개선 후보) | 직접 실행 |
| [`harness/outcome_scorecard.py`](../../harness/outcome_scorecard.py) | 활성 프로젝트를 가로질러 process, Agent effectiveness, 실제 제품 outcome을 분리하고 모든 집계에 denominator·source 수·측정일을 붙임 | 직접 실행 |

guard 효능 재현은 별도다. dcNess 소스 checkout 에서만 제공되는
`evals/guard_efficacy.py` 는 LLM 없이 hook/function 진입점을 직접 호출해 file boundary,
Bash/MCP mutation, order gate, TDD guard 의 allow/block fixture 를 검증하고 범주별
pass/fail count 를 출력한다.

```sh
python3 evals/guard_efficacy.py
python3 evals/guard_efficacy.py --json
```

이 결정적 suite 의 PASS 는 "fixture 로 박은 guard 계약이 재현된다"는 뜻이다. 보안 증명이나
악의적 agent 완전 차단 주장이 아니다. `known-bypass-boundary` 범주는 문서화된 한계
(예: command substitution 은 외부 변경 denylist 의 best-effort 범위 밖)를 숨기지 않고
측정 표면에 올려둔다.

> **스크립트 위치** — `scripts/` · `harness/` 는 plug-in 본체로 배포된다. 외부 활성
> 프로젝트는 이 파일들이 repo 안이 아니라 **plug-in 캐시**에 있으므로, 아래 명령은
> 먼저 그 루트를 변수로 잡고 prefix 한다. `/run-review` 는 skill 이 경로 해석을
> 대신하므로 prefix 불필요.
>
> ```sh
> # Claude Code 세션 안: 활성 plug-in 경로가 환경변수로 주어진다 (가장 정확).
> DCN="$CLAUDE_PLUGIN_ROOT"
> # dcNess 저장소 체크아웃에서 돌릴 땐: DCN=.
> # 세션 밖 수동 실행이고 캐시에 여러 버전이 깔려 있으면 버전 디렉토리를 직접 지정한다:
> #   DCN=~/.claude/plugins/cache/dcness/dcness/<버전>   (예: .../0.7.1)
> # (lexical `tail`/GNU `sort -V`/mtime 어느 것도 버전 선택을 보장 못 함 — 명시가 안전.)
> ```

핵심 가설은 단순하다. dcNess 의 무거운 절차(검증·구현·리뷰 시퀀스)를 sub-agent 가
흡수하면 **메인 Claude 의 turn 누적이 줄어든다**. 그게 사실인지 숫자로 본다.

LLM 행동 eval 은 또 다른 범위다. [`evals/run.sh`](../../evals/run.sh) 는 실제 agent 를
호출해 지침이 story slicing 같은 판단을 계속 하게 만드는지 보는 회귀 도구이며, guard
hook/function 의 결정적 allow/block 성능을 대신하지 않는다.

## 지표 구분

한 표에 서로 다른 지표를 섞어 "좋아졌다"로 뭉개지 않는다.

비교 단위와 측정 불가 처리, Agent effectiveness와 실제 제품 결과의 전체 의미 계약은
[`outcome-scorecard.md`](outcome-scorecard.md)가 소유한다. 본 문서는 기존 측정 도구의
재현 recipe와 공개 숫자 해석을 소유한다.

| 지표 | 의미 | 산출 근거 |
|---|---|---|
| cost / turn reduction | 메인 turn, token, cost 가 얼마나 줄었는가 | Claude Code session JSONL + `measure_main_turns.py` / `run_review.py` |
| review rejection | `impl-validator` 가 실제로 반려한 비율 | `impl-validator` verdict: `FAIL / (PASS + FAIL)` (legacy LGTM 는 집계 호환만 유지) |
| blocked events | run 이 안전하게 멈춘 횟수 | `ledger.jsonl` 의 `blocked` event |
| escalate | agent 가 자동 진행을 거부하고 사용자/상위 설계로 올린 횟수 | step verdict 에 `ESCALATE` 포함 |
| waste | 반복 실패, 도구 반복, gate 모순 등 비용 낭비 finding | `run_review.py` 의 waste detector |
| PR merge success | 생성된 PR 중 실제 merge 완료로 확인된 비율 | `pr_created` denominator 중 matching `pr_merged` event |

`pr_merged` 만 있고 matching `pr_created` 가 없으면 성공률을 만들지 않는다. 이 경우
집계기는 merged event count 와 orphan count 는 보여주지만 ratio 는 `측정 불가`로 둔다.
빈칸을 synthetic 추정값으로 채우지 않는다.

### 공개 숫자 최소 기준

- **단일 run / n=1**: anecdote. headline 성능 주장 금지.
- **한 프로젝트만 있는 fleet**: single-project snapshot. 다른 프로젝트 일반화 금지.
- **cross-project claim**: 최소 2개 프로젝트, 총 20개 이상 finished run, 지표별 denominator
  명시. cost/turn 비교는 작업 종류가 다른 run 을 섞지 말고 variant 별 n 을 따로 쓴다.
- 모든 표는 `n`, source count, 측정 날짜 또는 run 범위, 재현 명령, 주요 한계를 표 바로
  옆에 적는다.

## 재현 1 — 메인 turn 측정

세션 JSONL 은 Claude Code 가 `~/.claude/projects/<project-id>/<session-id>.jsonl`
에 자동 기록한다. 그 파일을 그대로 넣는다.

```sh
# 세션 1개 측정 (텍스트 리포트) — $DCN 은 위 "스크립트 위치" 참조
python3 "$DCN"/scripts/measure_main_turns.py ~/.claude/projects/<project-id>/<session-id>.jsonl

# JSON 출력 (집계·비교용)
python3 "$DCN"/scripts/measure_main_turns.py <jsonl-path> --json

# 디렉토리 일괄 (해당 프로젝트의 모든 세션)
python3 "$DCN"/scripts/measure_main_turns.py ~/.claude/projects/<project-id>/
```

출력은 한 세션의 메인 assistant turn 을 tool turn / text-only turn /
thinking-only turn 으로 분류하고, tool 별 빈도와 sub-agent(`Task` 호출) 분포를
함께 보여준다. **메인 turn 이 적을수록** 메인 컨텍스트 누적·비용이 작다.

## 재현 2 — run 사후 분석 (비용 + 낭비 finding)

dcNess loop(`begin-run` ~ `end-run` 사이클)을 한 번이라도 돌린 run 은
**활성 프로젝트 저장소 안** `.claude/harness-state/.sessions/<sid>/runs/<rid>/ledger.jsonl`
에 step 이벤트가 쌓인다(홈 디렉토리가 아니라 repo-local이다. worktree 안에서
돌려도 `git rev-parse --git-common-dir` 로 main repo 의 `.claude/harness-state/`
가 단일 source 가 된다). 이걸 분석한다.

```
/run-review            # 최신 run 자동 분석
/run-review <run-id>   # 특정 run 명시
/run-review list       # run 목록만
```

`/run-review` 는 step별 비용, 낭비(WASTE — 같은 실패 재시도 / read-only Bash 낭비 /
도구 반복, gate 모순 등) finding, 수정 제안을 리포트로 출력한다. 현재 run 의 waste pattern
이 같은 sessions root 의 과거 run 에서도 임계(기본 3회) 이상 반복됐으면 재발 기반 개선
후보로 같이 표면화한다. 실 구현은
[`harness/run_review.py`](../../harness/run_review.py) 다.

## 실측 샘플 (turn 절감)

아래는 현재 공개 가능한 **단일 표본**이다. n=1 이므로 일반 성능 주장이 아니라
재현 절차를 보여주는 anecdote 다.

| 지표 | 값 | 비고 |
|---|---|---|
| baseline (옛 다단계 모델) | ~280 turn/task | 외부 활성 프로젝트 impl 1-task 세션 3개 평균 (n=3) |
| Hybrid A (build-worker 2-step) | 121 turn/task | impl 1-task 측정 (n=1) |
| 절감 | ~57% | 121 / 280 기준, anecdote |

turn 구성 분석 (Hybrid A 샘플): thinking-only + text-only = 50.7% / sub-agent
호출 = 3.1% / git+gh 분리 호출 = 13.8%. 즉 sub-agent 가 작업을 흡수해도 메인의
*대화 + 관리* 자체 base load 가 ~80-100 turn 존재한다 — turn 을 0 으로 만드는
도구가 아니라, 무거운 구현·검증 누적을 sub-agent 로 옮겨 메인을 가볍게 하는 도구다.

출처: dcNess v0.2.28 릴리즈의 외부 활성 프로젝트 1-task 측정 (저장소 내부 release
notes 기록). 측정 스크립트의 재현 정확성은 알려진 두 세션(turn 203 / 349)을 정확히
재산출하는지로 교차 검증했다.

### 한계 (반드시 같이 읽을 것)

- **표본 크기**: 절감 수치의 분자(Hybrid A)는 n=1, 분모(baseline)는 n=3. 통계적
  대표성이 아니라 *방향성*을 보여주는 일화(anecdote)에 가깝다.
- **단일 출처**: 모든 수치가 한 외부 활성 프로젝트에서 나왔다. dcNess 저장소 자체는
  `/init-dcness` 를 적용하지 않으므로 자기 run 은 대표성이 없다.
- **환경 의존**: turn 수는 작업 난이도 / 세션 분할 / 모델 버전에 따라 달라진다.
  위 수치는 절대 보장값이 아니라 같은 조건 재현 시 참고선이다.
- **측정 != 성공률**: 위 표는 turn 비용만 본다. PR 성공률 / blocked 비율 등은 아래 참조.

## 재현 3 — fleet 집계 (여러 run 가로질러)

위 두 도구가 run 1개를 보는 반면, [`harness/benchmark_aggregate.py`](../../harness/benchmark_aggregate.py)
는 한 프로젝트의 **모든 run 의 `ledger.jsonl` 을 가로질러** 집계한다 — PR 머지 성공률,
review rejection, escalate 수, blocked 수, waste top-N, 재발 기반 개선 후보.
`run_review.py` 의 검증된 waste 분류를 재사용한다. helper 기반 run 은 `end-run`
직후 recurrent WasteFinding 을 프로젝트-로컬 `.claude/loop-lessons/` 에도 반영하므로,
다음 같은 agent/mode `begin-step` 에서는 `[LESSONS]` 로 최근 lesson 이 주입된다.

```sh
# 활성 프로젝트 안에서 (sessions-root 자동 탐색) — $DCN 은 위 "스크립트 위치" 참조
python3 "$DCN"/harness/benchmark_aggregate.py

# 경로 명시 + impl run 만 + JSON
python3 "$DCN"/harness/benchmark_aggregate.py <repo>/.claude/harness-state/.sessions --entry-point impl
python3 "$DCN"/harness/benchmark_aggregate.py <sessions-root> --json

# 동일 waste pattern 이 2회 이상 반복되면 개선 후보로 표면화
python3 "$DCN"/harness/benchmark_aggregate.py --recurrence-threshold 2
```

재발 개선 후보의 기본 임계값은 3회다. 후보는 룰 추가, skill 박제, 기존 룰 제거 검토
중 하나를 사람이 결정하기 위한 표면화일 뿐이며, `CLAUDE.md`·룰·skill·문서를 자동
수정하지 않는다. GOOD 사례는 집계 대상이 아니다.

### multi-run 측정 recipe

1. 같은 프로젝트에서 `/impl` 또는 `/impl-loop` 로 여러 task 를 처리한다. PR 생성은
   `$PLUGIN_ROOT/scripts/pr-create.sh`, 머지는 `$PLUGIN_ROOT/scripts/pr-finalize.sh` 경로를 타야 `pr_created` /
   `pr_merged` ledger event 가 자동으로 남는다.
2. 각 run 을 정상 종료한 뒤 프로젝트별 fleet JSON 을 저장한다.

```sh
cd <activated-project>
python3 "$DCN"/harness/benchmark_aggregate.py \
  .claude/harness-state/.sessions \
  --entry-point impl \
  --json > /tmp/dcness-fleet-$(basename "$PWD").json
```

3. 여러 프로젝트를 비교할 때는 프로젝트별 JSON 을 분리 보관하고, 표에는 source count 를
   직접 적는다.

```sh
for repo in <project-a> <project-b>; do
  (
    cd "$repo"
    python3 "$DCN"/harness/benchmark_aggregate.py \
      .claude/harness-state/.sessions \
      --entry-point impl \
      --json > "/tmp/dcness-fleet-$(basename "$repo").json"
  )
done
```

4. publish 가능한 표는 다음 항목을 같이 적는다: `run_count`, `pr_created_count`,
   `pr_merge_success_ratio`, `pr_reviewer_rejection_count/review_count`,
   `blocked_event_count`, `escalate_count`, `waste_top`, `improvement_candidates`,
   source count, 한계.

여러 활성 프로젝트를 한 번에 같은 scorecard로 재현하려면 다음 명령을 쓴다. 현재 ledger에
없는 제품 AC/journey와 탐색 효과는 다른 process 지표로 채우지 않고 `측정 불가`로 출력한다.

```sh
python3 "$DCN"/harness/outcome_scorecard.py --redact-paths
python3 "$DCN"/harness/outcome_scorecard.py --redact-paths --json
```

시점 snapshot과 원천 registry 위치는 [`outcome-baseline.md`](../internal/outcome-baseline.md)에
보존한다.

### fleet 실측 (외부 활성 프로젝트 1곳)

아래는 한 외부 활성 프로젝트의 누적 run 을 위 집계기로 산출한 **측정 시점 스냅샷**이다
(run 이 계속 쌓이므로 재실행하면 값이 조금 다를 수 있다). `list_runs` 가
`run_finished` + 유효 receipt 를 가진 run 만 포함하므로(불완전 run 은 정직하게 제외)
표본 수는 실제 디스크상 run 보다 작을 수 있다.

| 지표 | 값 | 비고 |
|---|---|---|
| 총 run | 44 | impl 40 / design 3 / architect-loop 1 |
| impl-validator FAIL 비율 | 42.6% | PASS 35 / FAIL 29 / legacy LGTM 4 — 리뷰 게이트가 실제로 반려 |
| escalate 결론 | 2 | 주로 architecture-validator |
| blocked 이벤트 | 1 | |
| waste top | TOOL_REPEAT_HIGH 39 / MUST_FIX_LEAK 11 / MISSING_CONCLUSION_ENUM 2 | `/run-review` 가 잡는 낭비 패턴 |
| PR 머지 성공률 | 측정 불가 | legacy snapshot: `pr_created` denominator 없음 |

해석: impl-validator 의 ~42% FAIL 은 "리뷰가 형식적으로 통과만 시키지 않고 실제로
반려한다"는 뜻이다 — 가드가 동작한다는 신호. waste top 은 어디를 개선하면 비용이
주는지 가리킨다.

**한계**:
- 출처가 한 프로젝트(단일 출처)이고, run 마다 작업 성격이 달라 비율은 절대 기준이
  아니라 그 프로젝트의 경향이다.
- 위 결론 분포 / FAIL 비율 / escalate / blocked / waste top 은 `ledger.jsonl` +
  `agent-trace.jsonl`(run 디렉토리 안)만으로 산출되어 정확하다. 반면 **비용**과
  invocation 의존 waste(`END_STEP_SKIP`)는 세션 JSONL 이 *실행 cwd* 로 키잉되는데
  worktree run 은 ledger 가 main repo 아래 있어 자동 유추가 빗나간다 — 이 두 지표가
  필요하면 `--repo <cwd>` 로 보정한다. 자동 복구(begin-run cwd 기록)는
  [`#766`](https://github.com/alruminum/dcNess/issues/766) 잔여.

### PR 머지 성공률 해석

신규 run 은 `pr-create.sh` 성공 시 `pr_created`, `pr-finalize.sh` 가 merge 완료를
확인한 뒤 `pr_merged` 를 기록한다. 집계기는 `pr_created` 를 denominator 로 삼고,
같은 PR 의 `pr_merged` 가 있을 때만 성공으로 센다.

기존 run 처럼 `pr_created` 가 없으면 PR 성공률은 측정 불가다. `pr_merged` 만 남은
수동/legacy event 는 orphan 으로 표시하고 성공률 분자에 넣지 않는다.

## 재현 4 — design run 영속 기록

`/design` run 은 각 stage PR 생성 전에 실행하는 `end-run` 시점에
`docs/metrics/design-runs.jsonl` 에도 compact record 를 남긴다. `design-ux` 와
`design-system` 은 같은 `entry_point=design` 아래 `stage` 값으로 구분하므로, 기존
단일 run 수치와 stage별 run 수치를 나란히 비교할 수 있다. 이 파일은
git-tracked design 산출물이므로 design worktree 의 같은 PR 에 포함되어야 한다.
`.claude/harness-state` TTL 정리나 Claude transcript 삭제 뒤에도 후속 세션이 읽을 수
있다. run-local prose/ledger 가 원본이고, 이 파일은 baseline 비교용 인덱스다.

```sh
"$PLUGIN_ROOT/scripts/dcness-helper" design-records
"$PLUGIN_ROOT/scripts/dcness-helper" design-records --json --limit 5
```

record v1 필드: `run_id`, `started_at`, `finished_at`, `duration_s`, `step_count`,
`final_verdict`, `clean`, `finding_classes`, `revalidation_cycles`, `units[]`,
`total_input_tokens`, `total_output_tokens`, `total_cost_usd`. `finding_classes` 는
FAIL/ESCALATE prose 안의 class token 언급 수라 finding 건수의 근사치다.
`units[].revalidation_cycle` 은 현 schema 에서 `units[].cycle` alias 로 남긴다.
토큰/비용은 세션 JSONL 매칭이 가능할 때만 채워지고, 불가능하면 0으로 남는다.

## 언제 유리하고 언제 과한가

route 별 권장은 README "[누구에게 맞나](../../README.md#누구에게-맞나)"
섹션이 요약본이고, 구현 경로 판정의 진본은
[`docs/plugin/workflow-router.md`](workflow-router.md) 다.

- **유리** — `test -> implement -> review -> PR` 순서와 agent 파일 경계를 반복적으로
  지켜야 하는 실제 제품 작업. 같은 run 을 사후에 다시 분석(replayability)하고 낭비를
  잡아 절차를 개선하려는 경우.
- **과함** — 한 줄 수정, 일회성 스크립팅, 탐색적 prototype. 이 경우 무거운 설계
  절차는 부르지 않는 것이 기본 설계(가벼운 기본 경로 + risk 높을 때만 절차 상승)와도
  맞는다.
