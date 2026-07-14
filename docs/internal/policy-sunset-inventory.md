# 정책 수명주기 inventory와 cleanup baseline

> #1089의 cleanup 전 snapshot이다. 측정 revision은 `b676140bcffdaa5843ce59198ecef4f997efddc9`이며, 분류 근거는 2026-07-14 KST의 저장소와 등록 활성 프로젝트 read-only 조사다. 이 문서는 제거 작업을 수행하지 않는다.

## 재현 명령과 산출물

한 명령이 Git tracked tree의 크기 지표, inventory schema·분류·후속 이슈 전수 배정, 전체 unit suite 실행시간을 함께 출력한다. untracked receipt와 현재 working copy의 새 파일은 revision 지표에 들어가지 않는다. suite도 지정 revision의 임시 detached worktree에서 실행해 dirty working tree를 격리한다.

```sh
python3.11 scripts/policy_cleanup_baseline.py \
  --revision b676140bcffdaa5843ce59198ecef4f997efddc9 \
  --inventory docs/internal/policy-sunset-inventory.json \
  --run-unit-suite
```

- 측정 구현: [`scripts/policy_cleanup_baseline.py`](../../scripts/policy_cleanup_baseline.py)
- 정책 slice 원장: [`policy-sunset-inventory.json`](policy-sunset-inventory.json)
- 고정 출력: [`policy-sunset-baseline.json`](policy-sunset-baseline.json)

`major text`는 `.py`, `.mjs`, `.js`, `.sh`, `.md`, `.json`, `.yml`, `.yaml`, `.toml`이다. `code LOC`는 `harness/`, `scripts/`, `evals/` 아래 Python이고 `test LOC`는 `tests/` 아래 Python이다. test 함수는 Python AST에서 이름이 `test_`로 시작하는 함수·메서드를 센다. 대형 파일 수는 major text의 논리 LOC가 각각 500·1,000 이상인 파일 수다. compatibility 후보는 `제거 가능`과 `한시적 호환 필요` slice의 합이며 `현재 실사용`은 분모에는 남지만 감량 후보로 세지 않는다.

| 지표 | cleanup 전 값 |
|---|---:|
| tracked file | 560 |
| major text file / LOC | 519 / 104,856 |
| code LOC | 29,190 |
| test LOC | 40,675 |
| code + test LOC | 69,865 |
| 500 / 1,000 LOC 이상 major text | 56 / 18 |
| test 함수 | 1,943 |
| 전체 unit suite | exit 0 / 118.693초 / detached clean tree |
| inventory entry / compatibility 후보 | 29 / 15 |

실행시간은 같은 명령의 wall-clock 비교값이며 하드 성능 gate가 아니다. revision, Python 3.11, 동일 명령을 함께 기록하고 후속 #1099에서 다시 잰다.

## 분류 계약

| 분류 | 판단 기준 | baseline 수 |
|---|---|---:|
| `현재 실사용` | 현행 writer·runtime safety·배포 topology가 직접 소비하며 오래됐다는 이유로 제거할 수 없음 | 14 |
| `제거 가능` | repo call/import와 활성 소비자 증거가 없고 현행 writer가 만들지 않는 surface | 4 |
| `한시적 호환 필요` | persisted 형식이나 실제 활성 프로젝트가 소비하며 대상·이유·제거 trigger·확인 방법이 모두 있음 | 11 |

영역별 29개는 design 6, run/ledger 8, routing 5, install/path 5, lifecycle 5다. 각 entry는 현행 SSOT, 구현, test/fixture, 문서·배포, 소비자 증거를 모두 가진다. 키워드가 같아도 release artifact의 `--contract`처럼 의미가 다른 적중은 `현재 실사용`으로 명시해 false positive를 버리지 않고 분류했다.

### 활성 소비자 snapshot

등록 파일 `~/.claude/plugins/data/dcness-dcness/projects.json`의 경로는 문서에 공개하지 않고 registry 순번으로만 조사했다.

| 관찰 영역 | 2026-07-14 read-only 결과 | inventory 영향 |
|---|---|---|
| legacy design artifact | 5개 중 2개 프로젝트, marker 포함 문서 72개 | `DES-003`~`DES-005` 한시 호환 |
| persisted run | `ledger.jsonl` 30개, `.steps.jsonl` 0개 | `RUN-001` 현행; 과거/cache 형식인 `RUN-002`는 종료 trigger 필요 |
| routing config | schema 3이지만 retired `code-validator`, `pr-reviewer`, `test-engineer` key 잔존 | `ROUTE-002` migration 대상 실재 |
| generated install | 프로젝트별 5개 대상 파일 보유량 `0/5, 2/5, 5/5, 0/5, 1/5` | partial install fallback인 `INST-002` 현행 |
| stories | 3개 프로젝트의 `stories.md` 8개가 모두 Story AC heading 없는 구양식 | `LIFE-002` 한시 호환 |
| legacy `design-variants/` prefix | 등록 프로젝트 0건 | `INST-004` 제거 가능 |

절대경로·프로젝트명은 근거가 아니라 민감한 host 정보라 기록하지 않았다. 후속 이슈는 같은 registry 순번과 해당 이슈의 확인 명령으로 재조사한다.

## 한시적 호환 4요소 감사

아래 11개 모두 대상, 유지 이유, 제거 trigger, 확인 방법을 가진다. 명령 전문과 trace path는 machine inventory에 있다.

| ID | 소비자 또는 대상 형식 | 유지 이유 | 제거 trigger | 확인 방법 |
|---|---|---|---|---|
| DES-003 | 기존 Ledger/References/frontmatter/Flow Map 문서 | doc-sync false fail 방지 | 활성 marker 0 + `--contract` 호출자 0 | design artifact audit + fixture |
| DES-004 | legacy Ledger·Decisions table architecture | 기존 capability/decision map 보존 | 문서 migration + parser 적중 0 | architecture map + fixture |
| DES-005 | legacy artifact를 가진 설계 pack | 존재만으로 validator Must 방지 | migration 뒤 leniency 없이 판정 동일 | contract pointer/docs sync tests |
| RUN-002 | `.steps.jsonl`과 mixed-upgrade run | 과거 review와 occurrence 순서 보존 | 보존기간 확정·migration·표본 0 | ledger/run-review tests |
| RUN-003 | 옛 row와 현행 receipt 공통 필드명 | reader 동시 migration 전 evidence 보존 | canonical receipt migration 완료 | ledger/benchmark/outcome tests |
| RUN-005 | `validator` 이름의 persisted trace | attribution과 boundary 복구 | archive migration + alias 적중 0 | run-review/boundary tests |
| RUN-008 | legacy stored verdict + prose sentinel | 과거 FAIL 비율 오판 방지 | verdict migration + old 표본 0 | run-review/aggregate tests |
| ROUTE-002 | schema 1·2와 retired route keys | local config를 조용히 폐기하지 않음 | config migration + scan 0 | routing doctor + tests |
| ROUTE-003 | `codex-first` 저장값 | 과거 explicit opt-in 의미 보존 | registered config 사용 0 + migration | routing status/provider-chain tests |
| LIFE-002 | Story AC 없는 stories | 소급 의미 추론·false fail 방지 | typed AC migration + scan 0 | AC coverage + fixture |
| LIFE-003 | checklist 없는 legacy issue | false close·영구 close 불가 방지 | 열린 issue migration/지원 종료 | issue close audit + fixture |

종료 날짜를 근거 없이 임의 지정하지 않았다. trigger를 만족하지 못한 채 reader를 제거하는 것은 #1089 안전 경계를 위반한다.

## 500줄 이상 major text 책임 감사

단순 분할은 개선으로 세지 않는다. 각 파일의 현재 책임, 중복·legacy 비중, 실제 감량 후보를 읽었다. `후속/판정`이 #1098인 항목도 앞선 정책 이슈가 제거한 branch·fixture를 입력으로 받을 뿐, 크기만으로 쪼개지 않는다.

| 파일 | LOC | 현재 책임 | 중복·legacy 관찰 | 후속/판정 |
|---|---:|---|---|---|
| `PROGRESS.md` | 556 | self 진행 기록 | 누적 이력이며 runtime 아님 | #1098 입력 제외; 분할 무효 |
| `commands/init-dcness.md` | 512 | 활성화·재실행·제거 orchestration | install 설명이 사용자 SSOT와 일부 반복 | #1096에서 배포 계약 단위 감량 |
| `docs/archive/change_rationale_history.md` | 2,633 | 과거 결정 archive | legacy 비중 높지만 실행 surface 아님 | #1098에서 archive 보존정책 없이는 삭제 금지 |
| `docs/archive/conveyor-design.md` | 684 | 폐기 설계 archive | 현행 loop와 중복 가능 | #1098 후보, 단 runtime 감량으로 계산 X |
| `docs/archive/document_update_record.md` | 1,777 | 과거 변경 archive | Git history와 중복 | #1098 후보, 별도 archive 근거 필요 |
| `docs/archive/status-json-mutate-pattern.md` | 553 | 폐기 status JSON 참고 | 현행 prose-only와 legacy 비중 높음 | #1098 후보, 외부 링크 감사 후 |
| `docs/internal/marketplace-artifact-baseline.json` | 658 | release artifact inventory | generated data, 책임 중복 없음 | 유지; 분할 무효 |
| `docs/internal/release-notes.md` | 2,184 | 릴리즈 이력 | GitHub PR history와 일부 중복 | #1098 후보지만 release SSOT 보존 필요 |
| `docs/plugin/loop-procedure.md` | 504 | loop mechanics SSOT | run/routing 호환 설명이 누적 | #1094·#1095 뒤 문구 삭제, 단순 분할 금지 |
| `evals/agent_effectiveness_measure.py` | 734 | paired trace 측정 | policy compatibility와 무관 | 현행; #1098 크기만으로 선택 금지 |
| `evals/calibrate_judge.py` | 542 | eval judge 보정 | compatibility와 무관 | 현행 |
| `evals/guard_efficacy.py` | 781 | hard safety 결정적 eval | 안전 invariant | 현행, 감량 이유로 제거 금지 |
| `evals/harness_experiment.py` | 590 | experiment runner | compatibility와 무관 | 현행 |
| `harness/agent_boundary.py` | 1,596 | file/external-state 권한 경계 | alias fixture 일부, 핵심 safety 다수 | #1094 alias 후 #1098; 안전 invariant 보존 |
| `harness/agent_effectiveness.py` | 690 | effectiveness record 검증 | compatibility와 무관 | 현행 |
| `harness/benchmark_aggregate.py` | 500 | run verdict·waste 집계 | legacy verdict 분기 포함 | #1094 `RUN-008`, 이후 #1098 |
| `harness/chain_view.py` | 531 | run chain view | run reader와 assertion 중복 가능 | #1094 결과 후 #1098 |
| `harness/codex_sandbox_permission.py` | 594 | Codex 제한 승인 receipt | 현행 safety | 유지 |
| `harness/guard_telemetry.py` | 657 | guard hit telemetry | compatibility와 무관 | 현행 |
| `harness/hooks.py` | 1,671 | order/state hook 집약 | 여러 세대 enum·run assertion 포함 | #1094 후 #1098; order guard 보존 |
| `harness/ledger.py` | 642 | canonical + legacy run reader | legacy/mixed/field 호환 비중 큼 | #1094 핵심 감량 후보 |
| `harness/outcome_scorecard.py` | 739 | process·effectiveness·outcome 집계 | legacy verdict 소비 중복 | #1094 뒤 #1098 |
| `harness/parallel_wave.py` | 948 | peer claim/wave 상태 | 현행 concurrency safety | 유지 |
| `harness/product_journey.py` | 864 | 제품 journey runner | compatibility와 무관 | 현행 |
| `harness/run_review.py` | 1,853 | persisted run 분석·waste report | legacy name/verdict/prose 비중 큼 | #1094 핵심, 이후 #1098 |
| `harness/session_state.py` | 2,190 | run lifecycle/state owner | legacy lane·path와 다세대 state 책임 | #1094 핵심, 단순 분할 무효 |
| `harness/session_state_cli.py` | 1,488 | CLI dispatch·routing | historical private re-export와 legacy route CLI | #1094 `RUN-006` + #1095 |
| `harness/session_state_cli_finalize.py` | 595 | end-step/finalize/prose receipt | prose fallback과 old field 설명 | #1094 |
| `harness/session_state_status.py` | 501 | status/diagnostic view | state reader assertion과 중복 가능 | #1094 뒤 #1098 |
| `harness/story_runner.py` | 509 | story stack state | 현행 lifecycle | #1097 reader 정리 뒤 #1098 |
| `harness/tdd_hooks.py` | 1,356 | generated hook 생성·status·self-test | install 상태별 분기 큼, 실제 partial 소비자 존재 | #1096; 단순 분할 금지 |
| `scripts/github_project_lifecycle.mjs` | 1,444 | GitHub Project state lifecycle | legacy story reader와 직접 무관 | 현행; #1098 크기만으로 선택 금지 |
| `scripts/loop_diagnose.py` | 884 | cross-project 진단 | compatibility와 무관 | 현행 |
| `templates/design-variants/_lib/canvas.js` | 618 | static mockup canvas runtime | policy legacy와 무관 | 현행 |
| `tests/test_agent_boundary.py` | 2,642 | 권한 경계 회귀 | legacy alias assertion 일부, safety fixture 다수 | #1094 후 #1098 중복 assertion 검토 |
| `tests/test_agent_effectiveness.py` | 591 | effectiveness schema | compatibility와 무관 | 현행 |
| `tests/test_benchmark_aggregate.py` | 565 | aggregate verdict 회귀 | legacy verdict fixture 포함 | #1094 후 #1098 |
| `tests/test_chain_view.py` | 522 | chain view 회귀 | run fixture 중복 가능 | #1094 후 #1098 |
| `tests/test_codex_sandbox_permission.py` | 564 | sandbox 승인 경계 | 현행 safety | 유지 |
| `tests/test_codex_validator_wrapper.py` | 1,522 | Codex wrapper/prose/boundary | 여러 wrapper fixture 중복 가능 | #1096 후 #1098, sandbox safety 보존 |
| `tests/test_design_surface.py` | 578 | design prompt/template sync | legacy authoring 부정 assertion 포함 | #1093 후 #1098 |
| `tests/test_generated_tdd_hooks.py` | 771 | generated install matrix | partial/install fixture가 실사용 | #1096 후 중복 fixture만 #1098 |
| `tests/test_github_project_lifecycle.py` | 1,544 | project lifecycle 스크립트 | compatibility와 무관 | 현행; #1098 크기만으로 선택 금지 |
| `tests/test_hooks.py` | 3,582 | order/state/hook 통합 회귀 | run·alias·fallback assertion 세대 다수 | #1094·#1096 뒤 #1098 핵심 |
| `tests/test_ledger.py` | 598 | ledger current/legacy/mixed/corrupt | compatibility fixture 비중 큼 | #1094 핵심; 4개 안전 시나리오 보존 |
| `tests/test_loop_diagnose.py` | 645 | cross-project 진단 | compatibility와 무관 | 현행 |
| `tests/test_multisession_smoke.py` | 647 | 동시 run smoke | 현행 concurrency safety | 유지 |
| `tests/test_outcome_scorecard.py` | 574 | outcome aggregation | legacy verdict fixture 일부 | #1094 후 #1098 |
| `tests/test_parallel_wave.py` | 978 | wave/merge lock | 현행 concurrency safety | 유지 |
| `tests/test_product_journey.py` | 610 | journey runner | compatibility와 무관 | 현행 |
| `tests/test_provider_chain.py` | 1,466 | provider chain 상태전이 | codex-first fixture와 현행 safety fallback 혼재 | #1095 핵심, mutation-after-failure 보존 |
| `tests/test_run_review.py` | 1,622 | run review current/legacy 분석 | legacy alias/verdict/.steps fixture 비중 큼 | #1094 핵심, 이후 #1098 |
| `tests/test_session_state.py` | 3,533 | state/CLI/run lifecycle | private re-export·legacy state fixture와 현행 safety 혼재 | #1094 핵심, 이후 #1098 |
| `tests/test_story_runner.py` | 545 | story runner lifecycle | 현행 stack fixture | #1097 뒤 #1098 |
| `tests/test_surface_docs_sync.py` | 1,005 | agent/docs/Codex mirror sync | legacy design leniency 문자열 assertion 포함 | #1093 후 #1098 |
| `tests/test_tdd_guard.py` | 816 | central/generated TDD guard | partial install fallback fixture가 실사용 | #1096 후 #1098, TDD invariant 보존 |

실제 감량 우선순위는 `ledger/run_review/session_state`와 대응 테스트의 다세대 persisted 형식, provider-chain의 `codex-first`, design legacy authoring·reader, install partial-state 증거다. archive·release data·safety eval·concurrency·journey 파일은 크기만으로 선택하지 않는다.

## 후속 범위 완전성

| 후속 | inventory 입력 | 책임 |
|---|---|---|
| #1093 | DES-001~006 | design authoring·reader·warning·validator·배포 |
| #1094 | RUN-001~008 | ledger/prose/alias/verdict/session state |
| #1095 | ROUTE-001~005 | schema/preset/export/provider fallback |
| #1096 | INST-001~005 | generated hook/partial install/root/path/worktree |
| #1097 | LIFE-001~005 | current writer/legacy stories/no-AC issue/human/advisory |
| #1098 | 위 500줄 이상 감사의 정책 제거 후 중복 책임 | 단순 분할이 아닌 assertion/helper 통합 |
| #1099 | baseline JSON과 29개 원장 전항목 | 동일 정의 재측정·전체 gate·부모 close audit |

machine validator 결과는 29/29 entry가 정확히 하나의 #1093~#1097에 배정되고 중복 ID가 없으며, 11/11 한시 호환 entry가 4요소를 갖춘다. 대형 파일 56/56도 표에서 유지·정책 cleanup·#1098 검토 중 하나로 판정했다. 어느 범위에도 속하지 않은 후보는 없다.

## Codebase Sanity receipt

- revision: `b676140bcffdaa5843ce59198ecef4f997efddc9`
- semantic scope: full tracked repository의 policy compatibility와 500줄 이상 major text; archive와 external active-project 절대경로는 read-only·비식별 집계
- 기계 증거: baseline command exit 0, full unit suite exit 0, 118.693초, detached clean tree
- coverage: `UNKNOWN` — repository에 full-suite coverage 도구·리포트가 없어 test 수나 green으로 추정하지 않음
- 분류: removable 4, temporary compatibility 11, current 14; unknown 0
- replacement hygiene: 현행 writer와 legacy reader를 분리했고 새 writer가 legacy 형식을 생성한다고 판정한 항목은 없음
- warning 경계: legacy marker 자체는 warning/후속 입력이며 소비자 증거 없이 dead code로 승격하지 않음

새 public command·agent·mode·workflow·상설 hard gate는 만들지 않았다. baseline 스크립트는 #1092/#1099 비교용 내부 one-shot 도구이며 plugin 배포 inventory와 `/init-dcness`에 포함하지 않는다.
