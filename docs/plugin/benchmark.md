# dcNess benchmark — 측정 재현 가이드 + 실측 샘플

> 이 문서는 "화려한 성능 자랑" 이 아니다. dcNess 가 실제로 어디서 비용을 줄이는지,
> 그 수치를 **누구나 자기 프로젝트에서 직접 재현**할 수 있게 하는 것이 목적이다.
> 공개된 표본은 작고(아래 한계 참조), 일부 정량 지표는 아직 집계 전이다
> ([수집 예정](#수집-예정-766) 참조). 과장 없이 있는 그대로 적는다.

## 무엇을 측정하나

dcNess 는 측정 인프라를 plug-in 본체에 같이 배포한다.

| 측정 도구 | 무엇을 보나 | 진입점 |
|---|---|---|
| [`scripts/measure_main_turns.py`](../../scripts/measure_main_turns.py) | Claude Code 세션의 메인 assistant turn 분포 (tool / text-only / thinking-only) + tool histogram + sub-agent 호출 분포 | 직접 실행 |
| [`harness/run_review.py`](../../harness/run_review.py) | run 1개의 step별 비용·토큰 + 잘한 점/낭비(waste) finding | `/run-review` skill |

핵심 가설은 단순하다. dcNess 의 무거운 절차(검증·구현·리뷰 시퀀스)를 sub-agent 가
흡수하면 **메인 Claude 의 turn 누적이 줄어든다**. 그게 사실인지 숫자로 본다.

## 재현 1 — 메인 turn 측정

세션 JSONL 은 Claude Code 가 `~/.claude/projects/<project-id>/<session-id>.jsonl`
에 자동 기록한다. 그 파일을 그대로 넣는다.

```sh
# 세션 1개 측정 (텍스트 리포트)
python3 scripts/measure_main_turns.py ~/.claude/projects/<project-id>/<session-id>.jsonl

# JSON 출력 (집계·비교용)
python3 scripts/measure_main_turns.py <jsonl-path> --json

# 디렉토리 일괄 (해당 프로젝트의 모든 세션)
python3 scripts/measure_main_turns.py ~/.claude/projects/<project-id>/
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

## 수집 예정 (#766)

다음 정량 지표는 체계적 데이터셋이 아직 없어 공개하지 않는다. cross-run 집계기 +
의미 있는 외부 표본이 쌓인 뒤 [`#766`](https://github.com/alruminum/dcNess/issues/766)
에서 채운다.

- PR 생성/머지까지 성공률
- blocked / escalate 비율
- pr-reviewer FAIL 비율 (build-worker lint 도입 전후 차이)
- run-review waste finding top N 집계

원자 데이터(step별 enum)는 이미 `ledger.jsonl` 에 자동 기록되지만, 여러 run 을
가로질러 집계하는 도구와 충분한 표본이 트리거 조건이다. **synthetic 추정값으로
빈칸을 채우지 않는다** — 정직한 빈칸이 가짜 숫자보다 낫다.

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
