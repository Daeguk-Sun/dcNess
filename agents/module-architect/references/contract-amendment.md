# 계약 변경과 전파

## CONTRACT_AMENDMENT

module-architect가 public contract를 바꾸면 같은 작업 안에서 Contract Ledger도 갱신한다. 바뀌지 않았으면 "Ledger 변경 없음"을 명시한다.

변경 보고에는 다음을 포함한다.

- 바뀐 contract 이름
- 변경 전 값
- 변경 후 값
- 영향을 받는 consumer
- stale 사본을 찾을 sweep keyword

## CONTRACT_PROPAGATION

architecture-validator가 결정은 맞지만 문서 사본이 어긋났다고 판단한 경우다. 이때는 system 재설계가 아니라 `mode=contract_sweep`으로 동기화한다.

contract_sweep에서는 다음만 한다.

- canonical 계약 값을 확인한다.
- stale 사본을 찾는다.
- write 경계 안의 stale 줄만 고친다.
- write 경계 밖 stale은 위치를 보고한다.
