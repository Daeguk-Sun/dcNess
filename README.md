# dcNess

> Stop Claude Code from skipping tests, reviews, and file boundaries before PRs.
> A Claude Code PR workflow guard that preserves test/review order and agent file boundaries.

> **Origin**: [`alruminum/realworld-harness`](https://github.com/alruminum/realworld-harness) fork-and-refactor
> **Spec(SSOT)**: [`CLAUDE.md`](CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)

**dcNess 는 Claude Code 용 PR workflow guard plugin 이다.**

Claude Code 가 혼자 달릴 때 가장 비싼 실수 — 테스트 생략, 리뷰 순서 뒤집기,
권한 밖 파일 수정, PR 조기 생성 — 를 PR 전에 hook 으로 막고 복구 경로를 안내한다.
Claude Code 기본 기능이 실행 능력을 준다면, dcNess 는 사용자가 정한 작업 순서와
agent 파일 경계를 보존하는 얇은 안전장치다.

dcNess 는 *모델을 불신해서 모든 사고를 대신하는* 하네스가 아니다. 모델이 좋아질수록
절차를 없애는 게 아니라 **절차의 목적을 이해하고 더 적은 마찰로 지키게** 하는, 사용자의
working-style 을 보존하는 얇은 거버넌스 하네스다. 그래서 기본 경로는 가볍고, 무거운 절차는
risk 가 높을 때만 조건부로 부른다([`docs/plugin/workflow-router.md`](docs/plugin/workflow-router.md)).

강제하는 것은 단 두 가지뿐이다.

- **작업 순서** — 검증·구현·리뷰 시퀀스 보존
- **접근 영역** — agent 별 파일 경계 + 외부 상태 변경 차단

출력 형식·flag·schema 는 강제하지 않는다(agent 자율). 에이전트는 prose 를 자유롭게
쓰고, 메인 Claude 가 그 prose 를 직접 읽어 다음 단계를 정한다. 형식 강제 사다리도,
메타 LLM 호출도 없는 **자유서술 방식** 이다.

## 누구에게 맞나

**맞다** — Claude Code 로 실제 제품을 만들면서 `test → implement → review → PR`
순서와 agent 파일 경계를 반복적으로 지키고 싶은 사람.

**안 맞다** — 범용 model/provider 분기나 MCP 런타임 확장이 목적인 경우(그건 dcNess 의
scope 가 아니다). Codex 분기는 read-only validator 3종 opt-in 에만 한정된다. 가벼운
단발 스크립팅만 원하는 경우엔 과할 수 있다.

## 설치 & 활성화

```sh
# marketplace 등록 + plugin 설치 (Claude Code CLI)
claude plugin marketplace add alruminum/dcNess
claude plugin install dcness@dcness
```

설치만으로는 아무 hook 도 발화하지 않는다(디폴트 비활성 = pass-through).
적용할 프로젝트에서 Claude Code 세션을 열고 활성화한다.

```
/init-dcness        # 현 프로젝트를 활성 whitelist 에 등록 (+ Read 권한 / git hook 자동 셋업)
```

**활성화 성공 기준** — `/init-dcness` 가 출력하는 진단표에서 `whitelist 활성` 이 PASS 이고 FAIL 항목이 0 이면 정상이다 (INFO·선택 WARN 은 정상).

```
[dcness] === 외부 활성 프로젝트 진단 ===
  [PASS] whitelist 활성: 활성
  ...
[dcness] 요약: N PASS / 0 WARN / 0 FAIL
```

> plugin 갱신: `claude plugin update dcness@dcness`
> (문제 시 `claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness`)

기존 프로젝트에서 terms.md 같은 plug-in 본체 문서/skill/hook 갱신만 받으려면 `claude plugin update dcness@dcness` 만 실행한다. `/init-dcness` 재실행은 필요 없다.
Codex read-only validator 분기를 새로 opt-in 하거나 project-local bootstrap 파일을 새로 설치·갱신할 때만 `/init-dcness` 를 다시 실행한다. 설치/갱신되는 Codex skills 는 `$CODEX_HOME/skills/dcness-*` 3개이며, wrapper 가 해당 `SKILL.md` 를 prompt 에 직접 포함한다. provider 분기 config 는 `~/.claude/plugins/data/dcness-dcness/routing.json` 에만 저장된다. 끄기:

```sh
dcness-helper routing disable-codex-validation
```

## 작업 흐름

**기본 공개 workflow 는 제품 생명주기 기준으로 작게 유지한다.** 사용자가 기본으로 기억할 흐름은 `/spec -> /design -> /impl -> /acceptance` 다.
상세 공개 진입점 계약은 [`docs/plugin/positioning.md`](docs/plugin/positioning.md), 구현 경로 판정은
[`docs/plugin/workflow-router.md`](docs/plugin/workflow-router.md).

| 기본 진입점 | 언제 쓰나 |
|---|---|
| `/spec` | 새 기능, 큰 기획, PRD 변경처럼 의도 합의가 먼저 필요할 때 |
| `/design` | PRD 이후 구현 전 product/technical design, 즉 설계 전체가 필요할 때. visual design 단독 요청은 `/ux` |
| `/impl` | 구현, 수정, 버그픽스, 작은 리팩터링을 실제 PR 로 끝낼 때 |
| `/acceptance` | PRD / Epic / Story 기준 제품 검수와 gap 후속 연결이 필요할 때 |

`/impl` 이 내부적으로 구현 경로(설계도 유무 — Lite / Standard)와 엔진(풀4/경량)을 직교로 고른다. impl 은 설계를 하지 않고 설계도를 보고 구현만 한다.

| 구현 경로 | 조건 | 실행 |
|---|---|---|
| Lite | 설계 문서 없음 + 파일/symbol/승인된 issue 같은 concrete signal + high-risk 0개 + 테스트 기준 명확 | 메인 직접 `test -> impl -> test pass -> pr-reviewer -> PR` |
| Standard | 설계 문서(경로)가 들어옴 | `--design-doc` 기록 후 받은 설계도로 구현 (엔진: 풀4 디폴트 / 경량 build-worker) |

high-risk trigger 나 새 epic/product feature 는 impl *내부 구현 경로가 아니라* impl 진입 *전* 설계 선행(`/spec` 내부 tech-review preflight 필요 시 / `/design`)으로 분기되고, 산출된 설계도를 들고 Standard 로 진입한다.

**새 기능**

```
/spec               # PRD 초안/최종화 + 필요 시 tech-review preflight + stories
/design             # 필요 시 deep 설계 — ux/system/module architect + validator
/impl               # 생성된 deep task 파일이 있으면 내부적으로 /impl-loop 위임
/acceptance         # story/epic 제품 검수와 gap 후속 분기
```

**버그 수정**

```
/impl               # 구현 경로 자동 판정 + PR/review/CI
```

**이슈 등록**

```
/to-issue           # 문제/작업 후보를 Issue Brief 초안으로 만들고 승인 후 등록
```

support/advanced 진입점은 기본 생명주기 공개 진입점 밖의 보조 흐름이다.

- `/to-issue` — 메인 주도 Issue Brief 초안 + 승인 후 GitHub issue/Project 등록
- `/tech-review` — high-risk 설계 선행에서 `/spec` 내부 preflight 로 쓰는 선행 기술 검증
- `/impl-loop` — deep impl task 파일용 legacy/advanced runner
- `/ux` — 화면 UX / 디자인 핸드오프 전문 흐름

검증·리뷰를 건너뛴 채 PR 머지로 못 가는 것이 dcNess 의 핵심이다. `pr-reviewer` 는 read-only
provider 분기 대상이라 Codex 로 보낼 수 있지만, 사용자-facing 단계 이름은 `pr-reviewer`
하나로 유지한다.

agent 의 결론(`PASS` / `IMPL_DONE` / `SPEC_GAP_FOUND` 등) → 다음 호출 매핑은
각 loop skill 의 `<skill>-routing.md` (**mermaid 분기 그래프** + enum 표 + retry +
escalate) 가 진본이다 — 예: [`skills/impl/impl-routing.md`](skills/impl/impl-routing.md)
(구현 진입), [`skills/design/design-routing.md`](skills/design/design-routing.md)
(설계), [`skills/impl-loop/impl-loop-routing.md`](skills/impl-loop/impl-loop-routing.md)
(deep task 구현). loop 별 진입 spec(entry_point / task_list / advance / expected_steps)은
각 skill 본문(`skills/<skill>/SKILL.md`)의 `## Loop` contract 가 진본이고, 공통 실행 절차(Step 0~8 mechanics)는
[`docs/plugin/loop-procedure.md`](docs/plugin/loop-procedure.md#진입-모델)다.

## 핵심 특징

| 항목 | 내용 |
|---|---|
| 결정론 | **자유서술 방식** — agent 가 prose 자유 emit, 메인 Claude 가 prose 를 직접 읽고 분기 판단. 기계 enum 추출·메타 LLM 호출 0 |
| 형식 강제 | **0** — 형식/flag/schema 모두 agent 자율. harness 강제 = 작업 순서 + 접근 영역만 |
| 컨텍스트 layer | 2 layer (CLAUDE.md + agents) |
| 게이트 | 거버넌스 + 7 CI workflow (cross-ref / git-naming / plugin-manifest / pr-body / public-surface / python-tests / release-sync) |
| Codex 분기 | opt-in local provider 분기 — `code-validator` / `architecture-validator` / `pr-reviewer` 만 Codex read-only wrapper 로 실행 가능 |

## 공개 진입점

| 분류 | 발화 | 역할 |
|---|---|---|
| 기본 workflow | `/spec` | 새 기능 spec + SPEC_ACCEPTANCE 체크포인트 |
| 기본 workflow | `/design` | product/technical design |
| 기본 workflow | `/impl` | 구현 진입 통합 — 구현 경로(설계도 유무 — Lite / Standard) + 엔진(풀4/경량) 내부 판정 |
| 기본 workflow | `/acceptance` | story/epic 제품 검수 MVP |
| support | `/to-issue` | Issue Brief 초안 작성 + 승인 후 GitHub issue/Project 등록 |
| 고급 workflow | `/tech-review` | high-risk 설계 선행의 `/spec` 내부 선행 기술 검증 |
| 고급 workflow | `/impl-loop` | deep impl task 파일용 legacy/advanced runner |
| 고급 workflow | `/ux` | 화면 UX 플로우 + 디자인 시안 핸드오프 |
| 유틸리티 | `/init-dcness` | 현 프로젝트를 plugin 활성 whitelist 에 등록 |
| 유틸리티 | `/run-review` | run 사후 분석 — step별 비용·차단 검출 |
| 유틸리티 | `/smart-compact` | 컨텍스트 압축 + 다음 세션 resume prompt 자동 생성 |
| 유틸리티 | `/efficiency` | 세션 토큰/캐시/비용 분석 + HTML 대시보드 |

12개 sub-agent(`agents/`) — architect / validator / engineer / reviewer / acceptance 계열 — 는 사용자-facing
진입점이 아니라 workflow 내부 gate/worker/reviewer 로 호출된다.

## 거버넌스 (dcNess 자체 저장소 작업 기준)

본 저장소의 모든 변경은 [`CLAUDE.md`](CLAUDE.md)(SSOT) 를 따른다.

- **게이트**: main-block · git-naming · pytest(pre-commit hook) + plugin-manifest · pr-body · public-surface · cross-ref(CI)
- **branch → PR → merge** 필수, main 직접 push 금지
- PR 절차: [`CLAUDE.md`](CLAUDE.md#커밋-pr-절차)

## 개발자 셋업 (dcNess 에 기여)

검증 기준은 Python 3.11 이다. macOS 기본 `python3` 는 Python 3.9 일 수 있으므로
로컬에서는 `python3.11` 을 명시한다. pre-commit hook 은 `python3.11` 을 우선 탐색하고,
CI 는 GitHub Actions `setup-python` 으로 Python 3.11 을 고정한다.

```sh
git clone https://github.com/alruminum/dcNess.git
cd dcNess
cp scripts/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

python3.11 -m unittest discover -s tests -v # 단위 테스트
node scripts/check_plugin_manifest.mjs     # manifest 검증
node scripts/check_public_surface.mjs      # 공개 workflow 진입점 검증
node scripts/check_cross_refs.mjs          # link/anchor + 옛 명칭 게이트
bash scripts/dcness-codex-validator --help # Codex validator wrapper smoke
```

- 의존성: Python 3.11+, Node.js 20+, **외부 패키지 0** (표준 라이브러리만)

## 참조 문서

| 문서 | 역할 |
|---|---|
| [`CLAUDE.md`](CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) | 정체성 SSOT (강제 영역 2 + 안티패턴 4) |
| [`docs/plugin/terms.md`](docs/plugin/terms.md) | 사용자-facing 용어 사전 — 용어·공개 진입점·분기 표현 수정/리뷰 시 lazy read |
| [`docs/plugin/positioning.md`](docs/plugin/positioning.md) | 공개 workflow 진입점 계약 — 기본/support/고급/유틸리티/내부 agent 분류 |
| 각 skill 의 `<skill>-routing.md` ([`impl`](skills/impl/impl-routing.md) / [`design`](skills/design/design-routing.md) / [`impl-loop`](skills/impl-loop/impl-loop-routing.md) 등) | 분기 규칙 진본 (mermaid + enum 표 + retry + escalate) |
| [`docs/plugin/loop-procedure.md`](docs/plugin/loop-procedure.md#진입-모델) | loop 실행 절차 — Step 0~8 mechanics (각 loop spec = 해당 skill `## Loop`) |
| [`docs/plugin/hooks.md`](docs/plugin/hooks.md#catastrophic-gatesh) | 순서 차단 훅 + 8 hook SSOT |
| [`PROGRESS.md`](PROGRESS.md) | 현재 상태 / TODO / Blockers |
| [`CLAUDE.md`](CLAUDE.md) | 메인 Claude 작업 지침 |
| [`AGENTS.md`](AGENTS.md) | 외부 에이전트(Codex 등) 지침 |

## Public Launch Tracker

현재 public launch 공개 노출 범위는 README / plugin manifest / GitHub About description 을 같은
포지셔닝으로 맞추는 것이 기준이다. 후속 readiness 항목은 아래 이슈가 맡는다.

- [`#520 /init-dcness doctor`](https://github.com/alruminum/dcNess/issues/520) — 활성화 실패를 사용자가 직접 진단할 수 있게 한다.
- [`#521 agent/skill RED-GREEN 시나리오 테스트`](https://github.com/alruminum/dcNess/issues/521) — guard 동작을 예제 기반으로 검증한다.
- [`#522 public benchmark`](https://github.com/alruminum/dcNess/issues/522) — public launch 전 성능·효용 근거를 정리한다.
- [`#524 runtime non-goal vs interop 포지셔닝`](https://github.com/alruminum/dcNess/issues/524) — provider 분기 시스템이 아니라 PR workflow guard 라는 경계를 명확히 한다.

### 역사 자료 (archive)

[`docs/archive/status-json-mutate-pattern.md`](docs/archive/status-json-mutate-pattern.md)
(자유서술 방식 원전 proposal) · [`migration-decisions.md`](docs/archive/migration-decisions.md)
· [`conveyor-design.md`](docs/archive/conveyor-design.md) (Python loop 실행기 v1 폐기 설계).

## License

MIT — see [`LICENSE`](LICENSE).
