# dcNess benchmark — 측정 재현 가이드 + 실측 샘플

> 이 문서는 "화려한 성능 자랑" 이 아니다. dcNess 가 실제로 어디서 비용을 줄이는지,
> 그 수치를 **누구나 자기 프로젝트에서 직접 재현**할 수 있게 하는 것이 목적이다.
> 공개된 표본은 작고(아래 한계 참조), 일부 정량 지표(PR 머지 성공률)는 아직 측정
> 불가다([`#766`](https://github.com/alruminum/dcNess/issues/766) 참조). 과장 없이 있는 그대로 적는다.

## 무엇을 측정하나

dcNess 는 측정 인프라를 plug-in 본체에 같이 배포한다.

| 측정 도구 | 무엇을 보나 | 진입점 |
|---|---|---|
| [`scripts/measure_main_turns.py`](../../scripts/measure_main_turns.py) | Claude Code 세션의 메인 assistant turn 분포 (tool / text-only / thinking-only) + tool histogram + sub-agent 호출 분포 | 직접 실행 |
| [`harness/run_review.py`](../../harness/run_review.py) | run 1개의 step별 비용·토큰 + 낭비(waste) finding | `/run-review` skill |
| [`harness/benchmark_aggregate.py`](../../harness/benchmark_aggregate.py) | 여러 run 가로질러 fleet 집계 (FAIL 비율 / escalate / blocked / waste top-N) | 직접 실행 |

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
placeholder 누수 등) finding, 수정 제안을 리포트로 출력한다. 실 구현은
[`harness/run_review.py`](../../harness/run_review.py) 다.

## 실측 샘플 (turn 절감)

아래는 현재 공개 가능한 **단일 표본**이다. 표본이 작다는 점을 먼저 밝힌다.

| 지표 | 값 | 비고 |
|---|---|---|
| baseline (옛 4-agent 모델) | ~280 turn/task | 외부 활성 프로젝트 impl 1-task 세션 3개 평균 (n=3) |
| Hybrid A (build-worker 2-step) | 121 turn/task | impl 1-task 측정 (n=1) |
| 절감 | ~57% | 121 / 280 기준 |

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
는 한 프로젝트의 **모든 run 의 `ledger.jsonl` 을 가로질러** 집계한다 — pr-reviewer
FAIL 비율 / escalate 수 / blocked 수 / waste top-N. `run_review.py` 의 검증된 파서를
재사용한다.

```sh
# 활성 프로젝트 안에서 (sessions-root 자동 탐색) — $DCN 은 위 "스크립트 위치" 참조
python3 "$DCN"/harness/benchmark_aggregate.py

# 경로 명시 + impl run 만 + JSON
python3 "$DCN"/harness/benchmark_aggregate.py <repo>/.claude/harness-state/.sessions --entry-point impl
python3 "$DCN"/harness/benchmark_aggregate.py <sessions-root> --json
```

### fleet 실측 (외부 활성 프로젝트 1곳)

아래는 한 외부 활성 프로젝트의 누적 run 을 위 집계기로 산출한 **측정 시점 스냅샷**이다
(run 이 계속 쌓이므로 재실행하면 값이 조금 다를 수 있다). `list_runs` 가
`run_finished` + 유효 receipt 를 가진 run 만 포함하므로(불완전 run 은 정직하게 제외)
표본 수는 실제 디스크상 run 보다 작을 수 있다.

| 지표 | 값 | 비고 |
|---|---|---|
| 총 run | 44 | impl 40 / design 3 / architect-loop 1 |
| pr-reviewer FAIL 비율 | 42.6% | PASS 35 / FAIL 29 / LGTM 4 — 리뷰 게이트가 실제로 반려 |
| escalate 결론 | 2 | 주로 architecture-validator |
| blocked 이벤트 | 1 | |
| waste top | TOOL_REPEAT_HIGH 39 / MUST_FIX_LEAK 11 / MISSING_CONCLUSION_ENUM 2 | `/run-review` 가 잡는 낭비 패턴 |

해석: pr-reviewer 의 ~42% FAIL 은 "리뷰가 형식적으로 통과만 시키지 않고 실제로
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

### 아직 측정 불가 — PR 머지 성공률 (#766 작업②)

PR 생성/머지까지의 **성공률**은 ledger 의 `pr_merged` 이벤트가 *선택 기록* 이라
대부분 비어 있어 산출하지 못한다. 집계기도 이 지표는 "측정 불가"로 출력한다.
GitHub PR 에서 파생하거나 이벤트 계측을 보강하는 작업은
[`#766`](https://github.com/alruminum/dcNess/issues/766) 에 남아 있다. **synthetic
추정값으로 빈칸을 채우지 않는다** — 정직한 빈칸이 가짜 숫자보다 낫다.

## 언제 유리하고 언제 과한가

route 별 권장은 README "[언제 유리하고 언제 과한가](../../README.md#언제-유리하고-언제-과한가)"
섹션이 요약본이고, 구현 경로 판정의 진본은
[`docs/plugin/workflow-router.md`](workflow-router.md) 다.

- **유리** — `test -> implement -> review -> PR` 순서와 agent 파일 경계를 반복적으로
  지켜야 하는 실제 제품 작업. 같은 run 을 사후에 다시 분석(replayability)하고 낭비를
  잡아 절차를 개선하려는 경우.
- **과함** — 한 줄 수정, 일회성 스크립팅, 탐색적 prototype. 이 경우 무거운 설계
  절차는 부르지 않는 것이 기본 설계(가벼운 기본 경로 + risk 높을 때만 절차 상승)와도
  맞는다.
