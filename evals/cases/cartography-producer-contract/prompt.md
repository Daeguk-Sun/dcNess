너는 실제 `module-architect:CARTOGRAPHY_REFRESH` producer contract를 실행하는 agent다. 먼저 다음 지침을 Read 한다.

- `{{REPO_ROOT}}/docs/plugin/agents/module-architect/module-architect-agent.md`

그 다음 `{{CASE_DIR}}`의 `architecture.md`, `route-only-request.md`, `boundary-request.md`를 읽는다. prewritten refreshed Root fixture 없이 두 invocation을 독립적으로 처리한다.

- Invocation A에는 실제로 적용할 최소 unified diff 또는 정확한 patch hunk와 producer 보고를 출력한다. Read-only eval이므로 파일 자체는 수정하지 않는다.
- Invocation B에는 patch를 내지 말고 필요한 backpressure 결론과 근거를 출력한다.
- A에서 요청 밖 Root 좌표나 epic/module/decision/impl 문서를 고치지 않는다.
- A와 B 각각에 module-architect 결론 enum을 명시한다.

마지막에는 이 두 producer 결과가 지침 계약을 충족했는지 감사 결론 PASS / FAIL / ESCALATE 중 하나를 쓴다.
