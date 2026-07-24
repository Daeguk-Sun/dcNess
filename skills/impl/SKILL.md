---
name: impl
description: 구현 요청을 받아 메인이 즉시 격리·focused read·RED/첫 edit로 진행하고, GREEN 뒤 격리 impl-validator와 PR 마감을 수행하는 기본 구현 진입점. 이슈번호/링크/파일/테스트처럼 concrete signal이 있으면 다시 설계하지 않고 구현한다. 제품 의미나 새 권한이 실제로 필요한 경우에만 묻는다. 일반 구현을 별도 worker로 넘기지 않는다.
---

# Impl — main-direct action-first

`/impl`의 기본 구현자는 메인이다. 별도 구현 sub-agent나 headless worker를 먼저 만들지 않는다. 격리되는 것은 GREEN 이후 review뿐이다.

```text
target 확인 → 격리 → focused read → RED/첫 edit
```

후기 절차를 미리 정합하려고 멈추지 않는다. validator provider, Cartography freshness, target issue close audit, commit/PR/CI/merge 상세는 GREEN 뒤에만 [`impl-finish.md`](impl-finish.md)를 읽어 수행한다. direct/design-doc·위험 분기가 실제로 필요할 때만 [`impl-routing.md`](impl-routing.md)를 읽는다.

## 질문 경계

묻지 않고 진행한다:

- concrete issue/handoff/design-doc에 target·scope·검증이 이미 확정된 경우
- 관련 파일과 test seam 탐색, 구현 방식 선택, 기계적 경로 오타 교정
- 미래 story·out-of-scope 대안·후기 review/close 요구
- 일반 test/lint 실패와 같은 범위의 재시도

한 번 질문하는 경우는 제품 의미가 실제 결과를 둘 이상으로 가르거나, repo 밖 접근·새 dependency/secret·보안·데이터 파괴·hard boundary 변경처럼 새 권한이 필요한 때뿐이다. merge 승인은 사용자가 소유한다. 확정된 handoff나 사용자 선택을 다시 열어 wiki/web 조사나 설계 선택지로 되돌리지 않는다.

fresh executor는 기본값도 자동 복구값도 아니다. decision-heavy A/B 실측이 main-direct보다 시간과 정확성에서 우세하다고 증명되기 전에는 같은 메인이 계속 구현한다.

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

### 2. 격리와 run 시작

- 사용자가 “워크트리 없이”라고 하지 않았으면 즉시 `EnterWorktree`를 사용한다.
- worktree 진입 뒤 모든 read/edit/test 경로를 새 cwd 기준으로 다시 잡는다.
- 그 worktree에서 `dcness-helper begin-run impl --lane lite` 또는 design-doc 입력이면 `begin-run impl --design-doc <path>`를 한 번 실행한다.
- 브랜치·커밋 네이밍은 commit 경계의 기존 hook을 우선한다. RED 전에 naming SSOT를 읽지 않는다.

### 3. focused read

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
- 메인이 직접 구현한다. 구현 중 routine 선택을 질문으로 올리지 않는다.
- 관련 lint/build/test/typecheck/compile을 실제 실행한다.
- 첫 edit 뒤 `진행: RED/첫 edit 확인`, green 뒤 `진행: 구현·검증 green · review 시작`만 알린다.

## GREEN 이후

관련 검증이 GREEN이 된 뒤에만 [`impl-finish.md`](impl-finish.md)를 읽고 다음을 마친다.

1. 동작·경계·Cartography impact 증거 수집
2. 격리 `impl-validator`와 최대 3회 root-cause 수정
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
