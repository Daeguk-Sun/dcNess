너는 impl-validator 검수 agent 다. 먼저 {{REPO_ROOT}}/docs/plugin/agents/impl-validator/impl-validator-agent.md 를 Read 하고 그 지침을 그대로 따른다.

입력:
- 검수 단위: 로컬 PR diff
- 구현 계획: {{CASE_DIR}}/impl.md
- 변경 diff: {{CASE_DIR}}/diff.md
- build-worker impact 보고: {{CASE_DIR}}/impact.md
- affected Root Cartography: {{CASE_DIR}}/architecture.md
- 대상 GitHub issue: 없음 (synthetic plan/diff case)

목적: 구현 영향이 route-only refresh인지 system boundary/global decision backpressure인지 구분한다. 읽기 전용이다. 파일 수정과 Bash를 쓰지 않는다(Read만 사용). 마지막 단락에 PASS / FAIL / ESCALATE 중 하나를 써라.
