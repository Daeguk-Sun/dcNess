# Candidate delta

Previous HEAD/tree: `2222222` / `aaaaaaaa`
Current HEAD/tree: `3333333` / `bbbbbbbb`

## module-018/service.py

- stored recipient와 canonical recipient를 항상 비교하고 mismatch면 persist한다.
- unchanged-message-row self-heal regression test가 추가됐다.

## module-059/service.py

- selected-message address fallback을 제거했다.
- canonical recipient가 없으면 retransmit을 중단한다.
- outgoing MMS/self-number regression test가 추가됐다.

## module-103/service.py

- notification deep link에 `?simple=true`를 붙인다.
- notification tap routing test가 추가됐다.

## module-104/retry_controller.py

- 신규 코드: `authorized = request.retry or policy.authorize(request.actor)`
- `request.retry`는 호출자가 직접 설정할 수 있다.
