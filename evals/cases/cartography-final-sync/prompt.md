너는 `/impl`·`/impl-loop` 마감의 final mutation owner다. 먼저 다음 지침을 Read 한다.

- `{{REPO_ROOT}}/skills/impl-loop/impl-loop-finish.md`

그 다음 `{{CASE_DIR}}`의 `architecture.md`, `route-only-request.md`, `boundary-request.md`를 읽는다. prewritten synced Root fixture 없이 두 invocation을 독립적으로 처리한다.

- Invocation A에는 실제로 적용할 최소 unified diff 또는 정확한 patch hunk와 final sync 보고를 출력한다. Read-only eval이므로 파일 자체는 수정하지 않는다.
- Invocation B에는 patch를 내지 말고 필요한 backpressure 결론과 근거를 출력한다.
- A에서 요청 밖 Root 좌표나 epic/module/decision/impl 문서를 고치지 않는다.
- module-architect를 호출하거나 stale Root를 validator에 먼저 보내지 않는다.

마지막에는 이 두 final mutation owner 결과가 지침 계약을 충족했는지 감사 결론 PASS / FAIL / ESCALATE 중 하나를 쓴다.
