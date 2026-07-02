---
name: canvas-design
description: 내부 전용 UI 기준 확보 wrapper. 신규 시각 구조 구현 전에 designer draft 생성, 사용자 PICK, 확정본 승격, docs/design-variants/canvas.html frame 등록을 한 경로로 수행한다. 공개 진입점이 아니며 /impl 과 /impl-loop 내부에서만 호출된다.
---

# canvas-design — 내부 UI 기준 확보 스킬

> 이 스킬은 **공개 진입점이 아니다**. 사용자가 외우는 workflow 는 `/spec -> /design -> /impl -> /acceptance` 그대로이며, canvas-design 은 `/impl` 과 `/impl-loop` 이 UI 기준 확보가 필요하다고 판정했을 때만 호출하는 내부 wrapper 다. `compact-design` 과 같은 내부 skill 지위이며 `/canvas-design` 으로 노출하지 않는다.

## 목적

신규 시각 구조 작업에서 구현자가 대조할 기준을 확보하고, 기준이 확정되면 그 기준을 `docs/design-variants/` canvas SSOT 에 반영한다. canvas SSOT 변경은 이 스킬 경유가 단일 경로다. `/impl` 과 `/impl-loop` 는 승격·canvas 등록 절차를 각자 복제하지 않고 이 스킬을 호출한다.

## 입력

- 대상 화면 `<screen-id>` — kebab-case. ux-flow 화면 인벤토리, `data-node-id`, 구현 컴포넌트와 같은 id 체계를 쓴다.
- 기준 소스:
  - `existing-confirmed`: 이미 있는 `docs/design-variants/<screen-id>.html`
  - `user-provided`: 사용자 제공 이미지, 스케치, HTML, 기존 외부 시안
  - `new-draft`: 신규 시각 구조 + 기준 없음
  - `skip`: 사용자가 "목업 없이"라고 했거나 시각 구조 불변
- 구현 맥락 — 관련 issue, impl task/compact plan, ux-flow, design.md, 기존 제품 화면 포인터

## 산출물 규약

`docs/design-variants/` 한 지붕이 확정본 SSOT 다.

- `docs/design-variants/canvas.html` — 프로젝트 전체 화면 지도. 확정 화면을 iframe frame 으로 등록하고, 필요하면 흐름 화살표를 둔다.
- `docs/design-variants/_lib/` — `canvas.js`, `show-ids.js` 같은 공유 helper.
- `docs/design-variants/<screen-id>.html` — 화면별 확정본. v 접미사는 쓰지 않는다. 히스토리는 git 이 보존한다.
- `docs/design-variants/drafts/` — 탐색용 draft. `.gitignore` 로 무시한다.

## 절차

1. **seed 보장**
   - `/init-dcness` 기본 경로는 UI seed 를 설치하지 않을 수 있다. draft 생성이나 canvas frame 등록 전 메인이 `docs/design-variants/` seed 를 부재 시만 만든다.
   - `docs/design-variants/_lib/show-ids.js` 가 없으면 `templates/design-variants/_lib/show-ids.js` 를 복사한다.
   - `docs/design-variants/_lib/canvas.js` 가 없으면 `templates/design-variants/_lib/canvas.js` 를 복사한다.
   - `docs/design-variants/canvas.html` 이 없으면 `templates/design-variants/canvas.html` 을 복사한다.
   - `docs/design-variants/.gitignore` 이 없으면 `templates/design-variants/.gitignore` 를 복사한다.
   - 이미 있는 파일은 덮어쓰지 않는다. 확정본과 기존 canvas frame 은 유지한다.
2. **3-way 기준 판정 확인**
   - 기준 있음: 사용자 제공 이미지·스케치·HTML 또는 기존 확정본을 기준으로 인정한다. 기존 확정본이면 그대로 반환한다. 사용자 제공 HTML 이면 메인이 확정본으로 승격하고 canvas 에 등록한다. 이미지·스케치처럼 node-id 가 없는 기준은 필요 시 designer 가 drafts 에 HTML draft 를 만들고 사용자 PICK 을 거쳐 확정한다.
   - 신규 시각 구조 + 기준 없음: designer 를 호출해 `docs/design-variants/drafts/<screen-id>-draft<N>.html` 을 만든다.
   - 시각 구조 불변 또는 사용자의 "목업 없이" 지시: mockup 생성을 생략하고 `skip` 으로 반환한다. 사용자의 "목업 없이" 지시는 항상 우선한다.
3. **designer draft 생성** (`new-draft` 또는 이미지·스케치의 HTML 변환 필요 시)
   - designer 는 `docs/design-variants/drafts/` 아래에만 write 한다.
   - draft HTML 은 single-file, no-build, `:root` CSS custom property 토큰, 주요 `data-node-id`, 필요한 상태(default/hover/focus/disabled/empty/error)를 포함한다.
   - draft 에서 helper script 는 `../_lib/show-ids.js` 를 참조한다.
4. **사용자 PICK**
   - 메인이 draft 경로와 핵심 node-id 를 사용자에게 제시한다.
   - NG 면 designer 를 재호출한다. round 한도는 두지 않는다.
   - OK 면 다음 단계로 진행한다.
5. **확정본 승격**
   - 메인이 선택된 draft 또는 사용자 제공 HTML 을 `docs/design-variants/<screen-id>.html` 로 승격한다.
   - 승격 시 `../_lib/show-ids.js` 참조를 `_lib/show-ids.js` 로 정규화한다.
   - 확정본은 v 접미사를 쓰지 않는다.
6. **canvas frame 등록**
   - 메인이 `docs/design-variants/canvas.html` 에 `<iframe data-frame-id="<screen-id>" src="<screen-id>.html"></iframe>` 를 등록한다.
   - 이미 같은 `data-frame-id` 가 있으면 중복 등록하지 않고 기존 frame 을 갱신한다.
   - 화면 간 흐름이 확정돼 있으면 `svg.flow-arrows` 의 `path[data-from][data-to]` 로 연결한다. 클릭 프로토타이핑은 후속 범위다.
7. **반환**
   - 확정 목업 경로: `docs/design-variants/<screen-id>.html`
   - canvas 경로: `docs/design-variants/canvas.html`
   - 핵심 node-id 매핑: `<data-node-id> -> 구현 컴포넌트/상태`
   - 의도적 차이가 이미 합의된 경우 그 이유

## 결론 enum

`/impl-loop` 이 이 스킬을 routed step 으로 호출하므로 마지막 단락은 반드시 아래 중 하나로 끝난다.

- `PASS` — seed 보장, 3-way 판정, 필요한 draft/PICK/승격/canvas 등록, 반환값 정리가 끝났고 구현 step 으로 진행 가능하다.
- `ESCALATE` — 사용자 PICK 대기, 기준 소스 불명확, seed 복사 실패, 화면 id 충돌처럼 메인이 임의로 진행하면 안 되는 조건이다. 사유와 필요한 사용자 입력을 함께 적는다.

## 권한 경계

- designer 는 drafts 전용이다. designer 는 `docs/design-variants/drafts/` 에만 write 한다.
- 확정본(`docs/design-variants/<screen-id>.html`), `canvas.html`, `_lib/` 갱신은 메인이 수행한다.
- engineer, test-engineer, build-worker, architect 계열 agent 는 `docs/design-variants/` 를 write 하지 않는다.
- canvas SSOT 를 바꿔야 하는 workflow 는 이 스킬을 호출하고, 승격 규약을 자체 문서에 중복 구현하지 않는다.

## 호출 측 계약

- `/impl` 은 진입 시 UI 기준 확보 분기를 한 줄로 echo 한 뒤 필요한 경우 이 스킬을 호출한다.
- `/impl-loop` 은 UI task 에서 engine 무관하게 구현 step 앞에 이 스킬을 호출한다. build-worker 와 풀 4-agent 모두 같은 확정 목업 경로를 읽는다.
- impl task 또는 compact plan 에 `design: required` 가 있으면 `## 디자인 참조` 섹션에 이 스킬이 반환한 확정 목업 경로와 핵심 node-id 매핑을 적는다.

## 참조

- 확정본 규약: [`docs/plugin/design.md`](../../docs/plugin/design.md)
- public surface 계약: [`docs/plugin/positioning.md`](../../docs/plugin/positioning.md)
- `/impl`: [`skills/impl/SKILL.md`](../impl/SKILL.md)
- `/impl-loop`: [`skills/impl-loop/SKILL.md`](../impl-loop/SKILL.md)
