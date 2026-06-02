# AGENTS — Common Instructions

작업 규칙 SSOT: [`CLAUDE.md`](CLAUDE.md). 본 파일은 *지침* 일 뿐 규칙을 *재기술하지 않는다*.

## 모든 에이전트(사람 포함) 강제 절차

1. **branch → PR → merge** (main 직접 commit 금지)
2. **commit 직전**: git pre-commit hook 자동 실행 (main-block + pytest).
3. **PR**: `.github/PULL_REQUEST_TEMPLATE.md` 체크리스트 작성.

## 금지

- `git commit --no-verify` 등 hook 우회.
- `CLAUDE.md` 외 파일에 작업 규칙 *재기술*. 참조만.

## 환경별 설정

### Claude Code

`.claude/settings.json` 에 PreToolUse hook(`cc-pre-commit.sh`)이 등록되어 `git commit` 실행 시 자동으로 게이트가 작동한다. 별도 조치 불필요.

### 외부 에이전트 (Codex 등) / 사람

git pre-commit hook 1회 설치:

```sh
cp scripts/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

이후 모든 `git commit` 이 자동 검사된다.

## Prose-Only 패턴 (검증 에이전트)

본 저장소는 [`docs/plugin/orchestration.md`](docs/plugin/orchestration.md) §0 (Prose-Only 원칙 — 형식 강제 X) 에 따라 검증 결과를 **자유 prose** 로 emit 한다. 검증 에이전트(code-validator, architecture-validator, plan-reviewer, pr-reviewer 등) 호출 시:

1. **stdout 으로 prose**: 형식 자유 (markdown / 평문 / 표). harness 가 prose 파일로 저장(`.claude/harness-state/<run_id>/<agent>[-<MODE>].md`).
2. **결론 enum**: prose 의 *마지막 단락* 에 enum 단어 1개 명시 (검증 에이전트 통일 — `PASS` / `FAIL` / `ESCALATE`). 모호한 표현 금지.
3. **이유 필수**: 결론 근거 = 파일 path + 라인 번호 + 구체적 사실. 추측 금지.
4. **폐기된 컨벤션**:
   - `---MARKER:X---` 마지막 줄 정형 + `MARKER_ALIASES` 폴백 (사다리 자체 폐기)
   - status JSON `@OUTPUT_FILE` / `@OUTPUT_SCHEMA` / `@OUTPUT_RULE` (이전 dcNess 패턴 — JSON 형식도 형식 강제)
   - `preamble.md` 자동 주입 / agent-config 별 layer (자기완결 docs)
   - 모두 사용 금지.

자세한 형식: [`agents/code-validator.md`](agents/code-validator.md), [`agents/architecture-validator.md`](agents/architecture-validator.md), [`docs/plugin/orchestration.md`](docs/plugin/orchestration.md) §0.

orchestrator 측 결론 routing 은 메인 Claude 가 prose 자체를 직접 읽고 판단 (prose-only, 이슈 #280/#284). [`harness/signal_io.py`](harness/signal_io.py) 는 prose 파일 I/O (`write_prose` / `read_prose`) 만 담당 — `MissingSignal` 은 not_found / empty 단일 normalize.

## 참조

- [`CLAUDE.md`](CLAUDE.md) — 작업 규칙 SSOT
- [`docs/plugin/orchestration.md`](docs/plugin/orchestration.md) §0 — Prose-Only 원칙 현행 SSOT (강제 영역 2 + 안티패턴 4)
- [`PROGRESS.md`](PROGRESS.md) — 현재 상태 / TODO / Blockers
- [`README.md`](README.md) — 프로젝트 개요 + Quick Start
