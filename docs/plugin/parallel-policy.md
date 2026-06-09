# 병렬 peer 세션 실행 정책

> impl chain 의 **opt-in 별도 세션 병렬** 정책 SSOT. 기본은 직렬 chain 이고, 병렬은 독립 task 가 명확히 판정될 때만 켜지는 예외다. lane/shape 판정 = [`workflow-router.md`](workflow-router.md). chain mechanics = [`loop-procedure.md`](loop-procedure.md).
>
> 🔴 **범위** — 본 문서는 허용 조건, claim board, merge lock, close semantics 를 정의한다. 구현 표면은 [`parallel_wave.py`](../../harness/parallel_wave.py) (`compute_waves`) + `dcness-helper wave-plan --register` + `wave-claim`/`wave-status` + [`pr-finalize.sh`](../../scripts/pr-finalize.sh) merge lock 이다.

## 1. 운영 원칙 — 직렬이 기본, 병렬은 조건부 예외

- **기본은 현행 직렬 chain.** impl chain 은 task 한 개씩 진행한다. 한 task 가 PR merge 까지 끝난 뒤 다음 task 에 진입한다.
- **병렬은 opt-in.** `wave-plan` 이 독립 후보를 계산하고 사용자가 병렬 실행을 명시적으로 선택한 경우에만 peer mode 를 등록한다.
- **각 peer 는 동등한 메인 세션이다.** 한 세션 안에서 worker 를 흩뿌리고 모으는 방식이 아니다. 사용자가 터미널 N개에서 독립 interactive Claude Code 세션을 띄우고 각 세션이 기존 `/impl-loop <canonical-impl-path>` single task 를 수행한다.
- **검증 규칙은 줄이지 않는다.** 각 peer task 는 기존 branch → PR → review → CI → merge 규칙을 그대로 탄다.

## 2. 실행 모델 — 독립 interactive 세션

```text
coordinator session
  └─ dcness-helper wave-plan --register <impl paths>

terminal A: /impl-loop <canonical path A> ─ claim A ─ PR A ─ pr-finalize ┐
terminal B: /impl-loop <canonical path B> ─ claim B ─ PR B ─ pr-finalize ├─ merge-lock serializes
terminal C: /impl-loop <canonical path C> ─ claim C ─ PR C ─ pr-finalize ┘
```

- 병렬 실행 주체는 **별도 interactive Claude Code 세션**이다. 별도 세션이므로 각자 `live.json`, run dir, worktree, branch 를 갖는다.
- 한 세션 안 동시 Agent fan-out 은 지원하지 않는다. strict conveyor 는 `current_step` 단일 슬롯을 전제로 하므로 한 세션 안 병렬 Agent 는 상태 모델을 깨뜨린다.
- peer mode 미등록 상태에서 `/impl-loop <impl-path>` 를 실행하면 기존 single flow 로 동작한다. 병렬 opt-in 이 기존 사용 경로를 바꾸면 안 된다.

## 3. wave planning / registration

coordinator 는 chain dry preview 직후 `compute_waves` 결과를 보고 병렬 후보를 안내한다.

```bash
dcness-helper wave-plan --register <impl-glob-or-dir> \
  --high-risk <high-risk-slug1,high-risk-slug2>
```

- `wave-plan` 은 `depends_on` + Scope 파일집합 disjoint 로 후보 wave 를 계산한다.
- `--register` 를 붙인 경우 computed `parallel` step 에 속한 impl 파일의 **canonical impl path** 만 claim board 에 등록한다. serial / high-risk / 의존 대기 task 는 등록하지 않는다. 이 등록이 peer mode activation 신호다.
- 사용자에게 peer 세션 입력은 `wave-id` 가 아니라 `/impl-loop <canonical-impl-path>` 로 안내한다.
- 안내에는 각 task 의 엔진을 명시한다: single 기본은 풀 4-agent, chain 기본은 build-worker, high-risk task 는 풀 4-agent 승격.

## 4. task claim board

claim 단위는 `wave-id + slug` 가 아니라 **canonical impl path** 다. board 는 main repo 의 `.claude/harness-state/wave-board/` 아래에 저장된다.

- `/impl-loop single` 진입 초기에 `wave-claim <impl-path>` 를 호출한다.
- 등록되지 않은 impl path → `mode=serial`, 기존 single flow 그대로 진행.
- 등록된 impl path → target claim JSON 을 직접 `O_EXCL` 로 생성한다. 같은 task 동시 claim 은 한 세션만 성공한다.
- fresh claim 또는 completed evidence 가 있으면 두 번째 세션은 시작하지 않는다.
- stale heartbeat 는 자동 회수하지 않는다. `wave-reclaim <claim> --reason ...` 처럼 명시 reclaim 후에만 재claim 가능하다.
- 사람이 볼 수 있는 상태에는 impl path, session, run, worktree, branch, heartbeat, state 가 포함된다 (`wave-status`).

## 5. merge lock / order / close semantics

peer task 는 PR 생성까지 독립적으로 갈 수 있지만, merge 단계는 repo-level mutex 로 직렬화한다.

- 실제 진입점은 [`pr-finalize.sh`](../../scripts/pr-finalize.sh) 이다. 스크립트가 `merge-lock acquire` 를 호출하고, peer claim 이 있는 브랜치만 lock 을 잡는다. claim 없는 일반 PR 은 `mode=serial` 로 기존 흐름을 유지한다.
- lock 획득 후 `git fetch origin main`, `gh pr update-branch`, `gh pr checks` 로 base/PR 상태를 다시 확인한다. 최종 pass/fail 은 기존 `gh pr checks --watch` 와 merge 결과가 결정한다.
- merge 성공 후 `merge-lock complete` 가 claim 을 `completed` 로 기록하고 lock 을 해제한다.
- merge 실패 / CI fail / conflict / 중단은 claim 을 failed/stale-reclaimable 상태로 남긴다. 사용자가 상태를 보고 재시도 또는 reclaim 한다.
- peer finalize 도중 프로세스가 `SIGKILL` 등으로 종료돼 `EXIT` trap 이 실행되지 않으면 merge lock 파일이 남을 수 있다. operator 가 holder/session 이 실제로 종료됐음을 확인한 뒤에만 `dcness-helper merge-lock break --stale-after <seconds> --reason "<why>"` 로 tokenless stale break 를 수행한다. fresh lock 은 break 되지 않는다.

### task_index order gate

기존 git-spec 은 story 마지막 task PR 이 `Closes #story` 를 가진다. peer mode 에서 뒤 task 가 먼저 merge 되면 story/epic 이 조기 close 될 수 있으므로 merge lock 은 같은 story 의 order 를 확인한다.

- 기준은 **board 에 claim 된 prior task** 가 아니라, 같은 `impl/` 디렉토리의 모든 sibling impl 파일 frontmatter 다.
- 현재 task 가 `story: <number>` + `task_index: i/total` 이면, 같은 story 에서 `task_index < i` 인 prior task 전체를 계산한다.
- prior task 가 board 에 있으면 `completed` 여야 한다.
- prior task 가 board 에 없으면 base/default branch history 같은 외부 evidence 로 이미 merged/completed 임이 확인돼야 한다. unmerged feature branch commit 은 evidence 로 보지 않는다.
- 확인 불가면 뒤 task merge 는 block 한다. 이 block 은 close semantics 보존을 위해 사용자 책임으로 넘기지 않는다.
- `story: 공통` 또는 malformed/non-story task 는 story close 대상이 아니므로 order gate 를 적용하지 않는다.

## 6. 독립성 판정

```text
같은 wave 병렬 가능 = depends_on 위상상 서로 선후 없음
                   AND Scope 파일집합 disjoint
```

| 축 | 의미 | 입력 위치 |
|---|---|---|
| `depends_on` | task 실행 선후. contract produces/consumes 와 ordering 을 흡수한 단일 SSOT | impl task frontmatter |
| Scope 파일집합 | 두 task 의 `수정 허용` 파일 경로 교집합이 있으면 동시 금지 | impl task `Scope > 수정 허용` |

`수정 허용` 은 **bullet 당 순수 파일 경로 하나**(또는 끝 `/` 디렉토리) 형식이어야 파서가 경로로 인식한다. 볼드/라벨/괄호 설명/다중 토큰/산문 bullet 은 경로 미인식 → 해당 task 가 *형식 미정규화*로 직렬 강등된다(의존성과 무관). 부가 설명은 `# 주석`(파서가 떼어냄) 또는 blockquote 로 둔다. 형식 미정규화로 강등된 slug 는 `wave-plan` 출력의 `format_unnormalized_slugs`(+ `serial_demotions[].cause = scope_unnormalized`)로 노출되어, 설계 검증(`/design` Step 5)·소비측 dry preview 가 "진짜 의존성 직렬"과 구분해 교정 방향을 안내한다([#693](https://github.com/alruminum/dcNess/issues/693)).

`depends_on` 은 세 상태를 구별한다.

- 미작성 / placeholder 잔존 = 미상 → 직렬 강등.
- 명시적 `[]` = 선행 없음 선언 → Scope 도 disjoint 면 병렬 후보.
- 목록 = 해당 선행 task 들에 의존.

고위험 task 는 직렬 강등한다. dry preview 의 `risk=high-risk` slug 를 `wave-plan --high-risk` 로 넘긴다. 경로상 명백한 migration/secrets/.env 계열은 parser 가 backstop 으로 직렬화한다.

## 7. 비용가드 / fallback

- `max_parallel_workers = 2` 로 시작한다. 상향은 실측 후 별도 결정이다.
- `depends_on` 미상, Scope 자유서술, Scope 겹침, high-risk, claim conflict, merge order block, CI fail, conflict 는 직렬/사용자 판단으로 강등한다.
- 병렬은 throughput 최적화일 뿐 aggregate 검증을 보장하지 않는다. 안전망은 독립성 판정, claim board, merge lock, base update, CI 재확인이다.

## 8. helper surface

| helper | 역할 |
|---|---|
| `wave-plan --register` | 독립 후보 계산 + computed parallel step task 만 peer mode 등록 |
| `wave-claim` | registered impl path claim. unregistered 는 serial 반환 |
| `wave-heartbeat` | claim heartbeat 갱신 |
| `wave-status` | board 현황 출력 |
| `wave-reclaim` | stale claim 명시 reclaim |
| `wave-release` | completed/failed/released 상태 기록 |
| `merge-lock acquire/release/complete` | `pr-finalize.sh` 내부 merge mutex + completed 기록 |
| `merge-lock break` | operator 확인 후 stale merge lock tokenless 복구 |
