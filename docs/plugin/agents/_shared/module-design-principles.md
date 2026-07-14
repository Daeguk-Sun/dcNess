# Agent 공통 모듈 설계 원칙

> 모듈 설계 시 system-architect / module-architect / build-worker / architecture-validator 가 공유하는 agent 내부 기준. 호출 시 본 문서 read 의무.

본 문서는 모듈 설계 원칙을 한 곳에 모은 SSOT 다. 각 agent 본문에서 같은 룰을 반복해 박지 않고, 본 문서를 참조한다.

## Deep Modules — 깊은 모듈

> 출처: John Ousterhout, "A Philosophy of Software Design". 모듈은 *작은 인터페이스* 위에 *풍부한 구현* 이 있을 때 잘 작동한다.

### 정의

**깊은 모듈** = 작은 인터페이스 + 풍부한 구현. 외부에 노출되는 메서드와 파라미터 수가 적고, 복잡한 로직은 내부에 숨겨진다.

```
┌─────────────────────┐
│   작은 인터페이스   │  ← 메서드 적음, 파라미터 단순
├─────────────────────┤
│                     │
│                     │
│  깊은 구현          │  ← 복잡한 로직 내부에 숨김
│                     │
│                     │
└─────────────────────┘
```

**얕은 모듈** (피해야 함) = 큰 인터페이스 + 빈약한 구현. 외부 노출이 많은데 내부는 단순 통과만 한다.

```
┌─────────────────────────────────┐
│       큰 인터페이스             │  ← 메서드 많음, 파라미터 복잡
├─────────────────────────────────┤
│  빈약한 구현                    │  ← 단순 통과만
└─────────────────────────────────┘
```

### 설계 시 자문

인터페이스 정의 시 다음 세 가지를 자문한다.

1. 메서드 수를 줄일 수 있는가?
2. 파라미터를 단순화할 수 있는가?
3. 더 많은 복잡성을 내부에 숨길 수 있는가?

### 적용 영역

- module-architect 의 모듈 안 인터페이스 결정 시
- build-worker 의 함수 / 클래스 시그니처 구현 시

## 단일 파일 다중 흐름 누적

> [Deep Modules](#deep-modules-깊은-모듈) 가 모듈의 *인터페이스 모양* 을, 의존성 강제가 모듈 간 *의존 방향* 을 본다면, 본 절은 *한 파일이 떠안은 제품 흐름의 수* 를 본다. 앞 두 렌즈로는 잡히지 않는 누적이다.

### 신호

한 파일 또는 모듈이 다음으로 자라면 분해 대상이다.

- 명백히 구분되는 여러 제품 흐름(모드 / 화면 / 파이프라인)이 한 파일에 공존한다.
- 그 크기 탓에 파일을 처음 연 에이전트가 어디서 무엇이 시작되는지 cold-start 재현하기 어렵다.
- 새 능력이 새 모듈이 아니라 기존 파일에 함수 append 로만 흡수된다.

레이어를 가리지 않는다. 백엔드 usecase 든 UI entrypoint 든 같은 신호로 본다. 다만 언어 / 도구가 파일 분리를 기계적으로 강제하지 않는 영역(동적 스크립트 UI, 단일 entrypoint)에서 가장 잘 누적된다 — 의존성 강제 도구나 능력당 파일 1개 규칙이 새 파일을 강제하는 영역은 이 누적이 잘 일어나지 않는다. UI 단일 entry 가 여러 모드를 한 파일에 떠안는 경우가 대표 증상이다.

### 분해 방향

- 제품 흐름 / 섹션 단위로 가른다. 한 흐름 = 응집 모듈 하나.
- 상태 소유 / 이벤트 처리 / 렌더링 같은 관심사를 한 덩어리로 뭉치지 않는다.
- 분해의 *단위* 는 프로젝트 컨벤션을 따른다 — 웹은 컴포넌트와 훅 / 스토어, 모바일 반응형은 View 와 ViewModel(또는 State / Intent / Reducer / View), 단일 스크립트 UI 는 흐름당 모듈. 하네스는 *방아쇠*(다중 흐름 공존 / 과대 크기)와 *방향*(흐름 단위 분리)만 정하고 단위는 프로젝트에 위임한다. 프레임워크 특이 마찰(예: 전역 세션 상태)이 있으면 규칙이 아니라 가이드라인으로 받는다.

### 임계 — 정성 신호, 하드 숫자 아님

파일 줄 수 같은 수치는 *판단 보조* 로만 본다. "N줄 넘으면 분해" 같은 하드 임계는 두지 않는다 — 프레임워크마다 줄 수의 의미가 달라 거짓 양성 / 음성을 낳고, 본 SSOT 의 [정량 패턴 축소 회피](#validator-의-검증-연결)와도 어긋난다. 신호는 "여러 흐름 공존 + 그 크기로 cold-start 재현 저해" 라는 정성 판단으로 본다.

### 강제 수준 — 소프트 신호

본 절은 hard gate 가 아니다. 빌드나 머지를 막지 않는다. impl-validator 의 finding 과 module-architect 의 분할 선호로 들어가며, 발견 시 자율 루프가 *이번 변경이 손대는 범위 한정* 으로 분해를 수렴시키고, 그 범위 밖 기존 누적은 후속 이슈로 분리한다. 사용자 개입은 스펙이 모호하거나 루프가 수렴하지 않을 때로 한정한다 — 소프트 신호는 "빌드를 차단하지 않는다 + PASS 로 수렴 가능하다" 라는 뜻이지 "사람이 매 finding 마다 개입한다" 가 아니다.

### 적용 영역

- module-architect — 기존 대형 파일을 건드리는 task 에서 append 대신 흐름 / 섹션 모듈 신설을 선호한다. 이번 task 가 손대는 seam 까지만 분해하고 무관한 흐름은 후속으로 남긴다.
- impl-validator — 이번 diff 가 이미 여러 흐름을 떠안은 파일에 또 다른 흐름을 더하는지 본다. footprint 밖 기존 누적은 MUST FIX 가 아니라 후속 권고로 둔다.

## Agent Operability

Agent Operability 는 다음 agent 가 cold-start 상태에서 올바른 edit target 을 찾고, 무관한 흐름을 깨지 않으며, 검증 경로까지 닫을 수 있는지를 보는 기준이다. 목적은 파일 크기 축소가 아니라 작업 가능한 소유권과 검증 위치를 남기는 것이다.

### 기준

- edit target determinism — 새 요청을 받았을 때 어느 owner module 을 고치면 되는지 짧은 탐색으로 결정되는가.
- context locality — 한 흐름을 이해하는 데 필요한 state, event, render, usecase 호출이 같은 owner flow/module 주변에 모여 있는가.
- searchability — flow 이름, 화면/모드 이름, public entrypoint, 테스트 이름으로 owner 를 찾을 수 있는가.
- state ownership — session/global/local state key 의 owner 가 모듈 또는 flow 단위로 드러나는가.
- extension point — 다음 mode/screen/panel/flow 를 어디에 추가해야 하는지 기존 구조가 알려 주는가.
- validation locality — 해당 흐름을 바꾼 뒤 어떤 test/smoke/UI/API/CLI 경로로 확인할지 owner 근처에 남는가.
- compaction survivability — 긴 세션이 compact 되어도 산출물의 module responsibility / public interface 또는 owner/entrypoint 요약만으로 edit target, state owner, validation path 를 복구할 수 있는가.

### Flow ownership

새 mode, screen, panel, API route, CLI command, pipeline flow 가 자체 state, event, render, usecase 호출을 가지면 별도 owner flow/module 을 갖는다. entrypoint 는 mode dispatch 또는 composition wiring 역할로 제한한다. 기존 owner 가 없으면 첫 task 는 기능 append 가 아니라 seam extraction task 로 잡는다. 단일 파일 유지가 프로젝트 관례상 불가피하면, 그 파일 안에서도 owner section, state owner, validation path, future extension point 를 산출물에 명시한다.

owner module 판단에서 entrypoint 파일 자체는 owner module 로 인정하지 않는다. 함수명 prefix 또는 같은 파일 위치는 searchability 보조 신호일 뿐 owner 분리 증거가 아니다. manual-only validation 은 owner 근처 validation path 가 아니다.

### 임계 — 작업성 신호, 하드 숫자 아님

Agent Operability 는 하드 임계나 라인 수 게이트가 아니다. UI 라서 분해하거나 파일이 크다는 이유만으로 FAIL 시키지 않는다. diff 가 새 append 를 만들며 edit target, state owner, validation path 를 흐리게 할 때 이번 변경 범위의 finding 으로 드러낸다.

### 적용 영역

- system-architect — THIN_BOOTSTRAP 에서는 root architecture 에 큰 모듈 경계와 의존 방향만 얇게 남기고, CHECKPOINT 에서 epic architecture 모듈 목록의 책임/공개 인터페이스/검증 경로에 flow 별 owner module, entrypoint role, state owner, forbidden append, validation path 를 연결한다.
- module-architect — epic architecture 모듈 목록과 impl task 의 owner/entrypoint 요약을 남기고, entrypoint 를 건드리기 전에 flow owner 를 확정한다. owner 가 없으면 seam extraction task 를 앞세운다.
- impl-validator — 이번 diff 가 edit target 을 불명확하게 만들거나 state owner 를 entrypoint/session 에 흩뜨리거나 overly broad entrypoint touch 를 요구하는지 본다. owner module 없이 entrypoint append + render/helper/session/global state 흡수 + owner 근처 validation path 부재가 한 diff 에 겹치면 소프트 신호가 아니라 MUST FIX 로 승격한다 — 크기가 아니라 작업성 악화 조합이 기준이다. footprint 밖 기존 누적은 후속 권고로 둔다.

## Interface Design for Testability — 테스트 가능성 위한 인터페이스 설계

> 출처: [mattpocock skills](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/interface-design.md). 좋은 인터페이스는 테스트를 자연스럽게 만든다.

### 룰 1. 의존을 만들지 말고 받아라

함수가 의존을 직접 `new` 하지 말고 인자로 받는다. 테스트 시 Mock 주입이 가능해진다.

```typescript
// 테스트 가능
function processOrder(order, paymentGateway) {
  // paymentGateway 를 인자로 받음
}

// 테스트 어려움
function processOrder(order) {
  const gateway = new StripeGateway();  // 직접 생성
}
```

### 룰 2. 결과를 반환하라, 부작용을 만들지 말라

함수는 반환값으로 결과를 표현한다. 외부 상태를 직접 변경하면 테스트 어렵다.

```typescript
// 테스트 가능
function calculateDiscount(cart): Discount {
  return new Discount(...);
}

// 테스트 어려움
function applyDiscount(cart): void {
  cart.total -= discount;  // 외부 상태 변경
}
```

### 룰 3. 공개 노출 범위를 작게

메서드와 파라미터를 줄이면 테스트도 단순해진다. 본 룰은 [Deep Modules](#deep-modules-깊은-모듈) 의 *작은 인터페이스* 영역과 직결된다.

- 메서드 적을수록 테스트 적게 필요
- 파라미터 적을수록 테스트 셋업 단순

### 적용 영역

- module-architect 의 함수 / 클래스 시그니처 결정 시
- build-worker 의 인터페이스 구현 및 테스트 작성 시 — 인터페이스가 위 세 룰 위반이면 SPEC_GAP_FOUND emit

## Product Behavior Slices — 제품 동작 수직 슬라이스

Story 설계의 기본 단위는 레이어나 파일 묶음이 아니라 사용자가 약속받은 동작이다. task 분할은 가능한 한 작은 수직 슬라이스가 실제 제품 경계(UI/API/CLI/worker entrypoint/통합 wiring)에서 관찰되도록 만든다.

### 설계 시 자문

1. 이 Story가 끝나면 사용자가 실제로 무엇을 실행하거나 확인할 수 있는가?
2. 각 task 또는 task 묶음이 그 동작의 어느 경계를 연결하는가?
3. 첫 제품 경계 동작 증거가 마지막 task까지 밀리지 않는가?
4. 파일 경계와 병렬 독립성을 위해 동작 슬라이스를 레이어별 부품으로 찢고 있지 않은가?

### 적용 영역

- module-architect — Story 완료 시 검증되는 동작과 첫 동작 증거 지점을 impl 문서에 남긴다.
- architecture-validator — impl 문서가 레이어별 부품 task만 만들고 실제 Story 동작 책임을 비워두면 finding 으로 드러낸다.
- build-worker — 핵심 AC를 mock-only green 이 아니라 제품 경계의 동작 증거로 연결한다.
- `/spec` stories.md — Story 분할·순서 자체가 동작 증분 단위가 되도록 같은 원칙을 Story 수준에 적용한다. 상세 기준은 [`skills/spec/spec-stories-reference.md`](../../../../skills/spec/spec-stories-reference.md).

## 동작 증거 기준

핵심 AC 의 완료 증거를 판정하는 단일 기준이다. build-worker / product-acceptance 등 역할별 지침은 이 기준을 자기 단계에 적용할 뿐, 기준 자체를 다시 정의하지 않는다.

- 핵심 AC 는 "코드가 있다" 또는 "테스트가 green 이다"가 아니라, 사용자에게 약속한 동작이 실제 제품 경계(API/CLI/UI/통합 wiring/compile-time contract)에서 확인됐는지로 본다.
- 인정하는 동작 증거 — AC 성격에 맞으면: 정적 타입검사/compile, 실데이터(non-mock) 통합 테스트, UI 자동화, API/CLI smoke, 실제 앱 진입점 실행. 사람 수동 E2E 만 뜻하지 않는다.
- mock/stub/fake 는 의존 경계를 격리하는 용도로만 쓴다. mock 기반 unit test 는 보조 증거다.
- 핵심 AC 가 mock-only green 으로만 뒷받침되고 위 실제 경계가 한 번도 확인되지 않았으면 gap 이다.
- 실데이터(non-mock) 통합 테스트는 실제 parser, renderer, DB/schema, filesystem, network adapter wrapper, local fixture 같은 제품 경계를 통과하면 된다 — 외부 서비스 live 호출을 강제하는 뜻이 아니다.

역할별 적용 시점: build-worker 는 테스트·구현·검증에서 AC 성격에 맞는 증거를 남기고, product-acceptance 는 검수에서 이 기준으로 gap 을 판정한다.

## 고위험 상태 계약

저장·identity·sync/reconcile·cross-story mutable state·권한 handoff·lifecycle 처럼 상태성이 높은 계약은 "observer 가 수렴한다", "repository 가 처리한다" 같은 추상 문구만으로 닫히지 않는다. 설계와 검증 모두 계약을 실제 전이로 추적한다. 추적은 고정 표나 JSON 산출물이 아니라 의미 요구다 — durable 의미는 기존 원칙대로 module responsibility / public interface 와 decision 에 둔다.

### 위험 신호

다음 중 하나라도 있으면 고위험 상태 계약으로 본다.

- DB·파일·외부 Provider·외부 시스템이 진본(SSOT) 또는 mirror/read model 이다.
- 같은 identity 를 유지한 채 가변 상태가 바뀐다.
- sync·reconcile·eventual consistency 가 있다.
- 여러 source·tenant·account 를 합친다.
- producer 와 consumer 가 다른 Story·task·module 에 있다.
- retry·중복 이벤트·동시 실행이 가능하다.
- 권한 handoff·지속 signal·lifecycle(foreground/background 포함)이 동작을 바꾼다.
- route/input 값과 화면 내부 live state 가 달라질 수 있다.

### 적용 가능한 전이

각 계약에서 적용 가능한 전이를 확인한다. 해당 없는 전이를 억지로 채우지 않는다.

1. 최초 생성·bootstrap
2. 동일 identity 의 가변 필드 변경 (mutable projection update)
3. 삭제
4. empty 와 read failure 구분
5. source 일부 실패와 기존 상태 보존
6. 같은 입력 반복 시 no-change/idempotence
7. retry·중복 이벤트·동시 호출
8. foreground/background·resume/pause
9. route/input 값과 화면 내부 live state 가 달라지는 전이

각 전이는 trigger → producer → state owner → mutation/write → persistence/read model → consumer → 제품 경계에서 관찰되는 결과 로 끝까지 연결한다. 중간 단계가 산출물에 없거나 impl scope 가 그 단계를 수정하지 못하면 설계 gap 이다.

### 상태성 작업의 코드 SSOT 표면

계약 표면 코드 SSOT 는 공개 포트·도메인 타입·공개 entrypoint 만 뜻하지 않는다. Story 가 저장·동기화·상태 전이를 변경하면 그 전이에 참여하는 내부 구현 표면도 계약 대조 입력이다 — 저장 schema·entity·mapper, DAO·repository, sync/reconcile·state reducer, 외부 adapter·receiver·observer·worker·lifecycle producer, 관련 기존 테스트.

### 확정 결정 처리

사용자가 확정한 기술 선택 자체를 취향으로 재논쟁하지 않는다. 그러나 확정 결정은 검증 면제 대상이 아니다 — 그 선택의 downstream 완결성, 다른 Story·decision 과의 충돌, state transition·error mode·consumer 존재 여부, impl scope 안 구현 가능성은 계속 설계·검증 대상이다. "재논쟁 금지"는 선택을 다른 선택으로 교체하지 말라는 뜻이지, 선택의 완결성과 모순을 검증하지 말라는 뜻이 아니다.

### 적용 영역

- module-architect — task 를 자르기 전에 Story 간 공유 identity·state·producer/consumer·transition 을 추적하고, 뒤 Story 가 요구하는 전이 능력이 앞 Story 의 저장·동기화 계약과 task scope 에 실제로 존재하는지 확인한다.
- architecture-validator — final epic 검증에서 고위험 상태 계약을 식별하고 적용 가능한 전이를 실제 제품 경계까지 추적한다. 추상 계약 문구는 실제 update 경로 증거를 대신하지 못한다.

## 의존성 강제 — 빌드 시점 차단

모듈 간 의존을 *명시 선언* 하고, 빌드 시점에 규칙 위반을 차단한다. *코드 작성 후 회귀 검증* 영역이 아니라 *작성 시점에 차단* 영역.

### 영역 1. 순환 의존 / 미허가 의존 빌드 시점 차단

언어별 도구로 빌드 시점에 차단한다.

| 언어 / 런타임 | 도구 |
|---|---|
| TypeScript | `tsconfig.json` 의 `paths` 영역 + `eslint-plugin-import` 의 `no-cycle` / `no-restricted-paths` |
| Python | [`import-linter`](https://pypi.org/project/import-linter/) — `.importlinter` 설정 |
| Go | `internal/` 디렉토리 패턴 — 패키지 가시성 자동 제한 |
| Java | `module-info.java` — JPMS 영역 |
| Rust | crate / module 의 `pub` 가시성 영역 + `cargo-modules` 정적 분석 |

module-architect 가 epic architecture 의 모듈 목록 또는 `docs/decisions/` 에 *어떤 도구로 강제할지* 명시 의무. system checkpoint 로 승격된 경우 system-architect 가 같은 결정을 보강한다.

### 영역 2. 모듈 공개 / 비공개 영역 구분 강제

모듈의 *공개 API* 와 *내부 구현* 영역을 언어 시스템으로 강제한다.

| 언어 / 런타임 | 도구 |
|---|---|
| TypeScript | `index.ts` 파일에서 `export` 영역 명시. 내부 파일은 import 금지 (`eslint-plugin-import` 의 `no-internal-modules`) |
| Python | `__init__.py` 의 `__all__` 영역 + 모듈 prefix `_` 영역 |
| Go | 대문자 시작 = 공개 / 소문자 시작 = 비공개 영역 (언어 시스템 영역) |
| Java | `public` / `package-private` / `private` 영역 |
| Rust | `pub` / `pub(crate)` / 기본 비공개 영역 |

module-architect 가 epic 단위 architecture.md 의 *모듈 목록 공개 인터페이스* 영역에 명시 의무.

### 영역 3. Dependency Injection 강제

모듈이 자기 의존을 *직접 import* 하지 않고 *외부에서 주입* 받는 패턴을 강제한다. [룰 1 (의존을 만들지 말고 받아라)](#룰-1-의존을-만들지-말고-받아라) 영역의 빌드 시점 강제.

구현 패턴:

- **생성자 주입** — 클래스의 `constructor(dep1, dep2)` 영역으로 의존 받음
- **인자 주입** — 함수의 인자로 의존 받음
- **프레임워크 영역** — Spring (Java) / NestJS / Angular (TypeScript) 의 DI 컨테이너

module-architect 가 epic architecture 의 모듈 목록 또는 `docs/decisions/` 에 DI 패턴 명시 의무. system checkpoint 로 승격된 경우 system-architect 가 같은 결정을 보강한다.

### 적용 영역

- system-architect — THIN_BOOTSTRAP 에서는 큰 모듈 의존 방향만 남기고, CHECKPOINT 에서 의존성 강제 도구 선정 + architecture/docs decision 보강
- module-architect — 모듈 공개 인터페이스 영역 명시 + DI 패턴 적용
- build-worker — 빌드 시점 강제 도구 설정 + 의존 작성

## 산출물 evidence 연결

본 SSOT 는 단순 read 의무로 끝나지 않는다. 적용 여부는 산출물에 남은 evidence 로 확인한다.

| Agent | evidence |
|---|---|
| [`system-architect`](../../../../agents/system-architect.md) | THIN_BOOTSTRAP 의 큰 모듈 topology 또는 CHECKPOINT 보고의 system boundary 결정, module responsibility 보강, 의존성 차단 도구, DI 패턴 |
| [`module-architect`](../../../../agents/module-architect.md) | epic architecture 모듈 목록, impl 템플릿 `주의사항` 의 모듈 설계 주의, owner/entrypoint 요약, 작은 공개 노출 범위, module/decision 링크, Story 동작 수직 슬라이스, 검증 가능한 수용 기준 |
| [`build-worker`](../../../../agents/build-worker.md) | phase 보고의 RED/GREEN/self-validate 증거, 계약 준수, 의존 주입 또는 wrapper 사용 |
| [`architecture-validator`](../../../../agents/architecture-validator.md) | 설계 표준, 계약과 인터페이스, 구현 가능성 축의 finding 또는 PASS 근거 |
| [`impl-validator`](../../../../agents/impl-validator.md) | merge candidate diff 의 의존 계약, 도메인/디자인 정합, 구현 위험, Agent Operability finding 또는 PASS 근거 |

## validator 의 검증 연결

[`architecture-validator`](../../../../agents/architecture-validator.md) 는 본 SSOT 를 고정 checklist 로 세지 않는다. 다음 축에서 evidence 를 확인한다.

- **설계 표준**: 모듈 공개 노출 범위, 의존 방향, DI 판단, 차단 도구가 산출물에 남았는가.
- **계약과 인터페이스**: module responsibility 와 decision 문서가 signature 뿐 아니라 invariant, ordering, error mode, config, consumer, forbidden alternative 를 담는가.
- **구현 가능성**: build-worker 가 의존을 주입하고 결과를 관찰할 수 있는가.
- **제품 동작 슬라이스**: Story 완료 시 실제로 검증되는 동작과 첫 제품 경계 증거가 산출물에 남았는가.
- **고위험 상태 계약**: 상태성 계약의 적용 가능한 전이가 producer → state owner → consumer 경로로 닫혔는가 ([고위험 상태 계약](#고위험-상태-계약)).
- **Agent Operability**: module responsibility / public interface 와 owner/entrypoint 요약으로 edit target, state owner, validation path 를 복구할 수 있는가.
- **drift 통제**: 같은 계약의 사본이 서로 다른 의미로 남지 않았는가.

자동으로 확인 가능한 신호는 적극 활용하되, grep 으로 잡히는 패턴만 검증 범위로 축소하지 않는다. 질적 판단이라는 이유만으로 finding 에서 제외하지 않는다 — 구체적인 위치, 깨지는 시나리오, 방치 시 영향이 입증되면 Must finding 으로 올리고, 근거가 부족한 우려만 advisory 또는 수동 review 권고로 남긴다.

**Module/Decision contract 연계** — "interface" 는 시그니처가 아니라 caller 가 올바르게 쓰기 위해 알아야 하는 **signature + invariant + ordering + error mode + config + consumer + forbidden alternative** 전부다 ([Deep Modules](#deep-modules-깊은-모듈) 의 작은 공개 노출 범위 뒤 풍부한 계약 관점의 운영화). 이 계약들은 epic architecture.md 의 `## 모듈 목록` 책임/공개 인터페이스 한 줄과 `docs/decisions/NNNN-slug.md` 에 둔다. impl 문서는 module id 와 decision id/link 만 참조한다. module-architect 가 public contract 변경 시 두 진본을 갱신하며, architecture-validator 는 module/decision 과 충돌하는 구현 차단 위험을 Must finding 으로 본다. 분류·분기 상세 = [`design-routing.md`](../../../../skills/design/design-routing.md#finding-분류-분기).

## 참조

- [`docs/plugin/terms.md`](../../terms.md) — 용어·공개 진입점·분기 표현 수정/리뷰 시 확인
- 각 loop skill 의 `<skill>-routing.md` — agent 호출 분기 (예: [`skills/design/design-routing.md`](../../../../skills/design/design-routing.md))
- [`harness/agent_boundary.py`](../../../../harness/agent_boundary.py) — agent 권한 영역 (코드 SSOT)
- John Ousterhout, "A Philosophy of Software Design"
- [mattpocock skills — Deep Modules](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/deep-modules.md)
- [mattpocock skills — Interface Design](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/interface-design.md)
