# Core incident calibration candidate v1

> 상태: `pending_owner_confirmation`. 아래 사람 판정을 소유자가 확인하기 전에는 [`core-incidents-v1.json`](../../golden/core-incidents-v1.json)의 `verification_status`를 `verified`로 바꾸지 않으며 calibration PASS를 허용하지 않는다.

## 원천 조건

- source run: `.metrics/evals/release-0.12.0`
- model: `sonnet`
- prompt 조건: `release-0.12.0-eval-fixture-snapshot`
- 원천 telemetry 시각: 2026-07-05 08:02:04Z~08:06:51Z
- 선택 attempt: 케이스별 run 1, 총 2회
- subset: [`core-incidents-v1`](../../core-incident-subset.json)

저장 report는 blind 검수 산출물이고 judge 파일은 그 뒤 별도 채점한 결과다. versioned human golden은 report SHA256에 결합되므로 report가 달라지면 `판정 불가`다.

## 소유자 확인 대상

### `shorts-real-spec`

- [run-1-report.md](shorts-real-spec/run-1-report.md)를 먼저 읽는다.
- E1 `OK` 후보: 보고가 완성 세로 쇼츠의 첫 end-to-end 검증이 Story 4까지 밀린 순서 결함을 명시한다.
- E2 `OK` 후보: 보고의 최종 결론이 `FAIL`이다.
- 그 뒤 [run-1-judge.md](shorts-real-spec/run-1-judge.md)가 위 사람 판정과 같은지 비교한다.

### `headless-prose-quality`

- [run-1-report.md](headless-prose-quality/run-1-report.md)를 먼저 읽는다.
- HPQ-1 `OK` 후보: `worker-bad`의 변경 파일·테스트·provider·미해결 gap 근거 부재를 지적한다.
- HPQ-2 `OK` 후보: `validator-bad`의 결론 enum과 검증 대상·근거 부재를 지적한다.
- HPQ-3 `OK` 후보: 자유 prose라는 이유로 `worker-good`을 거부하지 않는다.
- HPQ-4 `OK` 후보: raw log는 파일로 보존하고 메인 context에는 경로만 남기라고 설명한다.
- HPQ-5 `OK` 후보: status JSON, marker, fixed table/schema를 요구하지 않는다.
- 그 뒤 [run-1-judge.md](headless-prose-quality/run-1-judge.md)가 위 사람 판정과 같은지 비교한다.

## 확인 후 재현

소유자가 위 라벨과 이유를 확인해 golden 상태가 `verified`가 된 뒤 실행한다.

```sh
python3 evals/calibrate_judge.py \
  evals/calibration/core-incidents-v1 \
  --golden evals/golden/core-incidents-v1.json \
  --expect-golden-version core-incidents-v1-human-v1 \
  --expect-subset-version core-incidents-v1
```

예상 집계는 attempt 2, 비교 9, 사람 golden과 judge 9/9 일치다. 불일치가 생기면 `judge_or_criteria_disagreement`, 사람이 report 자체를 `MISS`로 판정하면 `agent_behavior_regression`, artifact/version/digest가 없거나 다르면 `판정 불가`로 분리한다. 이 결과는 model·prompt·강제 규칙을 자동 변경하지 않는다.
