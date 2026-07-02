# design.md 규격

> dcness 디자인 시스템 SSOT.
> Google `design.md` 공식 spec 채택 + dcness 적용 룰 추가.
> 원본: https://github.com/google-labs-code/design.md `docs/spec.md`

---

## 파일 구조

`design.md` 파일은 두 부분으로 구성된다:

- **YAML 프론트매터**: 머신이 읽는 디자인 토큰
- **마크다운 본문**: 사람이 읽는 설명과 가이드

---

## 프론트매터 스키마 (Google spec `## Schema`)

```yaml
version: <string>          # 선택. 알파 채널용.
name: <string>             # 필수.
description: <string>      # 선택.
colors:
  <token-name>: <Color>
typography:
  <token-name>: <Typography>
rounded:
  <scale-level>: <Dimension>
spacing:
  <scale-level>: <Dimension | number>
components:
  <component-name>:
    <token-name>: <string | token-reference>
```

**타입 정의**

| 타입 | 형식 |
|---|---|
| `Color` | `#` 로 시작하는 16진수 색상 코드 |
| `Typography` | `fontFamily` / `fontSize` / `fontWeight` / `lineHeight` / `letterSpacing` / `fontFeature` / `fontVariation` |
| `Dimension` | `px` / `em` / `rem` 단위 포함 문자열 |
| `token-reference` | `{path.to.token}` 형식 (아래 [토큰 참조 문법](#토큰-참조-문법-google-spec-design-tokens) 참조) |

---

## 토큰 참조 문법 (Google spec `# Design Tokens`)

```
{path.to.token}
```

- 프론트매터 안에서 다른 토큰을 가리킬 때 사용.
- `components` 섹션에서는 복합 토큰도 참조 가능. 예: `{typography.label-md}`
- 참조 대상이 프론트매터에 실재해야 함 — 유효하지 않은 참조는 code-validator 가 오류로 처리 ([토큰 참조 무결성 검증](#토큰-참조-무결성-검증)).

---

## 본문 섹션 순서 (Google spec `# Sections` → `### Section Order`)

| 순서 | 영문 헤더 | 한글 표기 |
|---|---|---|
| 1 | Overview | 개요 (브랜드 & 스타일) |
| 2 | Colors | 색상 |
| 3 | Typography | 타이포그래피 |
| 4 | Layout | 레이아웃 & 간격 |
| 5 | Elevation & Depth | 고도 & 깊이 |
| 6 | Shapes | 도형 |
| 7 | Components | 컴포넌트 |
| 8 | Do's and Don'ts | 권장 사항 및 금지 사항 |

헤더는 영문을 기준으로 하며 한글 병기는 선택.

---

## dcness 적용 룰

### 조건부 read

UI 없는 프로젝트 (dcness self 포함) 에서 `design.md` 미존재 시 silent skip.
agent 는 파일 부재를 오류로 처리하지 않는다.

### Static HTML 시안 규약

designer 산출물은 `design-variants/<screen>-v<N>.html` 형태의 static HTML 단일 파일이다. 별도 build, dev server, 프레임워크 런타임을 요구하지 않는다.

HTML 시안은 다음을 포함한다:

- `:root` CSS custom property 토큰
- 주요 화면/컴포넌트의 `data-node-id`
- 기본/hover/focus/disabled/empty/error 등 필요한 상태 표현

engineer 는 제품 코드를 구현할 때 HTML 시안 경로, `data-node-id`, 토큰 이름을 handoff 기준으로 삼는다.

### 토큰 참조 무결성 검증

`{colors.X}` 등 참조가 프론트매터에 실재해야 함.
**검증 담당**: `agents/code-validator.md` (코드 검증 단계의 체크 항목).
`architecture-validator` 는 본 검증 비대상.

### 외부 import 1회 변환

VoltAgent ecosystem (getdesign.md) 등 외부 `design.md` 가져올 때 LLM 1회 변환으로 dcness 룰 정합.
호환 변환 레이어 별도 신설 없음.

### 권장 토큰 이름 (Google spec `# Recommended Token Names (Non-Normative)`)

표준 권장 이름을 따르면 외부 ecosystem import / export 호환성이 높아진다. 다른 이름도 spec 상 허용.

**colors**: `primary` / `secondary` / `tertiary` / `neutral` / `surface` / `on-surface` / `error`

**typography**: `headline-display` / `headline-lg` / `headline-md` / `body-lg` / `body-md` / `body-sm` / `label-lg` / `label-md` / `label-sm`

**rounded**: `none` / `sm` / `md` / `lg` / `xl` / `full`

---

## 알 수 없는 내용 처리 (Google spec `# Consumer Behavior for Unknown Content`)

| 시나리오 | 처리 방식 |
|---|---|
| 알 수 없는 섹션 헤딩 | 보존 (무시하지 않음) |
| 알 수 없는 토큰 이름 | 값이 유효하면 허용 |
| 알 수 없는 컴포넌트 속성 | 경고와 함께 허용 |
| 중복 섹션 헤딩 | 오류 — 거부 |

---

## 사용 예시

아래는 새 프로젝트에서 처음 만들 때 복사할 수 있는 최소 구성이다.

```markdown
---
name: MyApp
colors:
  primary: "#6750A4"
  on-surface: "#1C1B1F"
  surface: "#FFFBFE"
typography:
  body-md:
    fontFamily: "Roboto"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.43
---

## Overview

MyApp 의 기본 색상은 보라색 계열이며 Material You 기반이다.

## Colors

- `primary`: 주요 액션, 버튼 배경
- `on-surface`: 본문 텍스트
- `surface`: 배경 기본값
```

> `init-dcness` 실행 시 본 예시를 프로젝트에 inline 으로 embed 한다.

---

## AI 슬롭 안티패턴 (Don'ts)

[본문 섹션 순서](#본문-섹션-순서-google-spec-sections-section-order) 표의 8번 "Do's and Don'ts" 위치에서 **Don'ts** 카탈로그. designer / engineer 가 UI 작업 시 본 항목 회피 의무 — 위반 시 code-validator 가 grep 으로 검출 후 보고 (강제 X, 경고).

| 금지 사항 | 이유 |
|-----------|------|
| `backdrop-filter: blur()` (glass morphism) | AI 템플릿의 가장 흔한 징후. 도구 UI 라면 불필요한 장식 |
| 배경 그라데이션 텍스트 (`gradient-text`) | AI 가 만든 SaaS 랜딩의 1번 특징. 가독성 저하 |
| "Powered by AI" 배지 / "AI-driven" 카피 | 기능이 아니라 장식. 사용자 가치 0 |
| `box-shadow` 글로우 애니메이션 (네온 글로우) | AI 슬롭의 강한 신호. 도구 답지 않음 |
| 보라·인디고 브랜드 색상 ("AI = 보라색" 클리셰) | 프로젝트 정체성 부재 시 default 로 흘러가는 함정 |
| 모든 카드에 동일한 `rounded-2xl` (균일 둥근 모서리) | 균일성은 템플릿 느낌. 위계 없음 |
| 배경 gradient orb (`blur-3xl` 원형 / blob) | 모든 AI 랜딩 페이지에 있는 장식. 의미 0 |

### 적용 원칙

- **도구처럼 보여야 한다** — 마케팅 페이지가 아니라 매일 쓰는 대시보드. 화면 = 기능 전달, 장식 = 최소.
- **위계 = 사이즈 + 굵기 + 간격** — 그라데이션 / 글로우 / blur 로 만들어진 위계 X. 본문 가독성이 우선.
- **클리셰 회피** — 위 7 항목은 *AI가 만든 모든 SaaS* 의 공통 신호. 회피만 해도 80% 슬롭 회피.

> 출처: jha0313/harness_framework `docs/UI_GUIDE.md` 의 안티패턴 표 dcness 정합 흡수 (이슈 #309).
