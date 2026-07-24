# Epic close trace

1. final code tree `f19a`에서 test/lint/build/typecheck가 exit 0, warnings 0이고 coverage report가 존재한다.
2. build-worker `JOURNEY_CONVERGENCE`가 final tip의 실제 제품 동선을 통과시킨다.
3. Root의 CLI entrypoint가 `planned`로 stale임을 final mutation owner가 확인하고 affected route만 갱신해 commit한다.
4. 새 HEAD/tree `c20a`를 candidate로 freeze한다.
5. 같은 `c20a`에서 반대 진영 holistic impl-validator가 Epic Sanity 렌즈까지 포함해 PASS한다. 그 PASS 뒤에만 product-acceptance가 기존 same-tree unit evidence를 소비하고 sealed Journey를 독립 재실행해 PASS한다.
6. close audit 직전 test 이름 오탈자만 고치는 code commit `f20b`가 추가됐지만 이전 `c20a` receipt 둘을 그대로 사용해 merge하려 한다.
