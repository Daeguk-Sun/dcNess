# 자기개선 루프

> dcNess self 운영용 SSOT. 이 문서는 측정 신호를 하네스 개선으로 닫는 절차를 정의한다.
> 외부 활성 프로젝트용 규격이 아니므로 `docs/plugin/`으로 배포하지 않는다.

## 원칙

자기개선 루프는 코드 강제 게이트가 아니다. dcNess가 측정 도구를 늘릴수록 그 측정을
소비하는 사람이 한 바퀴를 돌 수 있도록, 문서 SSOT와 릴리즈 리듬만 제공한다.

루프는 항상 사람 판단을 통과한다. 측정값은 후보를 표면화하고, 룰·skill·hook·CI의 추가,
제거, 축약, 보류 결정은 사람이 한다. 자동 룰 박제와 자동 제거는 범위 밖이다.

## 루프 슬롯

| 슬롯 | 질문 | 현재 담당 |
|---|---|---|
| Sense | 어떤 신호를 보나 | `/run-review`, benchmark/fleet 집계, `evals/guard_efficacy.py`, `evals/run.sh`, 가드 발화 텔레메트리 후보 [#875](https://github.com/alruminum/dcNess/issues/875), 재발·낭비 집계 후보 [#876](https://github.com/alruminum/dcNess/issues/876), judge 보정 후보 [#894](https://github.com/alruminum/dcNess/issues/894) |
| Diagnose | 여러 신호를 어떻게 우선순위화하나 | 릴리즈 점검 [#878](https://github.com/alruminum/dcNess/issues/878)이 겸한다. 릴리즈 후보에서 Sense 신호를 한 자리에서 모아 blocker, release-note follow-up, 별도 issue로 나눈다. |
| Decide | 무엇을 바꾸나 | 추가 전 제거 검토를 먼저 한다. 새 룰·hook·CI를 추가하기 전에 기존 룰 삭제, 문구 축약, SSOT 파생 생성으로 같은 효과를 낼 수 있는지 확인한다. 첫 사례는 개수 하드코딩 제거 [#877](https://github.com/alruminum/dcNess/issues/877)이다. |
| Act | 실제 변경은 어디서 하나 | 일반 dcNess 변경 절차대로 branch → PR → merge를 탄다. PR 본문에 Sense 근거, Diagnose 판단, Decide 이유, Verify 계획을 짧게 적는다. |
| Verify | 개선이 먹혔는지 어떻게 보나 | 변경 성격별로 결정적 eval, 행동 eval, 다음 Sense 주기 재측정을 분리한다. |

## 트리거 리듬

릴리즈마다 한 번 돈다. [`plugin-release.md`](plugin-release.md)의 릴리즈 전 점검에서
Sense 산출물을 모으고, Diagnose/Decide 결과를 릴리즈 노트 또는 후속 이슈에 남긴다.

평소 run 중 발견한 단발 신호는 바로 룰로 박지 않는다. 같은 신호가 반복되거나 릴리즈
점검에서 비용·위험이 충분히 커졌을 때 Decide 슬롯으로 올린다.

## 결정 규칙

Decide 슬롯은 아래 순서로 판단한다.

1. 기존 강제 장치를 제거하거나 축약할 수 있는가.
2. 문서 본문 하드코딩을 없애고 SSOT 파생 생성이나 링크로 대체할 수 있는가.
3. 권고 문구만으로 충분한가.
4. 그래도 되돌릴 수 없는 경계를 막아야 할 때만 hook·CI 같은 강제를 추가한다.

이 순서는 [`CLAUDE.md`의 안티패턴](../../CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)
중 "룰이 룰을 부르는 reactive cycle"을 피하기 위한 기본값이다.

## 검증 기준

Verify는 하나의 PASS로 뭉개지 않는다.

| 변경 종류 | Verify 도구 | 한계 |
|---|---|---|
| hook/function/order/TDD guard 변경 | `python3 evals/guard_efficacy.py` | fixture 계약의 재현만 본다. 실제 agent 행동은 보지 않는다. |
| agent·skill 행동 판단 변경 | `bash evals/run.sh` | LLM 실행이라 흔들림이 있다. judge 신뢰성은 [#894](https://github.com/alruminum/dcNess/issues/894) 보정 대상이다. |
| 릴리즈 전 핵심 실사고 회귀 | `EVAL_RUNS=3 EVAL_RELEASE_CHECK=1 bash evals/run.sh` | `shorts-real-spec`, `headless-prose-quality`는 N/N 통과가 기준이다. |
| 재발·낭비·비용 신호 | 다음 Sense 주기 재측정 | evals 밖 운영 신호라 즉시 증명할 수 없다. |

`evals/run.sh`는 블라인드 검수 보고와 judge 채점 결과를 `.metrics/evals/` 아래 또는
`EVAL_OUTPUT_DIR`로 지정한 위치에 저장한다. MISS가 났을 때 사람은 해당 파일을 직접 읽어
agent 결함인지 judge 결함인지 구분한다.

## 첫 실증

첫 루프 실증은 [#877](https://github.com/alruminum/dcNess/issues/877)로 기록한다.

| 슬롯 | 기록 |
|---|---|
| Sense | 하네스 엔지니어링 리뷰에서 구성 요소 개수 하드코딩과 그 stale 방지 deny-list가 reactive cycle 사례로 식별됐다. |
| Diagnose | [#893](https://github.com/alruminum/dcNess/issues/893)의 자기개선 루프 epic에서 Decide 슬롯 첫 사례로 배치했다. |
| Decide | 개수 변경마다 문서 본문과 deny-list를 같이 고치는 방식 대신, 본문 개수 표기를 제거하고 SSOT 링크·파생 검증으로 대체한다. |
| Act | [#893](https://github.com/alruminum/dcNess/issues/893) 구현 PR에서 README/CLAUDE/loop-procedure/smart-compact의 count prose와 cross-ref count deny-list를 제거한다. |
| Verify | `python3.11 -m unittest tests.test_surface_docs_sync tests.test_evals_harness -v`와 `node scripts/check_cross_refs.mjs`로 확인한다. |

## 이슈 연결

- Epic: [#893](https://github.com/alruminum/dcNess/issues/893)
- Sense: [#875](https://github.com/alruminum/dcNess/issues/875), [#876](https://github.com/alruminum/dcNess/issues/876), [#894](https://github.com/alruminum/dcNess/issues/894)
- Decide: [#877](https://github.com/alruminum/dcNess/issues/877)
- Trigger/Diagnose: [#878](https://github.com/alruminum/dcNess/issues/878)
