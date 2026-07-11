# 정답표 — 실제 producer 계약

- [E1][MUST] prewritten refreshed Root fixture 없이 Invocation A의 affected attachment export 상태와 CLI export as-built edge만 바꾸는 구체적인 bounded Root patch를 직접 산출한다.
- [E2][MUST] A에서 실제 runtime entrypoint와 integration/CLI 제품 동작 증거를 근거로 attachment export만 `landed`로 올리고 message search·scheduler cleanup·Global decisions sentinel은 보존한다.
- [E3][MUST] local-only/ignored `docs/architecture.md`를 code PR에 넣지 않되 canonical local Root patch 적용이 필요하며 durable handoff만으로 freshness가 해소되지 않는다고 판정한다.
- [E4][MUST] A 보고에 affected 좌표, before/after, 증거, 보존 범위, 같은 merge candidate diff와 갱신 Root를 impl-validator가 재검증할 handoff를 포함하고 결론을 PASS로 낸다.
- [E5][MUST] Invocation B의 storage policy·shared public boundary·global decision 변경에는 Root patch를 산출하지 않고 `SYSTEM_CHECKPOINT_REQUIRED`로 backpressure한다.
- [E6][MUST_NOT] 어느 invocation에서도 epic architecture, impl task, module docs, decision을 새로 쓰거나 재설계하지 않는다.
