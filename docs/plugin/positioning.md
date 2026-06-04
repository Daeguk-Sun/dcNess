# Public Workflow Surface

> dcNess 사용자가 기본으로 외울 진입점과, 내부 gate/agent 를 구분하는 제품 표면 계약.

dcNess 의 기본 공개 workflow 는 세 개만 전면에 둔다.

| 기본 진입점 | 언제 쓰나 | 내부 처리 |
|---|---|---|
| `/impl` | 구현, 수정, 버그픽스, 작은 리팩터링을 실제 PR 로 끝낼 때 | Lite / Standard / Deep lane 을 내부 판정 |
| `/product-plan` | 새 제품 기능, 큰 기획, PRD 변경처럼 의도 합의가 먼저 필요할 때 | PRD / stories / 기술 검토 스켈레톤 작성 |
| `/issue-report` | 아직 분류되지 않은 버그나 이상 동작을 접수할 때 | qa 분류 뒤 `/impl` 또는 planning lane 추천 |

사용자는 lane 이름을 외울 필요가 없다. `/impl` 이 작업의 되돌리기 비용과 불확실성을 보고 다음 내부 lane 중 하나를 고른다.

| 내부 lane | 조건 | 실행 |
|---|---|---|
| Lite | high-risk 가 없고 파일, symbol, 승인된 issue, 테스트 명령처럼 구현 경계가 이미 concrete | 메인 직접 `test -> impl -> test pass -> pr-reviewer -> PR` |
| Standard | high-risk 는 없지만 수정 범위, 테스트 기준, 작은 내부 contract 가 애매함 | `module-architect` compact plan 1-pass 후 plan-aware 구현 |
| Deep | high-risk trigger 가 있거나 새 epic/product feature 처럼 사전 설계 합의가 필요함 | 기존 PRD / tech-review / architect-loop / deep impl task 흐름 |

## Advanced Entrypoints

아래 skill 은 기본 표면이 아니라 고급/전문 진입점이다. 사용자가 직접 호출할 수는 있지만 README 기본 흐름에서는 `/impl` 또는 `/product-plan` 뒤의 내부 단계로 설명한다.

| 고급 진입점 | 위치 |
|---|---|
| `/tech-review` | Deep lane 의 선행 기술 검증 |
| `/architect-loop` | Deep lane 의 설계 루프 |
| `/impl-loop` | deep impl task 파일용 legacy/advanced runner |
| `/ux` | 화면 UX / 디자인 핸드오프 전문 흐름 |

## Utility Surface

운영 보조 command 는 workflow entrypoint 와 분리한다.

| 유틸리티 | 역할 |
|---|---|
| `/init-dcness` | 프로젝트 활성화 |
| `/run-review` | 끝난 run 사후 분석 |
| `/smart-compact` | resume prompt 포함 context compact 보조 |
| `/efficiency` | 세션 토큰/비용 분석 |

## Internal Agents

agent 는 사용자가 외워야 하는 command 가 아니다. `architecture-validator`, `build-worker`, `code-validator`, `designer`, `engineer`, `module-architect`, `pr-reviewer`, `qa`, `system-architect`, `tech-reviewer`, `test-engineer`, `ux-architect` 는 workflow 내부에서 호출되는 gate/worker/reviewer 로 분류한다.

특히 `code-validator`, `architecture-validator`, `pr-reviewer` 는 read-only validation provider routing 대상이다. provider 가 Claude 든 Codex 든 사용자-facing 단계 이름은 `pr-reviewer` 같은 agent 이름으로 유지한다.

## Contract Gate

기본/고급/유틸리티/내부 agent 목록과 skill/command/agent 의 frontmatter name 대 path 정합은 [`scripts/check_public_surface.mjs`](../../scripts/check_public_surface.mjs) 가 검사한다. 새 기본 workflow 를 추가하려면 이 문서와 gate 기대값을 함께 수정해야 한다.
