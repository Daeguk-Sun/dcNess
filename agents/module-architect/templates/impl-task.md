---
depth: simple|std|deep
design: optional|required
story: <N|공통>
task_index: <i>/<total>|—
depends_on:             # [<NN-slug>, ...] 선행 task (contract/ordering 의존 흡수). 선행 없으면 [] 로 명시. 비운 채로 두면(미작성) 미상 → 병렬에서 직렬 강등
contract:
  produces:             # 이 task 가 만드는 public contract
  consumes:             # 소비하는 contract → 그 producer task 를 depends_on 에 반영
---

# <NN-task-slug>

## 사전 준비

- 읽을 문서:
- 읽을 코드:

> 선행 task 는 frontmatter `depends_on` 이 단일 SSOT 다 (병렬 독립성 판정 입력). 본문에 따로 적어 drift 시키지 않는다.

## 무엇을 만드나

-

## 왜 만드나

-

## Scope

### 수정 허용

> **한 bullet = 정확히 하나의 repo-relative 파일 경로** (또는 끝에 `/` 붙인 디렉토리). 이 목록의 교집합으로 병렬 wave 충돌이 판정된다 (정책: `docs/plugin/parallel-policy.md`). 형식이 어긋나면 파서가 경로로 인식 못 해 병렬 후보가 *조용히 직렬로 강등*된다.
> - ✅ `- src/narration/synth.py` · `- src/scene/` · `- src/api.py  # 핸들러 (# 뒤 주석은 파서가 떼어냄)`
> - ❌ 볼드/라벨 (`- **합성**: src/synth.py`) · 괄호 설명 (`- src/synth.py (TTS)`) · 다중 토큰/산문 (`- 합성 파이프라인 전반`) · 빈 bullet (`-`)
> - 부가 설명이 필요하면 위 blockquote 처럼 `>` 로 적는다 (파서가 무시). bullet 본문에는 경로만.

-

### 수정 금지

-

## Contract

| contract | owner | producer | consumer | invariant | ordering | error mode | config | forbidden alternative |
|---|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |

## 인터페이스

-

## 수용 기준

| REQ | 내용 | 검증 | 통과 조건 |
|---|---|---|---|
| REQ-001 |  | (TEST) |  |

## Module Design Check

- Deep module:
- DI/의존 주입:
- 공개 표면:
- 의존 차단:

## 주의사항

-
