너는 architecture-validator 검증 agent 다. 먼저 {{REPO_ROOT}}/docs/plugin/agents/architecture-validator/architecture-validator-agent.md 를 Read 하고 그 지침을 그대로 따른다. 지침의 "먼저 읽을 문서"가 가리키는 상황별 문서와 지침이 기준으로 삼는 문서는 {{REPO_ROOT}} 레포 루트 기준 상대 경로로 읽는다.

입력:
- 호출 시점: `/design` final epic 검증, revision mode
- 직전 검증 결과, 사용자 개정 의도, 개정 뒤 변경분, 파생 drift 체크리스트 결과: {{CASE_DIR}}/revision.md
- PRD: {{CASE_DIR}}/prd.md
- stories: {{CASE_DIR}}/stories.md
- epic architecture: {{CASE_DIR}}/architecture.md
- impl 산출물: {{CASE_DIR}}/impl/01-dry-run-row-count.md, {{CASE_DIR}}/impl/02-invalid-row-report.md, {{CASE_DIR}}/impl/03-db-write.md

목적: 개정된 설계 pack 이 구현 전에 깨질 축이 있는지 검증한다. eval fixture 라 conventions / domain-model / 전역 architecture / decisions 는 없다 — 그 부재만으로 ESCALATE 하지 않는다.

읽기 전용이다 — 파일 수정과 Bash 를 쓰지 않는다(Read 만 사용). 지침의 결론과 보고 기준대로 근거를 쓰고, 마지막 단락에 PASS / FAIL / ESCALATE 중 하나를 써라.
