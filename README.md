# dcNess

> **Origin**: [`alruminum/realworld-harness`](https://github.com/alruminum/realworld-harness) fork-and-refactor
> **Spec(SSOT)**: [`CLAUDE.md`](CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)

**dcNess 는 Claude Code 용 거버넌스 하네스 plugin 이다.**

코딩 에이전트가 혼자 달릴 때 빠지는 함정 — 검증 건너뛰기, 권한 밖 파일 수정,
순서 뒤집기 — 을 막는 데 집중한다.

강제하는 것은 단 두 가지뿐이다.

- **작업 순서** — 검증·구현·리뷰 시퀀스 보존
- **접근 영역** — agent 별 파일 경계 + 외부 시스템 mutation 차단

출력 형식·flag·schema 는 강제하지 않는다(agent 자율). 에이전트는 prose 를 자유롭게
쓰고, 메인 Claude 가 그 prose 를 직접 읽어 다음 단계를 정한다. 형식 강제 사다리도,
메타 LLM 호출도 없는 **prose-only** 방식이다.

## 누구에게 맞나

**맞다** — Claude Code 로 실제 제품을 만들면서 PR/이슈/구현 루프에 **거버넌스**(검증
순서 보존, 파일 경계, 재현 가능한 run-review)가 필요한 사람.

**안 맞다** — 범용 model/provider 라우팅이나 MCP 런타임 확장이 목적인 경우(그건 dcNess 의
scope 가 아니다). Codex route 는 read-only validator 3종 opt-in 에만 한정된다. 가벼운
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

**활성화 성공 기준** — 아래처럼 `active: YES` 가 출력되면 정상이다.

```
[dcness] active: YES
```

> plugin 갱신: `claude plugin update dcness@dcness`
> (문제 시 `claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness`)

`/init-dcness` 재실행 시 기존 프로젝트도 Codex read-only validator route 를 opt-in 할 수 있다. 설치/갱신되는 Codex skills 는 `$CODEX_HOME/skills/dcness-*` 3개이며, wrapper 가 해당 `SKILL.md` 를 prompt 에 직접 포함한다. route config 는 `~/.claude/plugins/data/dcness-dcness/routing.json` 에만 저장된다. 끄기:

```sh
dcness-helper routing disable-codex-validation
```

## 작업 흐름

dcNess 는 단계별 skill 로 작업을 끌고 간다. `/impl-loop` 은 **설계 산출물(impl task 문서)이
있어야** 동작하므로, 보통 아래 순서를 탄다.

**새 기능**

```
/product-plan       # PRD + stories + tech-review 스켈레톤 (그릴미 대화)
/architect-loop     # 1 epic 설계 — ux/system/module architect + validator → impl task 문서 생성
/impl-loop          # 생성된 task 들을 순차 구현 (task 마다 1 PR)
/run-review         # 방금 run 의 step별 비용·차단 분석
```

**버그 수정**

```
/issue-report       # 이슈 분류 → 라우팅 추천
/impl-loop <task>   # 분류 결과에 따라 fallback 경로로 구현
```

각 task 는 **1 PR** 로 처리되며, 엔진은 둘 중 하나다(개수·발화로 자동 분기).

- **풀 4-agent**(단일 task 기본·`엄정` 발화) — `test-engineer → engineer → code-validator
  → pr-reviewer`. **독립 code-validator** 가 구현↔계획 정합을 검증한 뒤에야 pr-reviewer 로 간다.
- **build-worker**(다중 task chain 기본·`빠르게` 발화) — `build-worker(test+impl+self-validate)
  → pr-reviewer`. 검증은 build-worker 가 **self-validate** 로 수행하고(독립 code-validator 단계
  없음 — 단 self-validate 미통과 시 code-validator 로 복원), pr-reviewer 가 2차 게이트다.

어느 엔진이든 검증·리뷰를 건너뛴 채 PR 머지로 못 가는 것이 dcNess 의 핵심이다.

agent 의 결론(`PASS` / `IMPL_DONE` / `SPEC_GAP_FOUND` 등) → 다음 호출 매핑은
각 loop skill 의 `<skill>-routing.md` (**mermaid 라우팅 그래프** + enum 표 + retry +
escalate) 가 진본이다 — 예: [`skills/architect-loop/architect-loop-routing.md`](skills/architect-loop/architect-loop-routing.md)
(설계), [`skills/impl-loop/impl-loop-routing.md`](skills/impl-loop/impl-loop-routing.md)
(구현). loop 별 진입·step 인덱스는
[`docs/plugin/loop-procedure.md`](docs/plugin/loop-procedure.md#한눈-인덱스-loop-진입-ssot), 각 loop 의 절차
풀스펙은 해당 skill 본문(`skills/<skill>/SKILL.md`)이 진본이다.

## 핵심 특징

| 항목 | 내용 |
|---|---|
| 결정론 | **prose-only** — agent 가 prose 자유 emit, 메인 Claude 가 prose 를 직접 읽고 routing. 기계 enum 추출·메타 LLM 호출 0 |
| 형식 강제 | **0** — 형식/flag/schema 모두 agent 자율. harness 강제 = 작업 순서 + 접근 영역만 |
| 컨텍스트 layer | 2 layer (CLAUDE.md + agents) |
| 게이트 | 거버넌스 + 6 CI workflow (cross-ref / git-naming / plugin-manifest / pr-body / python-tests / release-sync) |
| Codex route | opt-in local routing — `code-validator` / `architecture-validator` / `pr-reviewer` 만 Codex read-only wrapper 로 실행 가능 |

## Skill (10개)

| 발화 | 역할 |
|---|---|
| `/init-dcness` | 현 프로젝트를 plugin 활성 whitelist 에 등록 (부트스트랩) |
| `/issue-report` | 버그/이슈 분류 (FUNCTIONAL_BUG / CLEANUP / DESIGN_ISSUE / KNOWN_ISSUE / SCOPE_ESCALATE) |
| `/product-plan` | 새 기능 spec/design — 그릴미 대화로 PRD + stories + tech-review 스켈레톤 작성 |
| `/tech-review` | 선행 기술 검증 (tech-reviewer 가 의존성·실현성 검토, `/architect-loop` 진입 전 단방향) |
| `/architect-loop` | 1 epic 설계 루프 — ux-architect → system-architect → architecture-validator(1차) → module-architect × K → architecture-validator(2차) |
| `/ux` | 화면 UX 플로우 + 디자인 시안 핸드오프 (ux-architect → designer → 사용자 PICK, UX_FLOW / UX_REFINE 2 모드) |
| `/impl-loop` | impl task 구현 루프 — 1개(single) / 여러 개(chain) × 풀 4-agent(엄정) / build-worker(경량). 개수·발화로 자동 분기 |
| `/run-review` | run 사후 분석 — step별 비용·차단 검출 |
| `/smart-compact` | 컨텍스트 압축 + 다음 세션 resume prompt 자동 생성 |
| `/efficiency` | 세션 토큰/캐시/비용 분석 + HTML 대시보드 |

12개 sub-agent(`agents/`) — architect / validator / engineer / reviewer 계열 — 가 위
skill 안에서 작업 순서와 접근 권한 경계에 따라 호출된다.

## 거버넌스 (dcNess 자체 저장소 작업 기준)

본 저장소의 모든 변경은 [`CLAUDE.md`](CLAUDE.md)(SSOT) 를 따른다.

- **게이트**: main-block · git-naming · pytest(pre-commit hook) + plugin-manifest · pr-body · cross-ref(CI)
- **branch → PR → merge** 필수, main 직접 push 금지
- PR 절차: [`CLAUDE.md`](CLAUDE.md#커밋-pr-절차)

## 개발자 셋업 (dcNess 에 기여)

```sh
git clone https://github.com/alruminum/dcNess.git
cd dcNess
cp scripts/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

python3 -m unittest discover -s tests -v   # 단위 테스트
node scripts/check_plugin_manifest.mjs     # manifest 검증
node scripts/check_cross_refs.mjs          # link/anchor + 옛 명칭 게이트
bash scripts/dcness-codex-validator --help # Codex validator wrapper smoke
```

- 의존성: Python 3.11+, Node.js 20+, **외부 패키지 0** (표준 라이브러리만)

## 참조 문서

| 문서 | 역할 |
|---|---|
| [`CLAUDE.md`](CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) | 정체성 SSOT (강제 영역 2 + 안티패턴 4) |
| 각 skill 의 `<skill>-routing.md` ([`architect-loop`](skills/architect-loop/architect-loop-routing.md) / [`impl-loop`](skills/impl-loop/impl-loop-routing.md) 등) | 라우팅 진본 (mermaid + enum 표 + retry + escalate) |
| [`docs/plugin/loop-procedure.md`](docs/plugin/loop-procedure.md#한눈-인덱스-loop-진입-ssot) | loop 한눈 인덱스 + Step 0~8 mechanics |
| [`docs/plugin/hooks.md`](docs/plugin/hooks.md#catastrophic-gatesh) | catastrophic 시퀀스 + 7 hook SSOT |
| [`PROGRESS.md`](PROGRESS.md) | 현재 상태 / TODO / Blockers |
| [`CLAUDE.md`](CLAUDE.md) | 메인 Claude 작업 지침 |
| [`AGENTS.md`](AGENTS.md) | 외부 에이전트(Codex 등) 지침 |

### 역사 자료 (archive)

[`docs/archive/status-json-mutate-pattern.md`](docs/archive/status-json-mutate-pattern.md)
(prose-only 원전 proposal) · [`migration-decisions.md`](docs/archive/migration-decisions.md)
· [`conveyor-design.md`](docs/archive/conveyor-design.md) (Python 컨베이어 v1 폐기 설계).

## License

MIT — see [`LICENSE`](LICENSE).
