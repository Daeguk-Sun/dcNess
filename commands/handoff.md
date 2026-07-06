---
name: handoff
description: 세션을 넘기기 전 의도/결정/진행/다음 액션을 `.dcness-work/handoffs/next-session.md` 에 인계 문서로 기록하는 command. 다음 세션 SessionStart 훅이 이 파일을 additionalContext 최상단에 최우선 주입한 뒤 archive 로 옮겨 clear 한다. CC auto-memory(불투명·모델 임의 저장)에 의존하지 않는 결정적 cross-session 인계다. 사용자가 "/handoff", "핸드오프 만들어줘", "핸드오프 문서 써줘", "인계 문서 작성해줘", "세션 인계", "다음 세션에 넘겨줘" 등을 말할 때 사용한다.
---

# Handoff — 다음 세션 warm 인계

> 세션을 넘기기 전 *다음 세션이 이것부터 읽고 시작할* 인계 문서를 `.dcness-work/handoffs/next-session.md` 에 쓴다. 다음 세션 SessionStart 훅이 그 내용을 최우선 주입하고 archive 로 옮겨 clear 한다. auto-memory 없이도 다음 세션이 자족적으로 이어가게 하는 결정적 레이어다.

## 언제 사용

- 세션을 마치며 다음 세션(자신이든 다른 세션이든)에 작업을 넘길 때
- 컨텍스트가 커져 압축·종료 전에 이어갈 지점을 명시적으로 남길 때
- 사용자가 "핸드오프 만들어줘", "인계 문서 써줘", "다음 세션에 넘겨줘" 등으로 발화할 때

> `/smart-compact` 는 *같은 세션* 안에서 `/compact` 로 컨텍스트를 압축한다. `/handoff` 는 *세션 경계 너머* 로 넘기는 결정적 인계다. 둘은 역할이 다르다.

## 절차

메인이 자체 두뇌로 다음을 수집해 `.dcness-work/handoffs/next-session.md` 에 쓴다.

1. **다음 액션 (필수)** — 다음 세션이 착수할 구체적 작업 1개. 이 항목이 없으면 handoff 를 쓰지 않는다.
2. **근거** — 왜 이게 다음인지 1~2줄.
3. **진행 상태** — 현재 branch / 관련 PR·이슈 / 미완료 지점.
4. **포인터** — 상세를 담은 산출물·파일·이슈 링크 (본문에 덤프하지 않고 링크만).

```bash
# repo 루트 기준으로 쓴다 — SessionStart 훅이 소비할 경로와 동일 유도(git top-level).
# 서브디렉토리에서 /handoff 를 발화해도 훅이 읽는 위치에 정확히 쓰이게 한다.
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
HANDOFF_DIR="$PROJECT_ROOT/.dcness-work/handoffs"
mkdir -p "$HANDOFF_DIR"
# 심링크 타겟 오염 방지 — 임시 파일에 쓴 뒤 rename 으로 교체한다. next-session.md 가
# 심링크여도 rename 은 링크 자체를 대체(타겟을 따라가 덮어쓰지 않음). 훅의 읽기측
# 심링크 하드닝과 대칭. `.dcness-work/` 는 writable 이라 이 방어가 필요하다.
cat > "$HANDOFF_DIR/.next-session.tmp" <<'EOF'
# 다음 세션 핸드오프 — <YYYY-MM-DD>

## 다음 액션 (필수)
- <다음 세션이 착수할 작업 1개>

## 근거
- <왜 이게 다음인지 1~2줄>

## 진행 상태
- branch: <현재 branch>
- 관련: <PR/이슈 링크>
- 미완료: <끊긴 지점>

## 포인터 (lazy)
- <핵심 파일 경로>
- <핵심 문서·이슈 링크>
EOF
mv -f "$HANDOFF_DIR/.next-session.tmp" "$HANDOFF_DIR/next-session.md"
```

파일을 쓴 뒤 사용자에게 경로와 다음 액션을 보고한다.

## 동작 계약

- **단문 원칙** — "다음 액션 1개(필수) + 근거 + 포인터 링크" 중심의 단문으로 제한한다. 세션 전체 요약 덤프 금지. 상세 컨텍스트는 포인터가 가리키는 산출물을 다음 세션이 질의 시점에 lazy 로드한다. SessionStart 주입량이 커지면 slim-inject 원칙이 무너진다.
- **결정적 단일 경로** — 활성 파일은 repo 루트(`git rev-parse --show-toplevel`) 기준 `.dcness-work/handoffs/next-session.md` 로 고정한다. 쓰기(command)와 읽기(SessionStart 훅)가 같은 repo-root 유도를 써 서브디렉토리 실행에도 정합한다. SessionStart 훅이 확인할 결정적 단일 경로가 하나 필요하므로 세션마다 다른 이름을 쓰지 않는다. 이미 파일이 있으면 덮어쓴다(가장 최근 인계만 유효).
- **소비 = archive claim** — 다음 세션 SessionStart 훅이 이 파일을 `.dcness-work/handoffs/archive/<ts>.md` 로 먼저 옮겨(mv) 원자적으로 소비한 뒤 그 내용을 additionalContext 최상단에 주입한다(무손실 clear). 다음다음 세션에 stale 재주입되지 않는다.
- **first-consumer-wins** — 병렬 peer 세션은 각자 SessionStart 를 발화하지만, 소비가 read 가 아니라 archive mv(rename)로 먼저 일어나므로 rename 에 성공한 first-consumer 만 handoff 를 얻는다. handoff 는 단일 소비자 인계 문서이고, 병렬 작업 분배는 [claim board](../docs/plugin/parallel-policy.md#4-task-claim-board) 몫이다.
- **git 제외** — `.dcness-work/` 는 git-excluded 작업 영역이다(활성화 시 `/init-dcness` 가 `.gitignore` 에 추가). handoff 는 커밋 산출물이 아니라 세션 간 scratch 다.

## 참조

- [`deliverables-map.md` Volatile 작업 영역](../docs/plugin/deliverables-map.md#volatile-작업-영역)
- [`hooks.md` session-start.sh](../docs/plugin/hooks.md#session-startsh)
- [`positioning.md` Utility 공개 노출 범위](../docs/plugin/positioning.md#utility-공개-노출-범위)
