# 문서 참조 표기 규약 (Doc Conventions)

> dcNess 외부 배포 문서의 **섹션 참조 표기** 단일 SSOT.
> cross-ref 무결성 CI(`scripts/check_cross_refs.mjs` / `cross-ref-validation.yml`)가
> 본 규약의 anchor 링크 부분을 강제한다.

## 왜 이 규약이 필요한가

섹션을 `§3.2` 같은 **위치번호**로 가리키면 두 문제가 생긴다.

1. **정합성 사각** — 섹션이 추가되면 아래 번호가 밀리는데, 다른 문서의 `hooks.md §3.2`
   참조는 그대로 남아 엉뚱한 섹션을 가리킨다. cross-ref CI는 markdown anchor 링크만
   검증하고 prose `§N.M`은 검증하지 못한다 → 조용히 썩는다.
2. **대화 불투명** — "§1.2를 보세요"는 그 번호가 무슨 내용인지 알 수 없는 토큰이다.

## 핵심 규칙

1. **위치번호 참조 금지** — `§3.2`·`§1.2`로 섹션을 가리키지 않는다.
2. **heading 번호 금지** — `## 1. 작업 절차`가 아니라 `## 작업 절차`. heading에 순번을
   붙이면 anchor(`#1-작업-절차`)가 번호를 머금어 같은 문제가 생긴다.
3. **제목 기반 anchor 링크 사용** — 섹션 참조는 클릭 가능한 markdown anchor 링크로.

## 표기 방법

| 맥락 | Before (금지) | After (권장) |
|---|---|---|
| 문서 간 | `hooks.md §3.2` | `[hooks.md의 catastrophic 시퀀스](../plugin/hooks.md#catastrophic-시퀀스)` |
| 문서 내 | `§1.2 참조` | `[작업 절차](#작업-절차)` |
| 대화(메인→사용자) | "§1.2를 보세요" | "`CLAUDE.md`의 작업 절차 절을 보세요" |

> 위 After 칸은 표기 *예시*라 인라인 코드로 감쌌다(실제 링크 아님). 본문에서 실제 섹션을
> 참조할 땐 백틱 없이 `[제목](경로#slug)` 형태의 진짜 링크로 쓴다.

## anchor slug 규칙

GitHub 방식 (cross-ref CI의 `slugify`와 동일):
- 소문자화 → 특수문자(`§`·점 등) 제거 → 공백을 `-`로. 한글·영숫자·하이픈 보존.
- 예: `## dcness 강제 원칙` → `#dcness-강제-원칙`
- 같은 파일에 동일 제목 heading이 둘이면 GitHub이 `-1` suffix를 붙인다 → 제목 유일성 권장.

## 유지하는 번호 (위치번호 아님)

번호가 *이름의 일부*인 고유식별자는 그대로 둔다. 참조할 때도 제목 anchor로.
- `Step 3`·`Phase 2` — 절차 단계 고유명
- `ADR-001` — 결정 기록 ID
- `F1`~`F14`·`M1`/`N`/`H1`/`L2` — 외부 실측 이슈·audit 코드
- `task_index: i/total` — 기술 명세

## 예외 (변환·검증 제외)

- **코드펜스/인라인코드 안의 `§`** — sample 명령어·코드 주석. cross-ref CI가 코드블록을 검증 제외.
- **historical 문맥** — "옛/폐기/deprecated/legacy"가 같은 줄에 있는 `§`(과거 기록 인용).
  DENY_LIST의 `HISTORICAL_CTX_RE` 예외.

## 적용 범위

외부 배포 영역: `docs/plugin/**`·`skills/**`·`agents/**`·`commands/**` + 루트
`CLAUDE.md`·`README.md`·`AGENTS.md`.
(`PROGRESS.md`·`docs/internal/**`은 self 운영/changelog 문서라 제외 — 단 본 규약 문서는
 신규 작성이므로 처음부터 규약을 따른다.)

## 회귀 차단

전환 완료 후, `scripts/check_cross_refs.mjs` DENY_LIST에 prose `§[0-9]` 패턴을 추가해
새 위치번호 참조를 CI에서 차단한다(코드펜스·historical 예외 자동 적용).
