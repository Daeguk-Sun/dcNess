# 핵심 eval 2건 — 사람 확인용 요약

## 무엇을 확인하는 문서인가

AI가 작성한 두 검수 report를 자동 채점기가 제대로 채점했는지 사람이 한 번 확인한다.

복잡한 기술 설정을 판단할 필요는 없다. 아래의 **확인 질문 7개**에 동의하는지만 보면 된다.

> 현재 상태: `pending_owner_confirmation`
>
> 사람이 확인하기 전에는 golden을 `verified`로 바꾸거나 calibration PASS로 처리하지 않는다.

## 결론부터 보기

현재 후보 판정은 다음과 같다.

- 쇼츠 작업 순서 report: 확인 질문 2개 모두 **예**
- 작업 report 품질 report: 확인 질문 5개 모두 **예**
- 따라서 사람 판정 후보는 E1, E2, HPQ-1~5 모두 `OK`다.

아래 설명을 읽고 같은 판단이면 마지막의 승인 문구만 답하면 된다.

## Report 1 — 완성 쇼츠 검증이 너무 늦게 나오는가

### 원래 문제

작업 계획이 여러 Story로 나뉘어 있는데, 사용자가 완성된 세로 쇼츠를 처음 확인할 수 있는 시점이 Story 4까지 밀려 있다. 검수 report는 이 순서 문제를 찾아야 한다.

### report가 실제로 한 말

report는 다음 두 가지를 분명히 말했다.

1. 완성 쇼츠의 첫 end-to-end 검증이 Story 4까지 밀린 것은 순서상 문제다.
2. 이 상태로는 설계·구현에 들어가면 안 되므로 최종 결론은 `FAIL`이다.

### 사람이 확인할 질문

- **E1:** report가 “완성 쇼츠의 첫 검증이 Story 4까지 밀렸다”는 문제를 실제로 지적했는가? → 후보 답: **예 (`OK`)**
- **E2:** report의 최종 결론이 `FAIL`인가? → 후보 답: **예 (`OK`)**

원문을 확인하고 싶을 때만 아래 파일을 연다.

- [AI 검수 원문](shorts-real-spec/run-1-report.md)
- [자동 채점 결과](shorts-real-spec/run-1-judge.md)

## Report 2 — 좋은 작업 보고와 나쁜 작업 보고를 구분하는가

### 원래 문제

세 개의 짧은 작업 보고를 비교한다.

- `worker-good`: 무엇을 바꿨고 어떻게 검증했는지 충분히 설명한 좋은 보고
- `worker-bad`: “끝났다, 될 것이다” 정도만 쓴 불충분한 보고
- `validator-bad`: 무엇을 검증했는지와 최종 결론이 없는 불충분한 검수 보고

검수 report는 나쁜 보고의 부족한 점을 잡되, 좋은 보고를 형식 때문에 거부하면 안 된다.

### report가 실제로 한 말

- `worker-bad`에는 변경 파일, 실행한 테스트, 사용한 provider, 남은 문제가 없다.
- `validator-bad`에는 검증 대상과 근거, `PASS`/`FAIL`/`ESCALATE` 결론이 없다.
- `worker-good`은 자유로운 prose 형식이어도 다음 판단에 필요한 정보가 있으므로 충분하다.
- 긴 raw log는 파일에 보존하고, 메인 대화에는 파일 경로만 남기는 편이 낫다.
- status JSON, marker, 고정 표나 고정 schema 같은 형식을 요구하지 않는다.

### 사람이 확인할 질문

- **HPQ-1:** `worker-bad`의 핵심 증거 부족을 지적했는가? → 후보 답: **예 (`OK`)**
- **HPQ-2:** `validator-bad`의 검증 대상·근거·결론 부족을 지적했는가? → 후보 답: **예 (`OK`)**
- **HPQ-3:** `worker-good`을 자유 prose라는 이유로 거부하지 않았는가? → 후보 답: **예 (`OK`)**
- **HPQ-4:** raw log는 파일로 보존하고 메인 대화에는 경로만 남기라고 설명했는가? → 후보 답: **예 (`OK`)**
- **HPQ-5:** status JSON, marker, 고정 표/schema를 요구하지 않았는가? → 후보 답: **예 (`OK`)**

원문을 확인하고 싶을 때만 아래 파일을 연다.

- [AI 검수 원문](headless-prose-quality/run-1-report.md)
- [자동 채점 결과](headless-prose-quality/run-1-judge.md)

## 사람이 답하는 방법

위 7개 후보 판단에 모두 동의하면 다음처럼 답한다.

`#1068 golden 전부 승인`

하나라도 동의하지 않으면 라벨과 이유만 적는다. 예: `HPQ-4는 MISS — report가 파일 보존을 명확히 요구하지 않음`.

## 왜 원본 report를 쉽게 다시 쓰지 않는가

원본 report는 당시 AI가 실제로 낸 답이며 SHA-256으로 golden에 결합돼 있다. 원문을 고치면 “당시 자동 채점이 맞았는가”를 검증할 수 없게 된다. 그래서 원본은 보존하고 이 문서에서 쉬운 말로 번역한다.

## 기술 참고 — 확인할 필요 없음

- source run: `.metrics/evals/release-0.12.0`
- model: `sonnet`
- prompt 조건: `release-0.12.0-eval-fixture-snapshot`
- 원천 telemetry 시각: 2026-07-05 08:02:04Z~08:06:51Z
- 선택 attempt: 케이스별 run 1, 총 2회
- subset: [`core-incidents-v1`](../../core-incident-subset.json)
- golden: [`core-incidents-v1.json`](../../golden/core-incidents-v1.json)

확인 질문은 7개지만 calibration 집계는 각 report의 최종 결과 비교 2개도 포함해 총 9개 비교로 표시한다. 전부 일치하면 사람 golden과 judge가 9/9 일치한다.

승인 후 재현 명령:

```sh
python3 evals/calibrate_judge.py \
  evals/calibration/core-incidents-v1 \
  --golden evals/golden/core-incidents-v1.json \
  --expect-golden-version core-incidents-v1-human-v1 \
  --expect-subset-version core-incidents-v1
```

불일치가 생기면 자동 채점 기준 불일치, AI 행동 회귀, artifact/version/digest 불일치를 구분해서 보고하며 model·prompt·강제 규칙을 자동 변경하지 않는다.
