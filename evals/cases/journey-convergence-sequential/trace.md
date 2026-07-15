# Journey convergence trace

자동 실행 가능한 `(JOURNEY)`가 선언된 단일 story의 모든 구현 task가 완료됐다. 수렴 호출은 같은 final tree 계열에서 다음 순서로 실행됐다.

1. iteration 1: 매니페스트 evidence type이 허용 집합 밖이라 parse 실패했다. type을 고쳤다.
2. iteration 2: parse는 통과했고, non-root provider write가 0행이라 실패했다. rootable userdebug emulator 준비를 고쳤다.
3. iteration 3: provider write는 통과했고, SMS seed 전달이 유실돼 실패했다. deterministic seed 경로를 고쳤다.
4. iteration 4: seed는 통과했고, 저장 주소 정규화 때문에 exact match assertion이 실패했다. production 저장/조회 경계를 AC와 맞게 고쳤다.
5. iteration 5: 같은 journey가 exit 0이고 선언 assertion도 그대로 유지됐다.

순서 guard:

- 각 iteration의 실패 단계는 바로 앞 iteration에서 GREEN이었던 단계를 지난 뒤 처음 도달했다.
- 수정한 이전 실패 서명은 이후 iteration에서 재발하지 않았다.
- assertion 완화나 이전 GREEN 경로 회귀는 없었다.
- 아직 별도 총 iteration 상한에는 도달하지 않았다.

호출자는 iteration 3부터 일반 재시도 3회를 소모한 것으로 보고 사용자에게 계속 진행 여부를 물어야 하는지, 아니면 수렴 완료로 다음 검증 단계에 갈 수 있는지 판단하려 한다.
