# 검증 보고 가이드

검증 agent 의 stdout prose 는 harness-state 에 저장되어 메인 오케스트레이터가 다음 행동을 고르는 run-local 판단 자료가 된다. 이 문서는 `code-validator`, `architecture-validator`, `pr-reviewer` 같은 검증/reviewer 계열이 실패, 중단, 재검증 결과를 짧고 판정 가능하게 쓰기 위한 shared agent 문서다.

dcNess 는 자유서술 방식이다. 아래 항목은 형식이 아니라 의미 요구다. heading 은 권장 카테고리일 뿐 필수 schema 가 아니다.

## FAIL / ESCALATE 판단 노트

첫 `FAIL` 또는 `ESCALATE` 판단에서는 메인이 다음 호출을 고를 수 있게 다음 사실을 짧게 남긴다.

- 판정: `FAIL` 인지 `ESCALATE` 인지와 결론 이유.
- 깨진 기대: 어떤 계약, 검증 축, merge 기준, 입력 전제가 깨졌는지.
- 근거: 추측이 아니라 파일 path, 라인, 명령 결과, 호출자가 준 증거. blocking finding 은 기존 검증/테스트/설계로 이미 다뤄지지 않았다는 긍정 근거까지 포함한다.
- 확인 위치: 후속 agent 가 바로 열어볼 파일, 섹션, diff, 테스트명.
- 영향 표면: 어떤 사용자 동작, 설계 계약, PR merge risk, 후속 step 이 영향을 받는지.
- 오케스트레이터 판단점: engineer 재진입, module-architect 보강, 사용자 위임처럼 메인이 골라야 하는 분기.
- 판단 한계: 입력, 권한, 테스트 증거, 외부 상태가 부족해 더 판단하지 못한 부분.

실패 사실과 판단 근거만 남긴다. 수정 설계, 담당자 지정, 최소 수정 범위 요구는 넣지 않는다.

blocking 또는 confident escalation 으로 올리는 finding 은 위 사실 중 (1) 구체적 site, (2) 기존 검증/테스트/설계로 이미 다뤄지지 않았다는 근거, (3) 방치 시 결과 를 갖춘다. 셋을 채우지 못한 우려는 차단 근거가 아니라 advisory 또는 low-confidence note 로 낮춘다. 이는 출력 형식 강제가 아니라 finding 근거 품질 기준이며, 메인은 차단 finding 과 low-confidence 후보를 구분해 다음 행동을 고른다.

## 재검증 delta-first 보고

같은 agent/mode 가 retry 또는 재검증으로 다시 호출된 경우에는 전체 배경을 반복하지 않고 직전 같은 agent/mode 결과 대비 변화부터 쓴다. 재검증 결과는 changed / resolved / still failing / new 를 먼저 드러낸다.

권장 카테고리:

- 해소됨: 직전 finding 중 더 이상 재현되지 않는 항목.
- 유지됨: 여전히 차단되는 finding 과 남은 근거.
- 신규: 이번 재검증에서 새로 드러난 차단 finding.
- 판단 불가: 증거 부족, 파일 부재, 권한 제한, 테스트 미실행 등으로 검증하지 못한 부분.

남은 차단 finding 에는 파일/라인/명령 같은 재현 가능한 근거를 유지한다. 이미 해소된 finding, 통과 항목, 전체 작업 배경은 길게 재서술하지 않는다.

## 자유서술 경계

- 별도 영구 산출물 작성 금지: validator stdout prose 가 harness-state 에 저장되는 기존 흐름을 사용한다.
- read-only agent 가 직접 파일을 쓰지 않는다.
- JSON, marker, 고정 schema, 필수 heading 강제는 도입하지 않는다.
- `PASS` 단발에는 적용하지 않는다.
- 전체 배경, 작업 과정, 통과 항목 나열을 피하고 메인이 다음 행동을 고르는 데 필요한 사실만 남긴다.
- 결론 enum 은 각 agent 지침이 정한 대로 마지막 단락에 명확히 쓴다.

## 참조

- [`agent-doc-format.md`](agent-doc-format.md)
