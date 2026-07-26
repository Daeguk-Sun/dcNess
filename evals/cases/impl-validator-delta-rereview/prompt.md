너는 같은 close의 2라운드 impl-validator 재리뷰를 수행한다. 먼저 다음 지침을 Read 한다.

- `{{REPO_ROOT}}/docs/plugin/agents/impl-validator/impl-validator-agent.md`

그 다음 아래 재리뷰 입력을 읽는다.

- 직전 receipt: `{{CASE_DIR}}/prior-receipt.md`
- receipt sha256: `c516ce8fe719c2d81b69353bc2cc178da7dfdcdfea28c99195f87645d400d53d`
- 직전 candidate HEAD/tree/workspace root: `2222222` / `aaaaaaaa` / 현재 fixture root
- 현재 candidate HEAD/tree/workspace root: `3333333` / `bbbbbbbb` / 현재 fixture root
- 직전 candidate HEAD..현재 candidate HEAD delta: `{{CASE_DIR}}/candidate-delta.md`

지침에 따라 판정 범위를 스스로 정하고, 직전 finding 해소 여부와 신규 delta 위험을 검토한다.
근거와 영향 범위를 자유 prose로 쓰고 마지막 단락에 PASS, FAIL, ESCALATE 중 하나를 명시한다.
