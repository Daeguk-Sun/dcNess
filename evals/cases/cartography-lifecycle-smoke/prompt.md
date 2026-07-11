너는 외부 활성 프로젝트의 dcNess lifecycle smoke를 감사하는 메인 agent다. 먼저 다음 workflow 지침을 Read 한다.

- {{REPO_ROOT}}/skills/design/SKILL.md
- {{REPO_ROOT}}/skills/impl/SKILL.md
- {{REPO_ROOT}}/skills/impl/impl-routing.md
- {{REPO_ROOT}}/skills/acceptance/SKILL.md

그 다음 {{CASE_DIR}}의 모든 fixture 파일을 읽고, 제공된 design·implementation·최초 code validation·Root refresh·code revalidation·acceptance·다음 design trace가 각 durable boundary를 올바른 순서와 책임으로 통과하는지 감사한다. 현재 단계에서 멈춰야 할 누락이 있으면 근거와 함께 지적한다. 파일을 수정하지 않고 Read만 사용한다. 마지막 단락에 PASS / FAIL / ESCALATE 중 하나를 쓴다.
