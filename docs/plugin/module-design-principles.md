# 모듈 설계 원칙 SSOT

> 모듈 설계 시 모든 agent (system-architect / module-architect / engineer / test-engineer) 가 따라야 하는 공통 원칙. 호출 시 본 문서 read 의무.

본 문서는 세 가지 영역의 원칙을 한 곳에 모은 SSOT 다. 각 agent 본문에서 같은 룰을 반복해 박지 않고, 본 문서를 참조한다.

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

### 룰 3. 표면을 작게

메서드와 파라미터를 줄이면 테스트도 단순해진다. 본 룰은 [Deep Modules](#deep-modules-깊은-모듈) 의 *작은 인터페이스* 영역과 직결된다.

- 메서드 적을수록 테스트 적게 필요
- 파라미터 적을수록 테스트 셋업 단순

### 적용 영역

- module-architect 의 함수 / 클래스 시그니처 결정 시
- engineer 의 인터페이스 구현 시
- test-engineer 의 테스트 작성 시 — 인터페이스가 위 세 룰 위반이면 SPEC_GAP_FOUND emit

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
| [`system-architect`](../../agents/system-architect.md) | architecture 템플릿의 `Module Design Check`, 의존성 차단 도구, DI 패턴, Contract Ledger |
| [`module-architect`](../../agents/module-architect.md) | impl 템플릿의 `Module Design Check`, 작은 공개 표면, contract/interface, 검증 가능한 수용 기준 |
| [`engineer`](../../agents/engineer.md) | 구현 보고의 계약 준수, 의존 주입 또는 wrapper 사용, 검증 결과 |
| [`test-engineer`](../../agents/test-engineer.md) | 테스트 보고의 REQ 연결, 의존 mock 경계, 구현 독립성 |
| [`build-worker`](../../agents/build-worker.md) | phase 보고의 RED/GREEN/self-validate 증거 |
| [`architecture-validator`](../../agents/architecture-validator.md) | 설계 표준, 계약과 인터페이스, 구현 가능성 축의 finding 또는 PASS 근거 |
| [`code-validator`](../../agents/code-validator.md) | 의존 계약, 도메인/디자인 정합, 구현 위험 축의 finding 또는 PASS 근거 |

## validator 의 검증 연결

[`architecture-validator`](../../agents/architecture-validator.md) 는 본 SSOT 를 고정 checklist 로 세지 않는다. 다음 축에서 evidence 를 확인한다.

- **설계 표준**: 모듈 공개 표면, 의존 방향, DI 판단, 차단 도구가 산출물에 남았는가.
- **계약과 인터페이스**: Contract Ledger 가 signature 뿐 아니라 invariant, ordering, error mode, config, consumer, forbidden alternative 를 담는가.
- **구현 가능성**: engineer 와 test-engineer 가 의존을 주입하고 결과를 관찰할 수 있는가.
- **drift 통제**: 같은 계약의 사본이 서로 다른 의미로 남지 않았는가.

자동으로 확인 가능한 신호는 적극 활용하되, grep 으로 잡히는 패턴만 검증 범위로 축소하지 않는다. 질적 판단이 필요한 영역은 finding 이 아니라 수동 review 권고로 분리해 사용자에게 보여준다.

**Contract Ledger (계약 원장) 연계** — "interface" 는 시그니처가 아니라 caller 가 올바르게 쓰기 위해 알아야 하는 **signature + invariant + ordering + error mode + config + consumer + forbidden alternative** 전부다 ([Deep Modules](#deep-modules-깊은-모듈) 의 작은 표면 뒤 풍부한 계약 관점의 운영화). 이 계약들은 architect-loop 에서 epic architecture.md 의 `## Contract Ledger` 에 1급 산출물로 모인다. system-architect 가 작성하고, module-architect 가 public contract 변경 시 갱신하며, architecture-validator 가 stale 사본과 shallow contract 를 검토한다. 분류·라우팅 상세 = [`architect-loop-routing.md`](../../skills/architect-loop/architect-loop-routing.md#finding-분류-라우팅).

## 참조

- 각 loop skill 의 `<skill>-routing.md` — agent 호출 라우팅 (예: [`../../skills/architect-loop/architect-loop-routing.md`](../../skills/architect-loop/architect-loop-routing.md))
- [`harness/agent_boundary.py`](../../harness/agent_boundary.py) — agent 권한 영역 (코드 SSOT)
- John Ousterhout, "A Philosophy of Software Design"
- [mattpocock skills — Deep Modules](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/deep-modules.md)
- [mattpocock skills — Interface Design](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/interface-design.md)
