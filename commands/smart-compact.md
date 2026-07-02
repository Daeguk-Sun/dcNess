---
name: smart-compact
description: 현재 세션의 의도/결정/진행상태를 능동 추출 → `/compact "<resume prompt>"` 형태 한 줄 명령을 클립보드에 복사하는 스킬. 사용자가 chat 입력창에 paste + enter 1 action 으로 *같은 세션* 안에서 `/compact` 실행 (컨텍스트 압축 + resume prompt 보존). 사용자가 "스마트 컴팩트", "smart-compact", "/compact 보다 똑똑하게", "컨텍스트 압축", "다음 세션 이어가기", "리줌 프롬프트" 등을 말하거나 컨텍스트 사용량이 60%+ 일 때 사용한다. CC 내장 `/compact` 와 차이 — 메인이 직접 의미 추출 + 명령 한 줄 씀.
---

# Smart Compact Skill

> CC 의 `/compact` 는 단순 요약. 본 skill 은 메인이 *현재 세션의 의도/결정/진행상태* 를 능동 추출 + `/compact "<resume prompt>"` 명령 한 줄 형태로 클립보드 복사. 사용자 paste + enter 1 action = 같은 세션 안에서 `/compact` 실행 + resume prompt 보존.

## CC 슬래시 명령 자동 실행 한계

Anthropic 공식 docs ([Skill 제한](https://code.claude.com/docs/en/extend-skills#restrict-claudes-skill-access)) — 메인 LLM 의 turn 안에서 `/compact` 자동 실행 *불가*. 슬래시 명령은 *사용자 chat input* 에서만 parse. Skill tool 도 `/compact` 미지원 (`/init` / `/review` / `/security-review` 만 가능).

→ 본 skill 은 *명령 한 줄을 클립보드에 써둠*. 사용자가 chat input 에 paste + enter = 같은 세션 안에서 한 번에 실행.

## 언제 사용

- 사용자 발화에 "smart-compact", "스마트 컴팩트", "컨텍스트 압축", "리줌", "이어가기", "context 60%+" 등
- 또는 메인이 자체 판단으로 컨텍스트 부담 ↑ 감지 시

## 출력 형식 — `/compact "<resume prompt>"` 명령 한 줄

클립보드에 박힐 최종 형태 = 한 줄 (사용자가 paste + enter):

```
/compact "[이전 세션 이어가기 — DCN smart-compact 생성] # 프로젝트 <레포 root, 현재 branch> # 최근 진행 (최근 PR 5~10개) - PR #X — 한 줄 요약 - ... # 핵심 디자인 결정 - 결정 1: 채택안 + 이유 - ... # 진행 중 작업 - 현재 분기: <branch> - 미완료 task: <list> - staged 변경: <요약> # 다음 단계 후보 - 옵션 A - ... # 미해결 의논거리 - Q1: ... # 컨텍스트 - 핵심 파일: <pathlist> - 핵심 docs: <pathlist> - 테스트 상태: <X/Y PASS>"
```

> `/compact "<text>"` 인자 = additional context. CC 가 압축 시 그 단락을 *반드시 보존* 한다.

**가독성 형식 (transcript 출력용)** — 메인이 사용자에게 보여줄 때는 줄바꿈 보존:

```
[이전 세션 이어가기 — DCN smart-compact 생성]

# 프로젝트
<레포 root, 현재 branch>

# 최근 진행 (최근 PR / Task-ID 5~10개)
- PR #X (Task-ID Y) — 한 줄 요약
- ...

# 핵심 디자인 결정 (현재 작업과 관련된 것만)
- 결정 1: 채택안 + 이유
- 결정 2: ...

# 진행 중 작업
- 현재 분기: <branch>
- 미완료 task: <list>
- staged 변경: <git diff --cached --stat 요약>

# 다음 단계 후보 (사용자가 결정 받았던 것들)
- 옵션 A
- 옵션 B
- ...

# 미해결 의논거리 (사용자 결정 대기)
- Q1: ...
- Q2: ...

# 컨텍스트 추가 (자동 디스커버용)
- 핵심 파일: <pathlist>
- 핵심 docs: <pathlist>
- 테스트 상태: <X/Y PASS>
```

→ 클립보드 쓸 때는 `/compact "<text>"` 한 줄로 (CC 슬래시 명령 단일 인자 처리).

## 절차

### Step 1 — 자동 추출

메인이 자체 LLM 두뇌로 다음 정보 수집:

1. **`git log --oneline -10`** + **`git status --short`** → 최근 commit / 현재 branch / staged
2. **`gh pr list --state merged --limit 5 --json number,title,mergedAt,body`** → 최근 머지된 작업 (WHAT/WHY 통합)
3. **`PROGRESS.md`** 상단 → 진행 상태 요약
4. **TaskList** → 미완료 task
5. **현재 transcript 의 미해결 의논거리** — 메인이 자체 식별 (사용자 결정 대기 중인 옵션들)
6. **테스트 상태** — `python3 -m unittest discover -s tests` 안 돌리고 최근 PR 본문의 검증 결과 사용

### Step 2 — 자동 prompt 생성

메인이 위 정보를 위 형식 템플릿에 채워넣어 resume prompt 본문 작성.

### Step 3 — `/compact "<resume prompt>"` 명령 한 줄로 클립보드 복사

```bash
# resume prompt 본문 (가독성 형식, 줄바꿈 포함)
RESUME=$(cat <<'EOF'
[이전 세션 이어가기 — DCN smart-compact 생성]

# 프로젝트
...
EOF
)

# /compact 명령 한 줄 = 줄바꿈을 \n 로 escape 안 함 (그대로 써도 CC 가 single arg 로 처리).
# 따옴표 escape 만 처리.
ESCAPED=$(printf '%s' "$RESUME" | sed 's/"/\\"/g')
COMPACT_CMD="/compact \"$ESCAPED\""

# macOS clipboard 복사
printf '%s' "$COMPACT_CMD" | pbcopy
# Linux: xclip / xsel
# Windows: clip

echo "[smart-compact] '/compact \"<resume prompt>\"' 명령 클립보드 복사 완료."
echo "[smart-compact] chat 입력창에 paste + enter = 같은 세션 안에서 /compact 실행 (컨텍스트 압축 + resume prompt 보존)."
```

또한 메인 transcript 에 resume prompt 본문 *가독성 형식* 그대로 출력 (사용자가 미리 검토 + 추가 수정 가능).

### Step 4 — 파일 백업 (선택)

```bash
mkdir -p .claude/resume-prompts
cat > ".claude/resume-prompts/$(date +%Y%m%d-%H%M%S).md" << 'EOF'
<resume prompt 본문 — 가독성 형식>
EOF
```

이러면 클립보드 깨져도 파일에서 복구 가능. 또한 `/compact` 인자 길이 한도 초과 시 사용자가 파일에서 잘라낸 짧은 prompt 로 재시도 가능.

## 추출 가이드라인

### 포함 (priority ↑)
- **현재 미해결 결정** — 사용자가 직전 메시지에서 옵션 받고 답 안 한 것들
- **핵심 결정 reasoning** — "왜 옵션 A 채택" (단순 결과만 아니라 근거)
- **진행 중 branch + uncommitted state**
- **다음 step 후보들** — 메인이 사용자에게 제시했던 선택지들

### 제외 (priority ↓)
- 단순 도구 호출 결과 (테스트 통과 numbers 정도만 요약)
- 옵션 검토 후 폐기된 안 (rationale 에 적혀있으면 reference)
- skip
- 자체 reasoning 의 중간 단계 ("음 이거 어떻게 할까" 류)

## 예시 출력 (이 세션 기준)

```
[이전 세션 이어가기 — DCN smart-compact 2026-04-29 22:00]

# 프로젝트
~/project/dcNess (main branch, plugin 개발 중)

# 최근 진행
- /to-issue issue drafting 흐름 정리 완료
- /impl-loop 병렬 peer 세션 정책 정리 완료
- PR #34 (DCN-CHG-35): multi-session e2e smoke 머지
- PR #33 (DCN-CHG-34): hooks/ 인프라 머지
- PR #32 (DCN-CHG-33): session_state.py CLI 확장 머지

# 핵심 디자인 결정
- Task tool + Agent + helper + 훅 패턴 채택 (Python `run_conveyor` 실행기 폐기)
- heuristic-only enum 추출 (haiku 미사용 — API 키 의존 회피)
- by-pid 레지스트리로 멀티세션 격리
- AMBIGUOUS = 메인 단독 판단 X, agent 재호출 → 사용자 위임 cascade

# 진행 중 작업
- branch: main (clean)
- 160/160 tests PASS

# 다음 단계 후보 (사용자 결정 대기)
- /init-dcness skill (enable/disable)
- /ux skill (static HTML 시안 흐름)
- commands/ 카테고리 추가
- ~~worktree 도입~~ → 옵션 D 채택 완료 — 행동형 skill 진입 시 EnterWorktree 기본 켜짐, 거부 표현 시에만 건너뜀 (loop-procedure §1.1)
- manual smoke (실 claude 에서 /spec → /design → /impl 흐름 검증)

# 미해결 의논거리
- ~~worktree 옵션 C vs D~~ → **D 채택 완료** (#255 정합). 행동형 skill 기본 켜짐, 거부 표현 정규식 `워크트리\s*(빼|없|말)`
- sid 대체 처리 (worktree 진입 시 main repo .claude/ 와 어떻게 cross-ref) → γ resolution 으로 해결 (`harness/session_state.py:_default_base`, 5 tests PASS)

# 컨텍스트
- 핵심: harness/session_state.py, harness/hooks.py, hooks/*.sh, commands/*.md
- spec: docs/archive/conveyor-design.md (v2 Task tool 패턴, 역사 자료), docs/plugin/loop-procedure.md
- agents/*.md 12개 모두 자유서술 방식 (DCN-CHG-27)
- 기준: CLAUDE.md 강제 원칙 + docs/plugin/workflow-router.md

다음 세션은 worktree 도입 의논 이어서 + manual smoke 또는 /init-dcness 진행.
```

## 한계

- 메인이 자체 추출이라 누락 가능 — 사용자가 출력 검토 + 추가 컨텍스트 쓸 수 있도록 prompt 마지막에 "추가 메모" 빈칸 둠
- clipboard 도구 없는 환경 (Linux 일부) — 파일 백업으로 fallback
- 컨텍스트 크면 추출 자체도 토큰 소모 — 60%+ 시점이면 선제 실행 권장
- **`/compact` 인자 길이 한도** — CC chat input 의 단일 행 길이 제한 가능. resume prompt 가 너무 길면 paste 후 일부 잘림 위험. 짧게 추출 권장 (PR 5개 / 결정 핵심만 / 미해결 의논거리 1~3개)
- **`/compact` 자동 실행 X** — Anthropic 공식 docs 정합 (메인 turn 안에서 슬래시 명령 자동 실행 불가). 사용자가 chat input 에 paste + enter 1 action 필요

## 참조

- CC 내장 `/compact` — 단순 요약. 본 skill 은 능동 추출 + resume prompt.
- GitHub PR 본문 + `gh pr list` — WHAT/WHY 추적 source (#182 후 dcness 자체 로그 시스템 폐기)
- `PROGRESS.md` — 진행 상태 source
