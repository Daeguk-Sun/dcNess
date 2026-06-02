# 모듈 설계 원칙 SSOT

> 모듈 설계 시 모든 agent (system-architect / module-architect / engineer / test-engineer) 가 따라야 하는 공통 원칙. 호출 시 본 문서 read 의무.

본 문서는 세 가지 영역의 원칙을 한 곳에 모은 SSOT 다. 각 agent 본문에서 같은 룰을 반복해 박지 않고, 본 문서를 참조한다.

## §1. Deep Modules — 깊은 모듈

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

## §2. Interface Design for Testability — 테스트 가능성 위한 인터페이스 설계

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

메서드와 파라미터를 줄이면 테스트도 단순해진다. 본 룰은 §1 Deep Modules 의 *작은 인터페이스* 영역과 직결된다.

- 메서드 적을수록 테스트 적게 필요
- 파라미터 적을수록 테스트 셋업 단순

### 적용 영역

- module-architect 의 함수 / 클래스 시그니처 결정 시
- engineer 의 인터페이스 구현 시
- test-engineer 의 테스트 작성 시 — 인터페이스가 위 세 룰 위반이면 SPEC_GAP_FOUND emit

## §3. 의존성 강제 — 빌드 시점 차단

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

모듈이 자기 의존을 *직접 import* 하지 않고 *외부에서 주입* 받는 패턴을 강제한다. §2 룰 1 (의존을 만들지 말고 받아라) 영역의 빌드 시점 강제.

구현 패턴:

- **생성자 주입** — 클래스의 `constructor(dep1, dep2)` 영역으로 의존 받음
- **인자 주입** — 함수의 인자로 의존 받음
- **프레임워크 영역** — Spring (Java) / NestJS / Angular (TypeScript) 의 DI 컨테이너

system-architect 가 architecture.md 의 *기술 스택* 영역에 DI 패턴 명시 의무. module-architect 가 모듈 안에서 패턴 적용 의무.

### 적용 영역

- system-architect — 의존성 강제 도구 선정 + architecture.md 에 명시
- module-architect — 모듈 공개 API 영역 명시 + DI 패턴 적용
- engineer — 빌드 시점 강제 도구 설정 + 의존 작성

## §4. 호출 시 read 의무 agent

본 SSOT 는 다음 agent 호출 시 read 의무다.

| Agent | 무엇을 위해 read 하는가 |
|---|---|
| [`system-architect`](../../agents/system-architect.md) | architecture.md 의 기술 스택 / 의존성 강제 도구 영역 결정 시 |
| [`module-architect`](../../agents/module-architect.md) | epic 단위 architecture.md 의 모듈 공개 API / 인터페이스 정의 시 |
| [`engineer`](../../agents/engineer.md) | 코드 작성 영역 — DI 패턴 / 표면 작은 인터페이스 적용 시 |
| [`test-engineer`](../../agents/test-engineer.md) | 테스트 작성 영역 — 인터페이스가 §2 룰 위반이면 SPEC_GAP_FOUND emit |

## §5. validator 의 자동 검증 영역

[`architecture-validator`](../../agents/architecture-validator.md) 가 본 SSOT 의 룰 위반 영역을 *자동 가능* 영역과 *수동 review 권고* 영역으로 분리해 검증한다.

### 자동 검증 가능 영역 (validator 가 직접)

- §3.1 순환 의존 — grep / 정적 분석으로 검출 가능
- §3.1 미허가 의존 — architecture.md 의 의존 그래프 ↔ 실제 import 영역 비교
- §3.2 public API contract 위반 — 시그니처 grep 비교

### 수동 review 권고 영역 (사용자에게 안내)

- §1 Deep Modules 의 *작은 인터페이스 + 풍부한 구현* 룰 — 질적 판단 필요
- §2 룰 2 *부작용 없는 결과 반환* 영역 — 코드 의도 판단 영역

validator prose 결론에 *자동 검증 통과 영역* + *수동 review 권고 영역* 분리 명시 의무.

## 참조

- [`docs/plugin/orchestration.md`](orchestration.md) — agent 호출 시퀀스
- [`harness/agent_boundary.py`](../../harness/agent_boundary.py) — agent 권한 영역 (코드 SSOT)
- John Ousterhout, "A Philosophy of Software Design"
- [mattpocock skills — Deep Modules](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/deep-modules.md)
- [mattpocock skills — Interface Design](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/interface-design.md)
