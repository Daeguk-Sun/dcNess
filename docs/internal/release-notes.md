# 릴리즈 노트

> 버전별 변경 요약. 상세 커밋은 `git log {prev_tag}..{tag}` 참조.

---

## Unreleased

---

## v0.26.0 (2026-07-20)

**커밋 범위**: `v0.25.0..v0.26.0` (머지 PR 2개, [#1172](https://github.com/Daeguk-Sun/dcNess/pull/1172) · [#1173](https://github.com/Daeguk-Sun/dcNess/pull/1173))
**핵심 변경**: **Agent step lifecycle 기록을 메인 호출에서 hook 소유로 옮기고, `/impl-loop` 의 provider chain 이 같은 capability 실패를 task 마다 반복 재실행하지 않도록 한** minor 릴리즈. (1) 표준 mode-less foreground Agent step 의 `begin-step`/`end-step` 을 메인이 직접 호출하지 않고 `SubagentStart`/`PostToolUse` hook 이 소유하도록 바꿔 task 당 main request/tool call 을 줄였고, (2) story-runner `chain_id` scope 의 provider 실패 sidecar 를 추가해 CLI 부재·인증·설정 실패처럼 chain 안에서 바뀌지 않는 실패만 memoize 하고 transient 실패는 계속 재시도한다.

### 무엇이 바뀌나

1. **Agent lifecycle 자동화 — main turn 축소** ([#1172](https://github.com/Daeguk-Sun/dcNess/pull/1172) Closes [#1170](https://github.com/Daeguk-Sun/dcNess/issues/1170)) — 표준 mode-less foreground Agent step 마다 메인이 `begin-step` 과 `end-step` 을 직접 호출해 task 당 main request/tool call 이 불필요하게 늘고, PreToolUse 시점에 lifecycle state 를 확정하면 병렬 sibling hook 이 호출을 deny 했을 때 실제 spawn 없는 orphan step 이 남던 문제를 해소. 실제 foreground spawn 이 증명되는 `SubagentStart` 를 `step_started` 경계로 삼아 identity 를 bind 하고, 성공 `PostToolUse` 에서 비어 있지 않은 prose 와 SHA receipt 를 한 번만 기록한다. sibling deny·async·failure·빈 prose·중복 payload·agent/mode/tool identity drift 를 false completion 없이 처리하고 `step_aborted` 복구 경로를 추가했다. modeful Claude 는 explicit `begin-step` + hook completion, Codex/Claude headless 는 wrapper begin/end 소유권을 그대로 유지해 provider 별 공개 계약은 바뀌지 않는다. worktree 와 PREVIOUS_TASKS 는 첫 prompt 전에 hook/wrapper 가 직접 전달하도록 옮겼다. 동일 frozen 1-task fixture 1+1 screening 에서 main requests 12→9, tool calls 12→9, wall-clock 46.831s→41.522s 였으며(양쪽 product AC 1/1, MUST-FIX 0), 단일 표본이므로 통계적 우월성 주장으로 확장하지 않는다.

2. **`/impl-loop` provider 실패 캐시** ([#1173](https://github.com/Daeguk-Sun/dcNess/pull/1173) Closes [#1171](https://github.com/Daeguk-Sun/dcNess/issues/1171)) — 여러 task 가 같은 provider chain 을 반복할 때 CLI 부재나 인증·설정 오류처럼 chain 안에서 바뀌지 않는 capability 실패도 매 task 재실행되어 같은 대기와 fallback 이 반복되던 문제를 해소. story-runner 가 발급하는 `chain_id` 와 exact project/worktree 를 scope 로 하는 provider failure sidecar 를 추가하고, Codex/Claude worker 가 실패를 내부 category 로 전달하도록 했다. `cli_missing`·`auth_unavailable`·`config_unavailable` 만 memoize 하며 timeout·idle·empty·interrupt·network 같은 transient 실패와 workspace/HEAD 변경 실패는 cache 하지 않는다. routing provider 에만 적용하고 explicit provider 와 permission retry 는 우회하며, 성공한 우회 실행은 stale entry 를 지운다. `chain_id` 가 없는 legacy schema 는 no-cache 로 계속 실행하고, unreadable/corrupt JSON 과 project identity mismatch 는 잘못된 scope 로 보아 fail-closed 처리한다. 동일 frozen 2-task fixture 에서 결과 2/2 성공과 fallback 횟수를 유지한 채 unavailable provider 실행이 2회→1회, fallback wall-clock 4.835초→3.759초였다.

### 자기개선 점검

- Sense/Diagnose: 이번 릴리즈 diff 가 Agent lifecycle hook 경계와 `/impl-loop` provider routing 을 건드려 결정적 guard-efficacy 를 재실행 — **48/48 PASS**, 회귀 없음. 전체 unittest 도 재실행해 공개 수치를 실측 동기화 — **1,167/1,167 PASS**. 두 머지 PR 은 각각 개별 CI(pytest·static-quality·public-surface·cross-ref·index-map·doc-sync·plugin-manifest·pr-body)를 통과했다.
- Decide: 소멸 후보 없음. follow-up 없음.
- Verify: Agent lifecycle 경계(sibling deny·async·identity drift·`step_aborted`)와 provider failure cache(category 분류·bypass·invalidation·concurrency) 신규/회귀 테스트 통과. 공개 evidence snapshot(README·`docs/plugin/benchmark.md`)을 v0.26.0 / 2026-07-20 실측(unit 1,167/1,167 · guard 48/48)으로 갱신했고 `node scripts/check_public_evidence.mjs` 로 문서 marker 와 실측 대조를 검증한다.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `hooks/**`·`hooks/hooks.json`·`harness/**`·`scripts/**`·`skills/**`·`docs/plugin/**` 변경.
- **Agent step 을 도는 모든 프로젝트** — 표준 mode-less foreground Agent step 의 lifecycle 기록을 hook 이 소유하므로 메인이 `begin-step`/`end-step` 을 직접 부르지 않는다. modeful Claude 와 headless wrapper 의 호출 계약은 그대로다.
- **`/impl-loop` 를 도는 프로젝트** — 같은 chain 안에서 provider CLI 부재·인증·설정 실패가 확인되면 다음 task 는 그 provider 를 건너뛰고 바로 fallback 으로 간다. transient 실패는 계속 재시도하므로 일시적 오류로 provider 가 영구 배제되지 않는다.

---

## v0.25.0 (2026-07-16)

**커밋 범위**: `v0.24.0..v0.25.0` (머지 PR 2개, [#1166](https://github.com/Daeguk-Sun/dcNess/pull/1166) · [#1167](https://github.com/Daeguk-Sun/dcNess/pull/1167))
**핵심 변경**: **dcNess 자신의 release publish 경계를 tag-only immutable 파이프라인으로 굳히고, 릴리즈 전 preflight 의 행동 예산·judge verdict 파싱을 정합화한** minor 릴리즈. 배포되는 외부 활성 프로젝트 runtime 동작 변화는 없으며, 공개 evidence snapshot 을 현재 revision 실측으로 갱신했다. (1) 같은 plugin version 의 release artifact 불변성을 tag/version/source SHA/bundle digest 4단 정합으로 강제하고 main-push sync 를 제거해 새 `vX.Y.Z` 태그에서만 publish, (2) release preflight 의 핵심 행동 eval 기본 실행을 case 별 1회로 고정해 최초 MISS 를 release FAIL 로 유지하고 judge 최종 verdict 파싱을 eval runner 와 일치시켰다. **v0.25.0 은 이 tag-only immutable publish 파이프라인을 처음 실제로 통과하는 릴리즈다.**

### 무엇이 바뀌나

1. **release artifact 불변성 강제 — tag-only immutable publish** ([#1166](https://github.com/Daeguk-Sun/dcNess/pull/1166) Closes [#1158](https://github.com/Daeguk-Sun/dcNess/issues/1158)) — release publish 가 `main` push 로 트리거돼 이미 배포한 version 의 artifact 가 tag 이동·재빌드로 조용히 바뀔 수 있던 문제를 해소. `sync_release.sh` 가 tag·manifest version·release commit parent 의 tested source SHA·release bundle digest 를 1:1 로 검증하고 같은 version 의 기존 release 와 candidate 의 source SHA/digest 가 다르면 checkout·push 전에 실패하도록 했다. `release-sync.yml` 은 `main` push 가 아니라 새 `vMAJOR.MINOR.PATCH` 태그에서만 실행하며, exact tag source 의 전체 unit suite 와 clean install/update smoke 를 통과한 뒤에만 publish 한다. clean install/update cohort 회귀 테스트와 release runbook 을 함께 갱신했다.

2. **release preflight 행동 예산 + core judge 최종 verdict 정합** ([#1167](https://github.com/Daeguk-Sun/dcNess/pull/1167) Closes [#1157](https://github.com/Daeguk-Sun/dcNess/issues/1157)) — preflight 의 핵심 행동 eval 이 실행 표본 수를 고정하지 않고 judge verdict 파싱이 eval runner 와 달라 판정이 흔들리던 문제를 해소. 기본 실행을 case 별 1회로 고정하고 최초 MISS 를 release FAIL 로 유지하며, 선택형 실패 진단만 자동 4 trial 상한 안에서 실행하되 전체 report·judge trace 를 보존한다. product outcome 축을 현재 성공률이 아니라 historical snapshot 수집 의미로 명확화하고, preflight 가 eval runner 와 동일하게 문서 마지막 `RESULT` 줄을 judge 최종 verdict 로 사용하도록 맞춰(중복 `RESULT` 순서 회귀 테스트 추가) 파싱 불일치를 제거했다.

### 자기개선 점검

- Sense/Diagnose: 이번 릴리즈 diff 가 release publish 경계(`sync_release.sh`·`release-sync.yml`)와 preflight/judge 파싱을 건드려 결정적 guard-efficacy 를 재실행 — **48/48 PASS**, 회귀 없음. 전체 unittest 도 재실행해 공개 수치를 실측 동기화 — **1,152/1,152 PASS**. 두 머지 PR 은 각각 개별 CI(pytest·static-quality·public-surface·cross-ref·index-map·doc-sync·plugin-manifest·pr-body)를 통과했다.
- Decide: 소멸 후보 없음. follow-up 없음.
- Verify: release artifact 불변성·preflight 행동 예산·core judge verdict 신규/회귀 테스트 통과. 공개 evidence snapshot(README·`docs/plugin/benchmark.md`)을 v0.25.0 / 2026-07-16 실측(unit 1,152/1,152 · guard 48/48)으로 갱신했고 `node scripts/check_public_evidence.mjs` 로 문서 marker 와 실측 대조를 검증한다.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — 이번 릴리즈의 실질 변경은 dcNess self 의 release publish 불변성과 preflight 판정이라 외부 활성 프로젝트 runtime 동작 변화는 없다. 배포물에서는 공개 evidence snapshot(README·benchmark)과 version bump 만 반영된다.
- **marketplace 설치/업데이트 사용자** — v0.25.0 부터 release 는 새 `vX.Y.Z` 태그에서만 publish 되고, 이미 배포한 version 의 tag 는 이동·재사용하지 않는다. 태그·version·tested source SHA·bundle digest 4단 정합이 맞아야 사용자에게 도달한 것으로 본다.

---

## v0.24.0 (2026-07-16)

**커밋 범위**: `v0.23.0..v0.24.0` (머지 PR 27개)
**핵심 변경**: **하네스가 쌓아온 legacy 호환 화석과 배포·runtime 무게를 실측 기준으로 걷어내고(감량), eval·product-acceptance 판정의 실행 간 흔들림(flakiness)을 표면화·정합화한** minor 릴리즈. (1) 정책 수명주기 inventory([#1092](https://github.com/Daeguk-Sun/dcNess/issues/1092))를 기준으로 소비자 없는 legacy 계약(구양식 설계 작성 모드·run ledger private facade·provider routing schema v1/v2·install/path prefix·legacy acceptance reader·중복 fixture)을 구현·테스트·배포 단위로 퇴역, (2) 배포 artifact 를 denylist 제외에서 positive allowlist 로 뒤집고 run/session 상태를 단일 transition 소유권으로 통합한 뒤 guard 입력/판정을 `HookRequest`·`GuardContext`·`GuardDecision` 으로 통일하고 runtime evidence(trace·histogram·dashboard·lesson/insight·agent effectiveness)를 배포물에서 제거(**breaking**), (3) LLM 행동 eval 의 flaky 케이스를 marker·자동 후보 표로 표면화하고 (case, run) 셀을 병렬 실행해 wall-clock 을 줄였으며 tier 별 처분을 재실행 규범과 함께 기록, (4) product-acceptance 검수 agent 가 실행마다 흔들리던 순서/분할·근거 판정을 단일 규칙으로 정합화, (5) impl-loop journey 수렴 경계·run-review enum 파싱·impl-validator 커밋 입력 계약을 정리.

### 무엇이 바뀌나

1. **정책 수명주기 sunset — legacy 호환 화석 퇴역** (Epic [#1089](https://github.com/Daeguk-Sun/dcNess/issues/1089)) ([#1116](https://github.com/Daeguk-Sun/dcNess/pull/1116) · [#1117](https://github.com/Daeguk-Sun/dcNess/pull/1117) · [#1119](https://github.com/Daeguk-Sun/dcNess/pull/1119) · [#1121](https://github.com/Daeguk-Sun/dcNess/pull/1121) · [#1124](https://github.com/Daeguk-Sun/dcNess/pull/1124) · [#1130](https://github.com/Daeguk-Sun/dcNess/pull/1130) · [#1133](https://github.com/Daeguk-Sun/dcNess/pull/1133) Closes [#1092](https://github.com/Daeguk-Sun/dcNess/issues/1092) [#1093](https://github.com/Daeguk-Sun/dcNess/issues/1093) [#1094](https://github.com/Daeguk-Sun/dcNess/issues/1094) [#1095](https://github.com/Daeguk-Sun/dcNess/issues/1095) [#1096](https://github.com/Daeguk-Sun/dcNess/issues/1096) [#1097](https://github.com/Daeguk-Sun/dcNess/issues/1097) [#1098](https://github.com/Daeguk-Sun/dcNess/issues/1098)) — 정책이 교체된 뒤에도 이전 writer·reader·fixture·문서의 종료 조건을 한 단위로 추적하는 원장이 없어 legacy 호환 표면이 무기한 누적되던 문제를 해소. 먼저 tracked tree 기준 29개 정책 slice 를 `현재 실사용`/`제거 가능`/`한시적 호환 필요` 로 분류한 inventory·baseline 을 확정([#1116](https://github.com/Daeguk-Sun/dcNess/pull/1116))하고, 이를 근거로 module-architect 의 구양식 `legacy contract sync` 작성 모드([#1117](https://github.com/Daeguk-Sun/dcNess/pull/1117)), `session_state` 가 동적 `__getattr__` 로 다시 노출하던 run ledger private CLI facade([#1119](https://github.com/Daeguk-Sun/dcNess/pull/1119)), routing schema v1/v2·`codex-first` alias([#1121](https://github.com/Daeguk-Sun/dcNess/pull/1121)), 소비자가 사라진 `LEGACY_PATH_PREFIXES` install/path 분기([#1124](https://github.com/Daeguk-Sun/dcNess/pull/1124)), AC·검증 주체가 없어도 `PASS` 를 내던 legacy acceptance reader([#1130](https://github.com/Daeguk-Sun/dcNess/pull/1130))를 퇴역하고, 여러 테스트에 중복되던 persisted run fixture writer 를 단일 책임으로 통합([#1133](https://github.com/Daeguk-Sun/dcNess/pull/1133))했다. 현행 crash recovery 경계와 실제 legacy sample 이 남은 reader 는 보존한다.

2. **배포 경계 positive allowlist + run 상태 단일 소유권 + guard/runtime evidence 경량화 — breaking** (Epic [#1142](https://github.com/Daeguk-Sun/dcNess/issues/1142)) ([#1148](https://github.com/Daeguk-Sun/dcNess/pull/1148) · [#1152](https://github.com/Daeguk-Sun/dcNess/pull/1152) · [#1153](https://github.com/Daeguk-Sun/dcNess/pull/1153) · [#1156](https://github.com/Daeguk-Sun/dcNess/pull/1156) Closes [#1143](https://github.com/Daeguk-Sun/dcNess/issues/1143) [#1144](https://github.com/Daeguk-Sun/dcNess/issues/1144) [#1145](https://github.com/Daeguk-Sun/dcNess/issues/1145) [#1146](https://github.com/Daeguk-Sun/dcNess/issues/1146)) — 배포 계약이 "저장소에서 무엇을 빼는가"(denylist)라 새 repo-only 파일이 기본 배포되고, run live state 와 append-only ledger 의 lifecycle writer 가 CLI·hook·worker 에 분산돼 partial write·pass-through facade drift 가 남던 문제를 해소. 먼저 외부 소비자가 없는 호환 경로를 제거([#1148](https://github.com/Daeguk-Sun/dcNess/pull/1148))한 뒤 `scripts/release_artifact.json` 을 schema v2 positive allowlist 로 전환해 public agents·commands·skills·hooks·사용자 문서와 실제 runtime/scripts 만 선언([#1152](https://github.com/Daeguk-Sun/dcNess/pull/1152))하고, `session_state.transition()` 을 live state 와 lifecycle ledger 의 유일한 mutation boundary 로 통합([#1153](https://github.com/Daeguk-Sun/dcNess/pull/1153))했다. 마지막으로 hook 입력 정규화와 정책 판정을 `HookRequest`·`GuardContext`·`GuardDecision` 으로 통일하고, runtime 에는 복구용 state 와 최소 guard/eval receipt 만 남기며 per-tool trace·histogram·dashboard·자동 lesson/insight·agent effectiveness 분석을 release artifact 에서 제거([#1156](https://github.com/Daeguk-Sun/dcNess/pull/1156))했다. **breaking/migration**: 옛 `dcness-helper guard-telemetry`·`insight` 와 `dcness-efficiency dashboard|patterns|patterns-dashboard|full` 은 silent unknown command 대신 exit 2 와 대체 경로를 안내한다. 손상·부분 `live.json`, malformed `ledger.jsonl`, 위변조된 `step_completed` receipt 는 빈 상태/누락 record 로 축소하지 않고 재생성 안내와 함께 fail-fast 한다. raw receipt 의 기존 epoch·필드 의미는 유지하고, repository 분석은 source checkout 의 `scripts/loop_diagnose.py`, token/cost 는 `dcness-efficiency analyze|summary`, 완료 run 복기는 `/run-review` 를 사용한다.

3. **eval flakiness 표면화 + (case, run) 병렬 실행 + tier 처분 기록** ([#1123](https://github.com/Daeguk-Sun/dcNess/pull/1123) · [#1127](https://github.com/Daeguk-Sun/dcNess/pull/1127) · [#1131](https://github.com/Daeguk-Sun/dcNess/pull/1131) · [#1132](https://github.com/Daeguk-Sun/dcNess/pull/1132) · [#1136](https://github.com/Daeguk-Sun/dcNess/pull/1136) · [#1138](https://github.com/Daeguk-Sun/dcNess/pull/1138) · [#1140](https://github.com/Daeguk-Sun/dcNess/pull/1140) · [#1141](https://github.com/Daeguk-Sun/dcNess/pull/1141) · [#1151](https://github.com/Daeguk-Sun/dcNess/pull/1151) Closes [#1122](https://github.com/Daeguk-Sun/dcNess/issues/1122) [#1120](https://github.com/Daeguk-Sun/dcNess/issues/1120) Part of [#1129](https://github.com/Daeguk-Sun/dcNess/issues/1129)) — LLM 행동 eval 에서 입력·지침이 같아도 실행마다 판정이 흔들리는 flaky 케이스를 표면화하는 경로가 없어(`saturation_candidate` marker 하나뿐이라 `7/10 (70%)` 같은 flaky 가 `active` 로 묻힘) 사람이 리포트를 직접 쳐서 정답률을 눈으로 골라야 하던 문제를 해소. `collect_eval_summary` 에 `flaky_candidate` 파생(min_runs 이상·`0 < passes < attempts`)을 추가하고 `loop_diagnose` 자동 후보 표·sweep digest 가 이를 통과시키도록 연결([#1123](https://github.com/Daeguk-Sun/dcNess/pull/1123))했다. 완전 직렬이던 `evals/run.sh` 를 (case, run) 셀 단위 병렬(`xargs -P "$EVAL_PARALLEL"`, 셀 내부 report→judge 순서만 유지)로 리팩터해 wall-clock 을 줄이고([#1127](https://github.com/Daeguk-Sun/dcNess/pull/1127)) 재실행 처분 규범을 명문화([#1131](https://github.com/Daeguk-Sun/dcNess/pull/1131))했으며, umbrella [#1129](https://github.com/Daeguk-Sun/dcNess/issues/1129) 의 심각·노랑·초록 tier flaky 케이스를 fixed/hold 로 처분 기록([#1132](https://github.com/Daeguk-Sun/dcNess/pull/1132) · [#1136](https://github.com/Daeguk-Sun/dcNess/pull/1136) · [#1138](https://github.com/Daeguk-Sun/dcNess/pull/1138) · [#1140](https://github.com/Daeguk-Sun/dcNess/pull/1140) · [#1141](https://github.com/Daeguk-Sun/dcNess/pull/1141) · [#1151](https://github.com/Daeguk-Sun/dcNess/pull/1151))했다.

4. **product-acceptance 순서/분할·근거 판정 정합** ([#1134](https://github.com/Daeguk-Sun/dcNess/pull/1134) · [#1147](https://github.com/Daeguk-Sun/dcNess/pull/1147) · [#1150](https://github.com/Daeguk-Sun/dcNess/pull/1150) · [#1164](https://github.com/Daeguk-Sun/dcNess/pull/1164) Closes [#1128](https://github.com/Daeguk-Sun/dcNess/issues/1128) [#1139](https://github.com/Daeguk-Sun/dcNess/issues/1139) [#1149](https://github.com/Daeguk-Sun/dcNess/issues/1149) [#1159](https://github.com/Daeguk-Sun/dcNess/issues/1159)) — product-acceptance 검수 agent(`docs/plugin/agents/product-acceptance/product-acceptance-agent.md`)가 story 순서/분할 축(핵심 사용자 확인 동작의 첫 end-to-end 검증이 뒤 story 로 밀리는 결함)과 결정 근거를 실행마다 비일관 판정하던 flaky 를 해소. 근거 표식(`사용자 확정`+결정ID) 인식과 경계선 blocker/warning 비일관을 잡고([#1134](https://github.com/Daeguk-Sun/dcNess/pull/1134)) 순서 축의 warning 강등 escape hatch 를 제거([#1147](https://github.com/Daeguk-Sun/dcNess/pull/1147))했으며, 그 가드가 정상 walking-skeleton(최종 전달 경계까지 얇게 end-to-end 로 닿는 흐름)을 순서 결함으로 과대판정하던 회귀를 전달 경계 도달 여부 기준으로 정밀화([#1150](https://github.com/Daeguk-Sun/dcNess/pull/1150))하고, 순서 판단을 여러 bullet 에 흩어진 상태에서 `순서 판단 단일 규칙` 하나로 축약해 Story AC 가 없어도 PRD·Epic·Story 목적의 제품 경계로 판정하도록 단일화([#1164](https://github.com/Daeguk-Sun/dcNess/pull/1164))했다.

5. **journey 수렴 계약 · run-review enum 파싱 · impl-validator 커밋 입력** ([#1162](https://github.com/Daeguk-Sun/dcNess/pull/1162) · [#1163](https://github.com/Daeguk-Sun/dcNess/pull/1163) · [#1126](https://github.com/Daeguk-Sun/dcNess/pull/1126) Closes [#1154](https://github.com/Daeguk-Sun/dcNess/issues/1154) [#1155](https://github.com/Daeguk-Sun/dcNess/issues/1155) [#1118](https://github.com/Daeguk-Sun/dcNess/issues/1118)) — `/impl-loop` 의 `(JOURNEY)` 가 flow·매니페스트만 쓰고 곧바로 write-zero product-acceptance 에 인계해 build-worker 실행 컨텍스트의 device/service 도달성과 모든 task 를 합친 final tip 수렴 경계가 없던 문제를 해소. product journey 계약에 `acceptance_environment`·`harness_paths` 를 추가하고 build-worker JOURNEY 수렴 mode 로 실행·관찰·수정 단계를 연결([#1162](https://github.com/Daeguk-Sun/dcNess/pull/1162))했다. 함께, run-review 가 상단 명시 `결론: **FAIL**` 을 tail-only scan 으로 놓치고 하단 incidental `PASS` 를 최종 enum 으로 오파싱하던 `MUST_FIX_GHOST` 오탐을, 문서 전체에서 `결론:` 뒤 enum 을 구조적으로 추출(복수면 마지막 명시 결론 우선)하도록 수정([#1163](https://github.com/Daeguk-Sun/dcNess/pull/1163))하고, impl-validator 가 검토 대상 커밋을 직접 조회하도록 Claude/Codex 미러에 read-only `git show`/`diff`/`log` 를 추가해 커밋 id + 변경 파일 목록을 1급 입력으로 삼도록 계약을 정리([#1126](https://github.com/Daeguk-Sun/dcNess/pull/1126))했다.

### 자기개선 점검

- Sense/Diagnose: 이번 릴리즈 diff 가 guard 입력/판정(`HookRequest`·`GuardContext`·`GuardDecision`)·run/session 상태 소유권·order gate·product-acceptance agent 지침·배포 artifact 경계·eval 러너를 건드려 결정적 guard-efficacy 를 재실행 — **48/48 PASS**(이전 39/39 → tdd-guard·boundary·order-gate 케이스 확장 반영), 회귀 없음. 전체 unittest 도 재실행해 공개 수치를 실측 동기화했다 — **1,143/1,143 PASS**. 각 머지 PR 은 개별 CI(pytest·static-quality·public-surface·cross-ref·index-map·doc-sync·plugin-manifest·pr-body)를 통과했다.
- Decide: 소멸 후보 없음. 이번 릴리즈 자체가 Epic [#1089](https://github.com/Daeguk-Sun/dcNess/issues/1089)/[#1142](https://github.com/Daeguk-Sun/dcNess/issues/1142) 로 legacy guard·compatibility surface·runtime evidence 를 대거 제거해 하네스를 감량했다. follow-up 없음.
- Verify: 27개 머지 PR 각각 CI PASS. 정책 sunset·배포 allowlist·run 상태 단일 소유권·guard evidence 경량화·eval flaky/병렬·product-acceptance 정합·journey 수렴·run-review enum·impl-validator 입력 신규/회귀 테스트 통과. LLM 기반 핵심 행동 eval 은 사용자 지시 minor 배포라 릴리즈 시점 재실행은 생략(advisory)하고, eval flakiness 프로그램([#1129](https://github.com/Daeguk-Sun/dcNess/issues/1129))의 tier 처분과 각 머지 PR 개별 실행 결과로 갈음했다.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `harness/**`·`hooks/**`·`scripts/**`·`skills/**`·`agents/**`·`docs/plugin/**`·`evals/**` 변경.
- **옛 진단 CLI 를 쓰던 프로젝트 (breaking)** — `dcness-helper guard-telemetry`·`insight` 와 `dcness-efficiency dashboard|patterns|patterns-dashboard|full` 은 silent unknown 대신 exit 2 + 대체 경로를 안내한다. repository 분석은 source checkout 의 `scripts/loop_diagnose.py`, token/cost 는 `dcness-efficiency analyze|summary`, 완료 run 복기는 `/run-review` 를 쓴다. 손상·부분 `live.json`/malformed `ledger.jsonl`/위변조 receipt 는 빈 상태로 축소하지 않고 재생성 안내와 함께 fail-fast 한다.
- **marketplace 설치/업데이트 사용자** — 배포 artifact 가 denylist 제외가 아니라 positive allowlist(제품 runtime·public agents/commands/skills/hooks·사용자 문서)만 담는다. 새 repo-only 파일은 기본 배포에서 제외되고, per-tool trace·histogram·dashboard·lesson/insight·agent effectiveness 분석은 배포물에서 빠진다. public `/run-review`·`/efficiency` 는 각각 단일 run 복기와 read-only token/cost 요약을 유지한다.
- **`/acceptance`·`/spec` 로 제품 검수하는 프로젝트** — product-acceptance 가 story 순서/분할 결함과 결정 근거를 단일 규칙으로 판정해 실행 간 흔들림이 줄고, 핵심 약속의 첫 end-to-end 검증이 뒤 story 로 밀리는 순서 gap 을 정상 walking-skeleton 과 구분해 지적한다.
- **`/impl-loop` 로 UI journey 를 도는 프로젝트** — `(JOURNEY)` 계약에 `acceptance_environment`·`harness_paths` 가 추가되고, build-worker 가 모든 task tip 에서 실행·관찰·수정하는 수렴 경계를 거친 뒤 product-acceptance 로 인계된다.

---

## v0.23.0 (2026-07-14)

**커밋 범위**: `v0.22.0..v0.23.0` (머지 PR 7개, #1101 · #1103 · #1104 · #1109 · #1110 · #1111 · #1114)
**핵심 변경**: **`/impl-loop` multi-story 토폴로지를 통합 브랜치에서 story PR stack 으로 바꾼 breaking 릴리즈** 이면서, **Codex headless build-worker 의 sandbox 경계를 프로젝트별 opt-in + 사용자 승인 복구로 열고**, marketplace 배포 artifact 를 경량화하고, 제품 outcome 증거 사슬을 UI journey 까지 확장하고, 릴리즈 운영을 단일 preflight 도구로 자동화한 minor 릴리즈. (1) 다중 story 구현이 long-lived 통합 브랜치·`Base Branch` marker 를 폐기하고 story branch stack 을 유지하다 merge 직전에만 `main` 으로 리타겟·rebase, (2) Codex `workspace-write` 의 network/writable-root 를 env opt-in 으로 열고 sandbox 거부를 감지→승인→1회 재시도로 복구, (3) marketplace clean install/update 가 `release` ref 를 직접 소비하도록 배포 artifact 를 단일 manifest 로 경량화(549→191 files), (4) product journey runner 에 UI 화면 증거(`boundary=ui`)와 `(JOURNEY)` 검증 경계 lifecycle 을 추가, (5) 릴리즈 전 evidence 축을 고정 순서로 한 번에 수집하는 `scripts/release_preflight.py` 운영 자동화와 공개 evidence 비식별화·문구 정정.

### 무엇이 바뀌나

1. **`/impl-loop` story PR stack 전환 — breaking migration** ([#1111](https://github.com/Daeguk-Sun/dcNess/pull/1111) Closes [#1108](https://github.com/Daeguk-Sun/dcNess/issues/1108)) — multi-story 흐름이 long-lived 통합 브랜치와 자동 merge 를 전제해 "사용자만 merge 를 승인한다" 는 운영 원칙 및 story 별 독립 PR 검증과 충돌하던 문제를 해소. story 1 은 `main`, 이후 story 는 직전 story branch 를 base 로 하는 stack 정보를 runner 가 산출하고, non-default base PR 의 finalize 를 fail-fast 로 차단하며, merge 직전에만 `main` 리타겟·rebase 및 downstream restack 을 수행한다. PR base 조회 실패도 fail-closed 로 처리하고 peer lock 이후 merge 직전 base 를 재검증한다. 자동 merge 를 제거하고 조건부 QA PR·stack-tip 대비 Code Validation/Sanity·story close acceptance 규칙을 동기화했으며, `Base Branch` marker 를 폐기했다. **마이그레이션**: 플러그인 업데이트 시 marker 가 남은 in-flight epic 은 `pr-trailer` 와 issue 생성이 fail-fast 하므로, marker 를 제거하고 `dcness-story-runner next-action` 의 `pr_base` 에 따라 story branch 를 재구성한 뒤 계속해야 한다. 기존 진행 branch 는 자동 변환하지 않는다.

2. **Codex build-worker sandbox opt-in + 사용자 승인 복구** ([#1110](https://github.com/Daeguk-Sun/dcNess/pull/1110) Closes [#1105](https://github.com/Daeguk-Sun/dcNess/issues/1105), [#1114](https://github.com/Daeguk-Sun/dcNess/pull/1114) Closes [#1113](https://github.com/Daeguk-Sun/dcNess/issues/1113)) — Codex headless build-worker 가 항상 기본 `workspace-write` sandbox 로 실행돼 loopback IPC·workspace 밖 build cache 쓰기가 필요한 Gradle 계열 외부 활성 프로젝트를 자체 검증하지 못하던 문제를 해소. `DCNESS_CODEX_NETWORK_ACCESS=1|true|on` 일 때만 network access 를, `DCNESS_CODEX_WRITABLE_ROOTS` 의 path-separator 목록으로 추가 writable roots 를 opt-in 전달한다(`danger-full-access` 미제공, 미설정·`off` 는 기존 인자 유지). 이어서 sandbox 거부를 일반 검증 실패와 구분해, `VALIDATION_BLOCKED` prose 를 제외한 Codex raw log 에서 실제 SocketException/sandbox write signature 만 permission receipt·ledger event 로 기록하고, `dcness-codex-permission` helper 가 이번 실행만 허용/프로젝트 저장(`.claude/settings.local.json` 보존 병합)/거부를 처리한 뒤 승인한 env 만 Codex worker 재시도 1회에 전달한다.

3. **marketplace artifact 경량화 + install/update 정합** ([#1103](https://github.com/Daeguk-Sun/dcNess/pull/1103) Closes [#1102](https://github.com/Daeguk-Sun/dcNess/issues/1102)) — 기존 `source: "./"` 설치가 저장소 전체 checkout 을 cache 에 복사해 사용자가 소비하지 않는 테스트·평가·내부 문서·self CI 도구까지 배포하던 문제를 해소. `scripts/release_artifact.json` 을 단일 include/exclude·필수 runtime·허용 cache metadata 계약으로 추가하고, marketplace source 를 GitHub `release` ref 로 전환해 candidate·release sync 가 하나의 artifact manifest 를 공유한다. 격리 install 기준 self 전용 파일을 제거한 payload 는 549파일·5,159,235 bytes·102,346 LOC 에서 191파일·2,139,171 bytes·43,138 LOC 로 줄었으며, Claude Code 2.1.170 으로 clean install 과 이전→새 명시 버전 update 를 모두 격리 검증했다. SessionStart additionalContext 는 별도 지표(2,068 bytes, 약 517 token)로 유지해 package 감소를 prompt 감소로 주장하지 않는다.

4. **UI journey 실행 증거 pilot + `(JOURNEY)` 검증 경계 lifecycle** ([#1104](https://github.com/Daeguk-Sun/dcNess/pull/1104) Closes [#1080](https://github.com/Daeguk-Sun/dcNess/issues/1080), [#1109](https://github.com/Daeguk-Sun/dcNess/pull/1109) Closes [#1107](https://github.com/Daeguk-Sun/dcNess/issues/1107)) — 기존 product journey runner 가 `api`·`cli`·`integration` 경계만 허용해 UI 다단계 흐름의 화면 상태·screenshot 을 receipt 에 연결하지 못하던 문제를 해소. runner 에 선택적 `boundary=ui` 와 `ui_evidence.steps` 를 추가해 UI 단계 최소 2개·final 단계 전체 AC coverage·screenshot/state/log 의 run-directory 경계·존재·SHA-256 을 fail-closed 로 검증하고, mock-only·앱 미기동·evidence 변조·symlink escape 가 제품 outcome PASS 가 되지 않게 했다. 이어서 module-architect REQ 에 도구 중립 `(JOURNEY)` taxonomy 를 추가하고, build-worker 는 flow·매니페스트만 작성한 뒤 product-acceptance 가 조건부 Bash 로 봉인 러너를 실행하는 lifecycle(설계 taxonomy→build-worker 산출물→acceptance 실행·판정)을 연결했다.

5. **릴리즈 운영 자동화(preflight) + 공개 evidence 비식별화·문구 정정** ([#1114](https://github.com/Daeguk-Sun/dcNess/pull/1114) 내 [#1088](https://github.com/Daeguk-Sun/dcNess/issues/1088), [#1101](https://github.com/Daeguk-Sun/dcNess/pull/1101) Closes [#1064](https://github.com/Daeguk-Sun/dcNess/issues/1064)) — 릴리즈 전 evidence 축(guard·핵심 행동 eval·judge calibration·제품 outcome·agent effectiveness·경량화 결정·공개 evidence·bundle 소비 smoke)을 감사 가능한 고정 순서로 한 번에 수집하는 `scripts/release_preflight.py` 와 harness 실험 러너(`evals/harness_experiment.py`), loop_diagnose 진단 보강을 추가했다. 함께, benchmark snapshot 측정일과 prose 불일치를 교정하고 cross-session 값을 unmeasured(null) 의미로 정정했으며, sanitizer/validator 의 host-home 탐지가 macOS `/Users` 뿐 아니라 Linux `/home` 경로도 `<HOME>` 으로 치환·거부하도록 강화했다.

### 자기개선 점검

- Sense/Diagnose: 이번 릴리즈 diff 가 order gate·headless worker(Codex sandbox)·boundary·TDD 인접 영역과 story-runner·product journey·release artifact 를 건드려 결정적 guard-efficacy 를 재실행 — **39/39 PASS**, 회귀 없음. 전체 unittest 도 재실행해 공개 snapshot 수치를 실측 동기화했다. 각 머지 PR 은 개별 CI(pytest·static-quality·public-surface·cross-ref·index-map·doc-sync)와 guard-efficacy 39/39 를 통과했고, #1104·#1109·#1111 은 행동 eval(30/30 등)을 개별 실행했다.
- Decide: 소멸 후보 없음. follow-up 없음. (marketplace artifact·release preflight 로 배포 경계·릴리즈 절차를 오히려 단순화했다.)
- Verify: 7개 머지 PR 각각 CI PASS. story PR stack runner·Codex sandbox opt-in/permission·release artifact·UI journey·(JOURNEY) lifecycle·release preflight 신규/회귀 테스트 통과. LLM 기반 핵심 행동 eval 은 사용자 지시 minor 배포라 릴리즈 시점 재실행은 생략(advisory)하고 각 PR 개별 실행 결과로 갈음했다.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `harness/**`·`hooks/**`·`scripts/**`·`skills/**`·`agents/**`·`docs/plugin/**` 변경. marketplace 는 이제 경량 `release` ref artifact 를 소비한다.
- **`/impl-loop` 로 multi-story/epic 을 도는 프로젝트 (breaking)** — 통합 브랜치·`Base Branch` marker 가 폐기되고 story PR stack 으로 바뀐다. marker 가 남은 in-flight epic 은 marker 제거 + `dcness-story-runner next-action` 의 `pr_base` 기준 story branch 재구성 후 계속해야 하며, 자동 변환은 없다.
- **Codex headless build-worker(Gradle 등) 사용 프로젝트** — `.claude/settings.local.json` 의 `env` 에 `DCNESS_CODEX_NETWORK_ACCESS`/`DCNESS_CODEX_WRITABLE_ROOTS` opt-in 을 추가하면 loopback IPC·workspace 밖 build cache 쓰기가 필요한 검증을 headless 로 수행할 수 있고, sandbox 거부 시 승인→1회 재시도 복구 여정이 제공된다.
- **marketplace 설치/업데이트 사용자** — 설치 cache 가 저장소 전체 checkout 이 아니라 경량 `release` ref artifact(v0.23.0 릴리즈 smoke 실측 194파일·약 2.23MB·45,019 LOC)를 소비한다. 소비하지 않던 테스트·평가·내부 문서·self CI 도구가 더는 배포되지 않는다.
- **`/acceptance`·`/impl-loop` 로 제품 검수하는 프로젝트** — UI 다단계 흐름의 화면 증거(`boundary=ui`)와 `(JOURNEY)` 검증 경계가 연결돼, mock-only/설명만으로 UI Story AC 가 제품 outcome PASS 되던 경로가 차단된다.

---

## v0.22.0 (2026-07-13)

**커밋 범위**: `v0.21.0..v0.22.0` (머지 PR 24개)
**핵심 변경**: **하네스가 "절차를 따랐다"가 아니라 "제품 outcome 과 agent 효과를 실측 증거로 남긴다"는 축을 세운** minor 릴리즈. (1) Epic 1064 로 agent 탐색·변경 효과를 실측 1+1 record 와 provenance 로 남기고, 공개 수치는 과장 대신 측정 계약 검증으로 하향하며, non-UI journey·lean ablation·공개 evidence freshness gate·close audit 까지 증거 사슬을 연결, (2) 제품 outcome scorecard 와 운영 baseline, 구현 전 결정 완전성 pilot 을 붙여 process 신호와 실제 제품 outcome 을 분리해 주장, (3) architecture cartography freshness lifecycle 을 연결해 설계 지도의 신선도 책임을 명시, (4) 수용 기준(AC) 계층과 이슈 마감 상태 계약을 정비해 미충족·표기 변형 우회로 clean close 되던 경로를 차단, (5) impl-loop story 경계·task 상태 복구, (6) 실사고 eval 사람 기준 보정과 claude -p 하네스 격리로 세션 baseline 을 43k→27k 로 낮췄다.

### 무엇이 바뀌나

1. **Epic 1064 — agent effectiveness 실측 측정 파이프라인** ([#1090](https://github.com/Daeguk-Sun/dcNess/pull/1090) · [#1086](https://github.com/Daeguk-Sun/dcNess/pull/1086) · [#1091](https://github.com/Daeguk-Sun/dcNess/pull/1091) · [#1083](https://github.com/Daeguk-Sun/dcNess/pull/1083) · [#1081](https://github.com/Daeguk-Sun/dcNess/pull/1081) · [#1082](https://github.com/Daeguk-Sun/dcNess/pull/1082) · [#1084](https://github.com/Daeguk-Sun/dcNess/pull/1084) Closes [#1064](https://github.com/Daeguk-Sun/dcNess/issues/1064) [#1070](https://github.com/Daeguk-Sun/dcNess/issues/1070)) — agent 의 탐색·변경 효과를 주장이 아니라 실측 record 로 남기는 측정 축을 세웠다. 실측 1+1 record 와 provenance 를 확보(`evals/agent_effectiveness_measure.py`, [`outcome-baseline.md`](outcome-baseline.md))하고, 공개 수치는 과장 대신 측정 계약 검증으로 하향했다. non-UI journey evidence 계약(story 1067), lean ablation 실증 기록(story 1069), agent 탐색·변경 효과 측정(story 1070), 공개 evidence freshness gate(story 1071)를 연결하고, evidence close audit 로 증거 미충족 마감을 차단한다.

2. **제품 outcome scorecard + 구현 전 결정 완전성 pilot** ([#1072](https://github.com/Daeguk-Sun/dcNess/pull/1072) · [#1076](https://github.com/Daeguk-Sun/dcNess/pull/1076) Closes [#1066](https://github.com/Daeguk-Sun/dcNess/issues/1066) [#1065](https://github.com/Daeguk-Sun/dcNess/issues/1065)) — process 신호(게이트 통과·절차 준수)와 실제 제품 outcome 을 분리해 주장하도록 outcome scorecard 와 운영 baseline 을 추가했다([`docs/plugin/outcome-scorecard.md`](../plugin/outcome-scorecard.md)). `/spec`·`/design` 에서 구현 방향을 바꾸는 결정의 완전성(결정 범위·근거 상태·질문/위임·완료 의미)을 pilot 으로 연결했다([`docs/plugin/decision-completeness.md`](../plugin/decision-completeness.md)).

3. **architecture cartography freshness lifecycle** ([#1060](https://github.com/Daeguk-Sun/dcNess/pull/1060) · [#1061](https://github.com/Daeguk-Sun/dcNess/pull/1061) · [#1063](https://github.com/Daeguk-Sun/dcNess/pull/1063) Closes [#1059](https://github.com/Daeguk-Sun/dcNess/issues/1059) [#1058](https://github.com/Daeguk-Sun/dcNess/issues/1058) [#1057](https://github.com/Daeguk-Sun/dcNess/issues/1057)) — architecture cartography 계약을 정합화하고, 구현이 설계 지도의 freshness 를 책임지는 경로와 freshness lifecycle 을 연결해 설계 지도가 코드 현실과 어긋난 채 방치되지 않도록 했다.

4. **수용 기준(AC) 계층 + 이슈 마감 상태 계약 정비** ([#1050](https://github.com/Daeguk-Sun/dcNess/pull/1050) · [#1049](https://github.com/Daeguk-Sun/dcNess/pull/1049) · [#1053](https://github.com/Daeguk-Sun/dcNess/pull/1053) · [#1054](https://github.com/Daeguk-Sun/dcNess/pull/1054) · [#1055](https://github.com/Daeguk-Sun/dcNess/pull/1055) · [#1079](https://github.com/Daeguk-Sun/dcNess/pull/1079) Closes [#1046](https://github.com/Daeguk-Sun/dcNess/issues/1046) [#1048](https://github.com/Daeguk-Sun/dcNess/issues/1048) [#1051](https://github.com/Daeguk-Sun/dcNess/issues/1051) [#1052](https://github.com/Daeguk-Sun/dcNess/issues/1052) [#1078](https://github.com/Daeguk-Sun/dcNess/issues/1078)) — 수용 기준 계층과 이슈 마감 계약을 정비해, 미충족·미체크 AC 로 clean close 되거나 AC 표기 변형으로 감사를 우회하던 경로를 차단했다. architecture-validator 고위험 상태 계약 추적, module-architect 상태 계약 선행 pass, close audit 실행 경로와 coverage 진단 정합화, module state idempotence 판정을 함께 보강했다.

5. **impl-loop story 경계·task 상태 복구** ([#1042](https://github.com/Daeguk-Sun/dcNess/pull/1042) · [#1045](https://github.com/Daeguk-Sun/dcNess/pull/1045) Closes [#1041](https://github.com/Daeguk-Sun/dcNess/issues/1041) [#1043](https://github.com/Daeguk-Sun/dcNess/issues/1043)) — `/impl-loop` 이 story 경계와 task 상태를 복구하고, story 를 교차 배치(interleave)하던 경로를 차단해 story 단위 runner 경계를 결정적으로 유지한다.

6. **eval 사람 기준 보정 + claude -p 하네스 격리 + codebase sanity 게이트** ([#1077](https://github.com/Daeguk-Sun/dcNess/pull/1077) · [#1074](https://github.com/Daeguk-Sun/dcNess/pull/1074) · [#1075](https://github.com/Daeguk-Sun/dcNess/pull/1075) Closes [#1068](https://github.com/Daeguk-Sun/dcNess/issues/1068) [#1073](https://github.com/Daeguk-Sun/dcNess/issues/1073) [#1062](https://github.com/Daeguk-Sun/dcNess/issues/1062)) — 실사고 기반 행동 eval 을 사람 기준으로 보정하고, eval 의 `claude -p` 하네스를 격리해 세션 baseline 을 43k→27k 로 낮췄다. Epic Codebase Sanity 마감 게이트를 연결했다.

7. **init-dcness 비활성화 안내 정정** ([#1085](https://github.com/Daeguk-Sun/dcNess/pull/1085) Closes [#955](https://github.com/Daeguk-Sun/dcNess/issues/955)) — `/init-dcness` 의 비활성화 안내가 실존하지 않는 경로를 가리키던 문제를 실존 경로(`/disable-dcness`)로 정정했다.

### 자기개선 점검

- Sense/Diagnose: 이번 diff 가 AC 상태 계약 validator·close audit·eval 하네스·architecture cartography·order gate 인접 영역을 건드려 결정적 guard-efficacy 를 재실행 — **39/39 PASS**, 회귀 없음. LLM 기반 행동 eval 은 사용자 지시 minor 배포라 생략(advisory)하고 각 머지 PR CI(pytest·static-quality·public-surface·cross-ref·index-map·doc-sync)로 검증됨.
- Decide: 소멸 후보 없음. follow-up 없음.
- Verify: 24개 머지 PR 각각 CI PASS. AC 계층·close audit·module state·story-runner·outcome scorecard·public evidence·product journey·lean ablation 신규/회귀 테스트 통과.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `docs/plugin/**`·`skills/**`·`agents/**`·`evals/**`·`harness/**`·`scripts/**` 변경.
- **이슈 마감 규율이 강화된 프로젝트** — 미충족·미체크 AC 나 표기 변형으로 clean close 하던 경로가 차단된다. AC 를 모두 충족·체크해야 마감 계약을 통과한다.
- **`/spec`·`/design` 사용 프로젝트** — 구현 방향을 바꾸는 결정의 완전성(범위·근거·질문/위임·완료 의미)이 pilot 으로 점검되고, 제품 outcome scorecard 로 process 신호와 실제 제품 outcome 을 분리해 본다.
- **설계 지도(architecture) 를 쓰는 프로젝트** — cartography freshness lifecycle 로 지도의 신선도 책임이 명시되어 코드와 어긋난 채 방치되지 않는다.
- **`/impl-loop` 로 story/epic 을 도는 프로젝트** — story 경계·task 상태가 결정적으로 복구되고 story 교차 배치가 차단된다.

---

## v0.21.0 (2026-07-10)

**커밋 범위**: `v0.20.0..v0.21.0` (머지 PR 3개, #1033 · #1037 · #1038)
**핵심 변경**: **`/impl`·`/impl-loop` 2진입점을 간소화하고, Stop hook 의 동일 agent 재라운드 오작동과 headless wrapper 의 telemetry 전제조건 hard-fail 을 함께 고친** minor 릴리즈. (1) `/impl` 이 설계도 유무 1차 분기·high-risk 자동 되돌림을 하지 않고 concrete signal 이 있으면 메인 직접 구현으로 진행하며 cross-provider review 를 기본화, (2) Stop hook 자동 end-run 이 동일 agent 재라운드에서 진행 중 라운드를 완료로 오인해 조기 `end-run` 하던 문제를 라운드 진행 감지로 보호, (3) headless wrapper 5종이 `sid/rid` telemetry 메타 미해결을 provider 실행 전제조건처럼 hard-fail 하던 것을 degraded 실행 경로로 바꿔 timeout/idle-timeout/raw log 보호를 유지, (4) `/to-issue` Issue Brief 자족성의 전제(등록 세션과 처리 세션이 다르다)를 명시.

### 무엇이 바뀌나

1. **`/impl`·`/impl-loop` 2진입점 간소화 + cross-provider review 기본화** ([#1033](https://github.com/Daeguk-Sun/dcNess/pull/1033) [#1032](https://github.com/Daeguk-Sun/dcNess/issues/1032)) — `/impl` 이 설계도 유무 1차 분기와 high-risk 자동 되돌림을 하지 않고, concrete signal 이 있으면 메인 직접 구현으로 진행한다. high-risk 는 설계 선행 권고 한 줄만 출력하고, 사용자가 진행을 택하면 구현한다. 자연어-only 요청은 GitHub issue 1개 등록 여부를 한 번 확인한다. `/impl-loop` 은 SDD story/epic 설계도 입력 → build-worker headless → merge candidate `impl-validator` 통합 리뷰 모델로 설명을 정리한다. 과거 `enable-role-split-routing` 으로 `routing.json` 에 `impl-validator=claude` 가 명시 저장된 프로젝트는 override 존중 원칙 때문에 새 cross-provider 기본을 자동으로 받지 않으며, 추천값을 다시 적용하려면 `dcness-helper routing enable-role-split-routing` 실행 후 `dcness-helper routing doctor` 로 확인한다.

2. **Stop hook 동일 agent 재라운드 진행 보호** ([#1037](https://github.com/Daeguk-Sun/dcNess/pull/1037) Closes [#1035](https://github.com/Daeguk-Sun/dcNess/issues/1035)) — Stop hook 자동 `end-run` 은 메인 응답 종료 시 마지막 완료 step 상태를 보고 run 종료 누락을 막는다. 하지만 동일 agent 가 여러 라운드를 도는 흐름에서 `end-step` 직후 같은 agent 의 새 `begin-step` 이 열려도, 기존 가드가 마지막 완료 step 과 `live.json.current_step` 의 `(agent, mode)` 일치만 비교해 진행 중 라운드를 완료로 오인하고 조기 `end-run` 할 수 있었다. 라운드 진행 감지를 추가해 진행 중 라운드를 종료하지 않도록 보호하고, step count 파싱 helper 를 정리했다.

3. **headless wrapper degraded 실행 경로** ([#1038](https://github.com/Daeguk-Sun/dcNess/pull/1038) Closes [#1036](https://github.com/Daeguk-Sun/dcNess/issues/1036)) — headless wrapper 5종이 telemetry 귀속용 `sid/rid` 해석 실패를 provider launch 전제조건처럼 취급해 hard-fail 하던 문제를 해소. `sid/rid` 는 로그·ledger 귀속 메타데이터이므로, 미해결만으로 본작업 실행을 차단하면 wrapper 의 timeout·idle-timeout·raw log 보존 보호까지 함께 사라졌다. 각 wrapper 가 중복 보유하던 `auto_detect_session_id`/`auto_detect_run_id` preflight 를 공통 `scripts/lib/headless_context.sh` 로 모으고, 미해결 시 hard-fail 대신 degraded 로 진행하되 timeout/idle-timeout/raw log 보호는 유지한다. headless context 진단 출력은 stderr 로 분리했다.

4. **`/to-issue` cross-session handoff 원칙 명시** ([#1033](https://github.com/Daeguk-Sun/dcNess/pull/1033)) — `/to-issue` 로 이슈를 등록하는 세션과 그 이슈를 처리·구현하는 세션은 기본적으로 다르다. 기존 원칙 섹션이 "Issue Brief 는 계약이고 대화는 context 다" 라고만 하고 *왜 자족적이어야 하는가* 의 전제(다른 세션이 처리한다)를 명시하지 않아 컨텍스트 이관이 약하게만 암시됐다. 등록 세션이 대화에서 이미 아는 배경·제약·의도를 Issue Brief 본문으로 옮겨 이슈가 자족적이어야 함을 명시했다.

### 자기개선 점검

- Sense/Diagnose: 이번 diff 가 Stop hook(`harness/hooks.py`·`hooks/stop-end-run.sh`·`harness/session_state.py`)·headless wrapper(`scripts/dcness-*`·`scripts/lib/headless_context.sh`)·`skills/impl*`·order gate 인접 영역과 `evals/guard_efficacy.py` 자체를 건드려 결정적 guard-efficacy 를 재실행 — **39/39 PASS**, 회귀 없음. LLM 기반 행동 eval 은 사용자 지시 빠른 minor 배포라 생략(advisory)하고 각 머지 PR CI(pytest·static-quality·public-surface·cross-ref·index-map)로 검증됨.
- Decide: 소멸 후보 없음. follow-up 없음.
- Verify: `test_provider_chain`(headless degraded 회귀 포함 신규)·`test_hooks`(Stop hook 재라운드)·`test_agent_routing`·`test_impl_preview` 및 각 머지 PR CI PASS.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `/impl` 경량화·`/impl-loop` runner, Stop hook 재라운드 보호, headless wrapper degraded 실행, `/to-issue` 원칙 강화 등 `skills/impl*/**`·`skills/to-issue/**`·`harness/**`·`hooks/**`·`scripts/**`·`docs/plugin/**` 변경.
- **`/impl`·`/impl-loop` 사용 프로젝트** — `/impl` 이 concrete signal 이 있으면 메인 직접 구현으로 진행하고 high-risk 는 권고 한 줄만 출력하며, 자연어-only 요청은 `/to-issue` 등록 여부 확인으로 이어진다. review 는 cross-provider 기본이다.
- **headless worker(Codex/Claude) 사용 프로젝트** — `sid/rid` telemetry 메타 미해결이어도 구현이 hard-fail 되지 않고 degraded 로 진행하며, timeout·idle-timeout·raw log 보호는 유지된다.
- **여러 라운드를 도는 impl 흐름** — Stop hook 자동 `end-run` 이 진행 중 라운드를 완료로 오인해 조기 종료하지 않는다.
- **`/to-issue` 사용 프로젝트** — 등록 세션의 배경·제약·의도가 Issue Brief 본문으로 옮겨져 다른 세션이 처리해도 이슈가 자족적이어야 함이 지침에 명시됐다.

---

## v0.20.0 (2026-07-10)

**커밋 범위**: `v0.19.0..v0.20.0` (머지 PR 1개, #1029)
**핵심 변경**: **헤드리스 `claude` 구현 worker 에 idle timeout 을 추가해 codex worker 와 패리티를 맞춘** minor 릴리즈. 무진행(stdout/stderr/workspace 무변화) 시 하드 타임아웃(1200s)까지 기다리지 않고 조기 종료한다.

### 무엇이 바뀌나

1. **`dcness-claude-worker` idle timeout — codex worker 패리티** ([#1029](https://github.com/Daeguk-Sun/dcNess/pull/1029) Closes [#1028](https://github.com/Daeguk-Sun/dcNess/issues/1028)) — 헤드리스 `claude` 구현 worker 가 하드 타임아웃(`DCNESS_CLAUDE_TIMEOUT` 기본 1200s)만 있어, 멈추거나 헛돌면 최대 20분 낭비 후에야 종료됐다. codex worker(`DCNESS_CODEX_IDLE_TIMEOUT`)와 동일한 폴링 루프로 `run_claude_once` 를 교체해 output/raw-log/git-status 무진행이 `DCNESS_CLAUDE_IDLE_TIMEOUT`(기본 180s) 이상 지속되면 `exit 124` 로 조기 종료한다. claude -p 의 progress 신호 차이로 인한 정상 세션 false-kill 을 완화하려 다중 신호를 함께 추적한다. correctness/boundary 강제(post-hoc git-diff 담당)와 무관한 순수 낭비 시간 방지다.

### 자기개선 점검

- Sense/Diagnose: 본 릴리즈는 worker timeout 파리티 단일 fix (guard/hook/agent/skill 미변경) 라 guard-efficacy·행동 eval 트리거 대상이 아니다.
- Decide: 소멸 후보 없음. follow-up 없음.
- Verify: `test_provider_chain` 13/13 (신규 idle 회귀 포함) 통과.

---

## v0.19.0 (2026-07-09)

**커밋 범위**: `v0.18.0..v0.19.0` (머지 PR 2개, #1018 · #1021)
**핵심 변경**: **기본 구현 진입점 `/impl` 을 경량화하고 `/impl-loop` 을 story 단위 결정적 runner 로 재편한** minor 릴리즈. (1) `/impl` 을 메인 직접 구현 + 격리 pr-reviewer 모델로 단순화해 내부 worker/headless 엔진 축을 외부 사용자에게서 숨기고, 자연어-only 요청은 `/to-issue` 등록 여부 확인으로 보내는 결정적 impl-preview helper 를 추가, (2) `/impl-loop` 에 task commit·ready-for-PR·story PR mark 상태를 관리하는 deterministic story-runner state helper 와 `scripts/dcness-story-runner` wrapper 를 추가하고 task commit + story PR 경계(code-validator/pr-reviewer 1회) 기준으로 문서를 정리, (3) 더 이상 쓰지 않는 compact-design surface 를 제거, (4) Codex headless worker 에 stdout/prose/git status 기반 idle timeout 을 추가, (5) no-trace 외부 활성 프로젝트가 in-place 구현 진입에서 generated TDD hook 미커밋으로 오차단되던 문제를 해소.

### 무엇이 바뀌나

1. **`/impl` 경량화 — 엔진 축 은폐 + 자연어-only preview** ([#1021](https://github.com/Daeguk-Sun/dcNess/pull/1021) Part of [#1019](https://github.com/Daeguk-Sun/dcNess/issues/1019)) — 기본 구현 진입점 `/impl` 이 일반 구현에서도 worker/headless 엔진 축을 노출하고 자연어-only 요청을 바로 구현으로 밀 수 있던 문제를 해소. `/impl` 을 메인 직접 구현 + 격리 pr-reviewer 모델로 정리해 내부 엔진 축을 외부 사용자에게서 숨기고, `harness/impl_preview.py` 결정적 helper 를 추가해 자연어-only 요청을 `/to-issue` 선등록(issue body 가 AC·히스토리 기준) 흐름으로 보낸다. 큰 `/impl` 변경은 리뷰 가능한 의미 단위 커밋으로 쪼갠다는 원칙을 추가했다.

2. **`/impl-loop` story-runner 결정적 상태 모델** ([#1021](https://github.com/Daeguk-Sun/dcNess/pull/1021) Part of [#1019](https://github.com/Daeguk-Sun/dcNess/issues/1019)) — `/impl-loop` 이 task 마다 PR/review/pre-flight 를 반복하던 오래된 모델을 story 단위 runner 방향으로 재편. `harness/story_runner.py` deterministic state helper 와 `scripts/dcness-story-runner` executable wrapper 를 추가해 task commit, ready-for-PR, story PR mark 상태를 LLM 기억이 아니라 JSON state 로 결정하고, `/impl-loop` 문서를 task commit + story PR 경계(code-validator/pr-reviewer 1회) 기준으로 정리했다. `dcness-story-runner` 는 `/impl-loop` 내부 deterministic helper 로 새 public skill/command 는 아니다.

3. **compact-design surface 제거** ([#1021](https://github.com/Daeguk-Sun/dcNess/pull/1021)) — 더 이상 쓰지 않는 `compact-design` SKILL 과 `compact-plan` 템플릿, 관련 문서·테스트 참조를 제거했다. `check_public_surface` / `check_design_artifact_structure` 및 문서 sync 테스트로 회귀 검증한다. 경량 모듈 설계 되돌림 목적지는 유지되던 잔재였고 새 product feature/epic 설계는 `/design` 이 담당한다.

4. **Codex headless worker idle timeout** ([#1021](https://github.com/Daeguk-Sun/dcNess/pull/1021)) — headless worker 가 출력/파일 변화 없이 오래 멈추면 전체 wall-clock timeout 중심 판정이 idle 을 조기 감지하지 못하던 문제를 해소. `dcness-codex-worker` 에 stdout/prose/git status 기반 idle timeout(`DCNESS_CODEX_IDLE_TIMEOUT`, 기본 180초)을 추가하고 session_state prompt probe cache 를 보강했다.

5. **no-trace 프로젝트 in-place TDD preflight 허용** ([#1018](https://github.com/Daeguk-Sun/dcNess/pull/1018) [#1017](https://github.com/Daeguk-Sun/dcNess/issues/1017)) — 0.18 impl pre-flight TDD 게이트가 generated TDD hook 파일의 Git 커밋을 항상 요구해, `.claude/`·`.dcness/`·`.codex/` 를 로컬 전용으로 두는 no-trace 외부 활성 프로젝트가 in-place 구현 진입에서 구조적으로 차단되던 문제를 해소. generated TDD hook 상태에 `linked_worktree`·`generated_files_commit_required` 를 추가하고 게이트 통과 조건을 `CC+Codex registered` 이며 `committed OR !commit_required` 로 조정했다. in-place 는 uncommitted 여도 디스크 실존·등록으로 통과하고, 새 checkout 으로 guard 전파가 필요한 linked worktree 의 missing/uncommitted hook 은 계속 차단한다.

### 자기개선 점검 기록

| 날짜 | 입력 | 판정 |
|---|---|---|
| 2026-07-09 | `python3.11 evals/guard_efficacy.py` (42/42) | 사용자 지시 빠른 minor 배포. 이번 diff 가 TDD pre-flight 게이트(#1018)·headless worker·order gate 인접 영역(`harness/tdd_hooks.py`·`harness/session_state.py`·`scripts/dcness-codex-worker`)을 건드려 결정적 guard-efficacy 를 재실행 — **42/42 PASS**, 회귀 없음. LLM 기반 행동 eval 은 이번 diff 가 결정적 gate/상태 helper 중심이라 각 머지 PR CI(pytest·static-quality·public-surface·cross-ref·index-map)로 검증됨 — 생략(advisory). loop_diagnose 심화 점검은 빠른 배포 지시로 생략. **소멸 후보 없음.** |

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `/impl` 경량화, `/impl-loop` story-runner 상태 모델, compact-design 제거, headless idle timeout, in-place TDD preflight 등 `skills/impl*/**`·`harness/**`·`scripts/**`·`docs/plugin/**`·`commands/init-dcness.md` 변경.
- **`/impl` 사용 프로젝트** — 일반 구현에서 내부 worker/headless 엔진 축이 노출되지 않고, 자연어-only 요청은 바로 구현되지 않고 `/to-issue` 선등록 여부 확인으로 이어진다. 큰 변경은 의미 단위 커밋으로 쪼개진다.
- **`/impl-loop` deep task 사용 프로젝트** — task commit + story PR 경계(code-validator/pr-reviewer 1회)로 정리되고, task 순서·resume·story PR 경계는 `dcness-story-runner` deterministic state 가 결정한다. `compact-design` 되돌림 경로는 더 이상 존재하지 않는다.
- **`.claude`/`.dcness`/`.codex` 를 로컬 전용으로 두는 no-trace 프로젝트** — in-place 구현 진입 시 generated TDD hook 미커밋으로 오차단되지 않고 디스크 실존·등록으로 통과한다. linked worktree 의 미전파 hook 은 계속 차단된다.

---

## v0.18.0 (2026-07-08)

**커밋 범위**: `v0.17.0..v0.18.0` (머지 PR 4개, #1012 · #1013 · #1014 · #1015)
**핵심 변경**: **구현 진입 게이트를 provider-agnostic 하게 앞당기고 경계·TDD 계약을 정밀화한** minor 릴리즈. (1) `/impl-loop` 가 `/impl` 사전점검을 우회하던 문제를 공통 impl entry pre-flight(impl plan boundary + generated TDD hook)로 `engineer`/`build-worker` 진입 직전에 강제, (2) headless implementation provider 의 boundary BLOCK 을 ledger/live marker 로 durable 기록해 같은 run 의 다음 step 을 provider-independent order gate 가 차단, (3) `tdd-exempt: <사유>` 마커로 구조적으로 테스트가 불필요한 파일의 사유 있는 통과 경로를 열되 빈 사유는 계속 deny, (4) `/init-dcness` 추천 라우팅을 구현 실행/계약 검증 역할로 분리하는 role-split preset 추가.

### 무엇이 바뀌나

1. **impl 진입 공통 pre-flight gate 강제** ([#1015](https://github.com/Daeguk-Sun/dcNess/pull/1015) [#1009](https://github.com/Daeguk-Sun/dcNess/issues/1009)) — `/impl-loop` deep task runner 가 `/impl` 문서 절차의 진입 사전점검을 우회해 boundary/TDD 보호막이 늦게 발화하던 문제를 해소. `boundary-suggestions --impl-plan <path>` 옵션을 추가해 impl 문서의 `### 수정 허용` 경로를 `ALLOW_MATRIX ∪ .dcness/boundary.json` 기준으로 대조하고, `evaluate_order_gate_for_step()` 의 `engineer`/`build-worker` 진입 직전에 impl plan boundary pre-flight 와 generated TDD hook pre-flight 를 강제한다. 실제 차단은 `begin-step`/catastrophic gate 공통 판정 함수에 넣어 Claude Agent provider 와 Codex/headless provider 가 같은 조건을 타며, Lite 기본 경로(계획 파일 없는 메인 직접 구현)와 dcNess self repo 는 대상에서 제외한다.

2. **headless boundary BLOCK durable 기록 + 다음 step 차단** ([#1013](https://github.com/Daeguk-Sun/dcNess/pull/1013) [#1010](https://github.com/Daeguk-Sun/dcNess/issues/1010)) — headless implementation provider(Codex/Claude)가 sub-agent boundary 밖 파일을 수정하면 wrapper 가 `exit 1` 로 끝나면서도 `end-step` 전 실패 경로라 durable marker 가 남지 않아 같은 run 의 다음 step 이 무심코 진행될 수 있던 문제를 해소. `dcness-codex-worker`/`dcness-claude-worker` 가 boundary violation 감지 시 `category=engineer_boundary` 의 `blocked` ledger event 와 `live.json` active run 슬롯의 run-level `blocked` marker 를 남기고, provider-independent order gate 가 live marker 또는 ledger-only fallback marker 를 보면 다음 `begin-step`/Agent 진입을 차단한다. `VALIDATION_BLOCKED` 와 달리 메인 검증 재실행으로 복구 불가한 상태(workspace 가 이미 역할 경계 밖으로 변함)라 run-level marker 로 처리한다.

3. **`tdd-exempt` 마커 지원** ([#1014](https://github.com/Daeguk-Sun/dcNess/pull/1014) [#1011](https://github.com/Daeguk-Sun/dcNess/issues/1011)) — TDD guard 가 DTO/stub/로직 무관 편집처럼 구조적으로 테스트가 불필요한 파일까지 hard block 하던 오탐에 사유 있는 통과 경로를 추가. `tdd-exempt: <사유>` 마커를 공통 Python helper 로 판정하고 generated hook 과 중앙 TS/JS fallback 이 같은 계약을 사용하도록 연결(기존 파일 내용·`Write`/`Edit` payload·Codex `apply_patch`·headless worker 사후 TDD 검사 공통). block 기본값은 유지하고 빈 사유 마커는 계속 deny 하며, 마커는 같은 줄에 사유가 있어야 해 남용을 막고 코드에 커밋되어 `rg "tdd-exempt:"` 로 사용 빈도를 감시할 수 있다. project-local generated hook 이 런타임에 `scripts/dcness-tdd-hooks run` 을 호출하는 기존 구조를 유지해 새 generated 파일 재배포 없이 plugin 업데이트로 계약이 적용된다.

4. **`/init-dcness` 추천 라우팅 역할 분리** ([#1012](https://github.com/Daeguk-Sun/dcNess/pull/1012) [#1008](https://github.com/Daeguk-Sun/dcNess/issues/1008)) — 추천 bundle 이 validation 축과 implementation 기본값을 따로 다뤄 구현 provider 와 검증 provider 가 같은 모델 축으로 몰릴 수 있던 문제를 해소. `enable_role_split_routing()` preset 을 추가해 `engineer`/`build-worker`=headless-chain, `test-engineer`/`code-validator`/`pr-reviewer`=claude, `architecture-validator`=codex 로 구현 실행과 계약 정의/검증 역할을 분리하고, `dcness-helper routing enable-role-split-routing` CLI 로 원자적 적용 후 status 를 출력한다. routing schema 는 그대로 `routes`/`implementation_routes` 만 쓰며 all-codex/Claude-only/legacy custom 경로는 유지한다.

### 자기개선 점검 기록

| 날짜 | 입력 | 판정 |
|---|---|---|
| 2026-07-08 | `python3.11 evals/guard_efficacy.py` (42/42) · `python3.11 scripts/loop_diagnose.py --idle-days 30 --since-days 90 --saturation-days 30 --saturation-min-runs 3` | v0.18.0 릴리즈 점검. 이번 릴리즈는 guard/hook 로직 변경 중심(order gate·tdd-guard·catastrophic-gate·boundary)이라 결정적 guard-efficacy 를 재실행 — **42/42 PASS**(이번 릴리즈의 tdd-exempt·boundary·provider-agnostic 케이스 추가 반영, 이전 33/33 → 42/42). loop_diagnose: 전 활성 프로젝트 guard 텔레메트리 `관측 이력 없음`(미배포/관측기간 부족) — 즉시 소멸 guard 후보 없음. 신규 통합 후보(NexusMessenger `TOOL_REPEAT_HIGH` waste/lesson 3건)는 이번 diff 와 무관한 활성 프로젝트 관측이라 follow-up 성격, 릴리즈 blocker 아님. LLM 기반 행동 eval 은 이번 diff 가 결정적 gate 로직이라 각 머지 PR CI(pytest·guard_efficacy·static-quality·public-surface·cross-ref)로 검증됨 — 생략(advisory). **소멸 후보 없음.** |

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — impl 진입 pre-flight gate, headless boundary BLOCK marker, `tdd-exempt` 마커, `/init-dcness` role-split 추천 라우팅 등 `harness/**`·`hooks/**`·`scripts/**`·`skills/impl*/**`·`commands/init-dcness.md`·`docs/plugin/**` 변경.
- **`/impl-loop` deep task 사용 프로젝트** — impl 계획의 `### 수정 허용` 비표준 경로와 generated TDD hook 미준비가 `engineer`/`build-worker` 진입 직전에 차단된다. dcNess self repo 는 pre-flight 대상에서 제외돼 plugin 자체 개발 흐름을 오차단하지 않는다.
- **테스트가 구조적으로 불필요한 파일** — `tdd-exempt: <사유>` 를 같은 줄 사유와 함께 남기면 TDD guard 를 통과한다. 빈 사유는 계속 차단되고 차단 메시지는 테스트 작성과 override 마커 두 경로를 함께 안내한다.
- **`/init-dcness` 신규/재실행 프로젝트** — 추천 라우팅이 role-split(구현 실행 headless-chain · 검증 claude/codex 분리)로 바뀐다. all-codex/Claude-only/legacy custom 경로는 그대로 선택할 수 있다.

---

## v0.17.0 (2026-07-08)

**커밋 범위**: `v0.16.0..v0.17.0` (머지 PR 6개, #996 · #1001 · #1003 · #1004 · #1005 · #1006)
**핵심 변경**: **구현 시점 엔진 위험 판정 분리 + 완료 설계 pack 개정(revision) 경로** 가 중심인 minor 릴리즈. (1) impl-task 의 `risk`/`engine` 판정을 설계 선행 판정용 `workflow-router` high-risk 표에서 떼어내 "구현 시점 위험" 기준으로 재정의해 이미 설계에서 소화한 위험의 풀 4-agent 과승격을 줄이고, build-worker self-check 는 self-grading drift 방지 목적으로 분리, (2) `/design` dispatcher 에 완료된 full design pack 을 UX 층/system·module 층으로 나눠 재진입시키는 개정 경로를 추가하고 final validator PASS 뒤에도 사용자 최종 설계 승인 전 commit/PR 을 막도록 계약 정합화, (3) `pr-finalize` post-merge 단계가 default branch worktree 를 실제 fast-forward sync + merged feature worktree cleanup 까지 책임지도록 확장, (4) harness/tests/scripts/templates 모듈 루트에 컴퍼스형 `CLAUDE.md` navigation 문서 추가.

### 무엇이 바뀌나

1. **구현 시점 엔진 위험 판정 분리 + build-worker self-check** ([#1004](https://github.com/Daeguk-Sun/dcNess/pull/1004) [#1002](https://github.com/Daeguk-Sun/dcNess/issues/1002), [#1006](https://github.com/Daeguk-Sun/dcNess/pull/1006)) — impl-task 의 `risk`/`engine` 판정이 설계 선행 여부를 가르는 `workflow-router` high-risk 표를 엔진 판정에도 재사용해, `/design` 에서 이미 소화한 위험(수직 슬라이스 cross-module, 플랫폼 SDK 표준 사용, 런타임 권한 흐름)까지 풀 4-agent 로 과승격되던 문제를 해소. `module-architect` impl-task 기준과 `/impl`·`/impl-loop` 엔진 fallback 을 "구현 시점 위험" 기준으로 동기화하고 `workflow-router` high-risk 표는 설계 선행 판정 전용임을 명시. build-worker 고위험 self-check 는 엔진 승격 기준과 직교하게 분리해, 도메인 invariant 변경을 decision 합의 여부와 무관한 drift-prone 영역으로 복원하고 kept/excluded 양쪽 trigger 목록을 5개 기준 문서 동기화 테스트로 방어.

2. **완료 설계 pack 개정(revision) 경로 + UX/system 층 분리** ([#1003](https://github.com/Daeguk-Sun/dcNess/pull/1003) [#997](https://github.com/Daeguk-Sun/dcNess/issues/997), [#1005](https://github.com/Daeguk-Sun/dcNess/pull/1005)) — `/design` dispatcher 가 완료된 full design pack 을 durable 산출물만으로 `/impl` 안내로만 확정하던 것을, 구조 변경·화면 통합·모듈 리네임·ADR 추가 같은 설계 개정으로 재진입시키는 1급 경로를 추가. UX 층 개정 신호(화면 통합/분할/삭제, `ux-flow.md`, 확정 목업, `docs/design.md` 토큰)는 `design-ux` revision mode 로 먼저 재진입 후 `design-system` revision mode 로 전파하도록 층을 분리. 영향 산출물만 개정·미변경 impl task 보존·파생 drift checklist·final validator 전체 pack 재검증 계약을 정합화하고, final PASS 뒤에도 사용자 최종 설계 승인 전에는 `git add`/`commit`/`push`/`gh pr create`/`pr-finalize` 를 호출하지 않도록 design·design-ux·design-system·loop-procedure·yolo 표·architecture-validator(Claude·Codex 미러) 계약을 맞춤.

3. **pr-finalize post-merge default worktree sync/cleanup** ([#996](https://github.com/Daeguk-Sun/dcNess/pull/996) [#995](https://github.com/Daeguk-Sun/dcNess/issues/995)) — `pr-finalize` 가 PR merge 후 `origin/<default>` ref 만 최신화하고 실제 default branch worktree HEAD 를 fast-forward 하지 않아 다음 작업 전 수동 `git pull --ff-only` 가 필요하던 문제를 해소. default branch worktree 가 있으면 `merge --ff-only` 로 동기화, 없으면 clean current worktree 를 전환해 동기화하며, merged clean linked feature worktree 와 stale admin entry 를 안전 조건 안에서 정리. dirty/non-fast-forward/checkout conflict 는 reset·stash 없이 `preserved` 목록으로 보존 출력. default branch 이름은 hard-code 대신 `gh repo view` ref 사용, 사용자-facing finalizer 경로를 `$PLUGIN_ROOT/scripts/pr-finalize.sh` 계약으로 정리.

4. **모듈별 컴퍼스형 CLAUDE.md navigation 추가** ([#1001](https://github.com/Daeguk-Sun/dcNess/pull/1001) [#998](https://github.com/Daeguk-Sun/dcNess/issues/998)) — harness/tests/scripts/templates 모듈 루트에 `CLAUDE.md` 를 추가해 모듈 단위 작업 시 root CLAUDE.md 전체 의존을 줄임. 작업 규칙을 재기술하지 않고 root CLAUDE.md 를 참조한 뒤 모듈별 소유 범위·핵심 파일·수정 주의점·검증 경로만 짧게 제공. dcness self 내부 navigation 문서로 외부 배포 공개 계약·`/init-dcness` inventory 변경은 없다.

### 자기개선 점검 기록

| 날짜 | 입력 | 판정 |
|---|---|---|
| 2026-07-08 | (빠른 배포 — eval 생략) | 사용자 지시로 self-improvement 권고 eval 점검(guard_efficacy · 행동 eval)을 생략한 빠른 minor 배포. 엔진 위험 기준 분리(#1004/#1006)·design revision 계약(#1003/#1005)·pr-finalize sync(#996)는 각 머지 PR CI(pytest·static-quality·public-surface·cross-ref·index-map)로 검증됨. **소멸 후보 없음.** |

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — 구현 시점 엔진 위험 판정 분리, `/design` 완료 pack 개정 경로, `pr-finalize` post-merge sync/cleanup, 모듈 CLAUDE.md navigation 등 `docs/plugin/**`·`skills/**`·`scripts/**` 변경.
- **`pr-finalize` 사용 프로젝트** — merge 후 default branch worktree 가 자동으로 `origin/<default>` 까지 fast-forward 되고 merged feature worktree 가 정리된다. dirty/non-fast-forward 상태는 자동 reset 없이 보존 목록으로 안내한다. 사용자-facing 문구는 `$PLUGIN_ROOT/scripts/pr-finalize.sh` 를 가리키므로 로컬 사본을 별도로 요구하지 않는다.

---

## v0.16.0 (2026-07-08)

**커밋 범위**: `v0.15.0..v0.16.0` (머지 PR 3개, #991~#993)
**핵심 변경**: **`/design` 설계 계약 정합 후속** 이 중심인 minor 릴리즈. (1) 확정 목업이 있는 UI epic 에서 module-architect / architecture-validator 프롬프트가 design SSOT(`docs/design.md`·확정 목업·canvas·node-id 매핑)를 빠뜨리는 것을 슬롯 예시·begin-step 리마인더·read-only `mockup-node-check` helper 로 방지, (2) design-variants canvas seed 에 화면 플로우 보드 모드를 추가해 라벨·캡션·상태·노드별 높이·초기 fit-to-view 를 표현, (3) module-architect impl-task 산출물의 테스트 grant 입도를 owner module 대응 하위 경로로 좁혀 병렬 wave disjoint 판정의 과다 충돌을 완화.

### 무엇이 바뀌나

1. **확정 목업 design SSOT 입력 누락 방지** ([#993](https://github.com/Daeguk-Sun/dcNess/pull/993) [#989](https://github.com/Daeguk-Sun/dcNess/issues/989)) — `agent-prompt-slots.md` 의 module-architect / architecture-validator 입력 예시에 확정 목업 UI epic design SSOT 항목을 추가하고, `begin-step` prompt slot check 가 확정 목업 파일을 감지하면 두 agent 에 design SSOT 리마인더를 출력하도록 확장. `dcness-helper mockup-node-check` read-only 서브커맨드를 추가해 impl `## 디자인 참조` 의 node-id 인용과 확정 목업 `data-node-id` 를 JSON 으로 대조하고, `/design` stage 2 mechanical pre-final checks 에 확정 목업 UI epic 한정 호출을 배선. `canvas.html`·`drafts/`·`_lib/`·`_` prefix HTML 은 확정 화면 목업에서 제외.

2. **design-variants canvas 플로우 보드 지원** ([#992](https://github.com/Daeguk-Sun/dcNess/pull/992) [#960](https://github.com/Daeguk-Sun/dcNess/issues/960)) — canvas seed 에 `.screen-node` 플로우 보드 모드를 추가해 캡션 카드·상태 chip·`data-h` 노드별 iframe 높이·곡선 화살표(`data-bend`)와 라벨 pill·초기 fit-to-view·노드/화살표 focus 강조를 렌더. `.screen-node` 존재 시에만 플로우 보드 모드로 전환해 기존 iframe grid seed 와 공존하고, 색상/폰트는 `--dcness-canvas-*` CSS custom property fallback 으로 분리해 활성 프로젝트가 자체 토큰으로 override 할 수 있다. `docs/plugin/design.md` 와 `skills/canvas-design/SKILL.md` 에 계약 문서화.

3. **테스트 grant 입도 지침 보강** ([#991](https://github.com/Daeguk-Sun/dcNess/pull/991) [#990](https://github.com/Daeguk-Sun/dcNess/issues/990)) — module-architect 의 `수정 허용` 작성 규칙과 impl-task 템플릿 Scope 안내에 테스트 grant 를 owner module 대응 하위 경로로 좁히라는 규칙과 넓은 grant 예외 조건을 추가. 공유 test-root grant 가 병렬 wave disjoint 판정에서 전 task 충돌로 보이던 문제를 산출물 작성 지침 단계에서 완화한다.

### 자기개선 점검 기록

| 날짜 | 입력 | 판정 |
|---|---|---|
| 2026-07-08 | (빠른 배포 — eval 생략) | 사용자 지시로 self-improvement 권고 eval 점검(guard_efficacy · 행동 eval)을 생략한 빠른 minor 배포. `begin-step` 리마인더·`dcness-helper mockup-node-check`·agent boundary read-only 분류 변경(#993)은 머지 PR CI(pytest·static-quality·public-surface·guard 관련 테스트)로 검증됨. **소멸 후보 없음.** |

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — 확정 목업 design SSOT 리마인더·`mockup-node-check` helper, canvas 플로우 보드 seed, 테스트 grant 입도 지침 등 `docs/plugin/**`·`skills/**`·`harness/**`·`templates/design-variants/**` 변경.
- **canvas seed 를 이미 배포받은 활성 프로젝트** — 기존 파일을 덮어쓰지 않는 정책상 plugin update 만으로 로컬 `docs/design-variants/_lib/canvas.js` 가 자동 교체되지는 않는다. 플로우 보드 모드가 필요하면 갱신된 template 파일을 해당 프로젝트 `docs/design-variants/` 로 복사해야 한다.

---

## v0.15.0 (2026-07-07)

**커밋 범위**: `v0.14.0..v0.15.0` (머지 PR 9개, #973~#987)
**핵심 변경**: **`/design` 내부 stage 분리·목업 선행 계약 + Codex/provider 실행 경로 정합** 이 중심인 minor 릴리즈. (1) `/design` 을 얇은 dispatcher 로 명시하고 내부 `design-ux`/`design-system` stage 로 분리해 stage 단위 durable 진행 상태를 남기며, 목업 선행 checkpoint·UX 산출물 stage 2 입력 계약·final 검증 retry 단일 counter 를 정합화, (2) sub-agent 모델 티어 재정렬 + Codex wrapper model/effort opt-in pin, provider wrapper `PLUGIN_ROOT` 해석 prelude 보강, Codex validator skill 의 stale 배포본 우선 선택을 plugin 원본 우선으로 수정, (3) mode 검증 SSOT 확장(begin-step/end-step 기준 통일) + impl task 산출물 경량화.

### 무엇이 바뀌나

1. **`/design` 내부 stage 분리 + 목업 선행 분기** ([#973](https://github.com/Daeguk-Sun/dcNess/pull/973) [#958](https://github.com/Daeguk-Sun/dcNess/issues/958), [#975](https://github.com/Daeguk-Sun/dcNess/pull/975) [#957](https://github.com/Daeguk-Sun/dcNess/issues/957)) — `/design` 을 얇은 dispatcher 로 명시하고 내부 `design-ux` / `design-system` stage skill 로 분리, epic phase SSOT 가 `ux-flow.md` 완료 + 설계 pack 부재 상태를 별도 라벨로 파생해 세션 단절 후 stage 재개가 가능해졌다. UI epic 에 목업 선행 여부 checkpoint(opt-out/yolo=목업 없음)와 목업=예 한정 디자인 시스템 체크포인트를 추가하고, 확정 목업을 stage 2 필수 입력으로 강제.

2. **design 계약 정합 후속** ([#986](https://github.com/Daeguk-Sun/dcNess/pull/986) [#974](https://github.com/Daeguk-Sun/dcNess/issues/974), [#987](https://github.com/Daeguk-Sun/dcNess/pull/987) [#970](https://github.com/Daeguk-Sun/dcNess/issues/970)) — stage 2 architect prompt checkpoint 에 UI epic 한정 UX 산출물 4종(epic ux-flow, `docs/design.md`, 화면별 확정 목업, canvas) 포인터를 기본 입력으로 명시하고 `ux-flow.md` 화면 인벤토리에 확정 목업 경로를 durable 하게 기록. final epic 검증 FAIL 재진입 counter 를 단일 provider-agnostic counter 로 명문화해 분류 전환·finding 영역 변경·provider 경로에 의한 cycle 리셋을 차단(3 cycle 한도 복구).

3. **Codex/provider 실행 경로 정합** ([#980](https://github.com/Daeguk-Sun/dcNess/pull/980) [#976](https://github.com/Daeguk-Sun/dcNess/issues/976), [#983](https://github.com/Daeguk-Sun/dcNess/pull/983) [#979](https://github.com/Daeguk-Sun/dcNess/issues/979), [#984](https://github.com/Daeguk-Sun/dcNess/pull/984) [#978](https://github.com/Daeguk-Sun/dcNess/issues/978)) — 판단 실패 비용이 큰 sub-agent(설계 pack 작성·검증·구현·제품 검수·경량 worker)의 모델 티어를 재정렬하고 `DCNESS_CODEX_MODEL` / `DCNESS_CODEX_EFFORT` opt-in pin 을 추가. provider wrapper 호출 예시에 `PLUGIN_ROOT` 해석 prelude 를 보강해 외부 활성 프로젝트의 경로 오추정을 차단. Codex validator 가 `$CODEX_HOME/skills` stale 배포본 대신 plugin 원본 skill 을 우선 주입하고 stale copy 를 경고.

4. **mode 검증 정합 + impl task 경량화** ([#985](https://github.com/Daeguk-Sun/dcNess/pull/985) [#977](https://github.com/Daeguk-Sun/dcNess/issues/977), [#982](https://github.com/Daeguk-Sun/dcNess/pull/982) [#981](https://github.com/Daeguk-Sun/dcNess/issues/981)) — `harness/signal_io.py` mode 검증 SSOT 를 확장해 begin-step/end-step 검증 기준을 통일하고 `epic-batch` 같은 skill label 표기·lowercase-hyphen mode prose PASS 를 인정(/design stage 2 mode 생략 우회 해소). impl-task 템플릿을 cold-start 필수 증거 중심으로 경량화하고 `수정 허용` 기본값을 owner module directory grant 로 전환.

### 자기개선 점검 기록

| 날짜 | 입력 | 판정 |
|---|---|---|
| 2026-07-07 | (빠른 배포 — eval 생략) | 사용자 지시로 self-improvement 권고 eval 점검(guard_efficacy · 행동 eval)을 생략한 빠른 minor 배포. `signal_io.py` mode 검증 변경(#985)은 머지 PR CI(pytest)로 검증됨. **소멸 후보 없음.** |

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `/design` stage 분리·목업 선행 계약, sub-agent 모델 티어 재정렬, Codex wrapper 정합, impl task 경량 템플릿 등 `agents/**`·`commands/**`·`skills/**`·`scripts/**`·`harness/**` 변경.
- **Codex 사용 프로젝트** — `DCNESS_CODEX_MODEL` / `DCNESS_CODEX_EFFORT` 환경변수로 모델·reasoning effort pin 을 opt-in 할 수 있다. `$CODEX_HOME/skills` 배포본이 stale 이어도 validator 는 plugin 원본 skill 을 우선하므로 폐기된 판단 축 주입이 차단된다.

---

## v0.14.0 (2026-07-07)

**커밋 범위**: `v0.13.0..v0.14.0` (머지 PR 9개, #946~#971)
**핵심 변경**: **설계 루프의 agent-first 전환 + 플러그인 agent 등록·읽기 경계 정합 + 세션 인계·다음작업 UX** 가 중심인 minor 릴리즈. (1) `/design` 설계 루프를 agent-first 로 전환하고 thin bootstrap 분기·checkpoint 계약을 정합화, (2) `agents/` 하위에 중첩돼 있던 문서 42개를 `docs/plugin/agents/` 로 옮겨 **가짜 agent 타입 등록 오염을 해소**하고 subagent read 경계에 활성 plugin `agents/`·`docs/plugin/` carve-out 을 추가, (3) 세션 간 warm 인계 레이어(`/handoff`)·"뭐하지/남은 일" next-pointer·next-work epic phase 판정으로 **콜드스타트/다음작업 진입 UX** 를 강화했다. 부수 — 외부 활성 프로젝트의 main 브랜치 직접 commit 차단, epic phase SSOT(`scripts/lib/epic_phase.mjs`) 도입, plugin-release 브랜치 예시 버전 언더스코어 정정.

### 무엇이 바뀌나

1. **설계 루프 agent-first 전환** ([#971](https://github.com/Daeguk-Sun/dcNess/pull/971) [#969](https://github.com/Daeguk-Sun/dcNess/issues/969)) — `/design` 설계 루프를 agent-first 로 전환하고, thin bootstrap 설계 분기를 추가하며 checkpoint 계약을 정합화.

2. **agent 등록 오염 해소 + subagent read 경계** ([#968](https://github.com/Daeguk-Sun/dcNess/pull/968) [#963](https://github.com/Daeguk-Sun/dcNess/issues/963), [#967](https://github.com/Daeguk-Sun/dcNess/pull/967) [#962](https://github.com/Daeguk-Sun/dcNess/issues/962)) — `agents/` 하위 중첩 문서 42개를 `docs/plugin/agents/` 로 이동해 가짜 agent 타입 등록 오염을 제거(pytest 트리거에 `docs/plugin/agents/` 추가). subagent read carve-out 을 활성 plugin `agents/`·`docs/plugin/` 에 부여하고 경계 검사를 plugin-relative 경로로, slot 경로 해소를 활성 `CLAUDE_PLUGIN_ROOT` 우선으로 정합화(codex 관찰 반영).

3. **세션 인계·다음작업 UX** ([#961](https://github.com/Daeguk-Sun/dcNess/pull/961) [#953](https://github.com/Daeguk-Sun/dcNess/issues/953), [#965](https://github.com/Daeguk-Sun/dcNess/pull/965) [#954](https://github.com/Daeguk-Sun/dcNess/issues/954), [#959](https://github.com/Daeguk-Sun/dcNess/pull/959) [#951](https://github.com/Daeguk-Sun/dcNess/issues/951)) — 세션 간 warm 인계 레이어(`/handoff` + SessionStart 최우선 주입·archive clear, claim-first 소비·심링크-safe·크기 상한)를 추가. "뭐하지/남은 일" 트리거로 다음 액션을 단정하고 focused preload 를 오케스트레이션하는 next-pointer 도입. next-work 를 lifecycle SSOT phase 계약과 동기화(story L2 승격 차단, 로컬 repo 식별을 git remote 기반으로 전환).

4. **epic phase SSOT + 외부 main 커밋 차단** ([#956](https://github.com/Daeguk-Sun/dcNess/pull/956) [#950](https://github.com/Daeguk-Sun/dcNess/issues/950), [#949](https://github.com/Daeguk-Sun/dcNess/pull/949) [#948](https://github.com/Daeguk-Sun/dcNess/issues/948), [#946](https://github.com/Daeguk-Sun/dcNess/pull/946)) — epic phase/다음액션 판정을 `scripts/lib/epic_phase.mjs` SSOT 로 통일하고 `docs/index.md` 에픽 표에 파생 다음 액션 컬럼을 추가. 외부 활성 프로젝트의 main 브랜치 직접 commit 을 차단(#948 결함 수정). plugin-release 브랜치 예시 버전을 언더스코어 형식으로 정정.

### 자기개선 점검 기록

| 날짜 | 입력 | 판정 |
|---|---|---|
| 2026-07-07 | (빠른 배포 — eval 생략) | 사용자 지시로 self-improvement 권고 eval 점검(guard_efficacy · 행동 eval)을 생략한 빠른 minor 배포. guard/hook 로직 회귀 위험이 낮은 변경(설계 루프·문서 이동·경계 carve-out·UX)이 중심. **소멸 후보 없음.** |

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `/design` agent-first 설계 루프, `/handoff` 세션 인계 레이어, next-pointer/next-work 다음작업 UX, subagent read 경계 정합 등 `agents/**`·`commands/**`·`skills/**`·`hooks/**` 변경.
- **가짜 agent 타입 등록 오염 해소** — `agents/` 하위 중첩 문서 이동으로 존재하지 않던 agent 타입이 등록되던 오염이 사라진다.
- **외부 활성 프로젝트 main 브랜치 보호 강화** — 외부 프로젝트에서 main 브랜치 직접 commit 이 차단된다(init-dcness 주장과의 불일치 해소).

---

## v0.13.0 (2026-07-06)

**커밋 범위**: `v0.12.0..v0.13.0` (머지 PR 13개, #932~#944)
**핵심 변경**: **신규 환경·공개 저장소에서의 설치·활성화 견고성(hardening)** 이 중심인 minor 릴리즈. (1) 공개 저장소 org 참조를 `Daeguk-Sun` 으로 통일하고 README fork 흔적을 제거, git hook 이 node 부재 시 fail-open, CLAUDE.md·requirements seed 의 python 판정을 `detect_platform` SSOT 로 통일해 **fresh 환경의 첫 설치·첫 이슈 등록이 깨지지 않도록** 했고, (2) `/to-issue` 를 **선등록 모델**로 전환(승인 게이트 폐기 + 맥락 추론 라벨 자동 + 이슈 생성 전 label 선upsert), (3) 기존 프로젝트를 역설계해 전역 docs 를 부트스트랩하는 **`/migrate-dcness` 신규 스킬**을 더했다. 부수 — README 를 "agent workflow harness" 프레임으로 포지셔닝 개편 + guard-efficacy advisory CI badge + hook fail-open 가시성, `session_state` 모듈 재분할, 자기개선 loop Decide 기록.

### 무엇이 바뀌나

1. **신규 환경·공개 저장소 릴리즈 hardening** ([#941](https://github.com/Daeguk-Sun/dcNess/pull/941), [#942](https://github.com/Daeguk-Sun/dcNess/pull/942), [#944](https://github.com/Daeguk-Sun/dcNess/pull/944)) — 배포 workflow·업데이트 훅·문서의 공개 저장소 org 참조를 `Daeguk-Sun` 으로 통일하고 README 앞머리의 fork Origin 줄을 제거. git hook shim 이 node 부재 시 fail-open(naming skip, main-block 은 유지)하도록 하고, `CLAUDE.md` seed 의 python 명령을 마커 조건화 + `python3` 로 완화, seed 의 python 판정을 `detect_platform` SSOT 로 통일해 `requirements.txt` 회귀를 수정. marketplace·plugin 설명을 한국어로 통일.

2. **`/to-issue` 선등록 모델 전환** ([#943](https://github.com/Daeguk-Sun/dcNess/pull/943)) — 승인 게이트를 폐기하고 맥락 추론 라벨을 자동 부여하는 선등록 모델로 전환, 발화 트리거·라우팅을 강화. 이슈 생성 전 `vNN`·epic slug label 을 선upsert 해 신규 저장소 첫 등록 실패를 차단.

3. **`/migrate-dcness` 신규 스킬** ([#940](https://github.com/Daeguk-Sun/dcNess/pull/940) [#828](https://github.com/Daeguk-Sun/dcNess/issues/828)) — 기존 프로젝트 코드를 역설계해 전역 docs 를 부트스트랩하는 마이그레이션 스킬을 추가(브랜치 격리·문서 분류 선행·부재 index seed 생성 등 codex 리뷰 근본원인 수정 포함).

4. **포지셔닝·guard-eval·fail-open 가시성 프로그램** ([#933](https://github.com/Daeguk-Sun/dcNess/pull/933), [#934](https://github.com/Daeguk-Sun/dcNess/pull/934), [#935](https://github.com/Daeguk-Sun/dcNess/pull/935) [#928](https://github.com/Daeguk-Sun/dcNess/issues/928)) — README 첫 화면과 plug-in metadata 를 "PR workflow guard" 에서 "agent workflow harness" 프레임으로 개편(설치 진단표·fail-open 감시·evidence 실측·Safety 범위 요약 노출), 결정적 guard-efficacy eval 을 advisory GitHub Actions workflow + README 상태 badge 로 고정, hook fail-open 이벤트를 run 종료 stderr 와 `/run-review` 리포트에 warning 으로 노출.

5. **`session_state` 모듈 재분할 + eval·loop 정비** ([#937](https://github.com/Daeguk-Sun/dcNess/pull/937) [#929](https://github.com/Daeguk-Sun/dcNess/issues/929), [#938](https://github.com/Daeguk-Sun/dcNess/pull/938), [#936](https://github.com/Daeguk-Sun/dcNess/pull/936) [#930](https://github.com/Daeguk-Sun/dcNess/issues/930), [#939](https://github.com/Daeguk-Sun/dcNess/pull/939) [#931](https://github.com/Daeguk-Sun/dcNess/issues/931), [#932](https://github.com/Daeguk-Sun/dcNess/pull/932)) — `session_state` 를 응집 하위 모듈로 재분할(역방향 헬퍼 core 복귀), flow ownership eval 판정 보강, v0.12.0 자기개선 후보 7건을 `보류`로 Decide 기록, plugin-release 절차에 release 브랜치 자동 sync 정합 확인 스텝 추가.

### 자기개선 점검 기록

| 날짜 | 입력 | 판정 |
|---|---|---|
| 2026-07-06 | `python3.11 evals/guard_efficacy.py` (33/33) · `python3.11 scripts/loop_diagnose.py --idle-days 30 --since-days 90 --saturation-days 30 --saturation-min-runs 3` | v0.13.0 릴리즈 점검. guard-efficacy **33/33 PASS**. loop_diagnose: 전 활성 프로젝트 guard 텔레메트리 `관측 이력 없음`(미배포/관측기간 부족) — 즉시 소멸 guard 후보 없음. 통합 후보(youTubeGenerator waste 4건 · dcness-self eval 포화 3건)는 전부 [#931](https://github.com/Daeguk-Sun/dcNess/issues/931) 에서 이미 `보류`로 Decide 된 기왕 항목이라 신규 후보 없음. **소멸 후보 없음.** 핵심 행동 eval(`shorts-real-spec`·`headless-prose-quality`) strict 케이스는 이번 릴리즈 diff(setup·문서·org 참조·`session_state` 재분할)와 무관해 live LLM 재실행은 생략(advisory). |

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — `/to-issue` 선등록 모델(승인 게이트 폐기 + 자동 라벨), `/migrate-dcness` 신규 스킬, README·metadata 포지셔닝 개편 등 `commands/**`·`skills/**` 변경.
- **신규 환경 설치·활성화 안정성 향상** — git hook 이 node 부재 시 fail-open 하고, seed 파일의 python 판정이 플랫폼 SSOT 로 통일돼 fresh 환경 첫 설치·첫 이슈 등록 실패가 줄어든다.
- **기존 활성 프로젝트**는 `init` 이 배포·복사하는 파일(스크립트·hook·워크플로우) 갱신을 받으려면 plugin update 후 `/init-dcness` 재실행이 필요하다.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.12.0 (2026-07-05)

**커밋 범위**: `v0.11.0..v0.12.0` (머지 PR 27개)
**핵심 변경**: 측정 신호를 하네스 개선으로 닫는 **자기개선 루프를 처음부터 끝까지 구축**한 게 중심인 minor 릴리즈. (1) Sense→Diagnose→Decide→Act→Verify SSOT 와 가드 발화 텔레메트리 · Diagnose 도구(`/loop-diagnose`) · 시간 기반 sweep · 프로젝트-로컬 lesson 층까지 루프 인프라를 깔았고, (2) 활성 프로젝트의 **컨텍스트 · 문서 거버넌스**(context audit · CLAUDE.md seed 감사 · docs 모듈 축)를 보강했으며, (3) **생성형 TDD hook** 계약과 파일 경계 override 제안 · init 온보딩 안내 같은 setup UX 를 더했다. 부수 — 이슈 label lifecycle · 보드 best-effort 미러, 행동 eval 판정 안정화 · judge calibration.

### 무엇이 바뀌나

1. **자기개선 루프 구축** ([#895](https://github.com/alruminum/dcNess/pull/895) [#893](https://github.com/alruminum/dcNess/issues/893), [#898](https://github.com/alruminum/dcNess/pull/898) [#875](https://github.com/alruminum/dcNess/issues/875), [#907](https://github.com/alruminum/dcNess/pull/907) [#903](https://github.com/alruminum/dcNess/issues/903), [#911](https://github.com/alruminum/dcNess/pull/911) [#904](https://github.com/alruminum/dcNess/issues/904), [#905](https://github.com/alruminum/dcNess/pull/905), [#925](https://github.com/alruminum/dcNess/pull/925) [#921](https://github.com/alruminum/dcNess/issues/921), [#899](https://github.com/alruminum/dcNess/pull/899) [#876](https://github.com/alruminum/dcNess/issues/876), [#900](https://github.com/alruminum/dcNess/pull/900) [#894](https://github.com/alruminum/dcNess/issues/894), [#922](https://github.com/alruminum/dcNess/pull/922) [#917](https://github.com/alruminum/dcNess/issues/917), [#901](https://github.com/alruminum/dcNess/pull/901) [#878](https://github.com/alruminum/dcNess/issues/878), [#912](https://github.com/alruminum/dcNess/pull/912) [#906](https://github.com/alruminum/dcNess/issues/906), [#913](https://github.com/alruminum/dcNess/pull/913) [#902](https://github.com/alruminum/dcNess/issues/902), [#897](https://github.com/alruminum/dcNess/pull/897) [#877](https://github.com/alruminum/dcNess/issues/877)) — 측정→개선 루프를 처음부터 끝까지 구축. 자기개선 SSOT([`docs/internal/self-improvement-loop.md`](self-improvement-loop.md), Sense→Diagnose→Decide→Act→Verify) 신설, 가드 발화 텔레메트리 수집 + 위생·품질 정비, Diagnose 도구 `/loop-diagnose`(활성 프로젝트 cross-project 신호 통합) + 시간 기반 sweep 스케줄 자동화, 재발 waste 신호 개선 후보 표면화, judge calibration 리포트, 프로젝트-로컬 lesson 층(`.claude/loop-lessons/<agent>[-<mode>].md` 자동 축적 → 다음 `begin-step` 에 `[LESSONS]` 주입), 릴리즈 전 가드 재평가 절차 명문화, 행동 eval 판정 안정화 · 통합 drift · 문서 count deny-list 보정.

2. **활성 프로젝트 컨텍스트·문서 거버넌스** ([#883](https://github.com/alruminum/dcNess/pull/883) [#881](https://github.com/alruminum/dcNess/issues/881), [#886](https://github.com/alruminum/dcNess/pull/886) [#885](https://github.com/alruminum/dcNess/issues/885), [#889](https://github.com/alruminum/dcNess/pull/889) [#884](https://github.com/alruminum/dcNess/issues/884), [#890](https://github.com/alruminum/dcNess/pull/890), [#924](https://github.com/alruminum/dcNess/pull/924) [#882](https://github.com/alruminum/dcNess/issues/882)) — 활성 프로젝트 컨텍스트 감사 트리거 추가, 활성 프로젝트 `CLAUDE.md` seed 감사, docs 산출물 모듈 축 추가 + index seed doc-sync 회귀 수정, 모듈별 `CLAUDE.md` 분할 권고 기준.

3. **생성형 TDD hook** ([#916](https://github.com/alruminum/dcNess/pull/916) [#909](https://github.com/alruminum/dcNess/issues/909), [#919](https://github.com/alruminum/dcNess/pull/919) [#908](https://github.com/alruminum/dcNess/issues/908), [#923](https://github.com/alruminum/dcNess/pull/923)) — 생성형 TDD hook 계약 추가 + 후속 보강 + 플랫폼 규칙 위임.

4. **온보딩·경계 setup UX** ([#926](https://github.com/alruminum/dcNess/pull/926), [#915](https://github.com/alruminum/dcNess/pull/915) [#910](https://github.com/alruminum/dcNess/issues/910)) — `init` 직후 온보딩 안내 추가, 파일 경계 override 제안 트리거.

5. **이슈·보드 lifecycle + 문서 현행화** ([#888](https://github.com/alruminum/dcNess/pull/888) [#887](https://github.com/alruminum/dcNess/issues/887), [#892](https://github.com/alruminum/dcNess/pull/892), [#896](https://github.com/alruminum/dcNess/pull/896), [#914](https://github.com/alruminum/dcNess/pull/914)) — issue label lifecycle next-work, 보드 미러 best-effort 처리, CLAUDE map 의 Stop hook 항목 복원, `CLAUDE.md` 현행화(환경변수 표·테스트 함정·pytest CI 짝).

### 자기개선 점검 기록

| 날짜 | 입력 | 판정 |
|---|---|---|
| 2026-07-04 | `python3.11 -m harness.guard_telemetry report` | 첫 Diagnose 수행. 프로젝트 `guard-telemetry.jsonl` 없음, `.metrics/evals/**/guard-telemetry.jsonl` 0개라 30일 관측 근거가 아직 없다. known guard는 원시 출력상 `재평가 후보`로 표시되지만, 장기 무발화가 아니라 신규 텔레메트리 관측 기간 부족으로 해석한다. 이번 릴리즈의 즉시 소멸 후보 없음. 다음 릴리즈에서 재확인한다. |
| 2026-07-05 | `python3.11 evals/guard_efficacy.py` (33/33) · `python3.11 scripts/loop_diagnose.py --idle-days 30 --since-days 90 --saturation-days 30 --saturation-min-runs 3` | v0.12.0 릴리즈 점검. guard-efficacy 33/33 PASS. 전 활성 프로젝트 guard 텔레메트리 `관측 이력 없음`(미배포/관측기간 부족)으로 2026-07-04 판정 유지 — 즉시 소멸 guard 후보 없음. 통합 후보는 youTubeGenerator waste 4건(모두 기왕) · dcness-self eval 포화 3건(4/4 100%)이며 릴리즈 blocker 아닌 follow-up 성격. 핵심 행동 eval(`shorts-real-spec`·`headless-prose-quality`)은 릴리즈 체크 모드 N/N 로 별도 확인. |

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — Diagnose 도구 `/loop-diagnose` · 프로젝트-로컬 lesson 주입 · 생성형 TDD hook · 파일 경계 override 제안 · `init` 온보딩 안내 등 `hooks/**` · `skills/**` · `commands/**` 변경.
- **자기개선 루프는 dcNess self 운영 절차** — SSOT·Diagnose 도구·sweep 스케줄은 dcNess 저장소 유지보수용이며, 외부 활성 프로젝트에는 lesson 층 주입 · TDD hook · 경계 override 제안 · 온보딩 안내가 사용자-facing 으로 도달한다.
- **기존 활성 프로젝트**는 `init` 이 배포·복사하는 파일(스크립트·hook·워크플로우) 갱신을 받으려면 plugin update 후 `/init-dcness` 재실행이 필요하다.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.11.0 (2026-07-03)

**커밋 범위**: `v0.10.0..v0.11.0` (머지 PR 24개)
**핵심 변경**: 설계 · 디자인 · 구현 세 파이프라인을 한꺼번에 재정비한 minor 릴리즈. (1) `/design` 을 **epic-batch 단일 워크플로우로 전면 재설계**하고 설계 산출물 계약을 감사(false-clean 차단)하는 품질 인프라를 깔았고, (2) 디자인 매체를 **pencil 에서 canvas 로 전환**해 `/ux` 를 canvas 선행-탐색 utility 로 재정의했으며, (3) 구현 게이트를 **provider-agnostic** 으로 복원하고 headless provider 3단 체인 + `/impl` 엔진 기본값을 **build-worker** 로 바꿨다. 부수 — 자동 머지 확인 창 · worktree 종료 clean 가드, README 2축 컨셉 현행화, `/spec` 그릴 규율 보강.

### 무엇이 바뀌나

1. **/design epic-batch 전면 재설계 + 설계 산출물 계약 감사** ([#834](https://github.com/alruminum/dcNess/pull/834), [#835](https://github.com/alruminum/dcNess/pull/835) [#836](https://github.com/alruminum/dcNess/pull/836) [#838](https://github.com/alruminum/dcNess/pull/838) [#839](https://github.com/alruminum/dcNess/pull/839) [#832](https://github.com/alruminum/dcNess/issues/832), [#840](https://github.com/alruminum/dcNess/pull/840) [#831](https://github.com/alruminum/dcNess/issues/831), [#837](https://github.com/alruminum/dcNess/pull/837) [#833](https://github.com/alruminum/dcNess/issues/833), [#849](https://github.com/alruminum/dcNess/pull/849) [#847](https://github.com/alruminum/dcNess/issues/847)) — `/design` 을 epic 단위 batch 워크플로우로 재구성. 설계 산출물(ux-flow / architecture / conventions / decisions / impl)의 계약 준수를 감사해 산출물이 비어도 PASS 로 통과하던 false-clean 을 doc-sync 배선으로 차단. design 측정 품질 인프라(`docs/metrics/design-runs.jsonl` 기록)를 final validator PASS 뒤 · PR 생성 전 worktree 커밋 순서까지 정합. architecture map 자동집계 열 정렬 결함 수정.

2. **디자인 매체 pencil → canvas 전환** ([#846](https://github.com/alruminum/dcNess/pull/846) [#842](https://github.com/alruminum/dcNess/issues/842), [#854](https://github.com/alruminum/dcNess/pull/854) [#843](https://github.com/alruminum/dcNess/issues/843), [#855](https://github.com/alruminum/dcNess/pull/855) [#844](https://github.com/alruminum/dcNess/issues/844), [#856](https://github.com/alruminum/dcNess/pull/856) [#858](https://github.com/alruminum/dcNess/pull/858) [#845](https://github.com/alruminum/dcNess/issues/845)) — pencil MCP 매체를 폐기하고 canvas 기반 `canvas-design` 워크플로우 신설. `/ux` 를 "구현 없이 목업 · 흐름을 먼저 굴리는 canvas 선행-탐색 utility" 로 재정의(내부 canvas-design 을 얇게 감싼 wrapper — drafts → 사용자 PICK → 확정본 승격 + canvas 등록). `/acceptance` 가 UI 목업 정합을 검수하도록 보강, `/ux` commit 경로 정리.

3. **구현 provider-agnostic 게이트 + headless provider 체인 + 엔진 기본값 build-worker** ([#865](https://github.com/alruminum/dcNess/pull/865) [#859](https://github.com/alruminum/dcNess/issues/859), [#869](https://github.com/alruminum/dcNess/pull/869) [#860](https://github.com/alruminum/dcNess/issues/860), [#867](https://github.com/alruminum/dcNess/pull/867) [#861](https://github.com/alruminum/dcNess/issues/861), [#872](https://github.com/alruminum/dcNess/pull/872) [#870](https://github.com/alruminum/dcNess/issues/870)) — 게이트가 특정 provider 전제를 벗지 못하던 문제를 provider-agnostic 으로 복원(결정적 guard eval 33/33). implementation provider 를 headless 3단 체인으로 구성하고, `/impl` 엔진 기본값을 풀 4-agent 에서 경량 build-worker 로 전환. headless 후속 정비.

4. **워크플로우 가드 보강** ([#863](https://github.com/alruminum/dcNess/pull/863) [#851](https://github.com/alruminum/dcNess/issues/851), [#864](https://github.com/alruminum/dcNess/pull/864) [#852](https://github.com/alruminum/dcNess/issues/852)) — 자동 머지 직전 확인 창 보강(merge guard), impl worktree 종료 시 clean 여부 판정 가드 + discard 조건 · 종료 링크 정리.

5. **문서 현행화 + /spec 그릴 규율** ([#866](https://github.com/alruminum/dcNess/pull/866), [#868](https://github.com/alruminum/dcNess/pull/868), [#862](https://github.com/alruminum/dcNess/pull/862) [#853](https://github.com/alruminum/dcNess/issues/853), [#857](https://github.com/alruminum/dcNess/pull/857) [#850](https://github.com/alruminum/dcNess/issues/850), [#873](https://github.com/alruminum/dcNess/pull/873) [#871](https://github.com/alruminum/dcNess/issues/871)) — README 를 2축 컨셉(워크플로우 · 모델 자율성)으로 재작성 · 현행화, 문서 중복 참조 정비(doc drift), `/spec` 그릴미 라우팅 · 그릴 규율 기준 보강.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — /design epic-batch · canvas-design · `/ux` 재정의(`skills/**`), provider-agnostic 게이트 · 엔진 기본값(`hooks/**` · `harness/**` · `skills/impl/**`), 머지 · worktree 가드, agent 가이드.
- **디자인 흐름 변경** — 디자인 매체가 pencil → canvas 로 바뀌어 `/ux` · `/design` 산출 경로가 canvas 기준으로 정렬된다. pencil MCP 를 쓰던 흐름은 더 이상 사용되지 않는다.
- **구현 엔진 기본값 변경** — `/impl` 기본 엔진이 build-worker(경량)로 바뀐다. 풀 4-agent(test-engineer → engineer → code-validator → pr-reviewer)는 발화 · 조건으로 선택.
- **Codex opt-in 프로젝트**는 provider routing · validator 미러 갱신(`codex/skills/dcness-*`)을 받으려면 plugin update 후 `/init-dcness` 재실행이 필요하다.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.10.0 (2026-06-30)

**커밋 범위**: `v0.9.0..v0.10.0` (머지 PR 16개)
**핵심 변경**: 외부 활성 프로젝트의 **docs 산출물 구조를 단일 SSOT 로 재설계**한 게 중심인 minor 릴리즈. `docs/plugin/deliverables-map.md` 신설로 prd/architecture/conventions/decisions/epic 산출물의 위치·양식·계층을 못박고, cross-ref 게이트에 **고아 문서 탐지**를 더해 구조 회귀를 차단하며, epic architecture 표를 전역 지도로 **자동 집계**한다. 부수 — `next` 진입점, Codex implementation routing(codex-first), doc-path·doc-sync 무결성 CI, Agent Operability 계약 가드, 단일 파일 다중 흐름 누적 분해 소프트 신호가 추가됐다.

### 무엇이 바뀌나

1. **docs 산출물 구조 SSOT 재설계** ([#806](https://github.com/alruminum/dcNess/pull/806) [#804](https://github.com/alruminum/dcNess/issues/804), [#812](https://github.com/alruminum/dcNess/pull/812) [#810](https://github.com/alruminum/dcNess/issues/810)) — `docs/plugin/deliverables-map.md` 를 신설해 외부 활성 프로젝트의 docs 산출물(전역 prd/architecture/conventions/decisions + epic 폴더 `stories.md`/`architecture.md`/`domain-model.md`/`ux-flow.md`/`impl/`) 위치·양식·계층을 단일 진본으로 정립. ux-flow 경계를 epic 폴더로 한정하고 ADR 파일을 `docs/decisions/` 로 통일하는 등 산출물 경로를 정합화. "한눈에 보기" 트리뷰 포함.

2. **cross-ref 고아 문서 탐지 게이트** ([#809](https://github.com/alruminum/dcNess/pull/809) [#805](https://github.com/alruminum/dcNess/issues/805)) — `scripts/check_cross_refs.mjs` 가 `docs/plugin`·`docs/internal` 의 어디서도 markdown 링크되지 않는 고아 `.md` 를 FAIL 로 잡는다. 참조 corpus 를 git tracked md 전체의 실제 링크로 한정(dev/CI parity), self-link 우회 차단, 정밀 매칭으로 오탐 제거.

3. **architecture map 자동 집계** ([#813](https://github.com/alruminum/dcNess/pull/813)) — `scripts/aggregate_architecture_map.mjs` 가 각 epic `architecture.md` 의 모듈 목록·Contract Ledger 표를 수집해 전역 `docs/architecture.md` 의 에픽 간 지도·전역 모듈 토폴로지·공유 계약 인덱스를 자동 생성/갱신한다(파생물, 수동 편집 금지).

4. **`next` 진입점** ([#825](https://github.com/alruminum/dcNess/pull/825) [#824](https://github.com/alruminum/dcNess/issues/824), [#826](https://github.com/alruminum/dcNess/pull/826) [#825](https://github.com/alruminum/dcNess/issues/825)) — 다음 작업 진입을 안내하는 `next` 포인터/진입점 추가 및 보강.

5. **Codex implementation routing** ([#822](https://github.com/alruminum/dcNess/pull/822)) — 구현 라우팅에 codex-first 경로를 추가. `/init-dcness` 가 `routing.json` 으로 validation/implementation routing 을 설정한다.

6. **doc-path·doc-sync 무결성 CI** ([#821](https://github.com/alruminum/dcNess/pull/821), [#827](https://github.com/alruminum/dcNess/pull/827) [#823](https://github.com/alruminum/dcNess/issues/823)) — 문서 경로 무결성 workflow + doc-sync 게이트 추가. `/init-dcness` 가 사용자 repo 로 배포하는 선택형 `.github/workflows` 템플릿 경로.

7. **Agent Operability 계약 가드** ([#818](https://github.com/alruminum/dcNess/pull/818), [#820](https://github.com/alruminum/dcNess/pull/820) [#819](https://github.com/alruminum/dcNess/issues/819)) — agent operability 계약 추가 + severity 승격·가드 보강.

8. **단일 파일 다중 흐름 누적 분해 신호** ([#816](https://github.com/alruminum/dcNess/pull/816) [#814](https://github.com/alruminum/dcNess/issues/814)) — 한 파일에 여러 흐름이 누적될 때의 분해 소프트 신호 추가 + Codex pr-reviewer provider 미러에 같은 축 반영(두 provider 정합).

9. **버그픽스·정리** ([#808](https://github.com/alruminum/dcNess/pull/808) [#807](https://github.com/alruminum/dcNess/issues/807), [#803](https://github.com/alruminum/dcNess/pull/803) [#797](https://github.com/alruminum/dcNess/issues/797), [#802](https://github.com/alruminum/dcNess/pull/802) [#800](https://github.com/alruminum/dcNess/issues/800), [#801](https://github.com/alruminum/dcNess/pull/801) [#799](https://github.com/alruminum/dcNess/issues/799)) — deprecated `docs/bugfix` 설계 산출물 완전 제거(Codex validator 미러 포함), architecture-validator occurrence off-by-one 수정(첫 재호출 누락 차단), init workflow/선택형 확장 템플릿 분리.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — docs 산출물 SSOT·집계 도구(`docs/plugin/**`·`scripts/**`·`agents/**`·`skills/**`), `next` 진입점, Agent Operability 가드, architecture map 자동집계.
- **신규 docs 산출물 구조** — `/spec`·`/design` 이 만드는 산출물 위치·양식이 `deliverables-map.md` 기준으로 정렬된다. 기존 활성 프로젝트의 이미 만든 문서는 강제 이동되지 않으며, 앞으로의 산출물이 새 구조를 따른다.
- **doc-path·doc-sync CI** 를 쓰려면 기존 활성 프로젝트는 `/init-dcness` 재실행(또는 `.github/workflows` 재배포)이 필요하다.
- **Codex opt-in 프로젝트**는 implementation routing(codex-first)·pr-reviewer 미러 갱신을 받으려면 plugin update 후 `/init-dcness` 재실행이 필요하다.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.9.0 (2026-06-18)

**커밋 범위**: `v0.8.0..v0.9.0` (머지 PR 10개)
**핵심 변경**: harness guard 의 신뢰성·가시성·커버리지 강화에 집중한 minor 릴리즈. TDD guard 가 Bash write 까지 차단하도록 확장되고, hook 의 의심스러운 fail-open 이 `dcness-helper status` 진단에 노출되며, sub-agent prompt 슬롯 self-check 와 engineer 파일 경계 코어 기본값 정리가 더해졌다. 공급망 보안(zizmor) 하드닝과 dcness 자체 품질 게이트(ruff/mypy/bandit · 결정적 guard 효능 eval)도 함께 들어갔다.

### 무엇이 바뀌나

1. **Bash TDD guard 적용** ([#792](https://github.com/alruminum/dcNess/pull/792) [#786](https://github.com/alruminum/dcNess/issues/786)) — TDD Guard 가 Edit/Write/NotebookEdit 뿐 아니라 **Bash write(redirect·tee·heredoc) 까지** 커버한다. 테스트 없이 소스 파일을 Bash 로 우회 생성하던 경로가 동일 기준으로 차단된다.

2. **hook fail-open 진단 노출** ([#791](https://github.com/alruminum/dcNess/pull/791) [#784](https://github.com/alruminum/dcNess/issues/784)) — `catastrophic-gate` / `file-guard` / `tdd-guard` 가 의심스럽게 fail-open(조용히 통과)되면 `fail-open-events.jsonl` 에 기록되고 `dcness-helper status` 에 진단 항목(PASS/WARN)으로 노출된다. guard 가 조용히 꺼졌는지 사용자가 확인할 수 있다.

3. **sub-agent prompt 슬롯 self-check** ([#795](https://github.com/alruminum/dcNess/pull/795) [#780](https://github.com/alruminum/dcNess/issues/780)) — `dcness-helper begin-step` 이 impl/design active run 에서 `[PROMPT_SLOT_CHECK]` advisory 를 출력하고, worktree 아래면 worktree 절대경로를 직접 포함한다. action loop 진입 시 worktree 슬롯 누락·방법 처방을 줄인다(advisory — 차단 아님).

4. **engineer 파일 경계 코어 기본값 정리** ([#796](https://github.com/alruminum/dcNess/pull/796) [#778](https://github.com/alruminum/dcNess/issues/778)) — engineer ALLOW_MATRIX 코어 기본값에서 프로젝트 고유 디렉토리(`^remotion/`)를 제거했다. 코어는 언어/레이아웃 중립 기본값만 유지하고, 프로젝트 고유 경로는 활성 프로젝트의 `.dcness/boundary.json` 이 SSOT 로 선언한다. ⚠️ `remotion/` 을 쓰던 프로젝트는 boundary override 가 없으면 engineer 가 더 이상 기본 허용받지 못하므로, 필요 시 `.dcness/boundary.json` 에 add override 를 선언해야 한다.

5. **벤치마크 fleet 지표 계측** ([#790](https://github.com/alruminum/dcNess/pull/790) [#785](https://github.com/alruminum/dcNess/issues/785)) — `pr-create` / `pr-finalize` 가 PR lifecycle ledger event 를 기록해, 이전엔 항상 "측정 불가" 였던 cross-run PR merge 성공률·orphan merge·review rejection 이 fleet 집계에 노출된다.

6. **공급망 보안 하드닝** ([#787](https://github.com/alruminum/dcNess/pull/787) [#781](https://github.com/alruminum/dcNess/issues/781)) — composite GitHub Action 의 input injection 제거, third-party action SHA 고정, read-only workflow 에 `persist-credentials: false` 적용. 외부 활성 프로젝트가 호출하는 `.github/actions/*` 에 직접 반영된다.

7. **내부 품질 인프라** (사용자 미도달) — dcness 자체에 ruff/mypy/bandit static gate([#788](https://github.com/alruminum/dcNess/pull/788) [#782](https://github.com/alruminum/dcNess/issues/782)), 결정적 guard 효능 eval([#789](https://github.com/alruminum/dcNess/pull/789)), release 배포물에서 self 전용 QA 파일 제외([#793](https://github.com/alruminum/dcNess/issues/793) [#794](https://github.com/alruminum/dcNess/pull/794)) 가 추가됐다. plug-in 본체 동작에는 영향이 없다.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — Bash TDD guard 확장·fail-open 진단(`hooks/**`), prompt 슬롯 advisory·engineer 경계 정리(`harness/**`), fleet 지표(`scripts/**`·`harness/**`), agent/skill 가이드.
- **⚠️ `remotion/` 디렉토리를 쓰던 프로젝트**는 plugin update 후 engineer 가 `remotion/` 에 쓰려면 활성 프로젝트 루트의 `.dcness/boundary.json` 에 add override 선언이 필요하다.
- **hook fail-open 점검**은 `dcness-helper status` 진단표에서 확인한다.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.8.0 (2026-06-17)

**커밋 범위**: `v0.7.1..v0.8.0` (머지 PR 11개)
**핵심 변경**: 프로젝트별 sub-agent 파일 경계 override(`.dcness/boundary.json`) 신설 + 설치/실행 진단 강화 + impl-loop chain 진행 뷰 자동 렌더 + cross-run 벤치마크 fleet 집계기 도입. 설계·검증 agent 의 보고/스코프 가이드도 함께 보강한 minor 릴리즈.

### 무엇이 바뀌나

1. **프로젝트별 sub-agent 파일 경계 override** ([#777](https://github.com/alruminum/dcNess/pull/777) [#696](https://github.com/alruminum/dcNess/issues/696)) — 활성 프로젝트가 `.dcness/boundary.json` 으로 sub-agent ALLOW_MATRIX 를 프로젝트별로 확장할 수 있다. engineer/test-engineer override 는 build-worker 합집합에도 전파. 단 write-zero agent 는 add override 로도 write 권한이 열리지 않고, `.dcness/` 디렉토리 전체와 self-disable 마커는 INFRA 로 보호되어 디렉토리 타깃 우회가 차단된다. boundary 탐색 경계는 working tree top-level / active project root 로 교정.

2. **설치·실행 상태 진단 강화** ([#765](https://github.com/alruminum/dcNess/pull/765) [#520](https://github.com/alruminum/dcNess/issues/520)) — `dcness-helper status` 진단표 확장으로 설치 상태를 한눈에 검증. plugin version 오보 차단, git hook 진단을 실제 실행 조건(`core.hooksPath` 정합) 기준으로 강화, README 활성화 확인 절차 동기화.

3. **impl-loop chain 진행 뷰 자동 렌더** ([#762](https://github.com/alruminum/dcNess/pull/762) [#755](https://github.com/alruminum/dcNess/issues/755)) — impl-loop chain 진행 상황을 view↔operations 정합 불변식 하에 자동 렌더. 비인접 transition·누적 in_progress 거부, impl-ui-design-loop 변종 + substeps override 지원.

4. **cross-run 벤치마크 fleet 집계기** ([#769](https://github.com/alruminum/dcNess/pull/769) [#766](https://github.com/alruminum/dcNess/issues/766), [#767](https://github.com/alruminum/dcNess/pull/767) [#522](https://github.com/alruminum/dcNess/issues/522), [#771](https://github.com/alruminum/dcNess/pull/771) [#770](https://github.com/alruminum/dcNess/issues/770)) — 여러 run 을 가로질러 집계하는 fleet 집계기 + 단위 테스트 도입. stored verdict precedence(prose 오파싱 방지), CHANGES_REQUESTED FAIL 집계, MUST_FIX_GHOST 가드를 게이트 PASS/LGTM+must_fix 모순만 검출하도록 정밀화(오탐 제거). dcness 자체 QA 도구로 plug-in 본체 동작에는 영향 없음.

5. **설계·검증 agent 가이드 보강** ([#774](https://github.com/alruminum/dcNess/pull/774) [#768](https://github.com/alruminum/dcNess/issues/768), [#764](https://github.com/alruminum/dcNess/pull/764) [#671](https://github.com/alruminum/dcNess/issues/671) [#674](https://github.com/alruminum/dcNess/issues/674), [#776](https://github.com/alruminum/dcNess/pull/776) [#775](https://github.com/alruminum/dcNess/issues/775)) — design lazy-read 스코프에 프로젝트 SSOT 설계문서 + 메인 전문 흡수 금지 명시, validator grounds + runtime risk upgrade 가이드 흡수, 호출 prompt 슬림 포인터 규약에 권장 3슬롯 템플릿 추가.

6. **Codex validator skill frontmatter + init-dcness 정리** ([#773](https://github.com/alruminum/dcNess/pull/773) [#772](https://github.com/alruminum/dcNess/issues/772), [#763](https://github.com/alruminum/dcNess/pull/763) [#690](https://github.com/alruminum/dcNess/issues/690)) — Codex validator skill frontmatter 추가, init-dcness 실행 절차 정리(diet).

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — sub-agent boundary override(`harness/**`), chain-view 렌더, agent 가이드(`agents/**`).
- **프로젝트별 경계 확장**을 쓰려면 활성 프로젝트 루트에 `.dcness/boundary.json` 을 추가한다(선택). 없으면 기존 ALLOW_MATRIX 기본값 그대로 동작.
- **설치 상태 점검**은 `dcness-helper status` 로 한눈에 확인 가능.
- **Codex opt-in 프로젝트**는 `codex/skills/dcness-*` validator skill frontmatter 갱신을 받으려면 plugin update 후 `/init-dcness` 재실행 필요.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.7.1 (2026-06-14)

**커밋 범위**: `v0.7.0..v0.7.1` (머지 PR 2개)
**핵심 변경**: 검증/리뷰 계열 agent 의 보고 가이드 보강 + 배포물 정리. 기능 추가 없는 patch.

### 무엇이 바뀌나

1. **검증 보고 가이드 보강** ([#759](https://github.com/alruminum/dcNess/pull/759) [#758](https://github.com/alruminum/dcNess/issues/758)) — `agents/_shared/validation-reporting-guidance.md` 추가. code-validator / architecture-validator / pr-reviewer(Claude) + Codex read-only validator skill 3종이 FAIL/ESCALATE 판단 근거와 재검증 delta 를 run-local prose 로 남기도록 가이드. 새 handoff 산출물·JSON·marker 없이 기존 자유서술 흐름 유지.

2. **배포물에서 `evals/` 제외** ([#760](https://github.com/alruminum/dcNess/pull/760)) — `sync_release.sh` 제외 목록에 `evals` 추가. 행동 eval 하네스는 dcness 자체 QA 도구라 release 브랜치(사용자 배포물)에서 빠진다. plug-in 본체 영향 없음.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — validator/reviewer 보고 가이드(`agents/**`).
- **Codex opt-in 프로젝트**는 `codex/skills/dcness-{code-validator,architecture-validator,pr-reviewer}` 갱신을 받으려면 plugin update 후 `/init-dcness` 재실행 필요.
- 배포물에서 `evals/` 가 빠져 설치물이 가벼워진다(기능 영향 없음).

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.7.0 (2026-06-13)

**커밋 범위**: `v0.6.6..v0.7.0` (머지 PR 13개)
**핵심 변경**: 제품 검수·설계 파이프라인이 "동작하는 수직 슬라이스"를 강제하도록 상·하류 양쪽을 보강. 검수가 mock-green·비사용자 동선을 걸러내고(하류), `/spec` story 분할·순서와 architecture-validator 구현 순서가 "사용자 검증 가능한 동작 증분"을 요구하며(상류), 이 지침이 실제로 작동하는지 검사하는 행동 eval 하네스(`evals/`)를 신규 도입.

### 무엇이 바뀌나

1. **검수 동작 증거·사용자 동선 판정 강화** ([#739](https://github.com/alruminum/dcNess/pull/739) [#738](https://github.com/alruminum/dcNess/issues/738), [#741](https://github.com/alruminum/dcNess/pull/741) [#740](https://github.com/alruminum/dcNess/issues/740)) — product-acceptance 가 mock-only green 을 동작 증거와 구분(정적 타입검사·실데이터 통합테스트·UI 자동화 등 자동 층 인정), 비개발자 flow 에 내부 schema/JSON 직접 입력을 요구하는 동선을 gap 으로 분리.

2. **task 분할 수직 슬라이스 기준** ([#743](https://github.com/alruminum/dcNess/pull/743) [#744](https://github.com/alruminum/dcNess/pull/744) [#742](https://github.com/alruminum/dcNess/issues/742)) — module-architect 가 파일 경계·병렬성보다 "Story 완료 시 검증되는 동작"을 우선해 task 를 자르고, architecture-validator(Claude/Codex)가 레이어별 부품 분할·첫 동작 지연을 finding 으로 잡는다.

3. **`/spec` story 분할·순서 동작 증분 기준** ([#746](https://github.com/alruminum/dcNess/pull/746) [#745](https://github.com/alruminum/dcNess/issues/745)) — story 분할의 1차 목표를 "사용자가 제품 경계에서 직접 확인 가능한 동작 증분"으로, 순서는 "얇은 end-to-end 골격(walking skeleton) 우선"으로 고정. SPEC_ACCEPTANCE 가 부품-먼저 backlog·동작 지연 순서를 기획 단계에서 gap 으로 식별.

4. **architecture-validator 구현 순서 검증 축** ([#748](https://github.com/alruminum/dcNess/pull/748) [#747](https://github.com/alruminum/dcNess/issues/747)) — epic architecture 의 구현 순서가 첫 제품 경계 동작을 앞당기는지 system 단위 검증 시점에 확인(사유 없는 부품-먼저 순서 = SYSTEM_BOUNDARY). system-architect 산출물 템플릿에 `구현 순서` 슬롯 추가.

5. **행동 eval 하네스 신규** ([#750](https://github.com/alruminum/dcNess/pull/750) [#749](https://github.com/alruminum/dcNess/issues/749), [#756](https://github.com/alruminum/dcNess/pull/756) [#618](https://github.com/alruminum/dcNess/issues/618)) — `bash evals/run.sh` 로 agent 가 기준대로 실제 판정하는지 사고 기반 fixture 로 확인. 계약 수준 정답표(agent 이름/문구 미포함, 회귀 테스트가 강제) + youTubeGenerator v03 쇼츠 실사고 L3 케이스 포함. dcness 자체 QA 도구이며 외부 배포 대상 아님.

6. **설계 검증 interleave 정리 + 하네스 정합 패치** ([#737](https://github.com/alruminum/dcNess/pull/737) [#691](https://github.com/alruminum/dcNess/issues/691), [#751](https://github.com/alruminum/dcNess/pull/751), [#752](https://github.com/alruminum/dcNess/pull/752), [#753](https://github.com/alruminum/dcNess/pull/753), [#754](https://github.com/alruminum/dcNess/pull/754)) — design validation interleave 절차 정리 + conveyor state cleanup·PR trailer finalize·user 메시지 문서 정합 등 운영 패치.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — plug-in 본체 경로(`agents/**`, `skills/**`, `docs/plugin/**`). `/spec → /design → /impl → /acceptance` 흐름에서 "다 만들고 나서 안 돌더라"가 **기획·설계 단계에서** 걸리게 된다.
- **Codex opt-in 사용 프로젝트**는 `codex/skills/dcness-architecture-validator` 갱신을 받으려면 plugin update 후 `/init-dcness` 재실행 필요.
- `evals/` 는 dcness 자체 QA 도구라 외부 활성 프로젝트로 배포되지 않는다.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.6.6 (2026-06-11)

**커밋 범위**: `v0.6.5..v0.6.6` (머지 PR 7개)
**핵심 변경**: v0.6.5 직후 누적된 버그픽스·문서 정합 패치 롤업. GitHub Project lifecycle CI 의 gh 토큰 전달 결함 수정, conveyor 종료·step 재진입 게이트 보강, codex validator mktemp macOS flake 회귀 가드, plugin 용어 SSOT 문서 추가. 기능 변경 없는 trivial patch.

### 무엇이 바뀌나

1. **GitHub Project lifecycle CI 토큰 전달 수정** ([#727](https://github.com/alruminum/dcNess/pull/727) [#726](https://github.com/alruminum/dcNess/issues/726), [#729](https://github.com/alruminum/dcNess/pull/729) [#728](https://github.com/alruminum/dcNess/issues/728)) — github-project-lifecycle composite action 이 `with: gh-token` 으로 토큰을 전달(env 미상속 결함 해소) + owner type 판별 실패 시 graceful degrade. init-dcness 가 배포하는 thin yml 도 동일 토큰 전달 + `read:org` 스코프 안내 추가.

2. **conveyor 종료·step 재진입 게이트 보강** ([#732](https://github.com/alruminum/dcNess/pull/732) [#730](https://github.com/alruminum/dcNess/issues/730), [#733](https://github.com/alruminum/dcNess/pull/733) [#731](https://github.com/alruminum/dcNess/issues/731), [#734](https://github.com/alruminum/dcNess/pull/734) [#722](https://github.com/alruminum/dcNess/issues/722)) — finalized fallback recurrence gap 차단 + step reentry run resolution 수정 + build-worker phase prose write 허용 + acceptance marker 로 Stop hook 종료 판정 보강.

3. **codex validator mktemp macOS 호환 회귀 가드** ([#735](https://github.com/alruminum/dcNess/pull/735) [#723](https://github.com/alruminum/dcNess/issues/723)) — BSD mktemp 의 trailing-X 제약 문서화 + 회귀 가드 테스트(정적+행위) 추가로 `.XXXXXX.md` 형 suffix 재유입 차단(macOS 로컬 pytest flake 해소).

4. **plugin 용어 SSOT 문서** ([#725](https://github.com/alruminum/dcNess/pull/725) [#721](https://github.com/alruminum/dcNess/issues/721)) — `docs/plugin/terms.md` 추가(용어·공개 진입점·분기 표현 기준).

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — plug-in 본체 경로(`harness/**`, `skills/**`, `scripts/**`, `docs/plugin/**`) + init-dcness 가 배포하는 yml.
- GitHub Project lifecycle CI 를 쓰는 활성 프로젝트는 토큰 전달 수정으로 머지→Done 자동전이가 안정화된다(기존 활성 프로젝트는 init-dcness yml 재배포 필요 — [#728](https://github.com/alruminum/dcNess/issues/728)).

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.6.5 (2026-06-11)

**커밋 범위**: `v0.6.1..v0.6.5` (머지 PR 12개)
**핵심 변경**: v0.6.1 직후 strict-conveyor·engineer 게이트 정합 버그픽스 일괄 + `/impl` 2축(lane×engine) 재설계 + sub-agent 검증 경계 보강. 외부 활성 프로젝트 영향이 큰 게이트 회귀 수정이 다수 포함된 패치 롤업. v0.6.1 릴리즈 이후 main 에 쌓였으나 미배포 상태였던 변경을 전부 전달한다([#718](https://github.com/alruminum/dcNess/issues/718) — 같은 버전 번호에 코드 2개가 공존하던 배포 누락 해소).

### 무엇이 바뀌나

1. **strict-conveyor·engineer 게이트 agent 이름 정규화 정합** ([#704](https://github.com/alruminum/dcNess/pull/704) [#700](https://github.com/alruminum/dcNess/issues/700), [#706](https://github.com/alruminum/dcNess/pull/706) [#701](https://github.com/alruminum/dcNess/issues/701), [#710](https://github.com/alruminum/dcNess/pull/710) [#709](https://github.com/alruminum/dcNess/issues/709)) — strict-conveyor 게이트가 `current_step.agent` 와 Agent `subagent_type` **양변 모두** namespace 정규화 후 비교(`dcness:engineer` ↔ `engineer` 불일치 차단 해소) + `current_step.agent` canonical 저장으로 end-step prose 파일명 모순 동시 해소. engineer 게이트 prerequisite 를 설계 산출물 실존으로 확장 + effective mode(`tool_input.mode` ∪ `current_step.mode`) 판정. namespaced agent 가 catastrophic 게이트를 우회하지 못하도록 후속 게이트도 정규화 비교. **이 묶음으로 [#718](https://github.com/alruminum/dcNess/issues/718)(impl-loop 풀 4-agent 진입 차단) 이 실배포본에서 해소된다.**

2. **`/impl` 2축(lane × engine) 재설계** ([#713](https://github.com/alruminum/dcNess/pull/713) [#711](https://github.com/alruminum/dcNess/issues/711), [#716](https://github.com/alruminum/dcNess/pull/716) [#714](https://github.com/alruminum/dcNess/issues/714)) — Deep lane 을 제거하고 lane(설계 산출물 유무) × 엔진(full 4-agent / build-worker) 을 직교 축으로 재모델링. Standard 진입은 `--design-doc` 단일 메커니즘으로 통일. Lite lane 에서 engineer 게이트를 lane-aware 로 면제(설계 산출물 없는 경량 작업이 게이트에 막히지 않도록).

3. **sub-agent 검증 경계 보강** ([#707](https://github.com/alruminum/dcNess/pull/707) / [#712](https://github.com/alruminum/dcNess/pull/712) / [#715](https://github.com/alruminum/dcNess/pull/715) [#705](https://github.com/alruminum/dcNess/issues/705)) — bash fd 복제·device sink redirect 를 외부 변경으로 오추출해 sub-agent 검증이 차단되던 false-block 수정 + 루트 직속 코드 파일(`app.py` 류 엔트리포인트) ALLOW 보강(prose 우회 제거) + 루트 도구체인 파일 deny + 검증 미실행 PASS 금지(`VALIDATION_BLOCKED` 계약).

4. **단계 간 되돌림 일급화 + impl-task risk 메타 + acceptance 검수** ([#708](https://github.com/alruminum/dcNess/pull/708) [#702](https://github.com/alruminum/dcNess/issues/702), [#717](https://github.com/alruminum/dcNess/pull/717) [#703](https://github.com/alruminum/dcNess/issues/703), [#720](https://github.com/alruminum/dcNess/pull/720) [#719](https://github.com/alruminum/dcNess/issues/719), [#699](https://github.com/alruminum/dcNess/pull/699) [#694](https://github.com/alruminum/dcNess/issues/694)) — 단계 간 되돌림(이전 단계 보강)을 정상 루프로 일급화. impl-task frontmatter 에 risk/engine 메타 도입으로 impl-loop dry preview 추론 제거. impl-loop story/epic 마감 시 acceptance 검수 삽입. sed clustered in-place 플래그 추출 보강.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — 전부 plug-in 본체 경로(`harness/**`, `skills/**`, `agents/**`, `docs/plugin/**`).
- **impl-loop 풀 4-agent 흐름 정상화** — v0.6.1 cache 에서 namespaced Agent 호출이 strict-conveyor 게이트에 매번 차단되던 회귀([#718](https://github.com/alruminum/dcNess/issues/718))가 해소된다. 별도 우회 없이 begin→Agent→end 사이클 통과.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.6.1 (2026-06-10)

**커밋 범위**: `v0.6.0..v0.6.1` (머지 PR 10개)
**핵심 변경**: v0.6.0 직후 버그픽스·문서 정합 패치. 병렬 wave 형식 직렬 강등 진단([#693](https://github.com/alruminum/dcNess/issues/693)), agent-boundary ALLOW_MATRIX 언어 중립화로 비-JS 외부 프로젝트 sub-agent write 회귀 수정([#694](https://github.com/alruminum/dcNess/issues/694)), GitHub Project lifecycle CI(머지→Done 자동전이) 설치.

### 무엇이 바뀌나

1. **agent-boundary ALLOW_MATRIX 언어 중립화** ([#697](https://github.com/alruminum/dcNess/pull/697) [#694](https://github.com/alruminum/dcNess/issues/694)) — sub-agent write 경계 매트릭스가 JS 경로 전제에 묶여 비-JS 외부 프로젝트에서 정상 write 가 차단되던 회귀 수정. 외부 활성 프로젝트 영향이 가장 큰 항목.

2. **병렬 wave 형식 직렬 강등 진단** ([#695](https://github.com/alruminum/dcNess/pull/695) [#693](https://github.com/alruminum/dcNess/issues/693)) — wave-plan 직렬 강등 사유를 기계 판독 cause 코드로 분류(형식 미정규화 vs 의존성). impl-task `### 수정 허용` 형식 규격 강화(생산) + design Step 5.0 형식 점검(검증) + impl-loop dry preview 사유 구분 안내(소비) 3면 정합.

3. **GitHub Project lifecycle CI** ([#692](https://github.com/alruminum/dcNess/pull/692)) — PR 머지 시 연결 issue 의 Project Status 를 Done 으로 자동 전이하는 워크플로 설치.

4. **버그픽스·문서 정합** ([#687](https://github.com/alruminum/dcNess/pull/687)/[#688](https://github.com/alruminum/dcNess/pull/688) [#684](https://github.com/alruminum/dcNess/issues/684), [#682](https://github.com/alruminum/dcNess/pull/682) [#681](https://github.com/alruminum/dcNess/issues/681), [#683](https://github.com/alruminum/dcNess/pull/683), [#689](https://github.com/alruminum/dcNess/pull/689), [#686](https://github.com/alruminum/dcNess/pull/686), [#680](https://github.com/alruminum/dcNess/pull/680)) — run-ledger completed_at scan 회귀 테스트 + helper rid fallback 복구 + TDD guard false-negative 수정 + legacy workflow skill alias 제거 + 서브에이전트 호출 prompt 슬림 포인터 규약 + hooks.md 차단 메시지/3-layer enforcement 문서 정합.

### 사용자 영향

- **`claude plugin update dcness@dcness` 로 자동 반영** — 전부 plug-in 본체 경로(`harness/**`, `skills/**`, `agents/**`, `docs/plugin/**`). ALLOW_MATRIX 회귀 수정으로 비-JS 외부 프로젝트의 sub-agent write 정상화.
- **lifecycle CI(머지→Done)** 는 `/init-dcness` 가 `.github/workflows` 로 배포하는 경로 — 기존 활성 프로젝트는 재배포(또는 `/init-dcness` 재실행) 필요.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.6.0 (2026-06-09)

**커밋 범위**: `v0.5.0..v0.6.0` (머지 PR 20개)
**핵심 변경**: GitHub Project v2 lifecycle 통합 — 단발 `/to-issue` issue 등록 흐름 신설 + 보드 등록 경로(`register-issue` / `bootstrap`) 통일 + 좌표 저장(gh variable) + Priority 맥락 추론. 부수 — product/spec public surface 확장(`/acceptance` 등) + plugin 문서 표면 정리(`module-design-principles` 를 agent shared reference 로 이동) + public surface 계약 테스트 보강.

### 무엇이 바뀌나

1. **GitHub Project v2 lifecycle 통합** ([#666](https://github.com/alruminum/dcNess/pull/666), [#668](https://github.com/alruminum/dcNess/pull/668), [#670](https://github.com/alruminum/dcNess/pull/670), [#675](https://github.com/alruminum/dcNess/pull/675) [#669](https://github.com/alruminum/dcNess/issues/669)) — Project 보드(`Status`/`IssueType`/`Priority` 3축 + repo label 6종)를 점검·생성하는 `github_project_lifecycle.mjs bootstrap` + issue 를 item 으로 등록하고 field 를 set 하는 `register-issue` subcommand 신설. 단발 `/to-issue` 와 epic/story 일괄 생성이 같은 register-issue 경로를 공유(멱등 add + drift 사후검증). 보드 좌표(owner/number)는 repo 변수 `DCNESS_PROJECT_NUMBER`/`DCNESS_PROJECT_OWNER` 에 저장(`/init-dcness` 셋업). 일괄 백필 시 사용자가 triage 한 기존 `Status`/`Priority` 를 보존([#669](https://github.com/alruminum/dcNess/issues/669)).

2. **단발 `/to-issue` 등록 흐름 신설** ([#664](https://github.com/alruminum/dcNess/pull/664), [#665](https://github.com/alruminum/dcNess/pull/665), [#668](https://github.com/alruminum/dcNess/pull/668), [#677](https://github.com/alruminum/dcNess/pull/677) [#676](https://github.com/alruminum/dcNess/issues/676)) — 자연어 문제/작업 후보를 표준 Issue Brief 로 만들어 GitHub issue + Project item 으로 등록하는 메인-직접 흐름. 필드 SSOT(`issue-fields.md`) + Issue Brief 템플릿 분리 + 생성 직전 `check_issue_body.mjs` pre-create validation. Priority 는 default `major` 로 조용히 수렴하지 않고 발화 맥락에서 추론([#676](https://github.com/alruminum/dcNess/issues/676)).

3. **product/spec public surface 확장** ([#650](https://github.com/alruminum/dcNess/pull/650), [#651](https://github.com/alruminum/dcNess/pull/651), [#652](https://github.com/alruminum/dcNess/pull/652), [#653](https://github.com/alruminum/dcNess/pull/653), [#654](https://github.com/alruminum/dcNess/pull/654), [#655](https://github.com/alruminum/dcNess/pull/655)) — product acceptance agent + `/acceptance`(mvp) + acceptance gap 라우팅 + `/spec`·`/design` alias 추가. public surface gate flip 으로 기본 노출 표면 재정렬.

4. **plugin 문서 표면 정리 + 계약 테스트 보강** ([#656](https://github.com/alruminum/dcNess/pull/656), [#657](https://github.com/alruminum/dcNess/pull/657) [#645](https://github.com/alruminum/dcNess/issues/645), [#658](https://github.com/alruminum/dcNess/pull/658), [#659](https://github.com/alruminum/dcNess/pull/659) [#521](https://github.com/alruminum/dcNess/issues/521), [#660](https://github.com/alruminum/dcNess/pull/660), [#661](https://github.com/alruminum/dcNess/pull/661), [#678](https://github.com/alruminum/dcNess/pull/678)) — `module-design-principles.md` 를 `docs/plugin` 에서 `agents/_shared` 로 이동(architect/implementation agent 내부 기준이라 소유권 정합) + `parallel-policy.md` 를 현행 peer 세션 정책으로 명확화(옛 fan-in 잔재 제거) + 사용자-facing 문서의 `doctrine` 표현을 설계/운영 원칙으로 교체([#678](https://github.com/alruminum/dcNess/pull/678)). compat alias 공개 노출 축소 + lifecycle alias drift 보강 + acceptance follow-up. skill/agent RED-GREEN 시나리오 테스트 하네스([#521](https://github.com/alruminum/dcNess/issues/521)) + init-dcness 회귀 트리거 + spec PRD 기술검토 preflight 흐름 정리.

### 사용자 영향

- **외부 활성 프로젝트: `claude plugin update dcness@dcness` 로 자동 반영** — 보드 lifecycle(bootstrap/register-issue) + `/to-issue` + `/acceptance` 가 plug-in 본체 경로(`skills/**`, `scripts/**`, `agents/**`, `docs/plugin/**`)로 적용. 보드를 쓰려면 `/init-dcness` 재실행 또는 좌표 수동 저장 필요.
- **`/to-issue` 신규** — 단발 issue 등록의 기본 진입점. Priority 는 맥락 추론값으로 근거와 함께 초안에 제시되고, 사용자는 교정만.
- **Priority 자동 추론** — `/to-issue` 가 더 이상 항상 `major` 로 박지 않는다([#676](https://github.com/alruminum/dcNess/issues/676)). epic/story 일괄 생성은 의도된 `major` 고정 유지.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.5.0 (2026-06-06)

**커밋 범위**: `v0.4.0..v0.5.0` (머지 PR 20개)
**핵심 변경**: 사용자 진입 표면 재편 — 신규 `/impl` public lane (Lite/Standard/Deep 내부 라우팅) + risk-based workflow router. 부수 — 모델 신뢰 시대 하네스 운영 원칙 전환 + hook 경계 정합 (hook 7→8) + 설계영역 Contract lifecycle 도입 + run-ledger(prose receipt) 신설 + opt-in 병렬 실행(독립 peer 세션 + claim board + merge lock).

### 무엇이 바뀌나

1. **신규 `/impl` public lane + risk-based workflow router** ([#616](https://github.com/alruminum/dcNess/pull/616) [#585](https://github.com/alruminum/dcNess/issues/585)/[#588](https://github.com/alruminum/dcNess/issues/588), [#595](https://github.com/alruminum/dcNess/pull/595) [#586](https://github.com/alruminum/dcNess/issues/586)) — 사용자가 lane별 command 를 외우는 대신 단일 구현 entrypoint `/impl` 이 Lite / Standard / Deep lane 으로 내부 라우팅한다. 기본 public workflow surface = `/impl` · `/product-plan` · `/issue-report` 3종으로 문서화. workflow 선택 기준을 `docs/plugin/workflow-router.md` 단일 진본으로 — gate 축(high-risk = planning gate) × shape 축(durable = implementation shape) 직교. `/impl-loop` 는 deep impl task 파일용 **legacy/advanced runner 로 재분류**(호출 자체는 유지). `scripts/check_public_surface.mjs` + CI gate 신설로 public surface 계약 회귀 차단.

2. **모델 신뢰 시대 하네스 운영 원칙 전환** ([#617](https://github.com/alruminum/dcNess/pull/617) [#591](https://github.com/alruminum/dcNess/issues/591), [#611](https://github.com/alruminum/dcNess/pull/611) [#609](https://github.com/alruminum/dcNess/issues/609), [#610](https://github.com/alruminum/dcNess/pull/610) [#607](https://github.com/alruminum/dcNess/issues/607)) — dcNess 는 model-distrust 하네스가 아니라 working-style 보존 하네스라는 운영 원칙을 CLAUDE.md/SSOT 에 명문화. 강제는 (1) 작업 순서 (2) 접근 영역 둘만, 그 외는 agent 자율. 무거운 절차(product-plan / tech-review / architect-loop)는 항상-on 이 아니라 risk-triggered escalation. tech-reviewer 재호출 hard block(코드 강제) 제거 + catastrophic 게이트 번호(§2.1.N) → 자연어 이름. finding 수용 원칙(점 패치 금지, 근본 재설계) 추가.

3. **hook / 권한 경계 정합 (hook 7 → 8)** ([#599](https://github.com/alruminum/dcNess/pull/599) [#597](https://github.com/alruminum/dcNess/issues/597), [#606](https://github.com/alruminum/dcNess/pull/606) [#598](https://github.com/alruminum/dcNess/issues/598), [#605](https://github.com/alruminum/dcNess/pull/605) [#604](https://github.com/alruminum/dcNess/issues/604), [#602](https://github.com/alruminum/dcNess/pull/602) [#596](https://github.com/alruminum/dcNess/issues/596), [#603](https://github.com/alruminum/dcNess/pull/603) [#601](https://github.com/alruminum/dcNess/issues/601)) — **SubagentStop hook 등록(7→8)** 으로 병렬/백그라운드 sub-agent active_agent 신뢰 clear + file-op self-attribution + pending_agents multi-slot. PreToolUse blocking semantics 통일(exit 2) + sub-agent external mutation denylist(Bash + GitHub MCP) + 따옴표-인지 토크나이저. strict conveyor gate(current_step 단일 슬롯 강제). SessionStart inject 슬림화 + hook-first recovery.

4. **설계영역 — Contract lifecycle 도입** ([#613](https://github.com/alruminum/dcNess/pull/613) [#612](https://github.com/alruminum/dcNess/issues/612), [#615](https://github.com/alruminum/dcNess/pull/615)) — architect 레벨을 늘리지 않고 **계약(Contract)을 1급 산출물로 관리**. architecture-validator 가 `FAIL` 을 "전파 누락(stale 사본)" vs "진짜 경계 오류" 로 분류 라우팅 → 단순 전파 누락이 불필요한 system 재설계로 비화하던 비용 차단. interface 를 시그니처뿐 아니라 invariant/ordering/error/forbidden 까지 단일 Contract Ledger 로 관리. module-architect impl 템플릿 경량화(private helper 이름·loop body·의사코드 선점 제거 → drift 표면 축소).

5. **run-ledger / prose receipt** ([#623](https://github.com/alruminum/dcNess/pull/623) [#587](https://github.com/alruminum/dcNess/issues/587), [#632](https://github.com/alruminum/dcNess/pull/632) [#631](https://github.com/alruminum/dcNess/issues/631)) — `harness/ledger.py` 신규 — run 단위 append-only event 장부 + helper-generated receipt(sha256 / prose_excerpt / must_fix / evidence_paths / next_action). 긴 prose 재주입 대신 evidence pointer 로 chain 상태(현재 task/phase/PR / next)를 한눈에 색인. read-side strict 검증(prose_file 실존 + sha256 digest match)으로 위조/손상 step 차단. 옛 `.steps.jsonl` deny-list. Epic4 하네스 회귀 8건 일괄 보강.

6. **opt-in 병렬 실행 — 독립 peer 세션** ([#637](https://github.com/alruminum/dcNess/pull/637) [#589](https://github.com/alruminum/dcNess/issues/589), [#638](https://github.com/alruminum/dcNess/pull/638) [#636](https://github.com/alruminum/dcNess/issues/636), [#639](https://github.com/alruminum/dcNess/pull/639), [#642](https://github.com/alruminum/dcNess/pull/642) [#641](https://github.com/alruminum/dcNess/issues/641)) — 기본은 직렬 chain, 병렬은 독립 task 가 기계 판정으로 확신될 때만 opt-in. 정책 SSOT = `docs/plugin/parallel-policy.md`(depends_on 3-state + Scope 파일집합 disjoint 판정). 실행 모델은 **별도 터미널 interactive peer 세션** — 각 세션이 기존 `/impl-loop <canonical-impl-path>` single task 를 수행. `harness/wave_board.py`(canonical impl path 단위 O_EXCL claim board) + `harness/merge_lock.py`(repo-level merge mutex + 같은 story prior task_index order gate + stale 복구)로 중복 작업·조기 close 차단. `scripts/pr-finalize.sh` 가 실제 merge 경로에서 peer guard 적용(미등록 PR 은 `mode=serial` 로 기존 흐름 유지). **주의**: 사이클 중 모델 진화 — [#638](https://github.com/alruminum/dcNess/pull/638) 의 "worktree 격리 fan-in" 은 [#642](https://github.com/alruminum/dcNess/pull/642) 의 peer 세션 모델로 대체됨(옛 helper 는 호환용 코드로만 남음).

### 사용자 영향

- **외부 활성 프로젝트: `claude plugin update dcness@dcness` 로 자동 반영** — 신규 `/impl` 진입점 + risk router + 8 hook + Contract lifecycle + run-ledger + 병렬 opt-in 이 plug-in 본체 경로(`skills/**`, `hooks/**`, `harness/**`, `scripts/**`, `docs/plugin/**`)로 자동 적용. 호출 방식(`/impl`·`/product-plan`·`/issue-report`·`/impl-loop`) 그대로.
- **`/impl` 권장, `/impl-loop` 는 advanced 유지** — 일반 구현·버그픽스·한 줄 수정의 기본 진입점은 이제 `/impl`. `/impl-loop` 는 architect-loop 산출 deep impl task 파일용 legacy/advanced runner 로 그대로 호출 가능.
- **tech-reviewer 재호출 코드 hard block 제거** — `/architect-loop` 진입 후 재호출은 이제 코드 강제 차단이 아니라 skill prose 권고. 운영 원칙 전환(강제 최소화)의 일환.
- **병렬은 명시적 opt-in 한정** — `wave-plan --register` 로 등록 + 사용자가 별도 터미널에서 peer 세션을 직접 띄울 때만 발화. 미등록 경로·yolo 모드는 기존 직렬 그대로(자동 ON 안 함). [#216](https://github.com/alruminum/dcNess/issues/216) cache_read 폭주 안티패턴 가드 유지.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.4.0 (2026-06-04)

**커밋 범위**: `v0.3.0..v0.4.0`
**핵심 변경**: `commands/*.md` → `skills/<name>/SKILL.md` 승격 (7 skill) + 라우팅을 각 skill 옆 `<name>-routing.md` 단일 진본으로 분산 + 전역 SSOT (`orchestration.md` / `handoff-matrix.md` / 전역 `routing.md`) 폐기. 부수 — Codex read-only validator skills 3종 신설 + harness 코드 다이어트 + agent 기능 강화 + 문서 컨벤션 SSOT 신설.

### 무엇이 바뀌나

1. **commands → skills 전환 (7 skill)** — `architect-loop` / `impl-loop` / `impl` / `issue-report` / `product-plan` / `tech-review` / `ux` 를 `commands/<name>.md` 단일 파일에서 `skills/<name>/SKILL.md` (진행 절차) + `skills/<name>/<name>-routing.md` (라우팅 SSOT — mermaid + 결론→다음 매핑 + retry 한도 + escalate) 디렉토리로 승격. SKILL.md 경량화. frontmatter `name` 동일 → 사용자 호출 방식 (`/architect-loop`·`/impl` 등) 그대로. plugin.json 무변경 (skills/ 자동 스캔, namespace `dcness:<name>`). 옛 `commands/<name>.md` 삭제 (동일 name 중복 등록 충돌 회피). 남은 commands = `efficiency` / `init-dcness` / `run-review` / `smart-compact`.

2. **라우팅 SSOT 분산 + 전역 집계 파일 폐기** — `docs/plugin/orchestration.md` + `handoff-matrix.md` + 전역 `routing.md` 폐기. 통찰 = "라우팅은 skill 이 소유, agent 는 결론(enum)만 낸다". 런타임에 안 읽히던 전역 집계 view(중복)를 각 skill 옆 `<name>-routing.md` 단일 진본으로 이전.

3. **Codex read-only validator skills 신설** — `code-validator` / `architecture-validator` / `pr-reviewer` 3종을 Codex read-only 실행으로 route 가능. `codex/skills/dcness-*/SKILL.md` + `scripts/dcness-codex-validator` wrapper (Codex read-only sandbox + prose 수집 + end-step 저장 + mutation guard) + `harness/agent_routing.py` (local routing). **사용자 repo 에 파일 안 만듦** — `~/.claude/plugins/data/dcness-dcness/routing.json` + `$CODEX_HOME/skills/` 에만. read-only 3종 한정(mutation agent migration 차단).

4. **harness 코드 다이어트** — `harness/interpret_strategy.py` + `scripts/analyze_metrics.mjs` + `tests/eval_{deepeval,agentevals}.py` 삭제 (enum 추출 / 전략 해석 / 외부 eval 의존 제거). `harness/agent_routing.py` + `harness/prev_tasks.py` 신규.

5. **agent 기능 강화** — architecture-validator premortem 시뮬레이션 + origin anchor provenance 검증 / tech-reviewer → system-architect signal 전달 / 신규 의존 경량 escalate (G3) / tech-stack grill checkpoint / UI-less 화면 ux skip gate / impl-loop prev-tasks 컨텍스트 inject + dry-run preview.

6. **문서 컨벤션 SSOT + 정리** — `docs/internal/doc-conventions.md` 신규 (문서 작성 규약 단일 진본). anchor-ref 마이그레이션 (§N 참조 → 제목 자연어), codeblock/주석 stale-ref 자연어화, routing/loop 중복 다이어트, README·manifest sync, loop-procedure 단일 목적 슬림화.

### 사용자 영향

- **외부 활성 프로젝트: `claude plugin update dcness@dcness` 로 skills 전환 자동 반영** — 호출 방식 (`/architect-loop`·`/impl-loop`·`/impl`·`/issue-report`·`/product-plan`·`/tech-review`) 그대로. 옛 `commands/<name>.md` 는 삭제됐지만 같은 namespace 로 skills 가 등록돼 동작 동형. (런타임 트리거 100% 확인은 사용자 환경에서 한 번 호출.)
- **Codex validator 쓰려면 `/init-dcness` 재실행** — plugin update 후 `/init-dcness` 재실행 시 Step 2.10 에서 `$CODEX_HOME/skills/dcness-*` 복사 + routing opt-in (Y/n). 끄기 = `dcness-helper routing disable-codex-validation`. opt-in 안 하면 기존 (메인 Claude in-session) validator 그대로.
- **옛 전역 SSOT 앵커 참조** — `orchestration.md` / `handoff-matrix.md` / 전역 `routing.md` 의 §N 앵커 참조는 전부 각 skill routing.md 또는 제목 자연어로 마이그레이션됨. 외부 사용자가 직접 참조하던 링크 없으면 영향 없음.

### 업데이트

```sh
claude plugin update dcness@dcness
# Codex validator 까지 쓰려면:
/init-dcness   # 재실행 → Step 2.10 routing opt-in
```

---

## v0.3.0 (2026-05-26)

**커밋 범위**: `v0.2.34..v0.3.0`
**핵심 변경**: `/architect-loop` 의 책임 구조 재설계 — system-architect 책임 좁힘 + module-architect 책임 확장 + Story 묶음 단위 호출 + architecture-validator 영역 갱신 (Spike Gate 폐기 + Cross-Story Interface + 공통 SSOT 룰 위반) + 모듈 설계 원칙 공통 SSOT 신설 ([#511](https://github.com/alruminum/dcNess/issues/511)). plug-in major bump — 옛 구조 epic 의 architect-loop 재진입은 자율, 새 epic 부터는 새 구조 강제.

### 무엇이 바뀌나

1. **system-architect 책임 좁힘** — 옛 구조에서는 도메인 모델 + 모듈 구조 + 기술 스택 + Story → impl 매핑 표 + Spike Gate 까지 다 책임 (한 호출에 task 27 개 outline 부담). 새 구조 = 전체 시스템 그림만 — root `docs/architecture.md` (기술 스택 + 외부 의존 + 전체 모듈 토폴로지) + root `docs/adr.md` (전체 시스템 수준 의사결정) + epic 단위 architecture.md (모듈 목록 + 의존 그래프 + 공통 task 목록 + Story → 모듈 매핑) + epic 단위 adr.md + epic 단위 domain-model.md. 페르소나 한 줄 정의 폐기 + 작업 명세 (What / When / DoD) 형식 ([#515](https://github.com/alruminum/dcNess/issues/515) 의 tech-reviewer 패턴 정합). `## impl 목차` 표 폐기. Spike Gate 별도 phase 폐기 (tech-reviewer 가 PRD 단계 cover, 차단 패턴 한 줄만 자기 규율로 흡수).

2. **module-architect 책임 확장 — Story 묶음 단위** — 한 호출 = 한 Story 단위 = N 개 impl 파일 작성 + 단위 안 task 식별 + 의존 순서 결정 + cross-task interface 정합 검증 + 도메인 sync. Story → 작업 매핑 + task 분할 책임 (옛 system-architect 영역) 흡수. K (호출 수) = Story 수 + 공통 호출 1 회 (공통 task 있으면) 또는 0 회. 옛 task 단위 K (~27) 와 다르게 새 K 는 Story 묶음 단위라 ~5+α 영역.

3. **architecture-validator 영역 갱신** — 3 영역 검증 — **Placeholder Leak (유지) + Cross-Story Interface 정합성 (옛 Cross-Task Interface 에서 변경 — Story 안은 module-architect self-check 가 cover, Story 간만 validator 영역) + 공통 SSOT 룰 위반 (신규 — 순환 의존 / 미허가 의존 / public API contract 위반 자동 영역 + Deep Modules / 부작용 없는 반환 수동 review 권고 영역 분리)**. Spike Gate 폐기. `/architect-loop` 안에서 두 시점 호출 — Step 3.5 (system-architect 직후, Placeholder + 공통 SSOT) + Step 5 (module 다 끝난 후, Cross-Story Interface).

4. **공통 SSOT 신설 — [`agents/_shared/module-design-principles.md`](../../docs/plugin/agents/_shared/module-design-principles.md)** — 세 영역 룰을 한 곳에 모음 — Deep Modules (John Ousterhout, "A Philosophy of Software Design") + Interface Design for Testability ([mattpocock skills](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/interface-design.md)) + 의존성 강제 세 영역 (순환 의존 / 미허가 의존 빌드 시점 차단 / 모듈 공개·비공개 영역 구분 강제 / DI 강제). system / module / engineer / test-engineer 의 호출 시 read 의무. drift 차단 + agent 본문 분량 ↓.

5. **batch 모드 폐기** — 옛 `/architect-loop` 의 batch 모드 (K ≥ 8 시 Story 단위 묶음 1 호출) 폐기. Story 묶음 자체가 batch 의 본질 해결.

6. **폴더 구조 SSOT 명확화 — system-wide + epic 단위 분리** — 옛 구조에서는 stories.md 위치 영역이 product-plan.md 와 architect-loop.md 사이 drift 가 있어 외부 사용자 프로젝트마다 메인 Claude 가 임의로 위치 결정 (jajang 은 epic 폴더 안 / youtube-gen 은 docs root). 새 구조 = root (`docs/prd.md` + `docs/tech-review.md` + `docs/architecture.md` + `docs/adr.md`) + epic 단위 (`docs/milestones/vNN/epics/epic-NN-*/stories.md` + architecture.md + adr.md + domain-model.md + ux-flow.md + impl/). PRD 는 root 단일 (제품 1 개 = PRD 1 개), milestone 진화는 같은 파일 안 영역 갱신.

### 사용자 영향

- **옛 epic 의 architect-loop 재진입은 자율** — architecture.md 의 `## impl 목차` 표가 들어있는 epic 은 새 구조와 충돌. 메인 Claude 가 강제 차단은 안 하되 옛 표 영역 의미가 사라짐 (`task_index` 의미 = 그 Story 안 task 순번으로 변경). 옛 epic 영역에서 새 architect-loop 호출 시 system-architect 가 epic 단위 architecture.md 신규 작성 영역으로 진행.
- **새 epic 부터는 새 구조 강제** — `/product-plan` 진입 시 epic 단위 stories.md 위치 (`docs/milestones/vNN/epics/epic-NN-<slug>/stories.md`) 영역으로 자동 작성. `/architect-loop` 영역도 같은 epic 경로 위에서 진행.
- **옛 batch 호출 코드 즉시 실패** — `/architect-loop` 의 batch 모드 명시 호출 영역은 v0.3.0 후 작동 안 함. 자연 폐기 (Story 묶음으로 갈음).
- **외부 사용자 dcness plug-in 갱신 명령** — `claude plugin update dcness@dcness`. 문제 발생 시 uninstall → install fallback (`claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness`).

### 옛 root 단위 stories.md (youtube-gen 패턴) 마이그레이션 가이드

옛 `docs/stories.md` (root) 영역을 새 구조로 옮길 때:

1. 기존 `docs/stories.md` 안 epic 헤더 영역 식별 (예: `## Epic — <설명>`)
2. 새 디렉토리 생성 — `docs/milestones/vNN/epics/epic-NN-<slug>/`
3. `docs/stories.md` 내용을 새 디렉토리 안 `stories.md` 로 이동
4. 같은 디렉토리에 architecture.md / adr.md / domain-model.md 신규 작성 (`/architect-loop` 호출 시 system-architect 가 자동 신규 작성)
5. `docs/stories.md` (root) 영역은 archive 또는 삭제 (`git rm`)
6. GitHub 이슈 등록 영역은 그대로 유지 (재등록 불필요) — 이슈 본문의 stories.md 경로 영역만 새 경로로 patch

### 옛 epic 단위 stories.md (jajang 패턴) 영역의 변화

기존 epic 단위 stories.md 영역 (예: `docs/milestones/v1/epics/epic-08-*/stories.md`) 은 위치 영역이 새 구조와 정합. 단 옛 architecture.md / adr.md 가 root 단일 영역 (예: `docs/ARCHITECTURE.md`) 인 경우 — root architecture.md / adr.md 영역으로 갱신 (대문자 → 소문자) + epic 단위 architecture.md / adr.md / domain-model.md 신규 작성. `/architect-loop` 재호출 시 system-architect 가 자동 처리.

### 모노레포 영역 (별도 issue 예정)

모노레포 (workspace 여러 개) 대응은 본 v0.3.0 영역 외. `CONTEXT-MAP.md` / `package.json` 의 `workspaces` / `pnpm-workspace.yaml` / `turbo.json` / `nx.json` 마커 detect 시 메인 Claude 가 사용자에게 안내 + 본 영역 별도 GitHub issue 등록.

### 보강 영역 (출시 후 측정 + 후속)

- **Story 크기 가이드 추가** (`commands/product-plan.md` 영역, 현 [`skills/spec/SKILL.md`](../../skills/spec/SKILL.md)) — Story 1 개당 예상 task ≤ 5 권장 / Story 큰 경우 분할 권고 / cross-cutting Story 표시. module-architect 한 호출의 산출 부담 통제.
- **cross-cutting Story 빈도 측정** — 외부 활성 프로젝트의 epic 1-2 개를 새 구조로 수동 시뮬레이션. 빈도 ≥ 30% 면 Architecture Mode opt-in (stories.md 마커로 모듈 묶음 / Story 묶음 선택) 재검토.
- **module-architect 모델 검토** — 새 구조에서 한 호출의 판단 차원이 깊어짐. sonnet 으로 누락 / 회전 발생 시 opus 승격 검토.
- **validator 자동 / 수동 영역 분리 운영** — 자동 검증 통과 영역 + 수동 review 권고 영역 분리 명시. 사용자가 수동 review 권고 영역에 PASS 주면 완료.

---

## v0.2.34 (2026-05-26)

**커밋 범위**: `v0.2.33..v0.2.34`
**핵심 변경**: `plan-reviewer` agent 폐기 + `tech-reviewer` 신설 + `/tech-review` 스킬 분리 + 단방향 catastrophic 룰 ([#516](https://github.com/alruminum/dcNess/pull/516)). 부수 — impl-loop 강화 (review 5줄 / SPEC_GAP 예외 / 세션 분할 / phase prose lint) + architect-loop batch + interface 정합성 검증 + SSOT cross-ref CI 게이트 + PR/git 인프라 다듬기 + CLAUDE.md 사용자 정체성 최상단 승격.

### 무엇이 바뀌나

1. **`plan-reviewer` 폐기 → `tech-reviewer` 신설 + `/tech-review` 스킬 분리** ([#516](https://github.com/alruminum/dcNess/pull/516)) — 옛 8 차원 (현실성 / MVP / 제약 / UX / 숨은가정 / 경쟁 / 과금 / 기술실현) reviewer 가 메인 그릴미와 §1~§5 중복 + 사후 self-check 의미 약함 (이슈 [#515](https://github.com/alruminum/dcNess/issues/515)). 새 정체성 = 페르소나 폐기 + 작업 명세 (What / When / DoD) 형식 + 책임 2 축 (기술 제약 검토 4 항목 / 용도별 스펙 깎기). Bash + Write 권한 부여 (`docs/tech-review.md` + `docs/tech-review/**` 한정) — 실측 + 증거물 (음성 / 이미지 / 로그) + 통합 HTML 리포트 (`docs/tech-review/report.html`) 산출. 워크플로우 = `/product-plan` (PRD + 스켈레톤) → 사용자 1 차 OK → `/tech-review` (본문 + evidence + HTML) → 사용자 2 차 OK → `/architect-loop`. **단방향 catastrophic** — `/architect-loop` 진입 후 tech-reviewer 재호출 금지 (회귀 사고 패턴 차단). 옛 plan-reviewer 호출 코드 (`Agent(subagent_type="plan-reviewer", ...)`) 는 plug-in update 후 즉시 실패 — 외부 활성 프로젝트는 `/tech-review` 로 이행 필요. `system-architect.md:101` ADR 4 카테고리 사후 self-check 룰도 같이 폐기 (선행 검증 = tech-reviewer 가 cover). 사용자 환경 `.gitignore` 에 `docs/tech-review/evidence/` + `docs/tech-review/report.html` 수동 추가 권고 (init-dcness 자동 추가 X — overwrite 위험).

2. **impl-loop 강화 — review 5줄 강제 + SPEC_GAP 예외 + 세션 분할** ([#513](https://github.com/alruminum/dcNess/pull/513) / [#514](https://github.com/alruminum/dcNess/pull/514)) — pr-reviewer return prose 5 줄 강제 + 다시 그리기 trade-off 명시 + 세션 분할 권장 (F8+F9+F13). build-worker 의 경량 SPEC_GAP 예외 + phase prose path 명시 + lint 강제 (F4+F7+F12). 매 task return 누적이 메인 컨텍스트 부풀게 하던 회귀 차단.

3. **architect-loop batch 모드 + cross-task interface 정합성 검증** ([#512](https://github.com/alruminum/dcNess/pull/512)) — architect-loop §4.2 module-architect × K 가 batch 호출 가능 (개별 호출 누적 비용 절감). architecture-validator 가 cross-task interface 정합성 검증 책임 추가 (F6+F11). handoff-matrix + orchestration §4.2 drift 동시 갱신 룰 박음 ([#505](https://github.com/alruminum/dcNess/issues/505)).

4. **SSOT 정리 — cross-ref CI 게이트 + dead link / 옛 명칭 회귀 차단** ([#495](https://github.com/alruminum/dcNess/pull/495) / [#496](https://github.com/alruminum/dcNess/pull/496) / [#497](https://github.com/alruminum/dcNess/pull/497) / [#498](https://github.com/alruminum/dcNess/pull/498) / [#499](https://github.com/alruminum/dcNess/pull/499) / [#500](https://github.com/alruminum/dcNess/pull/500)) — `scripts/check_cross_refs.mjs` + CI workflow `cross-ref-validation.yml` 신규 (dead link / dead anchor / 옛 명칭 deny-list 자동 catch). SSOT M1 (archive 인용 9건 본문 자족화) + M2 (handoff-matrix §1 ↔ orchestration §4 양방향 drift 룰) + N (옛 명칭 정리 — auto-loop / direct-impl-loop / §1.4 / §3.5 / §3.1.5 / §7.5) + agent ↔ SSOT 정합 (HIGH 5건 + drift 룰 callout).

5. **PR / git 인프라 다듬기** ([#502](https://github.com/alruminum/dcNess/pull/502) / [#509](https://github.com/alruminum/dcNess/pull/509) / [#510](https://github.com/alruminum/dcNess/pull/510)) — `scripts/create_epic_story_issues.sh` 의 milestone title 추출 정정 (gh CLI 정합). `pr-finalize.sh` 의 auto-merge 토글이 clean status PR 에서 거부되는 케이스 즉시 머지 fallback + `origin/main` ref-only fetch 정석 패턴 (F1+F3+F14). `check_pr_body.mjs` 의 task-index trailer + Story 마지막 task `Closes` 강제 가드 (F10) + build-worker / git-spec 에 task-index trailer 의무 명시 (F10 보강).

6. **`CLAUDE.md` 사용자 정체성 최상단 승격 + 헤더 영역 정리** ([#493](https://github.com/alruminum/dcNess/pull/493)) — 사용자 정체성 (한국어 시니어 엔지니어 / 자연스러운 표준어 / 결론부터 / 클릭 가능 링크) 을 §0 프로젝트 정체성 옆으로 승격. 매 세션 시작 시 메인 Claude 가 즉시 인지하는 두 영역만 최상단.

### 사용자 영향

- **외부 활성 프로젝트의 옛 `plan-reviewer` 호출 코드 즉시 실패** — `/tech-review` 로 이행 필요. `/product-plan` 재진입 시 새 워크플로우 (PRD + 스켈레톤 → 사용자 1 차 OK → `/tech-review` → 사용자 2 차 OK → `/architect-loop`) 따라 진행.
- **외부 환경 `.gitignore` 수동 추가 권고** — `docs/tech-review/evidence/` + `docs/tech-review/report.html` (로컬 보존, repo 부풀음 차단).
- **옛 `commands/run-review.md` 의 `EXTERNAL_VERIFIED_PRESENT/MISSING` baseline 폐기** — 새 baseline 신설 X (과거 측정 데이터는 보존). plan-reviewer 산출물 패턴 사라짐.

---

## v0.2.33 (2026-05-23)

**커밋 범위**: `v0.2.32..v0.2.33`
**핵심 변경**: `docs/plugin/git-spec.md` 단일 SSOT 신설 (PR + commit + 이슈 등록 룰 통합) + PR body 게이트 over-firing 해소 + review heuristic 강화 (TOOL_REPEAT_HIGH 신규 / must_fix 부정 한국어 라벨 흡수) + helper 진단성 + pr-reviewer 권한 경계 명확화 + 한국어 톤 표준화.

### 무엇이 바뀌나

1. **`docs/plugin/git-spec.md` 신설 + `git-naming-spec.md` 폐기 + `issue-lifecycle.md` 축소** ([#491](https://github.com/alruminum/dcNess/pull/491)) — 브랜치·커밋·PR 네이밍 (§1~§6) + 이슈 등록 양식 (§7) + PR 트레일러 룰 (§8) + 이슈 완료 룰 (§9) 단일 SSOT. `issue-lifecycle.md` 는 흐름·메커니즘 (sub-issue API / 멱등성 / 마일스톤 조회 / pre-flight gate) 만 남김 (202 → 78줄). `.github/PULL_REQUEST_TEMPLATE.md` 신 양식 (관련 이슈 번호 / 배경 및 문제 / 원인 / 작업내용 / 결정 근거 / Test Plan / 참고). dcness self 전용 `## 배포 경로 검증` 섹션 = self 만 (외부 SSOT 누출 X — CLAUDE.md §0.3 정합).

2. **PR body 게이트 over-firing 해소** ([#492](https://github.com/alruminum/dcNess/pull/492)) — `scripts/check_pr_body.mjs` 의 정규식 확장 (`CLOSE_RE` → `TRAILER_RE`). `Part of #N` 트레일러도 valid 로 인정 (close 키워드 단독 강제 폐기). 중간 task PR 마다 fail 발화하던 룰 모순 해소. 외부 활성 프로젝트의 다음 PR 부터 즉시 적용 (composite action 상대경로 호출 — 재배포 불필요).

3. **pr-reviewer 권한 경계 명확화** ([#485](https://github.com/alruminum/dcNess/pull/485)) — `commands/impl.md` + `commands/impl-loop.md` 정상 흐름 표현 정정. pr-reviewer 의 `tools: Read, Glob, Grep` 명시 + commit/push/PR 생성·머지는 *메인 Claude 전담* 분리. 외부 활성 프로젝트 CC 가 "pr-reviewer 가 PR 만들어야 하는데 권한이 없다" 호소하던 회귀 차단.

4. **review heuristic — TOOL_REPEAT_HIGH 신규** ([#487](https://github.com/alruminum/dcNess/pull/487)) — `harness/run_review.py` 의 `_detect_tool_repeat_findings`. agent-trace.jsonl 의 (tool, input) 카운트 임계 (Bash 5+ / Read 4+ / 기타 5+) 초과 시 `TOOL_REPEAT_HIGH` MEDIUM finding emit. build-worker 가 같은 명령 반복 호출하는 안티패턴 catch.

5. **review heuristic — must_fix 부정 한국어 라벨 흡수** ([#486](https://github.com/alruminum/dcNess/pull/486)) — `_MUST_FIX_NEGATION_RE` 의 between 영역 일반화 (`[\s:=]*` → `[^\n]{0,30}?`). pr-reviewer prose 의 `**MUST FIX 항목**: 없음` 같은 한국어 라벨 형태 흡수. `MUST_FIX_LEAK` HIGH false positive 차단.

6. **helper sid/rid 진단성 강화** ([#488](https://github.com/alruminum/dcNess/pull/488)) — `harness/session_state.py` 의 `diagnose_sid_rid_resolution`. 3 layer (env / PPID / active_runs scan) 상태 + escape hatch (`DCNESS_SESSION_ID/RUN_ID` export 명령) stderr 출력. 사용자 자가 해결 영역 확보.

7. **한국어 톤 표준화 — '박-' 동사 회귀 전수 보정** ([#490](https://github.com/alruminum/dcNess/pull/490)) — `agents/` + `commands/` + `hooks/` + `harness/` + `scripts/` + `docs/plugin/` 영역의 비표준 동사 변형 약 137건 (37 파일) 을 자연스러운 한국어 표준 동사로 통일.

### 왜 바뀌나

본 release 의 두 핵심 변경 (#491 SSOT 통합 / #492 게이트 해소) 은 같은 뿌리:

- **#491 SSOT 통합**: 직전 release (v0.2.32) 까지 PR / commit / 이슈 등록 룰이 5곳 (PR template / git-naming-spec / issue-lifecycle / build-worker inline / create_epic_story_issues inline) 에 분산. PR #485 작성 시 commit message 와 PR body 가 같은 정보를 다른 양식으로 *중복 작성* 하는 패턴 노출. 외부 활성 프로젝트 CC 의 *어디 룰 따를지* 추적 비용 제거 목적.

- **#492 게이트 해소**: SSOT 통합 작업 중 사용자가 반복 발생하는 fail 메일 보고 → 게이트 룰 (`close 키워드 1+ 강제`) 와 dcness 룰 (`중간 task PR = Part of #N`) 정면 모순 발견. 정규식 의미 진화 (\"close 키워드\" → \"트레일러\") 로 해소.

나머지 #485 / #486 / #487 / #488 / #490 은 외부 활성 프로젝트 (jajang) 의 실측 회귀 사례 받아 부수 보강.

### 사용자 행동

- **외부 활성 프로젝트는 plug-in 업데이트만 받으면 즉시 적용** (CLAUDE.md §0.5 경로 1·3):
  - `pr-body-validation` 게이트가 `Part of #N` 도 통과 → 우회 마커 (`Document-Exception-PR-Close:`) 빈도 급감
  - 새 SSOT `docs/plugin/git-spec.md` 가 plug-in 본체 경로로 자동 read
- **외부용 PR template 자동 배포는 본 release 에 포함 X** — 외부 사용자가 자기 `.github/PULL_REQUEST_TEMPLATE.md` 작성 또는 메인 CC 가 spec §5 본문 직접 read 후 PR body 작성

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.2.32 (2026-05-23)

**커밋 범위**: `v0.2.31..v0.2.32`
**핵심 변경**: `/impl-loop` 분기 룰을 "양식별 분기" → "impl 파일 존재 여부" 1차원으로 단순화. build-worker 가 모든 input (정식 양식 / bugfix / 자유 형식) 받음. impl 파일 부재 시 module-architect 자동 선두 진입.

### 무엇이 바뀌나

1. **`commands/impl-loop.md` 분기 룰** — 정규식 양식 매치 (`docs/milestones/.../impl/NN-*.md`) 폐기. **impl 파일 존재 여부 1차원**만 본다:
   - 있음 → build-worker 직진 (2-step: build-worker + pr-reviewer)
   - 없음 → module-architect 가 먼저 impl 파일 생성 → build-worker 진입 (3-step)
2. **`commands/impl-loop.md` 후보 경로 (4-agent + module-architect 선두 5-step) 섹션 폐기** — build-worker capability 활용 100%. code-validator 독립 호출 X (build-worker 안 self-validate 로 흡수 — #446 정합).
3. **`commands/impl-loop.md` 자동 폴백 룰 명시** — build-worker 가 진행 중 `SPEC_GAP_FOUND` 던지면 메인이 module-architect 호출 → impl 파일 보강 → build-worker 재시도 (cycle ≤ 2). attempt 한도 초과 시 사용자 위임.
4. **`commands/impl-loop.md` 진행 뷰 단계 수 표기 정정** — sub-step 수 = 2 (impl 있음) / 3 (impl 없음). 옛 후보 경로 5-step 표기 폐기.
5. **`agents/build-worker.md` phase 1 read 의무 톤 다운** — `## 인터페이스 / ## 수용 기준 / ## 핵심 로직 / ## 생성·수정 파일` 4 섹션 강제 → "양식 자유. 어디 건드릴지 + 어떻게 검증할지 박혀있으면 진행, 의문 시 `SPEC_GAP_FOUND`" 자율 판단. 1줄 fix 같은 가벼운 task 에 4 섹션 다 강제하는 빡빡함 제거.

### 왜 바뀌나

본 세션 외부 사용자 케이스 — bugfix 3건 (`docs/bugfix/#N-*.md`) 을 `/impl-loop` 으로 진행했는데 build-worker 가 *능력은 있지만* skill 분기 룰이 정식 양식만 허용해서 4-agent 후보 경로로 강제 분기. build-worker 본인 명세서 (`agents/build-worker.md:25`) 에는 "정식 양식 또는 bugfix 양식 둘 다 받음" 박혀있는데 매니저 (skill) 가 그 능력을 활용 안 함 = 모순.

근본 단순화로 양식별 분기 자체 폐기. 분기 기준 = "impl 파일 있나 없나" 단 하나. build-worker 가 내용 보고 자율 판단하는 구조 (정보 부족 시 `SPEC_GAP_FOUND` → 자동 폴백). `/impl` 단발 호출은 4-agent 모델 유지 (단발은 누적 위기 없음, 엄정성 우선 의도된 티어링).

### 사용자 행동

`/impl-loop` 진입 시 자동 적용. 다음부터 모든 양식 (정식 / bugfix / 자유 형식) 이 build-worker 한 번에 처리 → 메인 토큰 절약 + 사용자 입장 단계 안 쪼개짐.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.2.31 (2026-05-22)

**커밋 범위**: `v0.2.30..v0.2.31`
**핵심 변경**: `/impl` + `/impl-loop` skill prose 에 TaskCreate / TaskUpdate 호출 강제 룰 (`## 강제 사전` 섹션) 박음. 메인 Claude 가 dcness helper `begin-step` 트래킹으로 충분하다 자율 판단해서 TaskCreate skip 하는 회귀 차단.

### 무엇이 바뀌나

1. **`commands/impl-loop.md`** — `## 절차` 직전에 `## 강제 사전 — TaskCreate / TaskUpdate (사용자 가시성, MUST)` 섹션 신설. WHY 명시 (`begin-step` = 내부 트래킹 / TaskCreate = 사용자 UI 가시) + catastrophic 안티패턴 명시 + 호출 시점 4개 (진입 / task 전환 / sub-step 전환 / 완료) 명시.
2. **`commands/impl-loop.md` `## 진행 뷰`** — "진입 시 / task i 진행 중" 두 줄에 **(MUST — §강제 사전 정합)** 라벨 추가 — 자율 영역 인식 차단.
3. **`commands/impl-loop.md` `## 안티패턴`** — "TaskCreate / TaskUpdate skip — begin-step 트래킹으로 충분 자율 판단" catastrophic 1줄 추가.
4. **`commands/impl.md`** — `## 절차` 직전에 동일 `## 강제 사전` 섹션 신설. inner loop 4-step (`test-engineer` / `engineer:IMPL` / `code-validator` / `pr-reviewer`) 에 task list 1개 + sub-step 4개 (fallback 시 5개) 생성 의무 명시.

### 왜 바뀌나

jajang 외부 작업 세션 중 메인 Claude 가 dcness helper `begin-step` / `end-step` 으로 트래킹된다는 이유로 Claude Code 의 TaskCreate 를 자율 skip 하는 회귀 발생. 사용자가 *Claude Code UI* 를 보는데 진행 상태 표시가 없어 "왜 task 안 만들고 셀프로 돌려?" 지적. 두 트래킹은 **다른 layer** — helper = 내부 state 파일 (사용자 UI 불가시), TaskCreate = 사용자 가시. 둘 다 호출 의무. skill prose 가 자연어 룰 중 가장 강한 위치 (메인이 skill 진입 시 반드시 inject) 라 거기 명시적으로 박음.

### 사용자 행동

`/impl` / `/impl-loop` 진입 시 자동 적용 — 메인 Claude 가 진입 직후 TaskCreate 호출 의무. 사용자는 Claude Code UI 에서 task 진행 상태 직접 확인 가능.

### 업데이트

```sh
claude plugin update dcness@dcness
```

---

## v0.2.30 (2026-05-22)

**커밋 범위**: `v0.2.29..v0.2.30`
**핵심 변경**: #457 산출물 양식 단순화 + CLAUDE.md 자기 검열 룰 제거. 메인 Claude 응답 속도 / 자연스러운 대화 톤 회복 + impl.md 에 사용자 review 영역 (What/Why/ADR) 분리 + sub-agent return 산출물 경로 백틱 의무.

### 무엇이 바뀌나

1. **impl.md 양식에 What/Why/ADR 3 섹션 추가** (PR #464) — 사용자가 module-architect 산출물을 보고 *뭘 만들지 / 왜 / 결정 근거* 한눈에 잡을 수 있게 평이한 한국어 서사로 분리. engineer 가 보는 영역 (`Scope` / `인터페이스` / `수용 기준`) 은 효율 양식 그대로. 경량 케이스 (버그픽스 등) 는 What/Why 1~2 줄 압축 + ADR 생략 가능.
2. **4 agent return prose 에 산출물 경로 백틱 의무** (PR #465) — `engineer` / `pr-reviewer` / `code-validator` / `test-engineer` 가 자기 산출물 (impl.md / 코드 / PR / 이슈 / review.md) 경로를 백틱으로 감싼 형태로 박는다. 메인 Claude 가 그대로 사용자 응답에 echo 하므로 사용자가 한 번 클릭으로 도달.
3. **CLAUDE.md §0.4 자기 검열 룰 제거** (PR #462, dcness self) — 외래어 / 영어 명사구 / 줄임말 금지 + 매 turn 자가 검열 + § 표시 강제 룰이 메인 응답 속도 ↓ + 톤 부자연 + *룰 만족 자체에 인지 자원 소모* 의 직접 원인. 사용자 프로필 각인 한 줄로 단순화 (`사용자는 한국어가 가장 익숙한 시니어 엔지니어`).

### 왜 바뀌나

jajang 2026-05-21 product-plan 세션에서 사용자가 며칠 헛수고한 사단이 있었다 — "허밍한 사람 목소리와 음악 합성이 가능한가" 라는 *가능성 확인* 질문을 했는데, 며칠간 Claude 가 한 작업은 "허밍 보컬 어떻게 튜닝할까" 였다. 가능성을 묻는 질문이 어떻게 좁은 디테일 작업으로 바뀌었는지 추적해보니, 사용자가 산출물 본문 (PRD / stories.md / impl/*.md) 을 *읽지 않고 넘긴* 게 핵심 원인.

안 읽은 이유 둘:
- 양식이 어려워 부담 (서사 부재, 데이터 / 약어 폭격)
- 산출물 경로가 클릭 가능 형태로 안 박혀 Finder 로 직접 찾아가야 했음

본 릴리즈는 이 두 마찰을 동시에 줄인다.

### 외부 활성 프로젝트 영향

- **agents/ 변경** (PR #464 / #465) 은 plug-in 본체 → `claude plugin update dcness@dcness` 시 자동 적용
- **CLAUDE.md §0.4 변경** (PR #462) 은 dcness self 작업 지침. 외부 활성 프로젝트의 CLAUDE.md 는 `/init-dcness` 가 만드는 별도 파일이라 자동 변경 X. 외부 프로젝트에서도 같은 결로 정리 원하면 사용자가 자기 CLAUDE.md 의 자기 검열 섹션 직접 갱신 (각인 한 줄로 단순화 권장)

### 보류 항목

- **처방 2-(2) 메인 출력 훅 강제** — sub-agent 거치지 않고 메인이 직접 가공한 정보 (이슈 # / PR # / 파일 경로) 의 백틱 강제. 위험도 / 오탐 평가 더 필요. PR #465 (처방 2-(1)) 만으로 실효 부족 시 별 이슈로 재진입.
- **메인 대화 톤 감사** (별 트랙) — 메인 응답 *대화 톤 자체* 도 정보 나열 방향으로 기울어진 부작용. 룰 시스템 누적 추정. 룰 추가 자체가 코끼리 함정일 수 있어 신중. 본 릴리즈 PR #462 가 부분 처방.

### #446 Hybrid A 트랙

v0.2.29 (build-worker 가드 + git 통합 스크립트) 적용 후 외부 활성 프로젝트 재측정 미완. 본 릴리즈는 build-worker 본문 직접 변경 없음. 단 return 경로 백틱 의무는 build-worker 도 같은 결 (engineer + pr-reviewer 흡수) 이라 *간접* 적용됨.

### 머지된 PR

- [PR #462](https://github.com/alruminum/dcNess/pull/462) — CLAUDE.md §0.4 자기 검열 룰 제거 (메타 처방)
- [PR #464](https://github.com/alruminum/dcNess/pull/464) — module-architect impl.md What/Why/ADR 3 섹션
- [PR #465](https://github.com/alruminum/dcNess/pull/465) — 4 agent return prose 경로 백틱 의무
- [#457 close + 요약 코멘트](https://github.com/alruminum/dcNess/issues/457)

---

## v0.2.29 (2026-05-21)

**커밋 범위**: `v0.2.28..v0.2.29`
**핵심 변경**: #446 Step 3 1-task 측정 결과 반영 — build-worker prompt 가드 3건 + 메인 git 통합 스크립트. 재측정 진입용.

### 1. 1-task 측정 결과 (#446 Step 3, 외부 활성 프로젝트)

v0.2.28 발행 후 외부 활성 프로젝트에서 1-task 측정 진입. 결과:

- 메인 turn = 121 (기준 ≤ 100 +21 미달)
- 기준선 ~280 turn/task 대비 ~57% 감소 (큰 절감 자체는 인정)
- 사후 보정 ~10 turn 중 ~8 turn = build-worker 의 3 결함 회수 가능
- 권장 보강 적용 시 ~110 turn 예상 (여전히 ≤ 100 미달 가능성)

분석: thinking-only + text-only = 50.7% / Agent 호출 = 3.1% / git+gh 분리 호출 = 13.8%. Hybrid A 가 sub-agent 안 작업 흡수해도 메인 *대화 + 관리* 자체 base load 는 ~80-100 turn.

### 2. build-worker prompt 가드 3건 (PR #458)

`agents/build-worker.md` 에 3 가드 절 신규:

- **§Scope 가드 (MUST)** — impl `## Scope` 의미적 경계 강조. ALLOW_MATRIX 형식적 경계 통과해도 의미 위반은 catastrophic. viability mock / `__DEV__` 분기 / 다른 화면 mock / 종단간 bridge 코드 본 task PR 안 박지 말 것. 필요 시 `IMPLEMENTATION_ESCALATE`
- **§stub / 회피 코드 금지 (MUST)** — TDD GUARD 회피 stub 안티패턴 차단. phase 2 build-impl 의 GREEN 의무 = 진짜 GREEN. 필요해 보이면 `SPEC_GAP_FOUND`
- **§PR body 초안 close-keyword 정확성 (MUST)** — impl frontmatter task_index + 부모 이슈 본문 + invocation prompt 만 source. task_index 매핑 (M/M = Closes / N<M = Part of / epic 마지막 둘 다)

### 3. 메인 git 통합 스크립트 (PR #460)

`scripts/pr-create.sh` 신규 — branch + add + commit + push + gh pr create 통합. 인자: `--branch / --base / --title / --body-file / --commit-msg-file`. 분리 5 호출 → 통합 3 turn (Write × 2 + Bash 1) = ~2 turn 회수.

`commands/impl-loop.md` 절차 §2.iii — 분리 명령 → `scripts/pr-create.sh` 통합 호출 예시. 분리 호출 비권장 명시.

### 4. 재측정 진입

본 릴리즈 적용 후 외부 활성 프로젝트에서 2번째 task 측정:

1. `claude plugin update dcness@dcness` → v0.2.29 적용
2. `/impl-loop <task>` 호출
3. 측정: `python3 scripts/measure_main_turns.py <new-sid>.jsonl`
4. 결과 비교:
   - ≤ 100 turn → 통과 → #446 Step 6 사후 검증
   - 100-150 turn → 본문 기준 재조정 (~150 현실적) + Hybrid A 유지
   - > 150 turn → 후보 경로 (4-agent) 복귀 PR + 단념

### 5. /impl 무변경

`commands/impl.md` 손 안 댐 (#446 엄격 제약). `/impl` 단발 호출 = 4-agent 모델 그대로.

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.29 적용
- 외부 활성 프로젝트에서 2번째 task 측정 진입

---

## v0.2.28 (2026-05-21)

**커밋 범위**: `v0.2.27..v0.2.28`
**핵심 변경**: `/impl-loop` Hybrid A 모드 활성화 — build-worker 2-step 진입점 전환 (#446 Step 4, 측정 진입용).

### 1. Hybrid A 활성화 (#446 Step 4, PR #455)

v0.2.27 까지 spec docs (agents/build-worker.md + docs/plugin/{handoff-matrix,orchestration,loop-procedure}.md) 머지된 채 진입점 보류 상태였던 Hybrid A 를 `commands/impl-loop.md` 진입점 활성화로 실측 진입:

- **§절차** — 4-agent 시퀀스 → Hybrid A 5 단계 재작성: ① 진입 직전 1회 확인 → ② begin-run + build-worker step (Agent 호출) → ③ git/PR 생성 (메인) → ④ pr-reviewer step + 머지 (`scripts/pr-finalize.sh` 호출) → ⑤ end-run + 5줄 요약 출력
- **§진행 뷰** — sub-step 4건 → 2건 (build-worker / pr-reviewer). 후보 경로 (정식 위치 impl 부재 시) sub-step 5건 (module-architect + 4-agent)
- **§review 출력 재정의 5줄 요약** — Hybrid A 기본 형식 (build-worker · pr-reviewer). 후보 경로 4-agent 형식 별도 1줄
- **§git 권한** — engineer / build-worker / test-engineer 등 sub-agent git/PR 호출 금지 명시. worker 는 PR 본문 + commit message 초안만 prose return
- **§안티패턴** — build-worker 항목 3건 추가 (phase prose 자체 Write 확인 / sub-sub 호출 금지)

### 2. 실측 진입 — 사용자 협력 측정

본 릴리즈가 #446 Step 3 통과 기준 (메인 turn ≤ 100, 엄정성 유지) 의 실측 진입용. 사용자가 자기 활성 프로젝트에서:

1. `/impl-loop <task-path>` 1회 호출 → build-worker 자동 진입 → 새 세션 JSONL 생성
2. `python3 scripts/measure_main_turns.py ~/.claude/projects/<encoded>/<sid>.jsonl` 측정
3. 결과 비교:
   - 기준선 ~280 turn/task (jajang 옛 세션, scripts/measure_main_turns.py 정확 재현 검증)
   - 통과 기준 ≤ 100 turn (목표 ~30)
4. 결과에 따라:
   - 통과 → 그대로 유지 → #446 Step 6 사후 검증 (2-3 task 추가 측정)
   - 미달 → 후보 경로 (4-agent) 로 복귀 PR + 0.2.29 hotfix + #446 Step 4-5 단념

### 3. /impl 무변경

`commands/impl.md` 손 안 댐 (#446 엄격 제약). `/impl` 단발 호출 = 4-agent 모델 그대로 (엄정성 우선 의도된 티어링).

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.28 적용
- 사용자 활성 프로젝트에서 `/impl-loop` 호출 시 build-worker 자동 진입. 측정 후 결과 보고

---

## v0.2.27 (2026-05-20)

**커밋 범위**: `v0.2.26..v0.2.27`
**핵심 변경**: `/impl-loop` 메인 컨텍스트 누적 감축 — 저비용 개선 (#446 Step 1) + 측정 자동화 도구. Hybrid A 설계 (#446 Step 2) 머지되었으나 본 릴리즈 한정 *활성화 보류* (실측 미완).

### 1. 저비용 개선 — agent 5종 return 가이드 구체화 + impl-loop review 출력 재정의 (#446 Step 1, PR #447)

jajang 실측 기준선 ~280 turn/task 의 post-Agent 누적 주범 = review.md 원본 그대로 출력 + agent 본문 장황한 서술. 두 갈래로 즉시 절감:

- **agent 5종 return 가이드 구체화** — `agents/{test-engineer,engineer,code-validator,pr-reviewer,module-architect}.md` 의 기존 generic return-terseness (#440) 옆에 산출물 구조별 *구체화* 단락 추가
  - test-engineer: 테스트 케이스 표 전수 입력 금지 (케이스 수 + 카테고리 + RED/GREEN + SPEC_GAP 만)
  - engineer: 파일별 변경 서술 → `M files +X -Y` 통계 + 의도 1-2 문장
  - code-validator: A/B/C 통과 항목 열거 금지 ("A/B/C 통과" 1줄)
  - pr-reviewer: A~F 체크리스트 본문 재진술 금지 (카테고리 라벨 + (파일:라인) + 1-2 문장)
  - module-architect: impl 본문 재진술 금지 (섹션 라벨 + 의도)
  - 공통: 워크트리 절대경로 반복 echo 금지
- **`commands/impl-loop.md` driver 범위 review 출력 재정의** — 원본 review.md 는 디스크 (`<run_dir>/review.md`) 그대로, 메인 컨텍스트는 5줄 요약 (task 결론 / agent 결과 / finding / PR·이슈 / next)
- `/impl` 단발 호출은 review.md 원본 그대로 출력 MUST 유지 — 엄정성 우선 (`commands/impl.md` 무변경)

### 2. 측정 스크립트 — scripts/measure_main_turns.py (PR #449)

Claude Code 세션 JSONL 파싱 → 메인 assistant turn 분포 (tool / text-only / thinking-only) + tool histogram + Agent 호출 분포 출력. Python 표준 라이브러리만, text/JSON 출력 + 디렉토리 일괄. #446 본문 기준선 (8af5fb4d=203 / 1518caa0=349) 정확 재현 검증. Step 3 프로토타입 통과 기준 + Step 6 사후 검증에 재사용.

### 3. Hybrid A 설계 — build-worker + 2-step (#446 Step 2, PR #448) — *본 릴리즈 한정 활성화 보류*

`/impl-loop` 메인 turn ~85-90% 감축 목적의 Hybrid A 모드 설계 완료:
- `agents/build-worker.md` 신규 — `/impl-loop` 한정 통합 worker (test + impl + self-validate 3 phase, helper Bash self-call, TDD GUARD 정합, git/PR/pr-reviewer 호출 메인 위임)
- `docs/plugin/{handoff-matrix,orchestration,loop-procedure}.md` 동기 (§4.3 진입 모드 3분기 / §4.8 Hybrid A 모드 / §3.2.1 worker phase prose 자체 Write)

**본 릴리즈 한정 활성화 보류 — `commands/impl-loop.md` 의 `/impl-loop` 진입점은 4-agent 시퀀스 유지**. 이유 = #446 Step 3 프로토타입 (jajang 1-task 실측 통과 기준) 미완. 실측 검증 후 별 PR 로 활성화. spec 은 머지된 채 (활성화 대기). 자세히 = `commands/impl-loop.md` §"Hybrid A 모드 (활성화 대기, #446)" (당시 기준 — 현 `skills/impl-loop/SKILL.md` 로 통합).

### 4. #345 흡수 권고

[#345](https://github.com/alruminum/dcNess/issues/345) (`/impl-loop` 메인 컨텍스트 누적 — task별 새 프로세스 driver 필요) 코멘트 박음 — 새 프로세스 제안은 6/15 Agent SDK 과금 분리로 폐기 (#438 정합), 본질 문제는 #446 트랙이 한 세션 안에서 Hybrid A 로 흡수. close 권고.

### 5. /impl 무변경 보장

전 릴리즈에서 `commands/impl.md` 손 안 댐 (#446 엄격 제약). `/impl` 단발 호출 = 4-agent 모델 그대로 (엄정성 우선 의도된 티어링).

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.27 적용
- 저비용 개선 + 측정 스크립트 즉시 효과. Hybrid A 활성화 = Step 3 통과 기준 충족 후 별 PR (예상 v0.2.28+)

---

## v0.2.26 (2026-05-19)

**커밋 범위**: `v0.2.25..v0.2.26`
**핵심 변경**: `/impl-loop` run 격리 복원 + 사람 친화 진행 뷰 (#443)

### 1. run 격리 복원 (#443 작업 1)

v0.2.25 의 in-session `/impl-loop` 이 모든 task 를 한 run 에 묶어 `run_review` 가 거대 review.md 1개를 내던 결함 수정. (`run_review` 는 run 단위 `--run-id` 동작 — 헤드리스 시절엔 task=자식세션=run 이라 자연 격리됐던 것이 in-session 복귀 시 옛 `b<i>.` 한-run 모델 잔재를 베껴 깨졌음.)

- `commands/impl-loop.md` — 각 task = 독립 `begin-run impl` … `end-run` run. **N task = N run = N run dir = N review.md** (task별 로그·`/run-review` 격리)
- `loop-procedure.md` §1.2 / §2 / §3.1 + `orchestration.md §4.8` — 옛 `b<i>.` 한-run 모델 잔재 정리
- `/impl-loop` 은 자기 run 이 없는 `impl-task-loop × N` driver — `orchestration.md §4.1` 카탈로그 정설 정합

### 2. 사람 친화 진행 뷰 (#443 작업 2)

`commands/impl-loop.md` `## 진행 뷰` 섹션 신규 — task 리스트가 주욱 펼쳐져 현재 페이즈 식별이 어렵던 문제 해소:

- 완료 task 는 한 줄 / 현재 task 만 sub-step 을 `ㄴ` 들여쓰기로 펼침 / 예정 task 는 대기 줄
- Task 시스템 = 평탄 리스트 (부모/자식 필드 X) + 생성순 표시 (샘플 task 렌더 실측 검증) → 중간삽입 불가 우회로 task 전환마다 [현재 헤더 + sub-step + 남은 헤더] rebuild

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.26 적용

---

## v0.2.25 (2026-05-19)

**커밋 범위**: `v0.2.24..v0.2.25`
**핵심 변경**: `/impl-loop`·`/impl` 헤드리스 (`claude -p`) 폐기 → 메인 in-session 오케스트레이터 복귀 (#438 + #440)

### 배경 — Anthropic Agent SDK 과금 변경

2026-06-15 부터 구독 플랜의 `claude -p` / Claude Agent SDK / GitHub Actions 사용량이 별도 "Agent SDK 크레딧" 풀로 분리 + full API rate 과금 (Pro $20 / Max 5x $100 / Max 20x $200, per-user, 미사용분 cycle 말 소멸). dcness 헤드리스 자식 세션 spawn 이 정확히 이 풀에 진입 → 구독 사용자 비용 폭증.

공식: https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan

### 1. 헤드리스 경로 완전 폐기 (#438, PR #439)

- `scripts/impl_loop_headless.py` (563줄) + `tests/test_impl_loop_headless.py` (478줄) 삭제
- `commands/impl-loop.md` 재작성 — `claude -p` 자식 spawn 제거, 메인 in-session per-task 오케스트레이션 복원. `orchestration.md §4.8` 의 `impl-task-loop × N` 모델이 이미 in-session 이라 헤드리스는 그 위 얇은 override 층이었음
- `commands/impl.md` — `## 헤드리스 실행 옵션 (#422)` 섹션 삭제
- 보존: 워크트리 1회 + base-ref(#424) / Pre-flight gate / 진입 직전 1회 확인(#346) / 1 task = 1 PR / 4-step 모두 호출 MUST(#431)
- 신규: false-clean 차단(메인 직접 확인) + compaction 복구 절 (루프 상태 = conveyor state 파일 SSOT)
- in-session = 구독 interactive 한도 — Agent SDK 크레딧 풀 미진입

### 2. impl-loop agent return 간결성 규율 (#440, PR #441)

- impl-task-loop 5 agent (engineer / test-engineer / code-validator / pr-reviewer / module-architect) "결론 + 권장 다음 단계" 섹션에 return 간결성 가이드 1블록 추가
- return prose = 결론 + 핵심 변경·발견 + 권장 다음 단계만. 과정 narration / 계획 재진술 / 파일별 장황한 설명 제거. 결론 근거 substance (실측 명령·수치 / 발견 항목 / 미완 작업)는 유지
- 형식 강제(라인 cap) 아닌 내용 선택 가이드 — prose-only 철학 정합
- in-session 복귀로 매 task return 이 메인 컨텍스트에 누적 → 큰 epic(15~30 task) 대비 잔여분 감축

### 업데이트

- `claude plugin update dcness@dcness` 한 번 → v0.2.25 적용

## v0.2.24 (2026-05-14)

**커밋 범위**: `v0.2.23..v0.2.24`
**핵심 변경**: 헤드리스 자식 stream-json 파서 — 사람 친화 progress view (#431 follow-up → PR #434)

### 1. 자식 spawn `--output-format stream-json --verbose` 전환

`scripts/impl_loop_headless.py:spawn_child`:
- 옛 `--output-format text` (raw line stream = verbose noise) → `stream-json --verbose` 로 교체
- `format_progress_event(ev)` 신규 — JSON event → 사람 친화 1 line per marker:
  - `tool_use.name == "Task"` → `  ㄴ <subagent_type> — <description>`
  - `tool_use.name == "Bash"` + conveyor 키워드 (begin-run/begin-step/end-step/end-run) → `  ㄴ <cmd>`
  - `type == "result"` → `  [result] <첫 줄>`
  - 그 외 도구 (Edit/Read/Glob 등) 는 skip — noise 차단
- `extract_event_text(ev)` 신규 — parse_result + 4-step keyword 검사용 text 추출

배경 (사용자 시연): jajang epic 19 헤드리스 진행 시 외부 progress (`Running... 11m 42s · ↓ 8.8k tokens`) 만 보이고 자식 sub-agent 흐름 안 보임. v0.2.23 의 `[child] <raw line>` stream 은 verbose noise 가 너무 많음. 사용자가 원한 형태:
```
xxxxx task
  ㄴ test-engineer — 테스트 작성중
  ㄴ engineer — 구현중
  ㄴ code-validator — 검증중
  ㄴ pr-reviewer — 리뷰중
```

stream-json + JSON 파서 + filter 후 1 line per marker 박으면 CC Bash foreground 의 ⎿ 들여쓰기에 자식 진행 자연 표시.

### 2. `commands/impl-loop.md` / `commands/impl.md` §절차 갱신

- stream-json + 사람 친화 progress 동작 명시
- Bash background + Monitor 패턴 폐기 (Monitor notification 이 메인 Claude 해석 layer 거쳐 효과 X)
- Bash foreground 호출 시 CC UI ⎿ 자연 표시 명시

### 사용자 업데이트 가이드

```sh
claude plugin update dcness@dcness
```

---

## v0.2.23 (2026-05-14)

**커밋 범위**: `v0.2.22..v0.2.23`
**핵심 변경**: 헤드리스 자식 실시간 가시화 + conveyor + inner 4-step 안전망 (#430 + #432)

### 1. 헤드리스 자식 stdout 실시간 line stream (#422 follow-up → PR #430)

`scripts/impl_loop_headless.py:spawn_child()`:
- `subprocess.run(capture_output=True)` → `subprocess.Popen + threading drain` 으로 교체 (line-buffered stream)
- 자식 line 마다 `[child] <line>` / `[child:err] <line>` 접두 박아 stream_to (default sys.stderr) 로 즉시 echo

`commands/impl-loop.md` / `commands/impl.md` 절차 — Bash tool `run_in_background=true` + Monitor stream MUST 명시.

배경: 메인 세션 헤드리스 진행 시 외부 progress (`11m 42s · ↓ 8.8k tokens`) 만 보이고 자식 sub-agent 흐름 안 보임 → 자식 line stream + Monitor 로 인터랙티브 `/impl` 과 동일 가시화.

### 2. 헤드리스 자식 conveyor + inner 4-step 안전망 (#431 → PR #432)

`scripts/impl_loop_headless.py:build_invocation`:
- `--append-system-prompt` 에 의무 4 항목 inject (commands/impl.md 본문보다 우선):
  1. 진입 즉시 begin-run 호출
  2. inner 4-step 모두 호출 (test-engineer → engineer → code-validator → pr-reviewer)
  3. PR merge 직후 end-run 호출
  4. 종료 prose enum (PASS/FAIL/ESCALATE)

`scripts/impl_loop_headless.py:process_task`:
- 자식 stdout 에 `code-validator` / `pr-reviewer` 흔적 부재 시 → blocked 강등 (parent text fragility 검사)

`commands/impl.md` §Inner loop 4-step 모두 호출 (MUST) 섹션 신규.

배경: jajang epic 19 task 06 자식이 test-engineer + engineer 만 호출하고 commit/push/PR 안 만들고 PASS 박고 종료 → headless parent false-clean 판정 → 메인 수동 수습. 자식 cost \$15~20/1회 실측인데 dcness-review 에 \$0 표시 = 측정 거버넌스 catastrophic 결함.

결함 1 (`dcness-review --latest` 가 자식 run 못 찾음) 은 결함 2 (자식 begin-run 미호출 → `.steps.jsonl` 부재) fix 로 자동 해소.

### 사용자 업데이트 가이드

```sh
claude plugin update dcness@dcness
```

---

## v0.2.22 (2026-05-14)

**커밋 범위**: `v0.2.21..v0.2.22`
**핵심 변경**: jajang Epic 19 followup 4 묶음 — 헤드리스 자식 정합 + TDD GUARD entry-file + worktree base-ref

### 1. impl-loop 자식 conveyor cycle 안전망 (#422 → PR #425)

`scripts/impl_loop_headless.py`:
- `[E]` 자연어 단락에 명시 `begin-run impl / begin-step / end-step / end-run` 호출 박음 (옛 indirect chain 위임 → silent-fail 회귀 차단)
- `process_task()`: `confirm_issue_closed is False` → `clean → blocked` 강등 (false-clean 안전망). 이슈 번호 부재 시 cwd `git status --porcelain` fallback 검사

배경: jajang Epic 19 NS2 자식이 사용자 위임 자연어 + enum 누락 + exit 0 종료 시 헤드리스 parent 가 `ALL CLEAN` 잘못 보고. `.steps.jsonl` 미작성 → `/run-review` 사후 분석 불가.

### 2. 헤드리스 자식 슬래시 직호출 리팩토링 (#422 follow-up → PR #426)

`scripts/impl_loop_headless.py`:
- 자식 prompt = `/dcness:impl <task-path>` 슬래시 직호출로 단순화 (chain 깊이 3 → 0)
- retry context → `--append-system-prompt` 로 inject
- 옛 `build_command()` ([A]~[E] 5 묶음 자연어) → `build_invocation()` 으로 폐기

`commands/impl.md`:
- §사전 read 의무 5번 항목 추가 (같은 epic 형제 머지 PR 환기)
- §헤드리스 실행 옵션 추가 — 단발 task 도 사용자 발화 `헤드리스|headless` 매치 시 헤드리스로 위임

배경: 자식이 슬래시 호출 받으면 `commands/impl.md` 본문이 system-reminder 로 자동 inject → 인터랙티브 `/impl` 과 동일 정확도. `.steps.jsonl` 정상 작성 → `/run-review` 가능.

### 3. TDD GUARD entry-file false-positive 해소 (#423 → PR #427)

`hooks/tdd-guard.sh`:
- entry-file path heuristic 추가: `App.{ts,tsx,js,jsx}` / `_layout.{ts,tsx,js,jsx}` / `apps/*/index.{ts,tsx,js,jsx}` / `src/main.{ts,tsx,js,jsx}`
- 파일 내용 시그니처 grep 추가: `registerRootComponent\(` / `AppRegistry\.registerComponent\(` (Edit 케이스 cover)

배경: Expo `apps/mobile/index.js` / RN `App.tsx` / expo-router `_layout.tsx` 가 boilerplate (비즈니스 로직 X) 인데 TDD GUARD 가 차단. engineer agent 의 빈 stub 회피 안티패턴 강화 위험.

회귀 방지: 일반 비즈니스 로직 (`src/business-logic.ts`) + 테스트 부재 → 여전히 deny.

### 4. outer worktree base-ref 분기 SSOT (#424 → PR #428)

`docs/plugin/loop-procedure.md` §1.1.1 신규:
- `**Base Branch:**` 마커 매치 시 outer worktree base 도 integration branch 정합 (`git worktree add -b <new> <path> origin/<integration>` + `EnterWorktree(path=)` 우회 패턴)
- §1.1 의 "수동 git worktree add 우회 금지" 룰에 §1.1.1 예외 명시

`commands/impl-loop.md` / `commands/impl.md` / `commands/architect-loop.md` §워크트리 섹션 + §1.1.1 참조 1줄 추가. `commands/architect-loop.md:57` 모호 표현 (`동일 base 에서 따야 함`) 구체화.

배경: jajang Epic 19 ADR-19E 통합 브랜치 패턴에서 outer worktree (origin/main 기반) vs sub-PR base (`feature/local-dsp`) mismatch → sub-PR diff 거대화 ("삭제 변경" false). 사용자 자율 회피 + 자식 자체 sub-worktree 패턴으로 NS1/NS2 머지 성공 — 룰 부재 우회 사례.

### 사용자 업데이트 가이드

```sh
claude plugin update dcness@dcness
```

---

## v0.2.21 (2026-05-13)

**커밋 범위**: `v0.2.20..v0.2.21`
**핵심 변경**: 통합 브랜치 패턴 지원 — git-naming + product-plan + scripts auto-detect (#413 + #414)

### 1. git-naming regex 완화 (#413)

`scripts/check_git_naming.mjs`:
- BRANCH_RE 에 `feature/<desc>` 패턴 추가 (자유 feature / 통합 브랜치 — 예: `feature/local_dsp`)
- 4 패턴 통일 기본 제약: 소문자 + `[a-z0-9_-]` + 최소 3자
- TITLE_RE 에 `[epic{N}]` (epic-only, 통합 → main 머지) + `[feature]` (자유 feature) 추가

`docs/plugin/git-naming-spec.md` §1 / §2 / §4 / §6 표 갱신 + base 분기 룰 명시.

배경: jajang Epic 19 (#262) 통합 브랜치 `feature/local-dsp` push 시 hook 차단 → `--no-verify` 우회. 본 release 로 차단 해소.

### 2. 통합 브랜치 모드 (`commands/product-plan.md`) (#414 problem A)

- §Step 6.5 신설 — 메인 → 사용자 그릴 (a) 일반 / (b) 통합 브랜치
- §Step 7 (a) trunk / (b) integration 분기
- (b) 흐름: `stories.md` 상단 `**Base Branch:** feature/<slug>` 마커 + 통합 브랜치 생성 + PRD sub-PR (`docs/<slug>_prd` from `feature/<slug>`)

mode 코드 분기 도입 X — 자연어 마커만으로 분기 (메인 Claude 의 stories.md grep 인식).

### 3. scripts/create_epic_story_issues.sh 헤더 양식 auto-detect + 마커 미러링 (#414 problem B)

- 헤더 양식 auto-detect: `## Epic — ...` (h2+h3, product-plan 양식) / `# Epic NN — ...` (h1+h2, jajang 양식)
- `**Base Branch:**` 마커 자동 epic issue body 미러링

배경: jajang stories.md (h1+h2) parse 실패 → 메인이 4 직접 호출로 우회. 본 release 로 양식 통일 흡수.

### 4. commands × 3 base 분기 체크리스트

`commands/impl.md` / `commands/impl-loop.md` / `commands/architect-loop.md` 의 PR 생성 직전 절차에 stories.md `**Base Branch:**` grep → `--base` 박는 룰 1줄 추가.

### 5. docs/plugin/issue-lifecycle.md §1.4 명문화

통합 브랜치 케이스 — base ≠ main sub-PR 의 GitHub auto-close 한계 + 마지막 통합 → main 머지 PR body 에 bulk close (`Closes #<story1...N>` + `Closes #<epic>`) 패턴 명문화. GitHub default branch 제약 (linking-a-pull-request-to-an-issue) 인용.

### 사용자 업데이트 가이드

```sh
claude plugin update dcness@dcness
```

문제 발생 시:
```sh
claude plugin uninstall dcness@dcness && claude plugin install dcness@dcness
```

업데이트 후 `feature/<desc>` 같은 자유 슬러그 브랜치명 + `[feature] / [epic{N}]` PR 제목 형식이 즉시 통과한다.

---

## v0.2.20 (2026-05-13)

**커밋 범위**: `v0.2.19..v0.2.20`
**핵심 변경**: `_summarize_input` cwd 기준 relative path 단축 (#408)

### v0.2.19 실증 결과 (본 세션 dcness self repo)

#401 (skill 진입 docs 통째 read 폐기) 처방 효과 강력 확인:
- 이전 (처방 전 jajang): `orchestration.md` 24.7k + `loop-procedure.md` 17.8k *통째 read*
- 현재 (처방 후 본 세션): `docs/plugin/*` 6회 모두 *부분 read* (max 1.5k chars). 통째 read 0회.
- → 메인이 lazy read 가이드 정합 행동 채택. 처방 작동.

cache_read 추이 (본 세션 967 turns):
- 초반 14k → 중반 497k → 후반 172k (감소)
- 메인 행동에 따라 cumulative cache_read 가 ↓ 가능 — cost-aware 의 효과 정합.

### path 단축 hotfix (PR #409, #408)

`harness/hooks.py:_summarize_input` 의 file_path/path 영역에 cwd 기준 relative 단축:

이전:
```
같은 input 반복: /Users/dc.kim/project/jajang/.claude/worktrees/impl-issue259/src/foo.ts ×3
```

후:
```
같은 input 반복: src/foo.ts ×3
```

- `_shorten_path` 함수 신규
- `_summarize_input` Read/Edit/Write/NotebookEdit 의 file_path/path 영역만 적용
- Bash command 는 단축 X (command 전체 의미 보존)
- cwd 외부 path 는 그대로 (절대 path 보존)

효과: ~6k chars / 세션 cache_read 감축 (~1.5k tok). 의미 손실 X.

### 테스트
- 6 신규 (`tests.test_hooks.ShortenPathTests`)
- 410 / 410 tests PASS

### 활성 사용자 권장
- `claude plugin update` 한 번 → v0.2.20 적용
- v0.2.19 까지 미적용 사용자는 한 번 update 로 #400 + #402 + #404 + #408 누적 처방 모두 받음

---

## v0.2.19 (2026-05-13)

**커밋 범위**: `v0.2.18..v0.2.19`
**핵심 변경**: cost / cache_read leak 감축 3종 처방 누적 (#400 / #402 / #404)

### 배경 — cost 분석

세션 분석 결과 (jajang 1106 events / dcness self 4989 events):
- 후반 turn cache_read 평균 267k~507k (초반 32k~57k 의 4.7~16배)
- cache hit 95% 인데도 cost 폭증 ($15~71 / run) = **컨텍스트 양** 자체가 본질
- 메인 turn cost 비중 98% (sub-agent 격리는 잘 작동 중)

### skill 진입 docs 통째 read 폐기 (PR #401, #400)

5 commands 의 "사전 read (skill 진입 즉시)" 룰 → "lazy — 필요시만":

- 이전: `docs/plugin/loop-procedure.md` + `orchestration.md` + `handoff-matrix.md` + `issue-lifecycle.md` read 후 진행 (~65.9k chars / ~16.5k tok 통째 read)
- 후: 본 skill 본문 + 인용된 §번호 만으로 진행. 룰 모호 / 분기 발생 시에만 grep + offset/limit 부분 read.
- 영향: `architect-loop.md` / `impl-loop.md` / `impl.md` / `issue-report.md` / `product-plan.md`
- 효과: skill 진입 시 메인 cache_read baseline 약 16.5k tok 한 번에 절감.

### SessionStart inject 다이어트 + cost-aware 가이드 (PR #403, #402)

`hooks/session-start.sh` 의 inject 본문 1425 → 1106 chars (-22%):

- 각 섹션 제목 단축 / verbose 부분 축약
- **cost-aware 행동 룰 1줄 신규**:
  > 큰 plan/docs 통째 read 회피 → grep + offset/limit. Bash output 길면 `| head` 잘라내기. sub-agent 위임 우선 (메인 직접 도구 ↓ → 메인 cache_read 누적 ↓)
- 직접: 매 turn cache_read ~-80 tok / 세션 turn 수만큼 누적 감축
- 간접: 메인이 cost-aware 행동 채택 → 큰 도구 결과 누적 회피 → cumulative cache_read 더 큰 감소

### hook 정상 통과 시 suppressOutput 시도 (PR #405, #404)

CC 본체 알려진 버그 (`anthropics/claude-code#34859`, `#34713` 등 9+ open) 회피 가설:

- hook exit 0 + 빈 stdout 정석 따라도 transcript 에 `Output truncated (0KB total)` 165자 wrapper attachment 박힘
- 3 PreToolUse hook (`catastrophic-gate.sh` / `file-guard.sh` / `tdd-guard.sh`) 정상 통과 path 에서 `{"suppressOutput": true, ...}` JSON emit
- 차단 path (deny / exit 1) 는 기존 동작 유지
- 실증 필요 — 다음 /impl 1 회 transcript 비교

### 알려진 한계 (Anthropic 영역)

- CC 본체가 모든 도구 호출에 165자 wrapper attachment 박는 패턴 = dcness 비활성 환경에서도 동일
- 회피 = 본체 fix 대기 또는 suppressOutput 시도 (#405)
- dcness 영역 처방 = 메인 행동 가이드 + skill 진입 docs lazy + hook output suppress

### 테스트
- 404 / 404 tests PASS (변경 X)

### 활성 사용자 권장
- `claude plugin update` 한 번 → 다음 세션부터 cost-aware 룰 + lazy docs read 자동 적용
- 사용자 실증: 다음 /impl 1 회 transcript 비교 (특히 attachment leak 감소 여부)

---

## v0.2.18 (2026-05-12)

**커밋 범위**: `v0.2.17..v0.2.18`
**핵심 변경**: review.md 다이어트 + 메인 자율 인사이트 매커니즘 (#392 / #394 / #396)

### review.md 폐기 통합 (PR #393, #392)

dcness 정신 정합 X 패턴 통합 폐기:

- **잘한점 5 패턴 전체 폐기**: ENUM_CLEAN / PROSE_ECHO_OK / DDD_PHASE_A / DEPENDENCY_CAUSAL / EXTERNAL_VERIFIED_PRESENT. jajang 실측 loop-insights 100% PROSE_ECHO_OK baseline 노이즈가 직접 동기.
- **6 정신 위반 waste 패턴 폐기**: ECHO_VIOLATION / PLACEHOLDER_LEAK / EXTERNAL_VERIFIED_MISSING / MISSING_SELF_VERIFY / MAIN_SED_MISDIAGNOSIS / PARTIAL_LOOP. agent 자율 영역 침해 + hardcoded 임계 = sub_eval.py:6~10 정신 위반.
- **redo_log + routing_telemetry 폐기**: jajang "하지 말 것" 0건 + record_cascade 0건 = 매커니즘 죽음.
- **`commands/audit-redo.md` skill 폐기**: redo_log 의존 매커니즘 죽음.
- 약 -800 lines (코드 + 테스트 + docs).

### review.md 측정 noted + 도구 분포 표 (PR #395, #394)

- **TOOL_USE_OVERFLOW + THINKING_LOOP → "측정 noted" 섹션**: severity 폐기, raw 알림. 사용자 요청에 따라 hardcoded 임계 유지하되 "결정" 형식 폐기.
- **도구 사용 분포 표 신규**: `agent-trace.jsonl` 의 PreToolUse pre entry 집계. step 별 윈도우 Read/Write/Edit/Bash/Glob/Grep 카운트. raw 측정 — 임계 X.
- `NoteFinding` dataclass 신규.

### 메인 자율 인사이트 매커니즘 (PR #397, #396)

자동 누적 폐기 후 대체:

- **`$HELPER insight <agent>[-<mode>] "<자연어 한 줄>"` CLI 신규**: 메인 자율 평가.
- **FIFO 10 cap 누적**: agent+mode 별 `.claude/loop-insights/<agent>[-<mode>].md`. 100 run 돌려도 ≤10줄 (200 tokens / agent inject).
- **agent+mode 분리 파일**: `engineer-IMPL.md` / `engineer-POLISH.md` 따로. 다음 run 의 같은 agent+mode begin-step 만 정확 inject.
- **review.md 끝 prompt 임베드**: REVIEW_READY 시 메인 시야 진입 — `## 📝 메인 인사이트 (1줄 자율 평가)`.

### end-run 단일화 (PR #397, #396)

- 옛 2개 명령 (`finalize-run --expected-steps <N> --auto-review` + `end-run`) → 1개 (`end-run`) 단순화.
- end-run 안전망 (`session_state.py:1001`) 이 finalize-run --auto-review 자동 발사.
- `commands/impl.md` §종료 조건 + `loop-procedure.md` §5.1 명시 갱신.

### 테스트
- 456 → 404 tests (폐기 -58 + 신규 +6)
- jajang run-459cce99 실데이터 검증: 다이어트 후 양식 정상 + 새 매커니즘 정상 작동

### 배경

이번 변경의 *원래 의도* = #321 의 본래 핵심: "단순 룰 정합 표시는 학습 가치 0. dcness self-improvement = 메인 LLM 자율 평가". sub_eval.py:6~10 자율 친화 재설계 (#272 W1) 정신을 review.md / loop-insights 영역까지 확장 적용.

---

## v0.2.17 (2026-05-12)

**커밋 범위**: `v0.2.16..v0.2.17`
**핵심 변경**: agent 다이어트 + 기획·설계 루프 재편 + **SSOT 다이어트 (9→7, 28% 감소)**

### 폐기된 agent (4)

- `security-reviewer` (PR #348) — `pr-reviewer §F-Security` + architect 위협 모델 가정·invariant 흡수
- `design-critic` (PR #351) — designer 1 시안 + 사용자 직접 PICK
- `product-planner` (PR #352) — 메인 Claude 가 사용자와 *직접 그릴미 대화* 로 PRD/stories.md 작성. 외부 검증은 `plan-reviewer` (잔존)
- (옛 단일 `architect` agent — 이미 system-architect / module-architect 로 분리 완료)

agent 13 → 9.

### stories.md 양식 단순화 + impl 파일 7 원칙 (PR #355)

- stories.md = user story (`As a / I want / So that`) 만. 옛 3 섹션 (`대상 화면·컴포넌트` / `동작 명세` / `수용 기준 (Story 단위)`) 폐기
- impl 파일 7 원칙 (Scope / 자기완결성 / 사전 준비 / 시그니처 / AC 실행커맨드 / 주의사항 / 네이밍)
- impl 파일 진입 prompt 의무 (architecture.md + adr.md + 의존 PR read)
- ADR 룰 + architecture.md 비대화 방지 (300줄 cap)

### `feature-build-loop` 폐기 + `/architect-loop` 신설 (본 PR — PR3-B)

- 옛 `feature-build-loop` (Step 2~6.N 통째 commit X 후 첫 task PR commit3 에 누적) → `/product-plan` (Step 2~3, PRD+stories PR1) + `/architect-loop` (Step 4~6.N, 설계 PR2) 분리
- `/architect-loop` 진입 = 사용자 명시 호출 (자동 X). 워크트리 ON 자동
- commit 단위: ux-flow → commit1 / architecture.md+adr.md → commit2 / impl/NN-*.md K 개 → commit 3..K+2 / PR 1개 + 머지
- 본 변경 SSOT = `commands/architect-loop.md`, `orchestration.md §3.1.5 / §4.2` (당시 기준 — 현 `skills/design/` + loop-procedure 로 해체)

### `Step 4.5 sync` + `backlog.md` 폐기 (본 PR)

- 옛 룰: engineer IMPL_DONE 후 메인이 stories.md `[x]` 체크 + backlog.md epic `[x]` 체크
- 폐기 사유: 새 stories.md 양식 = task `[ ]` 자체 없음 (user story 만, PR #355) + 진행 추적 SSOT 단일화 (GitHub issue close 시스템 + PR body `Closes`/`Part of` 트레일러)
- impl-task-loop commit3 = src/** **only** (옛 `src/**, stories.md 등` 룰 폐기)

### PR body `Closes` 판정 메커니즘 변경 (본 PR)

- 옛 룰: stories.md 부모 Story 섹션 `[ ]` 카운트 (awk one-liner)
- 새 룰: impl 파일 frontmatter `task_index: <i>/<total>` + `story: <N>` grep
- module-architect 가 frontmatter 박음 (호출자 prompt 의 `task_index` 그대로). epic 마지막 story 판정 = gh API 1 회 호출

### 이슈 등록 자동화 (PR #353)

- `scripts/create_epic_story_issues.sh` 신설 — stories.md parse + epic/story 이슈 생성 + sub-issue API 연결 한 명령
- `/impl` / `/impl-loop` 진입 직전 task 진행 상태 확인 룰 (issue #346 옵션 C — `git log --grep` + plan tail read)

### 마이그레이션 정책

- **활성 프로젝트 (jajang 등) 진행 중 working tree** — 옛 룰 그대로 종료. 신규 epic 만 새 룰 (`/architect-loop`) 적용
- **옛 양식 stories.md (task `[ ]` 박힌)** — 잔재 허용. backfill 강제 X. 새 작성만 새 양식
- **자동 변환 원하는 사용자용** — `scripts/migrate_stories_to_new_format.sh` (report-only, 자동 변환 X)

### Breaking Change 호환 깨짐 알림

다음 sub-agent 직접 호출자 = 깨짐:
- `subagent_type: "dcness:product-planner"` → 메인 Claude 가 사용자와 직접 그릴미 대화 + `plan-reviewer` 외부 검증
- `subagent_type: "dcness:design-critic"` → designer 1 시안 + 사용자 PICK
- `subagent_type: "dcness:security-reviewer"` → `pr-reviewer §F-Security` 흡수

해당 호출자 = `/issue-report` / `/impl` / `/product-plan` / `/architect-loop` skill 진입으로 자동 라우팅.

### `harness/hooks.py` catastrophic gate 단순화 (본 PR)

- §2.3.4 / §2.3.5 = 옛 단일 `architect` agent + mode 시절 잔재. prerequisite 검증은 메인 영역 (architect-loop skill §Pre-flight gate / 전제 조건) 으로 이전 — 코드 강제 폐기
- §2.3.1 / §2.3.3 / §2.3.6~§2.3.8 = 유지
- `_has_plan_ready` 갱신: `module-architect.md` + occurrence (`module-architect-N.md`) 우선, legacy 호환 유지

### 배포 경로 (CLAUDE.md §0.5)

- (1) plug-in 본체 — `commands/architect-loop.md` 신설 + `agents/{module-architect,system-architect,engineer,pr-reviewer,qa}.md` 갱신 + `harness/hooks.py` 갱신
- (2) init-dcness 배포 — `scripts/migrate_stories_to_new_format.sh` (선택 사용)
- (3) SSOT 문서 — `docs/plugin/{orchestration,loop-procedure,issue-lifecycle,handoff-matrix}.md` 갱신

**사용자 적용**:
```sh
claude plugin update dcness@dcness
```

기존 활성 프로젝트의 진행 중 epic 은 옛 룰 그대로 종료. 신규 epic 부터 `/product-plan` → `/architect-loop` → `/impl-loop` 시퀀스 적용.

### SSOT 다이어트 5 PR (#366~#371)

자연어 SSOT 9개 → **7개**, 총 2,388줄 → **1,714줄** (28% 감소). 외부 사용자 시야 5 SSOT (orchestration / loop-procedure / handoff-matrix / hooks / issue-lifecycle).

#### PR-0 (#366) — enum 현행화 잔재 정리
- `agents/architecture-validator.md` `system-architect READY` → `PASS` (3곳)
- `docs/plugin/handoff-matrix.md` §1.4b/§1.9 Note (옛 6 mode / 옛 validator 5 모드 폐기 알림) → 제거
- `docs/plugin/orchestration.md` + `commands/impl.md` 옛 `MODULE_PLAN_READY` 마커 표현 제거

#### PR-1 (#367) — `known-hallucinations.md` 폐기
- 39줄, entry 1건 (jest) — SSOT 별도 파일 ROI △. agent body 의 *공식 docs WebFetch* 가이드가 진본
- 3 agent (code-validator / module-architect / system-architect) cross-ref 제거

#### PR-2 (#368) — `orchestration.md` 다이어트 + 시퀀스 재구성
- 463 → 351줄 (24% 감소)
- §2 시퀀스 재편: §2.1 catastrophic (원칙) / §2.2 기획 mermaid / §2.3 설계 mermaid / §2.4 구현 mermaid
- §3 mini-graph 6개 폐기 (§4 풀스펙 표가 진본). §4.8 direct-impl-loop 폐기 (§4.3 와 100% 동일)
- **§2.3 catastrophic → §2.1** cross-ref 갱신 (코드/테스트/문서 ~25 곳, stderr 메시지 + 테스트 매치 정합)

#### PR-4 (#369) — 작은 SSOT 4개 다이어트
- `hooks.md` (281→239): 미사용 event 압축 / 외부 사용자 영향 반복 단락 폐기 / 우회 표 통합 / 한눈요약 폐기
- `handoff-matrix.md` (225→201): §1.2 번호 정렬 / §1.4 "기술 에픽" 단락 폐기 / §4.3 코드 인용 → link
- `issue-lifecycle.md` (191→181): §1.3.1 sub-issue 절차 압축 / §2.3 1줄 압축
- `design.md` §5.4 작성 스타일 폐기 (글로벌 메모리 중복)

#### PR-3 (#371) — `dcness-rules.md` 폐기 + 슬림 inject + loop-procedure 흡수
- `dcness-rules.md` (263줄) 폐기
- **SessionStart inject**: 263줄 BLOCKING GATE Read 강제 → **~30줄 슬림 본문 직접 inject** (92% 감소)
- 토큰: `[dcness-rules 로드 완료]` → `[dcness 활성 확인]`
- §1 강제 영역 2가지 + 안티패턴 4건 → `CLAUDE.md §0.7` 본문 흡수
- §3 mechanics + 행동지침 (echo 5~12줄 / REDO 분류 / 자가점검 / AMBIGUOUS / step 명명) → `loop-procedure.md §3.1/§3.2` 흡수
- §4 리뷰 출력 + 개선점 코멘트 → `loop-procedure.md §6` 흡수
- 10 agent cross-ref redirect + 코드 SSOT (`agent_boundary.py`, `hooks.py`, etc.) 갱신

### 사용자 영향 — SSOT 다이어트

**외부 활성 프로젝트** (jajang 등):
- 매 세션 SessionStart inject: 263줄 → ~30줄 (**92% 감소**)
- 새 토큰 `[dcness 활성 확인]` (옛 `[dcness-rules 로드 완료]` 대체)
- catastrophic 룰 번호 `§2.3.x` → `§2.1.x` (코드 stderr 메시지 자동)
- agent body cross-ref redirect 완료 — agent 동작 변경 0

**plug-in update 시 자동 적용** — 사용자 수동 작업 0.

---

## v0.2.16 (2026-05-11)

**커밋 범위**: `v0.2.15..(다음 태그)`
**핵심 변경**: TDD 게이트 design pivot — CI 게이트 + commit-msg chain 전체 rollback, PreToolUse tdd-guard 도입

- **이슈 #320 design pivot (PR #339)** — v0.2.10~v0.2.13 의 CI 게이트 (composite
  action) + commit-msg TDD chain 이 monorepo lifecycle hook / pm 다양성 / missing
  test script 등 함정 누적. 사용자 의도 ("구현보다 테스트 먼저") 는 사후 검증
  아니라 *작성 전 차단*. PreToolUse hook 시점 차단으로 전환.
  - **Rollback**:
    - `.github/actions/tdd-gate/action.yml` 삭제
    - `scripts/check_tdd_staged.mjs` 삭제
    - `scripts/hooks/commit-msg` TDD chain 제거 (git-naming 만 남김)
    - `commands/init-dcness.md` Step 2.9 (CI 게이트) + Step 2.10 (commit-msg TDD) 제거
    - **유지**: `scripts/pr-finalize.sh` (사용자 명시 의도)
  - **신규**:
    - `hooks/tdd-guard.sh` — PreToolUse[Edit|Write|NotebookEdit] hook
    - `hooks/hooks.json` matcher 등록
    - `commands/init-dcness.md` Step 2.9 (신규 안내문)
  - **영감**: jha0313/codex-live-demo `.codex/hooks/tdd-guard.sh`
  - **동작**: agent 가 src 파일 Edit/Write 시도 시 매칭 test 파일 존재 검사 →
    없으면 deny + 한국어 안내. TS/JS 한정. 자동 skip (설정/타입/Next.js 특수/비-코드)
    풍부. 다른 언어 영향 0.

**차이** (이전 v0.2.13 commit-msg vs 본 PR PreToolUse):

| | v0.2.13 commit-msg | v0.2.16 PreToolUse |
|---|---|---|
| 시점 | commit 직전 | 코드 작성 *직전* |
| 진짜 TDD | △ 사후 검증 | ✅ 작성 전 차단 |
| 실행 | O test 실행 | ❌ 존재만 |
| 함정 | jajang 사단 (lifecycle / pm) | 적음 (자동 skip 풍부) |
| 범위 | 4 언어 | TS/JS |
| 옵트인 | 마커 파일 | 자동 (TS/JS 검출) |

**실증 검증 8 케이스**:
- test 없는 src → DENY
- test 있는 src → PASS
- 설정 / Next.js / .py / test 자체 / empty → silent skip

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `hooks/tdd-guard.sh` + `hooks/hooks.json` plug-in 업데이트 자동
- (2) init-dcness 배포 — Step 2.9 안내문. tdd-guard 사용자 repo cp X (plug-in hook 직접 발화)
- (3) SSOT 문서 — N/A

**한계 (v0.2.16)**:
- TS/JS 한정 — 다른 언어 후속
- *test 실행 X* — 존재만 확인 (실행은 사용자 vitest watch / CI 등 개별)
- agent 가 `Bash` 으로 직접 파일 작성 시 차단 X (단 catastrophic-gate 등 다른 hook 이 잡음)

**사용자 적용**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트 (jajang — 이전 TDD 인프라 정리):
```sh
cd ~/project/jajang
git rm .github/workflows/tdd-gate.yml
git rm -f .dcness/tdd-gate-enabled
git commit -m "..."
```

이후 agent Edit/Write 시 tdd-guard 자동 발화. 사용자 추가 설정 0.

---

## v0.2.15 (2026-05-11)

**커밋 범위**: `v0.2.14..(다음 태그)`
**핵심 변경**: TDD 게이트 polish — `ignore_scripts` input + `pr-finalize.sh` 한 명령 머지

- **이슈 #320 jajang prepare hook self-block (PR #336)** — composite action 에
  `ignore_scripts` input 추가. monorepo workspace `"prepare": "npm run build"`
  같은 hook 이 root `npm ci` 시 발화 → 빌드 실패 → tdd-gate self-block 회피.
  - `with: { ignore_scripts: true }` 옵트인 시 `--ignore-scripts` flag 적용
  - pnpm / yarn / bun / npm 모두 지원
  - 디폴트 false (기존 행동 유지)
  - thin yml 템플릿에 `fetch-depth: 0` + 옵트인 주석 추가

- **이슈 #320 pr-finalize helper (PR #337)** — 머지 절차 5 명령 → 1 명령.
  사용자 피드백 "머지되면 main 으로 다시 되돌아가고 pull 까지 했으면" 대응.
  - `scripts/pr-finalize.sh` 신규
  - 흐름: gh pr merge --auto → gh pr checks --watch → auto-merge 완료 대기 → checkout main + pull
  - argument 없으면 current branch 의 open PR 자동 검출
  - working tree dirty 시 사용자 확인 후 sync skip
  - CI FAIL / 머지 안 됨 시 exit 1 + 안내
  - `git-naming-spec.md §6` + `CLAUDE.md §5` 머지 절차 갱신 — 1 명령으로 통합

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `.github/actions/tdd-gate/action.yml` + `scripts/pr-finalize.sh`
- (2) init-dcness 배포 — Step 2.9 thin yml 갱신 (옵트인 주석 + fetch-depth)
- (3) SSOT 문서 — `git-naming-spec.md` §6 + `CLAUDE.md` §5

**jajang 즉시 적용**:
```sh
claude plugin update dcness@dcness
/init-dcness   # 새 thin yml 받음
# .github/workflows/tdd-gate.yml 에서 with: ignore_scripts: true 박음 (monorepo prepare hook self-block 회피 시)
bash scripts/pr-finalize.sh   # 머지 + main sync 자동
```

---

## v0.2.14 (2026-05-11)

**커밋 범위**: `v0.2.13..(다음 태그)`
**핵심 변경**: init-dcness Step 2.11 — 인프라 머지 자동화 (사용자 부담 0)

- **이슈 #320 (사용자 피드백) (PR #334)** — `/init-dcness` 가 cp 만 하고 git
  add/commit/PR 사용자 부담. 까먹으면 workflow yml 이 main 미반영 → CI 게이트
  dead code. 본 release 가 자동 commit + PR 까지 끝까지 진행.
  - `commands/init-dcness.md` Step 2.11 신규
  - 변경 파일 검출: `.github/workflows/` + `.dcness/` 명시 path
  - branch 검사: main 일 때만 자동 진행 (사용자 작업 보호)
  - 사용자 동의 (Y/n) 후: branch → stage → commit → push → PR
  - branch 패턴: `docs/dcness_init_{timestamp}` (git-naming-spec 정합)
  - 자동 머지 X — 인프라 PR 은 사용자 검토 후 머지 권장

**jajang 사단 (실측)**:
- 기존: `git-naming-validation.yml` 만 main 등록. `tdd-gate.yml` + `pr-body-validation.yml` working tree 잔존
- 본 release 후 `/init-dcness` 재실행 → Step 2.11 발화 → 자동 PR → 머지하면 모든 workflow 정상

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `commands/init-dcness.md` plug-in 업데이트 자동
- (2) init-dcness 배포 — Step 2.11 신규. 기존 활성 프로젝트는 `/init-dcness` 재실행 시 발화
- (3) SSOT 문서 — N/A

**한계**:
- 사용자가 이미 PR 만든 인프라 변경 있을 때 중복 시도 가능 (메인 Claude 가 사전 `gh pr list --search` 검사 권장)
- `gh` CLI 미설치 환경 → push 까지만 + 사용자 수동 PR 권유

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트:
```sh
/init-dcness   # Step 2.11 발화 — working tree 인프라 변경 검출 시 자동 PR 제안
```

---

## v0.2.13 (2026-05-11)

**커밋 범위**: `v0.2.12..(다음 태그)`
**핵심 변경**: TDD 게이트 phase 4 — pre-commit (commit 단 차단, 자체완결 wall)

- **이슈 #320 #1 phase 4 (PR #332)** — commit-msg hook chain 에 TDD 게이트 추가.
  staged src 변경 = test 변경 함께 + 변경분 test 실행 PASS 강제. branch protection
  의존성 0 → 진짜 자체완결 wall.
  - `scripts/check_tdd_staged.mjs` 신규 — 본체 (옵트인 마커 + skip marker + 분기 + 실행)
  - `scripts/hooks/commit-msg` 갱신 — git-naming 후 TDD 게이트 chain
  - `commands/init-dcness.md` Step 2.10 신규 — 옵트인 + 3-commit 구조 정합 안내
- **옵트인 메커니즘**: `.dcness/tdd-gate-enabled` 마커 파일 활성화 신호. 부재 시 silent pass.
  다른 프로젝트 영향 0 (외부 활성화 프로젝트가 옵트인 안 한 경우 자동 발화 X).
- **skip marker**: commit message 안 `[skip-test: <사유>]` 매치 시 우회 — 단순 typo /
  문서 변경 / refactor 무영향 케이스 정당 우회.
- **변경분만 실행**: test-engineer 작성 task 용 test (5~15개) 만 실행 = 수초. 풀
  스위트 아님.
- **4 언어 자동 검출**: jest / vitest (deps 검사) / pytest / cargo test / go test.

**3-commit 구조 정합** (loop-procedure §3.4):

| commit | stage | TDD 게이트 |
|---|---|---|
| commit1 (docs) | `docs/impl/NN.md` | PASS (src 0) |
| commit2 (tests) | `src/__tests__/**` | PASS (test 만) |
| commit3 (src) | `src/**` + stories.md | PASS (branch diff test 인지) |
| 위반: src 만 | `src/bar.ts` | BLOCK |

**6 케이스 실측 검증** 완료 (PR #332 body 참조).

**layered defense 완성**:

| 단 | 어디서 | dcness 도입 |
|---|---|---|
| 1 | **commit 단** (commit-msg hook) | **v0.2.13 phase 4 ← 본 release** |
| 2 | CI workflow (affected) | v0.2.12 phase 3 |
| 3 | Branch Protection | 사용자 수동 (안내문) |

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `scripts/check_tdd_staged.mjs` + `scripts/hooks/commit-msg`
  chain — plug-in 업데이트 자동 반영
- (2) init-dcness 배포 — Step 2.10 신규. 기존 활성 프로젝트는 `/init-dcness` 재실행
  시 발화. commit-msg shim 은 이미 chain 로직 박혀있어 사용자가 옵트인 마커만 작성하면
  즉시 동작.
- (3) SSOT 문서 — N/A

**한계 (phase 4)**:
- node test runner: jest / vitest 자동. 그 외 (mocha / ava 등) → `npm test` 폴백
- rust: 단순화 — `cargo test` 풀 폴백 (변경 test 파일만 native 한계)
- python: pytest 만 (unittest 만 쓰는 프로젝트면 `[skip-test]` 우회)
- `--watch` 룰 (git-naming-spec §6) 그대로 — commit 단 차단으로 CI 우회 위험 ↓
  단 룰 완화는 별도 결정

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트:
```sh
/init-dcness   # Step 2.10 발화 — 옵트인 (Y) 시 .dcness/tdd-gate-enabled 마커 작성
git add .dcness/tdd-gate-enabled  # 팀 공유
```

---

## v0.2.12 (2026-05-11)

**커밋 범위**: `v0.2.11..(다음 태그)`
**핵심 변경**: TDD 게이트 phase 3 — affected detection 자동 (CI 병목 해소, 사용자 설정 0)

- **이슈 #320 #1 phase 3 (PR #330)** — composite action 이 4 언어 변경분 affected
  만 자동 실행. v0.2.11 phase 2 풀 스위트의 CI watch 병목 (2~5분/PR × N task)
  해소.
  - **node**: nx.json / turbo.json / pnpm-workspace.yaml 자동 검출 →
    `nx affected` / `turbo run test --filter=...[<base>]` /
    `pnpm -F "...[<base>]" test`. dependency 그래프 자동 포함.
    - 미검출 (yarn classic / npm workspaces / bun / 단일) → 풀 폴백
  - **python**: 변경 .py 파일의 가장 가까운 상위 `pyproject.toml` / `setup.py` /
    `setup.cfg` 식별 → 그 root 별 pip install + pytest. 변경 0건 → skip.
  - **rust**: Cargo.toml `[workspace]` 검출 시 변경 파일 → member 매핑 →
    `cargo test -p <member>`. 단일 crate → `cargo test`. 변경 0건 → skip.
  - **go**: 변경 .go 의 dirname (유니크) → `go test ./<path>/...`. 변경 0건 → skip.
  - **PR base 자동 추출**: `github.event.pull_request.base.sha` 또는 origin/main 폴백

**jajang 효과**:
- apps/mobile (js + pnpm workspaces) 변경 → 해당 workspace + dependents 만 jest
- apps/api (python) 변경 → apps/api 안 pytest 만
- 둘 다 변경 안 됐으면 skip
- 사용자 작업 0 — `package.json["dcness"]["testCommand"]` override 박을 필요 없음

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `.github/actions/tdd-gate/action.yml` plug-in 업데이트 자동
- (2) init-dcness 배포 — Step 2.9 안내문 갱신. thin yml unchanged (composite action
  호출 1줄만 박힘 → 자동 phase 3 적용)
- (3) SSOT 문서 — N/A (capability 확장)

**한계 (phase 3)**:
- python/rust/go dependency 그래프 자동 포함 = phase 4 (현재 path 기반)
- yarn classic / npm workspaces / bun affected = 풀 폴백 (native filter 약함)
- 비-지원 언어 (Elixir/Ruby/Java/.NET/PHP/Swift) = phase 4

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트는 thin yml 그대로 — composite action 만 phase 3 자동 적용 (다음 PR 부터).

---

## v0.2.11 (2026-05-11)

**커밋 범위**: `v0.2.10..(다음 태그)`
**핵심 변경**: TDD 게이트 phase 1 → phase 2 — polyglot universal (#320 #1 확장)

- **이슈 #320 #1 phase 2 (PR #328)** — TDD 게이트가 node 한정에서 4 언어 universal
  로 확장. v0.2.10 phase 1 의 *node + root `scripts.test` 단일 명령* 가정이
  polyglot 모노레포 (jajang = apps/mobile=js + apps/api=python) 에 안 맞아 root fix.
  - `.github/actions/tdd-gate/action.yml` — 4 언어 검출 + 매트릭스 실행
    - node: package.json + pm 자동 (pnpm/yarn/bun/npm)
    - python: pyproject.toml / setup.py / setup.cfg / requirements*.txt + pytest (unittest 자동 cover)
    - rust: Cargo.toml + cargo test --all
    - go: go.mod + go test ./...
  - 검출된 *모든* 언어 PASS 필요 (polyglot matrix 결합)
  - 4 언어 모두 미검출 시 fail (비-지원 언어 phase 3 대기)
  - `commands/init-dcness.md` Step 2.9: 4 언어 안내문 + polyglot 가이드

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `.github/actions/tdd-gate/action.yml` plug-in 업데이트 자동 반영
- (2) init-dcness 배포 — Step 2.9 안내문 갱신. 기존 활성 프로젝트는 `/init-dcness`
  재실행 시 새 안내문 받음. thin yml 은 unchanged (외부 composite action 호출 1줄만
  박혀있어 자동 phase 2 적용)
- (3) SSOT 문서 — N/A (capability 확장)

**polyglot 적용 효과**:
- jajang (mobile=js + api=python): plugin update + `/init-dcness` 재실행만으로
  자동 cover. root `scripts.test` 위임 명령 / 별도 pytest workflow 작성 불필요.
- 향후 polyglot 활성 프로젝트들 모두 자동 혜택.

**한계 (phase 2)**:
- 지원 외 (Elixir / Ruby / Java / .NET / PHP / Swift) — phase 3 후속
- Python tooling = pip 만 (poetry / pdm / uv 는 phase 3)
- 풀 스위트만 — incremental 로컬 hook 은 phase 4

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트:
```sh
/init-dcness   # Step 2.9 발화 — TDD 게이트 옵트인 + 4 언어 안내문
```

---

## v0.2.10 (2026-05-10)

**커밋 범위**: `9a63e28..(다음 태그)`
**핵심 변경**: jajang Epic 12 회고 통합 — 진짜 bug 5건 root fix (이슈 #320 / #302 / #321 C / #292)

- **이슈 #320 #1 — TDD 게이트 3 단 (PR #322)**: jajang Epic 12 task 03 cascade 26
  cases 사단 root fix. engineer 의 prompt-level boundary 룰 (echo / grep) 은 차단력
  0 → mechanical wall 도입. 산업 표준 (incremental pre-commit → CI 풀 → branch
  protection) 중 *CI 풀* + *branch protection* 단을 dcness 가 배포.
  - `.github/actions/tdd-gate/action.yml` 신규 (node 전용, pm 자동 검출)
  - `commands/init-dcness.md` Step 2.9 추가 — 옵트인 thin yml + branch protection 안내

- **이슈 #320 #2 — PR body Closes pre-flight (PR #324)**: jajang Story 2 #239 OPEN
  영구 잔존 사단. `loop-procedure.md §3.4` 의 PR body 자동 판단 bash 가 stories.md
  *전체* `[ ]` 카운트 → 다른 Story 미완 task 와 섞임 → 본 task 가 부모 Story 마지막
  이라도 `Part of` 박힘. awk 으로 부모 Story 섹션 한정 카운트로 교체.
  - `docs/plugin/loop-procedure.md` §3.4 bash 골격 수정
  - `docs/plugin/issue-lifecycle.md` §1.4 적용 절차 4 step 명문화 추가

- **이슈 #302 #1 — RETRY_SAME_FAIL allow-list 보강 (PR #323)**: jajang run-cf83861d
  false positive 3건 — architect MODULE_PLAN × 4 task 정상 호출이 retry 오인 → review
  trust 저하. `harness/run_review.py` allow-list 에 `PROSE_LOGGED` (#284 prose-only
  mode 표준 sentinel) 추가 + prose 내용 다르면 다른 invocation 으로 판정 룰 추가.
  - 회귀 테스트 2 추가 (test_retry_same_fail_prose_logged_skip /
    test_retry_same_fail_different_prose_skip)

- **이슈 #321 C 1/4 — STRAY_DIR_LEAK detector (PR #325)**: jajang run-dbd49faf
  `.claire` × 3 회 연속 typo 사례. `harness/run_review.py:detect_wastes` 에 typo
  의심 디렉토리 검출 추가 (difflib similarity 0.70 threshold + KNOWN_INFRA_DIR_NAMES
  allow-list).
  - 회귀 테스트 3 추가. false positive 후보 9개 검증 (.vscode/.cargo/.cache 등
    모두 0.70 미만)

- **이슈 #292 partial — Step 4.5 범위 외 path 명문화 (PR #326)**: jajang main
  stories.md drift 177건의 root cause 일부 명문화. `loop-procedure.md §4` 본문에
  `quick-bugfix-loop` / engineer 직접 호출 / 메인 직접 commit / dcness 도입 이전
  잔재 — 사용자 책임 path 명시 + backfill 가이드 cross-link.

**배포 경로** (CLAUDE.md §0.5):
- (1) plug-in 본체 — `harness/`, `agents/` 변경은 plug-in 업데이트 자동 반영
- (2) init-dcness 배포 — Step 2.9 신규 (TDD 게이트). 기존 활성 프로젝트는
  `/init-dcness` 재실행 필요 — Step 2.9 자동 발화하여 thin yml 옵트인
- (3) SSOT 문서 — `loop-procedure.md` / `issue-lifecycle.md` plug-in cache 직접 read

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트는 추가로 `/init-dcness` 재실행 (Step 2.9 발화 + TDD 게이트
옵트인 + branch protection 안내). 멱등 — 다른 Step 들은 이미 적용된 경우 skip.

---

## v0.2.9 (2026-05-09)

**커밋 범위**: `156691f..(다음 태그)`
**핵심 변경**: init-dcness 신규 프로젝트 초기 docs 폼 시드 (이슈 #296)

- **이슈 #296** — `/init-dcness` 실행 시 `docs/PRD.md` / `docs/ARCHITECTURE.md` /
  `docs/ADR.md` 3개 파일 시드 (부재 시만, 멱등). 사용자가 PRD 논의 후 채워넣을
  표준 placeholder 제공 — 매 프로젝트마다 다른 형태로 시작하던 분산 해소.
  - `templates/project-init/{PRD,ARCHITECTURE,ADR}.md` 신규.
  - `commands/init-dcness.md` Step 2.8 추가 — 부재 시 사용자 동의 받고 cp.
  - 짧고 placeholder 위주 (한 화면 내 완결).

**배포 경로**: 본 변경은 init-dcness 가 사용자 repo 로 *복사·배포* 하는
인프라 (배포 경로 2). 기존 활성화 프로젝트는 자동 적용 안 됨 — `/init-dcness`
재실행 시 부재 파일만 시드 (멱등). 신규 프로젝트는 이번 release 부터 자동 시드.

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트에서 docs 폼 받고 싶으면 `/init-dcness` 재실행 (멱등).

---

## v0.2.8 (2026-05-09)

**커밋 범위**: `4926adf..(다음 태그)`
**핵심 변경**: helper picker semver 정렬 — 가장 오래된 cache 선택 회귀 수정 (이슈 #293)

- **이슈 #293** — helper 진입 패턴 `ls -d ${CLAUDE_PLUGIN_ROOT:-.../dcness/dcness/*} | head -1`
  이 알파벳 순 정렬로 *가장 오래된* cache (예: 6 버전 환경에서 0.2.2) 선택. v0.2.7
  의 prose-only mode (이슈 #284 정착) 에 도달 못 해 0.2.2 의 enum-required mode +
  옛 휴리스틱 강제. jajang run-f0c23053 실측에서 휴리스틱 FP 2건 발생 (validator
  prose "0 FAIL" → enum=FAIL 오추출 / pr-reviewer "MUST FIX 없음 + NICE TO HAVE
  4건" → must_fix=true 오판정). 4 파일 (총 9 occurrences) 의 picker glob 패턴
  `head -1` → `sort -V | tail -1` 교체:
  - `docs/plugin/loop-procedure.md` (1)
  - `commands/run-review.md` (1)
  - `commands/init-dcness.md` (5)
  - `commands/efficiency.md` (2)

**영향**:
- v0.2.7 의 prose-only mode 가 picker 가 옛 cache 강제로 도달 못 했던 회귀 수정.
- 본 v0.2.8 부터는 picker 가 항상 최신 semver 선택 → prose-only mode 자연 활용.
- cache 다중 버전 환경 (`claude plugin update` 누적) 에서 모두 영향.

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 cache 가 0.2.7 이 아닌 옛 버전을 picker 강제하던 환경 (jajang 실측 사례) 은
본 업데이트 후 정상화.

---

## v0.2.7 (2026-05-08)

**커밋 범위**: `1cff44a..(다음 태그)`
**핵심 변경**: enum 시스템 폐기 → prose-only routing 전환 (epic #280)

- **이슈 #281** — `harness/routing_telemetry.py` 신규. PostToolUse Agent 훅이
  매 sub 종료 시 prose tail (1200자 cap) 을 `.metrics/routing-decisions.jsonl`
  에 1줄 append. 메인이 사용자 위임할 때는 CLI `record-cascade --reason ...`.
  enum heuristic-calls.jsonl 의 prose-only 후속 — 회귀 검증용 raw baseline.
- **이슈 #282** — `docs/plugin/handoff-matrix.md §1` 의 enum 표 12 종을
  자연어 routing 가이드로 재포맷. agent 별 가능한 결론 *유형* + 권장 다음
  처리 흐름을 prose 로 서술. §2 retry / §3 escalate / §4 권한은 보존.
- **이슈 #283** — 22 agent 파일 (12 master + 5 architect sub-mode + 5
  validator sub-mode) 의 enum 표를 자연어 가이드로 환원. frontmatter
  description / leading prose / "## 결론 enum" 표 모두 "결론 + 권장 다음
  단계 자연어 명시" 로 통일. 기존 enum 단어는 *예시 권장 표현* 으로 보존.
- **이슈 #284** — `harness/interpret_strategy.py` telemetry write 코드
  제거 (`.metrics/heuristic-calls.jsonl` 신규 기록 0). `_cli_end_step` 의
  `--allowed-enums` optional. 미지정 시 prose-only mode (stdout
  `PROSE_LOGGED`). legacy `--allowed-enums` 호출은 호환 보존.
  `dcness-rules.md §3.3` / `loop-procedure.md §3.1` prose-only mode 권장
  으로 갱신.
- **이슈 #285** — 배포 경로 검증. 본 epic 모든 변경은 plug-in 본체 (배포
  경로 1) 안. `claude plugin update` 로 자동 전파. init-dcness 가 사용자
  repo 로 복사하는 인프라 (배포 경로 2) 변경 없음. 사용자용 SSOT 문서
  (배포 경로 3) 는 plug-in cache 안 — 자동 갱신.

**전환 모델 (정착 후)**:
1. agent 가 prose 마지막 단락에 *어떤 결과로 끝났는지 + 메인이 누구를
   부르는 게 적절한지* 자유 표현.
2. 메인 Claude 가 prose + handoff-matrix.md §1 자연어 가이드 보고 routing.
3. `routing-decisions.jsonl` raw 누적 → 회고 분석 (#281).
4. 결정 못 하면 `routing_telemetry record-cascade` 후 사용자 위임.

**업데이트**:
```sh
claude plugin update dcness@dcness
```

기존 활성화 프로젝트는 plug-in update 만으로 자동 적용. init-dcness 재실행
불필요. 외부 활성화 프로젝트 동작 확인은 사용자가 일반 작업 진행 중 자연스
럽게 검증 (특별한 검증 절차 없음).

---

## v0.2.6 (2026-05-08)

**커밋 범위**: `09e537f..c69e28a`
**핵심 변경**: engineer 권한 경계 강화 + POLISH self-verify 면제 + Step 7 회고 메모리 의무 + 워크트리 hook 정정 + DeepEval 마이그레이션

- `agents/engineer.md`: 자체 `git commit/push/branch` 호출 + `stories.md/backlog.md/batch-list.md` 직접 수정 사전 차단 (#148). §권한 경계 / §IMPL_PARTIAL / §커밋 단위 규칙 / §1 task = 1 PR 안티패턴 4 군데 정합. POLISH 자가 검증 anchor 면제 명시 (#252)
- `harness/run_review.py`: `MISSING_SELF_VERIFY` 검사에서 `POLISH_DONE` 제외 — POLISH prose 본문 자체가 검증 substance, anchor 강제는 잉여 (#252). 회귀 방지 unittest 추가
- `docs/plugin/loop-procedure.md §5.5`: 7b caveat 보고 양식에 "📝 메모리 candidate" 섹션 + 의무 룰 추가 (#149). 7a clean 도 review report waste finding 시 동일 적용
- `docs/plugin/dcness-rules.md`: "Step 7 회고 → 메모리 저장 의무" 룰 추가 — SessionStart inject 로 매 세션 자동 인지 (#149)
- `scripts/hooks/cc-pre-commit.sh`: cwd 결정 우선순위 뒤집기 — `git rev-parse --show-toplevel` 우선, fallback `CLAUDE_PROJECT_DIR` (#268). 워크트리 안 commit 이 메인 main 으로 오인 차단되던 회귀 수정
- `tests/eval_*.py` + 평가 인프라: AgentEvals → DeepEval 마이그레이션 (#263)

**업데이트**:
```sh
claude plugin update dcness@dcness
```

---

## v0.2.5 (2026-05-07)

**커밋 범위**: `8d097b4..6612db0`  
**핵심 변경**: 루프 종료 후 finalize-run 강제 안전망 + REVIEW_READY 신호

- `loop-procedure.md §3.3`: advance enum 마지막 step → 사용자 대기 없이 즉시 Step 7 명시 (issue-240)
- `loop-procedure.md §5.1`: 트리거 명시 + end-run 안전망 설명 추가
- `session_state.py _cli_finalize_run`: `finalized_at` 플래그 저장 + review → `review.md` 파일 저장 + stderr `[REVIEW_READY]` 신호
- `session_state.py _cli_end_run`: `finalized_at` 없으면 자동 `finalize-run --auto-review` 실행
- `dcness-rules.md`: 파일 경로 채널별 형식 분기 룰 추가 (CC 채팅 = 평문 백틱, 도큐 = 마크다운 링크)

**업데이트**:
```sh
claude plugin update dcness@dcness
```

---

## v0.2.4 (2026-05-07)

**커밋 범위**: `0fb69df..6038ceb`  
**핵심 변경**: PostToolUse prose 추출 전면 실패 수정

- PostToolUse hook 에서 tool_response 가 list 포맷일 때 prose 추출 전면 실패하던 버그 수정 (issue-232)
- `plugin-release.md` 'bump' → '버전 올리기' 표현 개선

---

## v0.2.3 (2026-05-07)

**커밋 범위**: `bfd500d..0fb69df`  
**핵심 변경**: `claude plugin update` 버그 수정

- `marketplace.json` `plugins[].source` 를 github object → `"./"` 로 복구
- 신규 install 은 두 포맷 모두 동작했으나, update 는 `"./"` 만 동작함을 확인 (`e68a440` 에서 잘못 변경된 것)
- git 태그 관리 시작 (이 버전부터 `v{버전}` 태그 병행)

---

## v0.2.2 (2026-05-07)

**커밋 범위**: `ff3ae5b..bfd500d`  
**핵심 변경**: 내부 문서 구조 정리 + dcness-rules 전면 재편

- `dcness-rules.md` 전면 재편 — 대원칙 신설, 루프 구조화, prose-only 통합 (issue-223)
- `main-claude-rules.md`, `self-guidelines.md`, `governance.md`, `branch-protection-setup.md` 삭제 — 역할 흡수 또는 중복 제거
- `CLAUDE.md §3` lazy 표 누락 파일 보완

---

## v0.2.1 (2026-05-07)

**커밋**: `ff3ae5bcdbd62c8f2240ca94f31d593133634101` (release branch HEAD)  
**핵심 변경**: marketplace 배포 경로 정비 + 로컬 게이트 강화

- release 브랜치에서 `marketplace.json` 제거 (sync_local_plugin.sh 폐기, issue-221)
- `dcness-rules.md` 로 rename + 정제 (issue-217)
- cc-pre-commit.sh 브랜치명·PR 제목 로컬 게이트 추가 (issue-171)
- run_review false positive 수정 (issue-171)
