# dcNess 용어 사전

> **Status**: ACTIVE
> **Scope**: dcNess 사용자-facing 문서, hook stderr, README, skill/agent 설명에서 쓰는 용어의 단일 기준.

이 문서는 설계 문서나 작업 메모가 아니라 표현 기준이다. 절차, 분기 표, hook 동작, decision 기록은 재서술하지 않고 각 소유 SSOT 로 연결한다.

## 배포와 읽기 규칙

- 이 파일은 사용자 repo 로 복사되는 파일이 아니다. dcNess plug-in 본체의 SSOT 로 배포된다.
- main 머지 후 사용자가 `claude plugin update dcness@dcness` 를 실행하면 외부 활성 프로젝트의 plug-in cache 에 반영된다.
- `/init-dcness` 재실행은 필요하지 않다.
- 에이전트가 자동 선독하는 문서가 아니다. 용어, 공개 진입점, 분기 표현, 사용자 표시 메시지를 수정하거나 리뷰할 때만 lazy read 한다.
- 코드 심볼, 파일명, CLI flag, 테스트 fixture 는 공식 용어와 별개의 기술 식별자다. 예: `catastrophic-gate.sh`, `check_bash_mutation`, `--lane`, `routing.json`.

## 파일명 결정

파일명은 `docs/plugin/terms.md` 로 둔다. `terminology.md` 와 `glossary.md` 는 의미는 맞지만 외래어 느낌이 강하고, `language.md` 는 단순 용어표를 넘어 표현 규칙 전체를 담는 문서처럼 보인다. `CONTEXT.md` 는 토큰 컨텍스트, 작업 맥락, 프로젝트 활성 컨텍스트와 혼동되므로 쓰지 않는다.

## 용어 표

| 공식 용어 | 피할 표현 | 정의 | 예시 | 소유 SSOT |
|---|---|---|---|---|
| 중대 차단 | `catastrophic` | dcNess 가 코드로 막는 최소 위반 범주. 작업 순서와 접근 영역처럼 되돌리기 비용이 큰 경계만 뜻한다. | 중대 차단은 형식 위반이나 비용 경고를 자동으로 막지 않는다. | [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일), [`hooks.md`](hooks.md) |
| 순서 차단 훅 | `catastrophic gate`, `catastrophic-gate` | sub-agent 호출 순서와 진행 step 순서를 막는 Claude Code hook. 파일명은 `catastrophic-gate.sh` 를 유지한다. | build-worker 는 설계 산출물 확보 후에만 순서 차단 훅을 통과한다. | [`hooks.md`](hooks.md#catastrophic-gatesh) |
| 작업 순서 보호 | `catastrophic 시퀀스` | validator, worker, reviewer 같은 단계의 선후관계를 보존하는 목적 설명. | 작업 순서 보호는 build-worker 설계 사전 조건과 begin-step 순서를 보존한다. | [`hooks.md`](hooks.md#catastrophic-gatesh), [`loop-procedure.md`](loop-procedure.md) |
| 외부 상태 변경 | `mutation`, `mutating` | repo 밖 또는 원격 상태를 바꾸는 행동. `git push`, PR 생성/머지/리뷰 제출, GitHub issue 생성/수정/닫기 등이 포함된다. | sub-agent 의 `gh pr merge` 는 외부 상태 변경이라 메인 영역이다. | [`harness/agent_boundary.py`](../../harness/agent_boundary.py), [`hooks.md`](hooks.md#file-guardsh) |
| 외부 변경 차단 목록 | `mutation denylist` | sub-agent Bash/MCP 호출에서 흔한 외부 상태 변경 명령을 막는 실수 방지 목록. 보안 경계가 아니라 best-effort guard 다. | 외부 변경 차단 목록은 `git push` 와 `gh pr create` 를 차단한다. | [`harness/agent_boundary.py`](../../harness/agent_boundary.py), [`hooks.md`](hooks.md#file-guardsh) |
| 공개 진입점 | `public surface`, `workflow surface` | 사용자가 `/` command 로 기억하고 호출하는 workflow 이름. | 기본 공개 진입점은 `/spec`, `/design`, `/impl`, `/acceptance` 다. | [`positioning.md`](positioning.md) |
| 공개 노출 범위 | `surface` | command 외에도 사용자에게 안정 계약처럼 보이는 문서, API, config, field 이름까지 포함하는 넓은 표현. | 새 공개 노출 범위를 추가하면 PR 에 justification 을 적는다. | [`positioning.md`](positioning.md), [`scripts/check_public_surface.mjs`](https://github.com/Daeguk-Sun/dcNess/blob/main/scripts/check_public_surface.mjs) |
| 구현 경로 | `lane` | `/impl` 안에서 사용자에게 echo 하는 내부 처리 이름. 현재 값은 issue-intake / direct / design-doc 다. | 파일·이슈·테스트 같은 concrete signal 이 있으면 direct 구현 경로다. | [`workflow-router.md`](workflow-router.md), [`skills/impl/impl-routing.md`](../../skills/impl/impl-routing.md) |
| 분기 규칙 | `routing` | 자유 형식 요청, agent 결론, retry/escalate 를 다음 단계로 보내는 판단 기준. | `/impl` 의 high-risk 신호는 설계 선행 권고이지 자동 차단이 아니다. | [`workflow-router.md`](workflow-router.md), 각 skill 의 `<skill>-routing.md` |
| 다음 호출 판단 | `agent routing` | agent 결론 prose 를 읽고 어떤 agent/step 을 다음에 호출할지 정하는 좁은 의미. | `FAIL` 이면 다음 호출 판단은 해당 skill 의 분기 규칙 문서가 소유한다. | [`loop-procedure.md`](loop-procedure.md#enum-분기), 각 skill 의 `<skill>-routing.md` |
| 사전 조건 | `prerequisite` | 특정 gate 나 workflow 진입 전에 이미 충족되어야 하는 조건. | design-doc 구현 경로는 설계 산출물 사전 조건을 `--design-doc` 으로 기록한다. | [`hooks.md`](hooks.md#catastrophic-gatesh), [`skills/impl/SKILL.md`](../../skills/impl/SKILL.md) |
| 자유서술 방식 | `prose-only` | agent 가 고정 JSON/schema/marker 없이 prose 로 보고하고, 메인 Claude 가 prose 를 직접 읽어 판단하는 방식. | 자유서술 방식에서도 마지막 단락의 결론 단어와 근거는 명확해야 한다. | [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일), [`loop-procedure.md`](loop-procedure.md#표준-1-step-시퀀스-per-agent-의무) |
| 진행 순서 검사 | `strict conveyor`, `strict-conveyor`, `conveyor` | active run 안에서 `begin-step -> Agent -> end-step` 물리 순서를 검사하는 hook 영역. | 진행 순서 검사는 `begin-step` 없이 Agent 를 직접 호출하면 차단한다. | [`hooks.md`](hooks.md#catastrophic-gatesh), [`loop-procedure.md`](loop-procedure.md#표준-1-step-시퀀스-per-agent-의무) |
| 하네스 경량화 실험 | `ablation` | 반복 비용이 있는 선택형 절차를 줄여도 품질 경계가 유지되는지 격리 fixture의 동일 task baseline/variant로 비교하는 승인형 실험. | 첫 1+1 결과가 명확하면 추가 trial 없이 유지·줄이기 후보·보류로 보고한다. | [`outcome-scorecard.md`](outcome-scorecard.md#개인-경량화-판단) |
| 운영 성과 요약 | `scorecard` | 과정·Agent 작업 효율·실제 제품 결과를 서로 대체하지 않고 나란히 보는 사용자-facing 요약. | 제품 결과가 없으면 다른 축으로 채우지 않고 측정 불가로 표시한다. | [`outcome-scorecard.md`](outcome-scorecard.md) |

## 수용 기준 계층

| 계층 | 역할 | 다음 계층과의 관계 | 소유 SSOT |
|---|---|---|---|
| PRD 유저 시나리오 | 기능 나열과 사용자의 정상·실패·복구 흐름을 제품 언어로 설명한다. Story 수용 기준은 두지 않는다. | `/spec` 이 시나리오를 Story 로 나누고 검증 약속을 붙인다. | [`skills/spec/spec-prd-reference.md`](../../skills/spec/spec-prd-reference.md) |
| Epic 완료 기준 | 여러 Story 가 함께 달성해야 할 epic 단위 결과를 `[command]`/`[agent-read]` 로 정의한다. | Story 전체가 합쳐졌을 때 product-acceptance 가 통합 증거를 대조하고, GitHub issue 에서는 close 감사용 체크리스트로 materialize 된다. | [`skills/spec/spec-stories-reference.md`](../../skills/spec/spec-stories-reference.md) |
| Story AC | `AC-NNN` Given/When/Then 으로 사용자에게 약속한 Story 단위 결과를 정의한다. 프로젝트 전역에서 ID가 불변인 검증 origin 이다. | module-architect 가 task REQ 로 번역한다. | [`skills/spec/spec-stories-reference.md`](../../skills/spec/spec-stories-reference.md) |
| task REQ | Story AC 를 task가 실행·관찰할 검증 언어로 번역한다. 제품 REQ 는 `(from AC-NNN)`, 소수 기술 REQ 는 `(technical: 이유)`를 쓰며, 검증방법은 `(TEST)`·`(AGENT READ)`·실앱 자동화 `(JOURNEY)` 중 하나다. | build-worker가 `(TEST)`·`(AGENT READ)`를 실행하고 `(JOURNEY)` flow/매니페스트를 작성하며, product-acceptance가 `(JOURNEY)`를 tip에서 실행·판정한다. | [`docs/plugin/agents/module-architect/templates/impl-task.md`](agents/module-architect/templates/impl-task.md) |

## 사용 지침

- 사용자-facing 설명과 stderr 에는 공식 용어를 먼저 쓴다.
- 파일명, 함수명, CLI flag 를 그대로 보여줘야 할 때는 literal 로 쓰고, 바로 뒤에 한국어 의미를 붙인다.
- 과거 의사결정 기록, `docs/archive/**`, `docs/internal/release-notes.md`, `PROGRESS.md` 는 기본적으로 소급 수정하지 않는다.
- 모든 agent 에 강제 read 를 추가하지 않는다. 용어, 공개 진입점, 분기 표현을 수정하거나 리뷰할 때만 이 문서를 참조하게 한다.

## 사용자-facing 표현 원칙

사용자에게 보이는 문서, hook 메시지, agent 보고는 사용자가 판단해야 하는 사실과 결과를 먼저 말한다. 내부 실행 토큰은 필요할 때만 literal 로 노출하고, 노출할 때는 사용자 의미를 같이 붙인다.

- `run_id`, `entry_point`, helper subcommand, agent mode, 내부 phase 이름은 디버그·복구·재현에 필요할 때만 쓴다.
- 내부 ID, 내부 추적 표현, 작업 디렉터리 절대경로, 반복 가능한 로그 원문은 사용자 판단에 직접 필요하지 않으면 숨기거나 요약한다.
- 사용자-facing 공개 설명에서는 기능 효과와 사용자가 해야 할 행동을 말하고, 하네스 내부 배관 설명은 링크나 상세 로그로 내린다.
- 단, 검증·장애 복구·감사 맥락에서는 근거가 우선이다. 내부 토큰을 감추느라 파일 경로, 명령, 실패 원인, 재현 방법을 흐리게 쓰지 않는다.
