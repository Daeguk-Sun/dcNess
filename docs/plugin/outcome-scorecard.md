# 제품 결과 scorecard 계약

> **Status**: ACTIVE
> **Scope**: 하네스 과정, agent의 실제 작업 능력, 제품 결과를 같은 관측 단위에서 비교하되 서로 대체하지 않는 측정 계약.

## 세 영역

| 영역 | 답하는 질문 | 대체할 수 없는 것 |
|---|---|---|
| **과정·merge** | guard·validator·PR 흐름이 실행되고 재작업과 낭비가 얼마나 생겼는가 | 실제 제품 outcome, Agent effectiveness |
| **Agent effectiveness** | agent가 올바른 맥락과 변경 대상을 더 정확하고 적은 탐색으로 찾아 작업했는가 | 기능·문서가 존재한다는 사실, PR merge |
| **실제 제품 outcome** | 사용자에게 약속한 제품 AC와 핵심 journey가 실제 제품 경계에서 성공했는가 | 테스트 수, guard PASS, validator verdict, PR merge |

세 영역은 한 scorecard에 나란히 둘 수 있지만 합산 점수로 뭉개지 않는다. 과정 지표가 green이어도 제품 AC·journey 증거가 없으면 제품 결과는 `측정 불가`다. 관측하지 못한 값을 0, 실패, 개선으로 바꾸거나 다른 영역의 지표로 채우지 않는다.

## 비교 단위와 공통 필드

비교 가능한 최소 단위는 같은 목표와 검증 경계를 가진 trial이다. 문단·표·JSON 중 특정 출력 형식을 강제하지 않지만, 비교할 때 다음 의미가 함께 있어야 한다.

| 의미 | 기록할 내용 |
|---|---|
| 작업 맥락 | task 유형, repo 유형, 목표/AC 식별자, 위험도 |
| 실행 조건 | model, provider, harness variant, trial ID와 같은 조건의 전체 trial 수 |
| denominator | 각 비율의 분자·분모, source 프로젝트 수, 측정일 또는 run 범위 |
| 비용 | wall-clock, input/output token, cost와 측정 근거 |
| 사람 개입 | 개입 횟수, 이유, 복구에 든 작업 |
| 결과 증거 | 실행 증거 종류(command, API/CLI/UI journey, screenshot/log, 실제 통합 경계 등), evidence 위치 |

필드가 legacy run에 없으면 `측정 불가`와 이유를 남긴다. 서로 다른 task 유형이나 repo 유형을 하나의 variant 효과처럼 합치지 않는다.

## 과정·merge 영역

과정 영역은 최소한 finished run, validator verdict와 재작업, guard/blocked 신호, PR 생성·merge, regression, waste 신호를 분리한다.

- finished run은 완료 event와 읽을 수 있는 receipt가 함께 있는 run만 센다.
- validator 재작업률은 FAIL 분자와 판정 가능한 verdict 분모를 함께 둔다.
- PR merge율은 `pr_created`를 분모로 하고 같은 PR의 `pr_merged`만 분자로 센다. 분모가 없으면 `측정 불가`다.
- waste count는 finished run 노출량을 denominator로 같이 제시한다.
- guard PASS·validator FAIL·PR merge는 하네스 과정의 증거이며 실제 제품 성공률로 표현하지 않는다.

## Agent effectiveness 영역

Agent effectiveness는 하네스 기능 보유 여부가 아니라 같은 조건에서 agent의 실제 작업 능력이 어떻게 달라졌는지를 본다.

| 관측 항목 | 의미 |
|---|---|
| SSOT·runtime entrypoint·capability owner 탐색 정확도 | 첫 선택이 현재 코드와 문서의 진짜 owner를 가리키는가 |
| 첫 올바른 변경 대상까지의 비용 | 걸린 시간, tool/read 양, 불필요한 파일 읽기와 tool 반복 |
| 오경로 | stale 문서, 잘못된 owner/entrypoint, 폐기된 경로를 선택한 횟수 |
| 영향 범위 누락 | 필요한 producer/consumer, 상태 전이, 테스트 또는 공개 경계를 빠뜨렸는가 |
| context 기인 재작업 | 구현 결함이 아니라 필요한 맥락 누락 때문에 validator가 되돌린 횟수 |
| cross-session 복구 | 다음 세션이 결정·현재 상태·다음 변경 대상을 정확히 복구했는가 |

Cartography freshness는 SSOT·entrypoint·owner 후보와 stale 여부의 입력 증거를 제공한다. Codebase Sanity는 code revision, 감사 scope, 경고·unknown·잔존 경로의 입력 증거를 제공한다. 두 기능이 존재하거나 PASS했다는 사실만으로 탐색 정확도·시간·재작업 감소가 입증되지는 않는다. 비교 trial의 before/after 또는 paired 관측이 없으면 effectiveness는 `측정 불가`다.

## 실제 제품 outcome 영역

제품 outcome은 제품 AC와 핵심 사용자 journey를 실제 경계에서 실행한 증거로 기록한다.

- AC별 pass/fail/측정 불가와 실행 증거 종류를 보존한다.
- journey는 앱 기동, API/CLI/UI 결과, 실데이터 통합 경계처럼 AC에 맞는 실제 경계를 통과해야 한다.
- mock-only green, guard PASS, validator PASS, PR merge만으로 outcome PASS를 만들지 않는다.
- regression은 이전에 통과한 제품 동작이 같은 조건에서 깨졌는지 별도 필드로 둔다.

## 주장 가능 범위

### 개인 경량화 판단

같은 task 또는 저장된 fixture에서 baseline과 후보를 한 번씩 실행하는 **1+1 paired screening**을 허용한다. 명확한 새 제품 AC gap·사람 복구·regression이 없고 비용 또는 사람 개입이 개선됐는지 보고 `keep` / `remove` / `hold`를 정하는 개인 판단용이다. 일반화나 공개 우위 근거가 아니다.

### 공개 우위 주장

공개 우위를 말하려면 다음 조건을 모두 충족한다.

- source 프로젝트 최소 2개와 총 20개 이상의 finished run.
- 모든 headline 값에 분자·denominator·source 프로젝트 수·측정일·재현 명령.
- 같은 task/repo 유형 안에서 비교 variant마다 2회 이상의 반복 trial. 1+1 screening만으로는 부족하다.
- 실제 제품 outcome이 포함되고, process/merge나 Agent effectiveness로 대체되지 않는다.
- 측정 불가, 작은 표본, provider/model 차이와 관측 한계를 수치와 같은 위치에 둔다.

## 현재 baseline 재현

외부 활성 프로젝트의 현재 process baseline은 [`outcome-baseline.md`](../internal/outcome-baseline.md)에 시점 snapshot으로 남긴다. 재현기는 기존 fleet 집계기를 재사용한다.

```sh
python3 "$DCN"/harness/outcome_scorecard.py --redact-paths
python3 "$DCN"/harness/outcome_scorecard.py --redact-paths --json
```

이 명령이 출력하는 제품 outcome과 Agent effectiveness의 `측정 불가`는 실패 판정이 아니라 해당 증거가 아직 ledger에 없다는 뜻이다.
시점 snapshot을 고정할 때는 `--measured-at <ISO-8601>`과 `--as-of <ISO-8601>`을 함께 쓰고, baseline에 포함한 stable ref마다 `--source-ref <ref>`를 반복한다. cutoff는 기존 run에 나중에 append된 event도 제외하고, source ref 고정은 registry 순서 변경이나 새 프로젝트 추가가 과거 source 집합을 바꾸지 못하게 한다. 고정한 ref가 registry에서 사라지거나 해당 runtime ledger를 읽을 수 없으면 재현기는 조용히 분모를 줄이지 않고 오류로 종료한다.
