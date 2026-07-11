---
name: migrate-dcness
description: 이미 /init-dcness 로 활성화한 기존(brownfield) 프로젝트를, 코드 역설계로 전역 docs(prd/architecture/conventions/decisions/index)의 *내용*을 채워 마치 처음부터 dcNess 를 써온 것처럼 agent 가 일할 문서 토대를 까는 일회성 유틸리티 진입점. 사용자가 "migrate-dcness", "dcness 마이그레이션", "기존 프로젝트 docs 역설계로 채워", "전역 docs 부트스트랩", "/migrate-dcness" 등을 말할 때 사용. /init-dcness(활성화)의 짝이며, epic/story 산출물(docs/epics/...)은 만들지 않는다.
---

# Migrate dcNess Skill — 기존 프로젝트 전역 docs 부트스트랩

> `/init-dcness` 가 인프라 활성화 + 빈 골격 seed 까지 한다면, `/migrate-dcness` 는 기존 코드를 역설계해 전역 docs 의 *내용*을 채운다. 일회성. 깊이 = 전역 docs 까지 (epic/story 역분해는 이후 `/spec`·`/design`).

## 언제 사용

- 사용자 발화: "migrate-dcness", "dcness 마이그레이션", "기존 프로젝트 docs 역설계", "/migrate-dcness"
- 기존 코드베이스가 있는 프로젝트에 dcNess 를 도입하는데, `/init-dcness` seed 골격만으로는 내용이 비어 agent 가 읽고 일할 토대가 없을 때

## 선행 조건

- `/init-dcness` 활성화가 먼저다. 미활성이면 [`/init-dcness`](init-dcness.md) 를 먼저 실행한다.
- 대상은 기존 코드가 있는 brownfield 프로젝트다. 빈 프로젝트는 `/init-dcness` seed 로 충분하므로 본 스킬은 no-op 이다.
- **일회성**: 전역 docs 토대가 이미 채워진 프로젝트에는 다시 돌리지 않는다.

## 범위 (깊이 경계)

- 채우는 전역 docs: `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/decisions/`, `docs/index.md`.
- 위치·양식 SSOT = [`docs/plugin/deliverables-map.md`](../docs/plugin/deliverables-map.md). 시드 양식 = 산출 양식 원칙을 따른다.
- **만들지 않는 것**: epic/story 산출물(`docs/epics/**`), module-architect 호출, 새 agent/새 템플릿. epic/story 역분해는 이후 `/spec`·`/design` 이 점진적으로 담당한다.

## 절차

### 0. 사전 준비 — 브랜치 격리 + 문서 분류 (모든 쓰기의 선행 조건)

어떤 쓰기보다 **먼저** 안전 경계를 세운다. 이 두 결과가 이후 모든 쓰기 단계의 입력이다.

- **브랜치 pre-flight (쓰기 전 필수)**: 현재 branch 가 기본 브랜치(`main` 등)면 부트스트랩 브랜치를 먼저 만들고 이후 모든 쓰기를 그 브랜치에서 한다. main 직접 쓰기/커밋 금지. 브랜치 네이밍은 [`docs/plugin/git-spec.md`](../docs/plugin/git-spec.md)(예: `docs/{desc}`).
- **docs 인벤토리 + 3범주 분류 (read-only)**: 각 전역 docs 대상을 아래 세 범주로 분류한다. 이 분류는 Step 1·2 가 무엇을 직접 쓰고 무엇을 diff 로 넘길지 결정한다.
  - (a) **부재** — 새로 쓴다.
  - (b) **빈 dcNess seed** — `/init-dcness` 가 템플릿에서 만든 내용 없는 골격 그대로이고 사용자 콘텐츠가 없다. 역설계 내용으로 **직접 채운다**.
  - (c) **비어있지 않은 사용자 문서** — 사용자가 이미 쓴 내용, 대상 repo 의 산재 문서, 비표준 ADR. **직접 쓰지 않는다.** 정렬은 Step 3 에서 diff + 승인.
- 코드 진본을 실측한다: 소스 레이아웃, manifest(`package.json` / `pyproject.toml` / `go.mod` / `Cargo.toml` 등), `README`, 빌드·CI 설정, 공개 entrypoint.
- 🔴 (c) 로 분류된 파일은 Step 1·2 에서 **절대 직접 쓰지 않는다.**

### 1. system-architect BROWNFIELD — 코드 파생 전역 docs

- Agent 로 `system-architect` 를 **BROWNFIELD 모드**로 호출한다. 지침은 [`system-architect` BROWNFIELD 모드](../docs/plugin/agents/system-architect/system-architect-agent.md#brownfield-모드-역설계-부트스트랩)가 SSOT 다.
- 산출 대상은 Step 0 에서 (a)/(b) 로 분류된 `docs/conventions.md`(스택·naming·tooling·style), 전역 `docs/architecture.md` Cartography(모듈 topology·의존 방향·runtime entrypoint·stable capability owner·`landed/stub` 상태와 실제 코드/검증 증거·as-built wiring/gotcha), `docs/decisions/NNNN-slug.md` 초안뿐이다. (c) 로 분류된 기존 문서는 채우지 않고 diff 후보로만 보고한다.
- PRD·stories 가 없어도 ESCALATE 없이 채운다 (그 공백을 메우는 것이 목적). 코드 근거가 약한 결정은 `DRAFT` 로 표기된다.

### 2. PRD 역추론 초안 (메인) — 필수 사용자 확인 게이트

- `docs/prd.md` 가 Step 0 에서 **(a) 부재 또는 (b) 빈 seed 일 때만** 초안을 쓴다. (c) 비어있지 않은 기존 PRD 면 직접 쓰지 않고 Step 3 의 diff + 승인 대상으로 넘긴다.
- 메인 Claude 가 `README`·모듈 구조에서 제품 맥락을 역추론해 초안을 쓴다. 양식 = [`skills/spec/templates/prd.md`](../skills/spec/templates/prd.md).
- 코드에 근거가 없는 "왜 / 누구 / 비즈니스 모델" 같은 필드는 자동 확정하지 않고 추정으로 남기며 본문에 `DRAFT` 로 표기한다.
- 🔴 **사용자 확인 전 진행 차단.** 사용자가 DRAFT 필드를 확인/교정하기 전에는 PR 단계로 넘어가지 않는다.

### 3. 사용자 문서 정렬 — diff + 승인

- Step 0 에서 (c) 로 분류된 기존 문서만 대상이다. 규격 위치/양식으로 정렬하는 변경은 **무단 덮어쓰기/이동 없이** diff 로 먼저 제시하고 사용자 승인 후에만 적용한다.

### 4. index 정리 + 선택 전역 요약 — 분류에 따라 직접 적용 vs 승인

이 스크립트들은 `docs/index.md` 진행 상태 섹션 append 와 `docs/index.md` generated 섹션 갱신으로 **파일을 직접 수정**한다. 따라서 Step 0 분류를 그대로 존중해야 Step 3 승인 가드를 우회하지 않는다. 전역 architecture 요약은 checked-in freshness 대상이 아니므로 필요할 때만 온디맨드로 생성한다.

공통 변수 (어느 분기든 필요 — 분기 밖에서 먼저 설정):

```bash
PLUGIN_ROOT="$(ls -d ${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/cache/dcness/dcness/*} 2>/dev/null | sort -V | tail -1)"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
```

- **`docs/index.md`·`docs/architecture.md` 가 (a) 부재면 먼저 seed 로 만든다.** generated-section 스크립트는 파일이 없으면 no-op 이라 index 가 끝내 안 생기므로, `docs/index.md`(양식 `skills/spec/templates/index.md`)·`docs/architecture.md`(양식 `docs/plugin/agents/system-architect/templates/root-architecture.md`, 단 Step 1 BROWNFIELD 가 이미 채웠으면 그 파일 유지)를 seed 원본에서 생성한 뒤 (b) 로 취급한다.
- **(a→seed)/(b) 이면** 아래를 직접 실행한다. 파생 섹션은 손으로 복제하지 않는다.

```bash
node "$PLUGIN_ROOT/scripts/ensure_docs_index_next_section.mjs" "$PROJECT_ROOT"
node "$PLUGIN_ROOT/scripts/aggregate_index_map.mjs" --root "$PROJECT_ROOT"
```

- **둘 중 하나라도 (c) 사용자 문서면** 직접 실행하지 않는다. 집계기는 `--check` 로 drift 만 확인하고(파일 미수정), index 진행 상태 섹션 append 는 추가될 블록을 미리 보여준 뒤, Step 3 처럼 diff + 사용자 승인 후에만 실제 갱신을 적용한다.

```bash
node "$PLUGIN_ROOT/scripts/aggregate_index_map.mjs" --root "$PROJECT_ROOT" --check
```

집계기는 `--root` 미지정 시 cwd 기본이므로, 서브디렉토리에서 호출해도 어긋나지 않게 `--root "$PROJECT_ROOT"` 를 넘긴다. epic 이 아직 없으므로 index epic 표가 비어 있어도 정상이다. 사람이 전역 architecture 요약을 보고 싶을 때만 `node "$PLUGIN_ROOT/scripts/aggregate_architecture_map.mjs" --root "$PROJECT_ROOT"` 를 별도 실행한다.

### 5. 단일 docs 부트스트랩 PR

- Step 0 에서 만든 부트스트랩 브랜치에서 커밋 → PR 하나로 마감한다. 커밋·PR 네이밍은 [`docs/plugin/git-spec.md`](../docs/plugin/git-spec.md) 를 따른다.
- PR 본문에 무엇을 코드 역설계로 채웠는지, 어떤 필드가 `DRAFT` 로 사용자 확인을 거쳤는지, 어떤 기존 문서를 승인 후 정렬했는지 남긴다.

## 배포 경로 검증

- command(`commands/migrate-dcness.md`) + agent(`system-architect` BROWNFIELD 모드) 변경은 plug-in 본체(분류 1)라, 사용자가 `claude plugin update` 로 plug-in 을 갱신하면 기존 활성 프로젝트에도 자동 도달한다. 별도 배포 복사 스텝은 없다.

## 참조

- [`docs/plugin/deliverables-map.md`](../docs/plugin/deliverables-map.md) — 전역 docs 위치·양식 SSOT
- [`system-architect` BROWNFIELD 모드](../docs/plugin/agents/system-architect/system-architect-agent.md#brownfield-모드-역설계-부트스트랩) — 역설계 산출 지침
- [`/init-dcness`](init-dcness.md) — 활성화 (본 스킬의 선행 짝)
- [`docs/plugin/positioning.md`](../docs/plugin/positioning.md) — Utility 공개 노출 범위
- [`docs/plugin/git-spec.md`](../docs/plugin/git-spec.md) — 브랜치·커밋·PR 네이밍
