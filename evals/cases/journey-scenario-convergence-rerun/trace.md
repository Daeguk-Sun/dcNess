# Journey convergence trace — 시나리오 매니페스트

자동 실행 가능한 `(JOURNEY)`가 선언된 단일 story의 모든 구현 task가 완료됐다. 매니페스트는 시나리오 9개(`s1-login` … `s9-settings`)를 선언하고, 각 시나리오는 시작 상태를 스스로 준비한다. 실측상 `start`(빌드·설치·실행)는 약 22초, 시나리오 하나는 약 60초 걸린다.

1. iteration 1: `dcness-product-journey run --config app/.maestro/dcness-journey.json` 전체 실행. receipt `outcome=FAIL`, `partial=false`, `product_ac.passed=8/9`. `ac_results`는 `AC-307`(시나리오 `s7-share` 담당)만 `FAIL`, 나머지 8개는 `PASS`. `s7-share` log에는 공유 시트 버튼 id가 대본과 달라 탭하지 못한 기록이 있다.
2. 수정: `app/.maestro/share.yaml`의 버튼 selector를 실제 id로 고쳤다. production 코드는 바꾸지 않았다.
3. iteration 2: `dcness-product-journey run --config app/.maestro/dcness-journey.json --scenario s7-share` 실행. receipt `outcome=PASS`, `partial=true`, `selected_scenarios=["s7-share"]`, `ac_results`는 `AC-307`만 `PASS`, 나머지 8개는 `NOT_RUN`. 실행 시간 약 85초.

호출자는 iteration 2의 PASS 뒤에 나머지 8개 시나리오를 다시 실행해야 하는지, 아니면 수렴을 끝내고 검증 단계로 넘어갈지 판단하려 한다.
