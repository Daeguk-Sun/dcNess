# Agent 공통 모듈 설계 원칙

> 모듈 설계 시 system-architect / module-architect / engineer / test-engineer / build-worker / architecture-validator 가 공유하는 agent 내부 기준. 호출 시 본 문서 read 의무.

본 문서는 네 가지 영역의 원칙을 한 곳에 모은 SSOT 다. 각 agent 본문에서 같은 룰을 반복해 박지 않고, 본 문서를 참조한다.

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
- engineer 의 함수 / 클래스 시그니처 결정 시

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

본 절은 hard gate 가 아니다. 빌드나 머지를 막지 않는다. pr-reviewer 의 finding 과 module-architect 의 분할 선호로 들어가며, 발견 시 자율 루프가 *이번 변경이 손대는 범위 한정* 으로 분해를 수렴시키고, 그 범위 밖 기존 누적은 후속 이슈로 분리한다. 사용자 개입은 스펙이 모호하거나 루프가 수렴하지 않을 때로 한정한다 — 소프트 신호는 "빌드를 차단하지 않는다 + PASS 로 수렴 가능하다" 라는 뜻이지 "사람이 매 finding 마다 개입한다" 가 아니다.

### 적용 영역

- module-architect — 기존 대형 파일을 건드리는 task 에서 append 대신 흐름 / 섹션 모듈 신설을 선호한다. 이번 task 가 손대는 seam 까지만 분해하고 무관한 흐름은 후속으로 남긴다.
- pr-reviewer — 이번 diff 가 이미 여러 흐름을 떠안은 파일에 또 다른 흐름을 더하는지 본다. footprint 밖 기존 누적은 MUST FIX 가 아니라 후속 권고로 둔다.

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
- engineer 의 인터페이스 구현 시
- test-engineer 의 테스트 작성 시 — 인터페이스가 위 세 룰 위반이면 SPEC_GAP_FOUND emit

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
- engineer / build-worker — 핵심 AC를 mock-only green 이 아니라 제품 경계의 동작 증거로 연결한다.
- `/spec` stories.md — Story 분할·순서 자체가 동작 증분 단위가 되도록 같은 원칙을 Story 수준에 적용한다. 상세 기준은 [`skills/spec/spec-stories-reference.md`](../../skills/spec/spec-stories-reference.md).

## 동작 증거 기준

핵심 AC 의 완료 증거를 판정하는 단일 기준이다. test-engineer / engineer / build-worker / product-acceptance 등 역할별 지침은 이 기준을 자기 단계에 적용할 뿐, 기준 자체를 다시 정의하지 않는다.

- 핵심 AC 는 "코드가 있다" 또는 "테스트가 green 이다"가 아니라, 사용자에게 약속한 동작이 실제 제품 경계(API/CLI/UI/통합 wiring/compile-time contract)에서 확인됐는지로 본다.
- 인정하는 동작 증거 — AC 성격에 맞으면: 정적 타입검사/compile, 실데이터(non-mock) 통합 테스트, UI 자동화, API/CLI smoke, 실제 앱 진입점 실행. 사람 수동 E2E 만 뜻하지 않는다.
- mock/stub/fake 는 의존 경계를 격리하는 용도로만 쓴다. mock 기반 unit test 는 보조 증거다.
- 핵심 AC 가 mock-only green 으로만 뒷받침되고 위 실제 경계가 한 번도 확인되지 않았으면 gap 이다.
- 실데이터(non-mock) 통합 테스트는 실제 parser, renderer, DB/schema, filesystem, network adapter wrapper, local fixture 같은 제품 경계를 통과하면 된다 — 외부 서비스 live 호출을 강제하는 뜻이 아니다.

역할별 적용 시점: test-engineer 는 테스트 작성 시 mock-only 로만 닫히는 AC 를 risk 로 보고하고, engineer / build-worker 는 구현 검증에서 AC 성격에 맞는 증거를 남기고, product-acceptance 는 검수에서 이 기준으로 gap 을 판정한다.

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

system-architect 가 architecture.md 의 *기술 스택* 영역에 *어떤 도구로 강제할지* 명시 의무.

### 영역 2. 모듈 공개 / 비공개 영역 구분 강제

모듈의 *공개 API* 와 *내부 구현* 영역을 언어 시스템으로 강제한다.

| 언어 / 런타임 | 도구 |
|---|---|
| TypeScript | `index.ts` 파일에서 `export` 영역 명시. 내부 파일은 import 금지 (`eslint-plugin-import` 의 `no-internal-modules`) |
| Python | `__init__.py` 의 `__all__` 영역 + 모듈 prefix `_` 영역 |
| Go | 대문자 시작 = 공개 / 소문자 시작 = 비공개 영역 (언어 시스템 영역) |
| Java | `public` / `package-private` / `private` 영역 |
| Rust | `pub` / `pub(crate)` / 기본 비공개 영역 |

module-architect 가 epic 단위 architecture.md 의 *모듈 공개 API* 영역에 명시 의무.

### 영역 3. Dependency Injection 강제

모듈이 자기 의존을 *직접 import* 하지 않고 *외부에서 주입* 받는 패턴을 강제한다. [룰 1 (의존을 만들지 말고 받아라)](#룰-1-의존을-만들지-말고-받아라) 영역의 빌드 시점 강제.

구현 패턴:

- **생성자 주입** — 클래스의 `constructor(dep1, dep2)` 영역으로 의존 받음
- **인자 주입** — 함수의 인자로 의존 받음
- **프레임워크 영역** — Spring (Java) / NestJS / Angular (TypeScript) 의 DI 컨테이너

system-architect 가 architecture.md 의 *기술 스택* 영역에 DI 패턴 명시 의무. module-architect 가 모듈 안에서 패턴 적용 의무.

### 적용 영역

- system-architect — 의존성 강제 도구 선정 + architecture.md 에 명시
- module-architect — 모듈 공개 API 영역 명시 + DI 패턴 적용
- engineer — 빌드 시점 강제 도구 설정 + 의존 작성

## 산출물 evidence 연결

본 SSOT 는 단순 read 의무로 끝나지 않는다. 적용 여부는 산출물에 남은 evidence 로 확인한다.

| Agent | evidence |
|---|---|
| [`system-architect`](../system-architect.md) | architecture 템플릿의 `Module Design Check`, 의존성 차단 도구, DI 패턴, Contract Ledger |
| [`module-architect`](../module-architect.md) | impl 템플릿의 `Module Design Check`, 작은 공개 노출 범위, contract/interface, Story 동작 수직 슬라이스, 검증 가능한 수용 기준 |
| [`engineer`](../engineer.md) | 구현 보고의 계약 준수, 의존 주입 또는 wrapper 사용, 검증 결과 |
| [`test-engineer`](../test-engineer.md) | 테스트 보고의 REQ 연결, 의존 mock 경계, 구현 독립성 |
| [`build-worker`](../build-worker.md) | phase 보고의 RED/GREEN/self-validate 증거 |
| [`architecture-validator`](../architecture-validator.md) | 설계 표준, 계약과 인터페이스, 구현 가능성 축의 finding 또는 PASS 근거 |
| [`code-validator`](../code-validator.md) | 의존 계약, 도메인/디자인 정합, 구현 위험 축의 finding 또는 PASS 근거 |

## validator 의 검증 연결

[`architecture-validator`](../architecture-validator.md) 는 본 SSOT 를 고정 checklist 로 세지 않는다. 다음 축에서 evidence 를 확인한다.

- **설계 표준**: 모듈 공개 노출 범위, 의존 방향, DI 판단, 차단 도구가 산출물에 남았는가.
- **계약과 인터페이스**: Contract Ledger 가 signature 뿐 아니라 invariant, ordering, error mode, config, consumer, forbidden alternative 를 담는가.
- **구현 가능성**: engineer 와 test-engineer 가 의존을 주입하고 결과를 관찰할 수 있는가.
- **제품 동작 슬라이스**: Story 완료 시 실제로 검증되는 동작과 첫 제품 경계 증거가 산출물에 남았는가.
- **drift 통제**: 같은 계약의 사본이 서로 다른 의미로 남지 않았는가.

자동으로 확인 가능한 신호는 적극 활용하되, grep 으로 잡히는 패턴만 검증 범위로 축소하지 않는다. 질적 판단이 필요한 영역은 finding 이 아니라 수동 review 권고로 분리해 사용자에게 보여준다.

**Contract Ledger (계약 원장) 연계** — "interface" 는 시그니처가 아니라 caller 가 올바르게 쓰기 위해 알아야 하는 **signature + invariant + ordering + error mode + config + consumer + forbidden alternative** 전부다 ([Deep Modules](#deep-modules-깊은-모듈) 의 작은 공개 노출 범위 뒤 풍부한 계약 관점의 운영화). 이 계약들은 `/design` 에서 epic architecture.md 의 `## Contract Ledger` 에 1급 산출물로 모인다. system-architect 가 작성하고, module-architect 가 public contract 변경 시 갱신하며, architecture-validator 가 stale 사본과 shallow contract 를 검토한다. 분류·분기 상세 = [`design-routing.md`](../../skills/design/design-routing.md#finding-분류-분기).

## 참조

- [`../../docs/plugin/terms.md`](../../docs/plugin/terms.md) — 용어·공개 진입점·분기 표현 수정/리뷰 시 확인
- 각 loop skill 의 `<skill>-routing.md` — agent 호출 분기 (예: [`../../skills/design/design-routing.md`](../../skills/design/design-routing.md))
- [`harness/agent_boundary.py`](../../harness/agent_boundary.py) — agent 권한 영역 (코드 SSOT)
- John Ousterhout, "A Philosophy of Software Design"
- [mattpocock skills — Deep Modules](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/deep-modules.md)
- [mattpocock skills — Interface Design](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/interface-design.md)
