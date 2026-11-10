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
/compact "[이전 세션 이어가기 — DCN smart-compact 생성] # 과제 원문 <AC 원문 또는 사용자 요청 원문> # 현재 하던 일과 다음 단계 - 현재: <branch, 하던 작업, 끊긴 지점> - 다음: <1~3개> # 완료 판정 조건 - <남은 AC, 통과해야 할 명령> # 사용자 지시·선호 - <지시·금지·선호> # 결정과 미해결 의논거리 - 결정: <채택안 + 이유> - 미해결: <사용자 결정 대기> # 포인터 - 파일: <pathlist> - 문서·이슈·PR: <links>"
```

> `/compact "<text>"` 인자 = additional context. CC 가 압축 시 그 단락을 *반드시 보존* 한다.

**가독성 형식 (transcript 출력용)** — 메인이 사용자에게 보여줄 때는 줄바꿈 보존:

```
[이전 세션 이어가기 — DCN smart-compact 생성]

# 과제 원문
<이슈 작업이면 AC 원문을 명령 출력으로 붙인다 — 모델이 다시 쓰지 않는다. 이슈가 없으면 사용자 요청 원문>

# 현재 하던 일과 다음 단계
- 현재: <branch, 하던 작업, 끊긴 지점, uncommitted 상태>
- 다음: <바로 이어서 할 일 1~3개>

# 완료 판정 조건
- <무엇이 확인되면 끝인지 — 남은 AC, 통과해야 할 명령, 사람 확인 대기 항목>

# 사용자 지시·선호
- <이번 세션에서 사용자가 준 지시·금지·선호. 없으면 "없음">

# 결정과 미해결 의논거리
- 결정: <다음 단계에 영향을 주는 채택안 + 이유>
- 미해결: <사용자 결정 대기 항목>

# 포인터
- 파일: <pathlist>
- 문서·이슈·PR: <links>
```

이 형식은 작업 경위가 아니라 **다음 일에 필요한 사실**을 고른다. 압축 뒤 정확도를 가장 잘 보존하는 요약은 지난 작업을 충실히 서술한 요약이 아니라 과제 원문, 현재 하던 일과 다음 단계, 완료 조건과 포인터를 고른 요약이라는 관찰(arXiv 2611.05306 "You don't need long context", Appendix A)을 따른다. 사람이 중간에 지시하는 작업은 압축 뒤 사용자 선호가 가장 먼저 사라지므로 사용자 지시·선호를 따로 둔다. 최근 머지 PR 같은 작업 경위는 다음 단계 판단에 필요할 때만 포인터로 남긴다.

→ 클립보드 쓸 때는 `/compact "<text>"` 한 줄로 (CC 슬래시 명령 단일 인자 처리).

## 절차

### Step 1 — 자동 추출

메인이 자체 LLM 두뇌로 다음 정보 수집:

1. **과제 원문** — 현재 작업 대상 이슈가 있으면 Step 3 의 `gh issue view` 명령 출력으로 AC 원문을 붙인다. 모델이 요약하거나 다시 쓰지 않는다. 이슈가 없으면 transcript 의 사용자 요청 원문을 옮긴다.
2. **`git status --short`** + 현재 branch → 하던 일과 uncommitted 상태
3. **TaskList** → 미완료 task, 다음 단계
4. **완료 판정 조건** — 남은 AC, 통과해야 할 검증 명령, 사람 확인 대기 항목
5. **사용자 지시·선호** — transcript 에서 사용자가 준 지시·금지·선호 (예: "머지는 명시 지시 때만", "워크트리 없이")
6. **현재 transcript 의 결정과 미해결 의논거리** — 다음 단계에 영향을 주는 결정 근거, 사용자 결정 대기 중인 옵션

### Step 2 — 자동 prompt 생성

메인이 위 정보를 위 형식 템플릿에 채워넣어 resume prompt 본문 작성.

### Step 3 — `/compact "<resume prompt>"` 명령 한 줄로 클립보드 복사

```bash
# resume prompt 본문 (가독성 형식, 줄바꿈 포함)
RESUME_HEAD=$(cat <<'EOF'
[이전 세션 이어가기 — DCN smart-compact 생성]

# 과제 원문
EOF
)
# 이슈 작업이면 AC 원문을 명령 출력으로 붙인다 — 모델이 다시 쓰지 않는다.
# Issue Brief 형식이 아니면 awk 없이 본문 전체를 쓰고, 이슈가 없으면 사용자 요청 원문을 RESUME_HEAD 에 직접 쓴다.
TASK_SOURCE=$(gh issue view <N> --json body --jq .body \
  | awk '/^\*\*Acceptance criteria:\*\*/{f=1} /^\*\*Human verification/{f=0} f')
RESUME_TAIL=$(cat <<'EOF'

# 현재 하던 일과 다음 단계
...
EOF
)
RESUME="$RESUME_HEAD
$TASK_SOURCE
$RESUME_TAIL"

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
- **과제 원문** — AC 원문은 명령 출력 그대로. 요약본이 원문을 대신하지 않는다
- **완료 판정 조건** — 다음 세션이 끝났는지 바로 판단할 기준
- **사용자 지시·선호** — 이번 세션에서 받은 지시·금지·선호
- **현재 미해결 결정** — 사용자가 직전 메시지에서 옵션 받고 답 안 한 것들
- **핵심 결정 reasoning** — "왜 옵션 A 채택" (단순 결과만 아니라 근거)
- **진행 중 branch + uncommitted state**

### 제외 (priority ↓)
- 작업 경위 서술 (최근 PR·commit 목록) — 다음 단계 판단에 필요한 것만 포인터로
- 단순 도구 호출 결과 (테스트 통과 numbers 정도만 요약)
- 옵션 검토 후 폐기된 안 (rationale 에 적혀있으면 reference)
- skip
- 자체 reasoning 의 중간 단계 ("음 이거 어떻게 할까" 류)

## 예시 출력

```
[이전 세션 이어가기 — DCN smart-compact 생성]

# 과제 원문
**Acceptance criteria:**
- [x] [command] 오프라인 상태에서 채팅방 진입 시 안내 문구가 보이는 UI 테스트가 통과한다.
- [ ] [command] 네트워크 복구 뒤 대기 중 메시지가 순서대로 전송되는 테스트가 통과한다.
- [ ] [agent-read] 재전송 실패 시 사용자에게 재시도 버튼을 보여 주는 동작이 화면 흐름 문서와 일치한다.

# 현재 하던 일과 다음 단계
- 현재: feature/offline-resend branch, 재전송 큐 구현 중. 순서 보장 테스트가 RED(2건 중 1건 실패), uncommitted 2파일
- 다음: 순서 보장 테스트 GREEN → 재시도 버튼 화면 흐름 대조 → PR

# 완료 판정 조건
- 남은 AC 2건 체크, 전체 unit test 통과
- 사람 확인 대기: 실제 기기에서 비행기 모드 전환 시나리오

# 사용자 지시·선호
- 머지는 명시 지시 때만
- 재시도 버튼 문구는 디자이너 확정 전까지 임시 문구 유지

# 결정과 미해결 의논거리
- 결정: 대기 메시지는 메모리가 아니라 로컬 DB 에 저장 — 앱 재시작 뒤에도 유지해야 해서
- 미해결: 재전송 최대 횟수(3회 vs 무제한) 사용자 결정 대기

# 포인터
- 파일: 재전송 큐 모듈, 오프라인 UI 테스트
- 문서·이슈·PR: 해당 story 이슈 링크, 화면 흐름 문서 경로
```

## 한계

- 메인이 자체 추출이라 누락 가능 — 사용자가 출력 검토 + 추가 컨텍스트 쓸 수 있도록 prompt 마지막에 "추가 메모" 빈칸 둠
- clipboard 도구 없는 환경 (Linux 일부) — 파일 백업으로 fallback
- 컨텍스트 크면 추출 자체도 토큰 소모 — 60%+ 시점이면 선제 실행 권장
- **`/compact` 인자 길이 한도** — CC chat input 의 단일 행 길이 제한 가능. resume prompt 가 너무 길면 paste 후 일부 잘림 위험. 짧게 추출 권장 (과제 원문은 AC 부분만 / 결정 핵심만 / 미해결 의논거리 1~3개)
- **`/compact` 자동 실행 X** — Anthropic 공식 docs 정합 (메인 turn 안에서 슬래시 명령 자동 실행 불가). 사용자가 chat input 에 paste + enter 1 action 필요

## 참조

- CC 내장 `/compact` — 단순 요약. 본 skill 은 능동 추출 + resume prompt.
- GitHub issue 본문 (`gh issue view`) — 과제 원문과 완료 판정 조건 source
- [arXiv 2611.05306 "You don't need long context"](https://arxiv.org/abs/2611.05306) Appendix A — 압축 형식 근거
