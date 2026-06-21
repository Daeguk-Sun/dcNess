# system freeze 참고

system-architect 산출물은 1차 validation PASS 뒤 기본적으로 freeze된 것으로 본다. 이후 모든 결함이 system 재설계 사유는 아니다.

## system 재진입 사유

`SYSTEM_BOUNDARY`에 해당할 때만 system-architect 재진입을 기본값으로 둔다.

- 도메인 invariant가 바뀜
- use case ownership이 바뀜
- port consumer가 바뀜
- 저장 정책이 바뀜
- `docs/decisions/` 수준의 전역 결정이 틀림
- 전역 architecture map 의 cross-epic anchor 가 잘못됨

## system 재진입이 아닌 것

`CONTRACT_PROPAGATION`은 결정 자체가 아니라 사본 전파가 틀린 경우다. 이 경우 module-architect의 `mode=contract_sweep`이 canonical 값을 stale 문서에 전파한다.

## freeze 이후 허용되는 append

새 epic 을 설계할 때 `docs/architecture.md` 는 append-growing map 으로 갱신될 수 있다. 다음은 system 재설계가 아니라 map 확장이다.

- `Cross-Epic Map` 에 새 epic 링크 추가
- `Global Module Topology` 에 새 owner epic 행 추가
- `External Boundaries` 에 이미 검토된 boundary 링크 추가
- 새 `docs/decisions/NNNN-slug.md` 링크 추가

기존 accepted decision 자체를 바꾸거나 전역 invariant 를 바꾸면 append 가 아니라 `SYSTEM_BOUNDARY` 로 본다.
