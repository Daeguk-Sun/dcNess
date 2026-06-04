# system freeze 참고

system-architect 산출물은 1차 validation PASS 뒤 기본적으로 freeze된 것으로 본다. 이후 모든 결함이 system 재설계 사유는 아니다.

## system 재진입 사유

`SYSTEM_BOUNDARY`에 해당할 때만 system-architect 재진입을 기본값으로 둔다.

- 도메인 invariant가 바뀜
- use case ownership이 바뀜
- port consumer가 바뀜
- 저장 정책이 바뀜
- root ADR 수준의 결정이 틀림

## system 재진입이 아닌 것

`CONTRACT_PROPAGATION`은 결정 자체가 아니라 사본 전파가 틀린 경우다. 이 경우 module-architect의 `mode=contract_sweep`이 canonical 값을 stale 문서에 전파한다.
