# 과거 blind eval 2건의 자동 채점 보정 — 사람 확인 문서

## 결론부터

이 문서는 **현재 모델을 새로 실행한 결과를 승인하는 문서가 아니다.**

2026-07-05에 Sonnet으로 실행했던 행동 eval 2건의 보고서를 고정해 두고,
그 보고서를 당시 자동 judge가 올바르게 채점했는지 사람이 사후 확인하는 문서다.
이 작업을 하는 GitHub 이슈는 #1068이며, 목적은 다음 두 실패를 구분하는 것이다.

- 검수 agent가 실제로 중요한 문제를 놓친 경우: **agent 행동 회귀**
- 검수 agent는 제대로 보고했지만 자동 judge가 잘못 채점한 경우: **judge 또는 판정 기준 불일치**

현재 상태는 `verified`다. 저장소 소유자가 2026-07-12에 아래의 자료 출처를 v1 보정
기준으로 인정하고 E1, E2, HPQ-1~5를 모두 `OK`로 확인했다.

## #1068이 고치려는 문제

dcNess 행동 eval 한 번에는 LLM 판단이 두 번 들어간다.

1. 검수 agent가 fixture를 읽고 검수 보고서인 `run-N-report.md`를 작성한다.
2. 별도 judge가 그 보고서와 케이스 정답표를 비교해 `run-N-judge.md`를 작성한다.

기존에는 두 번째 단계의 judge 결과를 사실상 정답처럼 사용했다. 그래서 eval 결과가
달라졌을 때 검수 agent가 사고를 놓친 것인지, judge가 멀쩡한 보고서를 잘못 채점한
것인지 구분할 수 없었다.

#1068은 이 문제를 다음과 같이 수정한다.

- 실제 사고 방지 가치가 높은 핵심 케이스 2건을 릴리즈 기본 subset으로 고정한다.
- 자동 judge와 독립된, 버전이 있는 사람 기준 정답(golden)을 만든다.
- 사람 정답과 judge 판정을 expectation별로 비교한다.
- 결과를 `agent_behavior_regression`, `judge_or_criteria_disagreement`, `판정 불가`로
  분리한다.
- 사람 확인 전 golden, 버전이 다른 golden, 보고서 SHA-256이 다른 golden은
  calibration PASS로 인정하지 않는다.
- calibration 결과만으로 model, prompt, 강제 규칙을 자동 변경하지 않는다.

이 이슈는 제품 앱의 사용자 journey를 실행하거나 현재 모델의 품질을 통계적으로
입증하는 이슈가 아니다. 그것은 #1067 및 후속 반복 측정의 범위다.

## 이 보고서는 정상 흐름에서 언제 만들어지는가

행동 eval은 `agents/**` 또는 `skills/**` 지침을 바꾼 PR의 머지 전이나 플러그인
릴리즈 전에 사람이 필요하다고 판단할 때 실행하는 권고 QA다. CI 필수 게이트는 아니다.

핵심 subset을 새로 실행할 때는 다음 명령을 사용한다.

```sh
bash evals/run-core.sh
```

실행 흐름은 다음과 같다.

1. `run-core.sh`가 [`core-incident-subset.json`](../../core-incident-subset.json)에서
   `shorts-real-spec`과 `headless-prose-quality`를 선택한다.
2. `run.sh`가 현재 `docs/`, `skills/`, `agents/`만 임시 instruction snapshot으로
   복사한다.
3. 검수 agent에는 fixture와 검수 prompt만 보여준다. `expected.md`, 사람 golden,
   과거 calibration 결과는 보여주지 않는다. 이 단계가 blind report 생성이다.
4. 검수 agent 출력이 `.metrics/evals/run-.../<case>/run-N-report.md`에 저장된다.
5. 그 뒤 별도 judge가 방금 생성된 report와 `expected.md`를 받아 expectation별
   `OK`/`MISS`를 판정하고 `run-N-judge.md`에 저장한다.
6. 사람 golden이 있으면 `calibrate_judge.py`가 사람 판정과 judge 판정을 비교한다.

즉 `run-N-report.md`는 제품 실행 로그가 아니라 **고정된 입력을 읽은 검수 agent의
판단 보고서**다. `run-N-judge.md`는 그 보고서에 대한 **자동 채점 결과**다.

## 이번 확인 자료는 언제, 어떤 데이터로 만들었는가

이번 사람이 확인할 자료는 #1068 작업 중 새로 생성한 report가 아니다.

- 원 실행 시각: 2026-07-05 08:02:04Z~08:06:51Z
- model: `sonnet`
- prompt 조건: `release-0.12.0-eval-fixture-snapshot`
- 원 실행 위치로 기록된 경로: `.metrics/evals/release-0.12.0`
- 선택한 attempt: 두 케이스의 `run 1`, 총 2회
- #1068 브랜치에 복사·고정한 시점: 2026-07-12

원 실행 디렉터리 `.metrics/evals/release-0.12.0`은 local metrics 경로였으며 현재 이
작업트리에는 남아 있지 않다. 현재 추적되는 증거는 이 디렉터리에 복사한 report와 judge,
실행 조건 메타데이터, report SHA-256이다. report 내용이 바뀌면 golden의 SHA-256과
불일치하므로 기존 사람 판정을 재사용할 수 없다.

따라서 사용자는 내용 판정 전에 먼저 다음을 결정해야 했다.

> **자료 출처 결정:** 원 실행 디렉터리 자체는 현재 없지만, 커밋된 report/judge 복사본,
> 실행 조건 메타데이터와 SHA-256 결합을 이번 calibration 기준 자료로 인정할 것인가?

이번 v1에서는 저장소 소유자가 이 자료를 기준으로 인정했다. 인정하지 않았다면 golden을
승인하지 않고 원 실행 자료를 다시 찾거나, 나중에
`bash evals/run-core.sh`로 새 blind report를 만든 뒤 그 실행을 기준으로 다시 사람
판정을 해야 한다.

## 확인 자료 1 — 실제 backlog에서 파생한 spec 검수 fixture

### 데이터의 성격

`shorts-real-spec`은 실제 앱을 실행한 결과가 아니다. youTubeGenerator의 세로 쇼츠
Epic에서 사용했던 PRD와 stories를 fixture로 보존하고, dcNess의 product-acceptance
agent가 설계·구현 전 spec 검수를 수행하도록 한 시뮬레이션이다.

여기서 `stories.md`는 architecture-validator의 설계 결과물이 아니라 과거 `/spec`
단계에서 만들어진 Story 분할 결과물이다. 당시 지침은 이 backlog를 통과시켰고,
완성 쇼츠의 첫 end-to-end 검증이 뒤 Story까지 밀린 상태로 다음 단계에 들어가 실제
런타임 gap으로 이어졌다.

2026-07-05의 eval은 **똑같은 과거 PRD와 stories를 release-0.12.0 시점의 새 검수
지침에 다시 제시**했다. 저장된 report는 이번에는 순서 결함을 지적하고 `FAIL`로
막았다. 따라서 이 한 번의 저장 결과가 보여주는 것은 다음과 같다.

- 과거에 통과됐던 문제 입력을 2026-07-05 시점의 product-acceptance 검수는 잡았다.
- 같은 입력이 검수 경계를 다시 통과하지 않도록 하는 회귀 방어가 한 attempt에서
  동작했다.

반대로 이 결과만으로 다음을 주장할 수는 없다.

- 현재 `/spec` agent가 처음부터 같은 형태의 잘못된 stories를 만들지 않는다.
- 2026-07-05 이후 변경된 현재 main에서도 항상 같은 판정이 나온다.
- 한 번의 성공으로 모든 유사 Story 순서 결함을 막는다고 일반화할 수 있다.

즉 이 케이스는 **잘못된 Story 생성 방지 테스트가 아니라, 과거의 잘못된 Story가
들어왔을 때 검수 단계에서 탐지·차단하는 회귀 테스트**다. 현재 지침 재현은 별도의
새 `run-core.sh` 실행으로 확인해야 한다.

- 실제 사고 연결: youTubeGenerator #214에서 완성 쇼츠의 첫 end-to-end 검증이 뒤
  Story까지 밀려 런타임 gap이 발생했다.
- 입력 데이터: [`prd.md`](../../cases/shorts-real-spec/prd.md),
  [`stories.md`](../../cases/shorts-real-spec/stories.md)
- 검수 agent에 준 요청: [`prompt.md`](../../cases/shorts-real-spec/prompt.md)
- 사람이 판단할 계약 기준: [`expected.md`](../../cases/shorts-real-spec/expected.md)
- 과거 검수 agent 출력: [`run-1-report.md`](shorts-real-spec/run-1-report.md)
- 과거 자동 judge 출력: [`run-1-judge.md`](shorts-real-spec/run-1-judge.md)

이 케이스는 실제 backlog의 모든 결함을 평가하려는 것이 아니다. 실제 사고와 직접
연결된 **완성 쇼츠의 첫 end-to-end 검증 순서**만 핵심 회귀 신호로 본다.

### 사람이 판정할 내용

자동 judge 파일을 정답 근거로 삼지 말고 `run-1-report.md` 자체를 기준으로 판단한다.

- **E1:** report가 완성 쇼츠의 첫 end-to-end 검증이 Story 4까지 밀린 순서 결함을
  실제로 지적했는가?
- **E2:** report의 최종 결론이 비통과인 `FAIL`인가?

현재 golden 초안은 E1과 E2를 모두 `OK`로 제안한다. 이유는 report의 `Gap 3`이 해당
순서 결함을 직접 지적하고 마지막 결론이 `FAIL`이기 때문이다. 사용자는 이 근거가
report 원문과 일치하는지만 확인한다. report에 함께 적힌 다른 gap이 올바른지는 이번
두 라벨의 판정 대상이 아니다.

## 확인 자료 2 — 합성 headless 보고서 품질 fixture

### 데이터의 성격

`headless-prose-quality`는 실제 프로젝트 실행 자료가 아니라 세 개의 짧은 보고서 예시를
만든 합성 fixture다. 목적은 오케스트레이터가 다음 분기를 결정할 증거가 있는 보고서와
없는 보고서를 검수 agent가 구분하는지 확인하는 것이다.

- 입력 데이터: [`worker-good.md`](../../cases/headless-prose-quality/worker-good.md),
  [`worker-bad.md`](../../cases/headless-prose-quality/worker-bad.md),
  [`validator-bad.md`](../../cases/headless-prose-quality/validator-bad.md)
- 검수 agent에 준 요청: [`prompt.md`](../../cases/headless-prose-quality/prompt.md)
- 사람이 판단할 계약 기준: [`expected.md`](../../cases/headless-prose-quality/expected.md)
- 과거 검수 agent 출력: [`run-1-report.md`](headless-prose-quality/run-1-report.md)
- 과거 자동 judge 출력: [`run-1-judge.md`](headless-prose-quality/run-1-judge.md)

### 사람이 판정할 내용

자동 judge 파일을 정답 근거로 삼지 말고 `run-1-report.md` 자체를 기준으로 판단한다.

- **HPQ-1:** `worker-bad`의 변경 파일, 테스트, provider/fallback, 남은 위험 등
  핵심 증거 부족을 지적했는가?
- **HPQ-2:** `validator-bad`의 검증 대상·근거와 최종 결론 부족을 지적했는가?
- **HPQ-3:** `worker-good`을 자유 prose라는 이유로 거부하지 않았는가?
- **HPQ-4:** raw headless log는 파일로 보존하고 메인 대화에는 경로만 남기는 방침을
  설명했는가?
- **HPQ-5:** status JSON, marker, 고정 표 또는 고정 schema를 해결책으로 요구하지
  않았는가?

현재 golden 초안은 HPQ-1~5를 모두 `OK`로 제안한다. 과거 report가 각 항목을 실제로
말하고 있는지 사용자가 확인한다. 좋은 보고서의 문체 취향이나 더 나은 작성 방식은
이번 판정 대상이 아니다.

## 사용자가 최종적으로 결정한 것

사용자가 승인한 대상은 **현재 Sonnet의 전반적 품질, dcNess 전체 eval 하네스,
youTubeGenerator 제품 결과가 아니다.** 다음 두 가지만 결정했다.

1. 원 실행 디렉터리가 현재 없는 과거 report/judge 복사본을 이번 v1 calibration의
   기준 자료로 인정했다.
2. 고정된 report 두 건에 대한 E1, E2, HPQ-1~5 사람 판정을 모두 `OK`로 확정했다.

확정된 승인 내용은 다음과 같다.

`#1068: 과거 실행 복사본을 v1 보정 기준으로 인정. E1, E2, HPQ-1~5 모두 OK.`

향후 다른 소유자가 동의하지 않는 항목을 발견하면 라벨과 report 원문의 근거를 적어
golden을 다시 검토한다.

`HPQ-4는 MISS — report가 raw log를 파일에 보존하라고 명확히 요구하지 않았다.`

자료 출처 승인을 철회한다면 다음처럼 기록하고 golden을 `pending_owner_confirmation`으로
되돌린다.

`#1068: 원 실행 디렉터리가 없는 복사본은 v1 보정 기준으로 승인하지 않음.`

## 결정 후 무엇이 일어나는가

- 자료 출처 승인과 사람 라벨 확정에 따라 golden의 `verification_status`를
  `verified`로 기록했다.
- 아래 비LLM 명령으로 사람 판정과 저장된 자동 judge 판정을 비교한다.
- 기대 라벨 7개와 report 최종 결과 2개를 합쳐 총 9개 비교로 집계한다.
- 사람이 report 자체를 `MISS`로 판정한 항목은 agent 행동 회귀로 기록한다.
- 사람과 judge가 다르게 판정한 항목은 judge 또는 판정 기준 불일치로 기록한다.
- report, judge, version 또는 SHA-256이 맞지 않으면 판정 불가로 처리한다.
- 어느 결과도 model, prompt 또는 하네스 강제 규칙을 자동 변경하지 않는다.

```sh
python3 evals/calibrate_judge.py \
  evals/calibration/core-incidents-v1 \
  --golden evals/golden/core-incidents-v1.json \
  --expect-golden-version core-incidents-v1-human-v1 \
  --expect-subset-version core-incidents-v1
```
