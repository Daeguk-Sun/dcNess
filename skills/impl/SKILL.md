---
name: impl
description: 구현 요청을 받아 이미 보이는 task shape로 구현 소유자를 한 번 정한 뒤 즉시 격리·RED/첫 edit로 진행하고, GREEN 뒤 반대 진영 impl-validator와 PR 마감을 수행하는 기본 구현 진입점. 단순 작업은 main-direct, 명확한 복잡 작업은 첫 source edit 전에 headless one-shot으로 시작한다. 제품 의미나 새 권한이 실제로 필요한 경우에만 묻는다.
---

# Impl — action-first owner selection

`/impl`은 구현 소유자를 첫 source edit 전에 한 번만 고른다. 단순 작업은 메인이 바로 구현하고, 명확한 복잡 작업은 격리 worktree에서 headless build-worker가 끝까지 구현한다. 중간 handoff, 즉 메인이 조금 구현한 뒤 worker로 넘기거나 review finding마다 구현 진영을 바꾸는 흐름을 금지한다.

```text
target 확인 → owner 1회 선택 → 격리 → RED/첫 edit
```

owner 선택을 위한 별도 repo scan·SSOT read·질문은 하지 않는다. validator provider, Cartography freshness, target issue close audit, commit/PR/CI/merge 상세는 GREEN 뒤에만 [`impl-finish.md`](impl-finish.md)를 읽어 수행한다. 위험 분기가 실제로 필요할 때만 [`impl-routing.md`](impl-routing.md)를 읽는다.

## 구현 소유자 선택

요청·issue·handoff에 이미 드러난 신호만 사용한다.

- **main-direct**: 한두 module의 국소 수정, exact source/test pointer가 있는 작업, docs/config, 기존 seam의 작은 버그
- **headless one-shot**: 여러 module/계층을 함께 바꿈, 새 runtime seam·migration·DI/manifest 연동, 넓은 테스트·빌드와 반복 검증, 예상 source 범위가 큰 작업
- **애매하면 main-direct**: 복잡도 판정을 위해 파일을 더 읽거나 사용자에게 선택을 묻지 않는다.

선택 뒤에는 같은 구현 소유자가 GREEN과 review finding 수정을 모두 맡는다. headless가 workspace를 바꾼 뒤에는 다른 provider로 넘기지 않고 same-workspace recovery 또는 BLOCKED만 허용한다. 메인은 제품 결정, 진행 보고, 외부 issue/PR mutation을 계속 소유한다.

## 진행 뷰 (task 리스트)

메인은 owner와 target을 확정하면 다음 고정 3개 task를 만들고 run 동안 반환된
task id를 재사용한다.

1. `구현 · <target> (<main-direct|headless>)`
2. `검증 · impl-validator`
3. `마감 · commit/PR/CI`

첫 task는 실행 시작과 함께 `in_progress`, 나머지는 `pending`으로 표시한다.
lifecycle state와 implementation-chain receipt가 실행 진본이고 Task 목록은
사용자 UI에 진행을 투영하는 표시다. 고정 3개이므로 이 `/impl` 진행 뷰는
추가 helper subprocess를 호출하지 않는다.

정상 fast-start에서는 세 `TaskCreate`와 `EnterWorktree 또는 첫 work action`을
같은 첫 tool-bearing turn의 독립 tool batch로 발행한다. `TaskCreate`가 기본
`pending`으로 만들어 반환한 id는 바로 다음의 **이미 필요했던** work action에서
첫 task를 `in_progress`로 바꾸는 `TaskUpdate`에 쓴다. 예를 들어 격리 결과를
받은 뒤 main-direct는 `TaskUpdate`와 `begin-run`·exact pointer read·RED/첫 edit
중 그 시점의 호출을, headless는 `TaskUpdate`와 background
implementation-chain launch를 같은 독립 batch로 발행한다. headless
implementation-chain은 TaskCreate나 TaskUpdate 결과를 기다리지 않는다.

이미 격리된 상태에서는 `TaskCreate`를 target 확인·exact pointer read·slim
prompt 준비처럼 원래 필요한 호출에 붙이고, 다음 원래 work action에
`TaskUpdate`를 붙인다. batch 발행이 불가능하면 work action을 먼저 실행하고
Task 호출은 다음의 이미 필요한 tool-bearing turn에 붙인다. Task만 처리하는
사이 turn이나 진행 뷰만을 위한 추가 assistant turn을 만들지 않는다. 아래
focused read의 `첫 tool call은 pointer만`은 work action의 read 경계를 뜻한다.
같은 batch의 Task sidecar는 추가 repo read나 blocking assistant turn이 아니다.

상태 변경은 기존 필수 작업과 같은 tool-bearing turn에 `TaskUpdate`로 묶는다.

1. 구현과 관련 gate가 GREEN이면 구현 task를 `completed`, 검증 task를
   `in_progress`로 바꾸고 candidate freeze/impl-validator 경로를 계속한다.
2. validator가 MUST FIX를 내면 같은 task를 새로 만들지 않고 구현 task를
   `in_progress`, 검증 task를 `pending`으로 되돌려 같은 owner의 rework를 표시한다.
3. validator PASS면 검증 task를 `completed`, 마감 task를 `in_progress`로 바꾸고
   commit·PR·CI·target AC audit을 진행한다.
4. 자동 마감이 끝나면 마감 task를 `completed`로 바꾼다. 사람 확인이 남으면
   Task를 늘리지 않고 `human verification 대기`를 별도 메시지로 유지한다.

resume 시 같은 제목의 기존 `/impl` task가 있으면 id와 상태를 재사용하고
`TaskCreate`를 중복 생성하지 않는다. Task tool이 없거나 호출이 실패하면 같은
3줄 완료/현재/예정 ASCII 뷰를 진행 메시지에 표시하고 구현은 계속한다. 진행
표시는 도구이지 gate가 아니다.

## 질문 경계

묻지 않고 진행한다:

- concrete issue/handoff/design-doc에 target·scope·검증이 이미 확정된 경우
- 관련 파일과 test seam 탐색, 구현 방식 선택, 기계적 경로 오타 교정
- 미래 story·out-of-scope 대안·후기 review/close 요구
- 일반 test/lint 실패와 같은 범위의 재시도

한 번 질문하는 경우는 제품 의미가 실제 결과를 둘 이상으로 가르거나, repo 밖 접근·새 dependency/secret·보안·데이터 파괴·hard boundary 변경처럼 새 권한이 필요한 때뿐이다. merge 승인은 사용자가 소유한다. 확정된 handoff나 사용자 선택을 다시 열어 wiki/web 조사나 설계 선택지로 되돌리지 않는다.

## 즉시 착수

### 1. target 최소 확인

- GitHub issue/PR이면 본문과 댓글을 한 번 읽고 target GitHub issue AC snapshot을 보관한다. AC가 없거나 검증 주체가 없으면 close 때 현행 typed AC로 갱신하며 의미를 임의 추론하지 않는다.
- 파일/symbol이면 `rg`와 관련 부분만 읽는다.
- 명시된 선행 PR이 있으면 merge 여부만 확인한다.
- repo 전체 scan, branch naming 문서, 전체 SSOT, wiki/web, validator/provider, generated TDD 설치 상태는 읽지 않는다.
- issue lifecycle state 변경은 기존 helper가 있으면 격리와 같은 첫 실행 묶음에서 처리한다. 그 helper 구현을 조사하지 않는다.

첫 메시지는 다음 한 줄이면 충분하다.

```text
착수: <target> 확인 · worktree 준비 · RED/첫 edit 진행
```

### 2. 격리와 실행

- 사용자가 “워크트리 없이”라고 하지 않았으면 즉시 `EnterWorktree`를 사용한다.
- worktree 진입 뒤 모든 read/edit/test 경로를 새 cwd 기준으로 다시 잡는다.
- main-direct면 그 worktree에서 `dcness-helper begin-run impl --lane lite` 또는 design-doc 입력이면 `begin-run impl --design-doc <path>`를 한 번 실행한다.
- 브랜치·커밋 네이밍은 commit 경계의 기존 hook을 우선한다. RED 전에 naming SSOT를 읽지 않는다.

headless one-shot이면 worktree 진입 직후 target, 보존할 결정, AC snapshot, exact pointer 또는 허용 scope, 검증 명령만 담은 slim prompt를 만들고 기존 chain을 첫 실행으로 호출한다. provider resolve, `begin-run`, `begin-step`, prompt-slot 문서 확인을 따로 하지 않는다.

```bash
PLUGIN_ROOT=""
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "$CLAUDE_PLUGIN_ROOT/scripts" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  PLUGIN_ROOT="$(ls -d "$HOME/.claude/plugins/cache/dcness/dcness/"* 2>/dev/null | sort -V | tail -1)"
fi
[ -n "$PLUGIN_ROOT" ] || { echo "[dcness] plugin root not found" >&2; exit 1; }
HELPER="$PLUGIN_ROOT/scripts/dcness-helper"
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
"$PLUGIN_ROOT/scripts/dcness-implementation-chain" build-worker \
  --direct-run \
  --issue-num <issue-number> \
  --prompt-file <slim-prompt> \
  --project-root "$PROJECT_ROOT"
```

design-doc 입력이면 `--design-doc <path>`만 추가한다. 대화형 호스트에서는 이 one-shot을 background tool 실행으로 시작하고 메인이 `ps`, `tail`, 수동 polling loop를 만들지 않는다. chain이 run/step lifecycle, provider chain, phase evidence, same-workspace recovery를 소유한다.

종료 receipt의 `provider=<actual>`이 실제 구현 소유자다. `exit 75` 전에는 workspace mutation이 없으므로 메인이 `claude-main` 소유자로 구현할 수 있다. 그 밖의 실패는 [`impl-routing.md`](impl-routing.md)에서 처리한다.

### 3. focused read

- 이 절은 main-direct에 적용한다. headless는 slim prompt 뒤 worker가 같은 규율로 읽고 구현한다.
- issue/handoff가 지정한 pointer와 test seam만 읽는다.
- 파일을 통째로 읽기 전에 `rg`로 symbol과 기존 테스트를 찾는다.
- 구현에 필요한 signature·인접 코드까지만 확장한다.
- 사용자 선택이 이미 확정된 run은 선택 확정 뒤 blocking assistant turn 2회 안에 RED 또는 첫 edit를 만든다.
- concrete pointer path가 주어졌으면 다음 순서를 바꾸거나 쪼개지 않는다.
  1. 첫 tool call은 pointer만 읽어 exact source·test path를 얻는다. repo 탐색을 섞지 않는다.
  2. 둘째 tool call 하나에서 그 exact source와 matching test를 함께 읽는다. 별도 `Read`, `find`, `ls`, 디렉터리별 `grep`/`cat`을 추가하지 않는다.
  3. 다음 tool-bearing turn은 RED test 또는 첫 edit다.
- source·test exact path까지 처음부터 주어졌으면 1·2를 한 tool call로 합친다.

### 4. RED → 구현 → GREEN

- 테스트 가능한 변경은 실패 테스트를 먼저 작성하고 실제 RED를 확인한다.
- docs-only·단순 설정처럼 테스트할 수 없으면 skip 사유를 한 줄 남긴다.
- 선택한 소유자가 직접 구현한다. 구현 중 routine 선택을 질문으로 올리지 않는다.
- 관련 lint/build/test/typecheck/compile을 실제 실행한다.
- 첫 edit 뒤 `진행: RED/첫 edit 확인`, green 뒤 `진행: 구현·검증 green · review 시작`만 알린다.

## GREEN 이후

관련 검증이 GREEN이 된 뒤에만 [`impl-finish.md`](impl-finish.md)를 읽고 다음을 마친다.

1. 동작·경계·Cartography impact 증거 수집
2. 실제 구현자의 반대 진영 `impl-validator`와 같은 구현 소유자의 최대 3회 root-cause 수정
3. 의미 단위 commit, PR, CI
4. target GitHub issue AC close audit와 최종 보고

GREEN 전에는 이 후기 진본이나 그 포인터가 가리키는 문서를 선행 read하지 않는다.

## 안전 불변식

- TDD, lint/build/test, hard boundary, branch→PR, 격리 review, CI를 제거하지 않는다.
- `tdd-exempt`나 boundary 확대를 자동 삽입하지 않는다.
- 대체한 helper·분기·문서·테스트는 같은 변경에서 삭제하고 옛 이름·호출 예시가 남지 않았는지 `rg`로 확인한다.
- 새 공개 command/skill/agent를 추가하지 않는다.

## 참조

- 초기 위험 분기(필요할 때만): [`impl-routing.md`](impl-routing.md)
- GREEN 이후 마감(필요할 때만): [`impl-finish.md`](impl-finish.md)
- 기본/고급 공개 진입점: [`positioning.md`](../../docs/plugin/positioning.md)
