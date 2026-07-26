# Previous impl-validator receipt

검토 범위는 base `1111111`부터 candidate `2222222`까지의 110개 변경 파일 전체였다.

MUST FIX:

1. `[quality-gap]` `module-018/service.py:41` — unchanged thread row가 canonical recipient로 self-heal되지 않는다.
2. `[quality-gap]` `module-059/service.py:88` — retransmit이 outgoing MMS의 self-number address로 fallback한다.
3. `[spec-gap]` `module-103/service.py:27` — notification deep link에 `simple=true`가 없다.

그 밖의 전체 diff와 직접 영향 표면에서는 blocker를 찾지 못했다.

FAIL
