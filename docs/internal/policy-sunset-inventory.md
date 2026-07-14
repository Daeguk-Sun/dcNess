# 정책 수명주기 inventory와 cleanup baseline

> #1089의 cleanup 전 snapshot과 후속 상태 전이를 함께 기록한다. 측정 revision은 `b676140bcffdaa5843ce59198ecef4f997efddc9`이며, 분류 근거는 2026-07-14 KST의 저장소와 등록 활성 프로젝트 read-only 조사다. baseline 수치는 고정하고 후속 cleanup은 별도 상태 전이로 누적한다.

## 재현 명령과 산출물

한 명령이 Git tracked tree의 크기 지표, inventory schema·분류·후속 이슈 전수 배정, 전체 unit suite 실행시간을 함께 출력한다. untracked receipt와 현재 working copy의 새 파일은 revision 지표에 들어가지 않는다. suite도 지정 revision의 임시 detached worktree에서 실행해 dirty working tree를 격리한다. 측정 구현은 terminal 분류까지 반영된 pre-#1099 main `071146c`에 고정했으며 #1099 최종 재측정 뒤 one-shot 코드와 전용 테스트를 함께 퇴역했다.

```sh
git show 071146c:scripts/policy_cleanup_baseline.py | \
python3.11 - --repo-root . \
  --revision <comparison-revision> \
  --inventory docs/internal/policy-sunset-inventory.json \
  --run-unit-suite
```

- 측정 구현: pre-#1099 main `071146c`의 `scripts/policy_cleanup_baseline.py` (고정 snapshot; #1092 LOC 정의 동일)
- 정책 slice 원장: [`policy-sunset-inventory.json`](policy-sunset-inventory.json)
- 고정 출력: [`policy-sunset-baseline.json`](policy-sunset-baseline.json)

측정 구현은 dcNess self에서만 쓴 일회성 내부 도구다. #1092~#1099 동안 marketplace release payload와 `init-dcness` 배포에서 제외했고, 최종 증거를 만든 뒤 구현 360줄·전용 테스트 219줄·release exclusion을 함께 제거했다. 재감사는 위 frozen source를 실행하므로 정의를 바꾸지 않는다.

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
| `퇴역 완료` | 제거 가능 판정 뒤 구현·테스트·fixture·문서 surface와 배포 경로를 함께 제거하고 검증한 terminal state | 0 |

baseline 영역별 29개는 design 6, run/ledger 8, routing 5, install/path 5, lifecycle 5다. #1099 통합 감사에서 누락된 run/orchestration fossil `RUN-009`를 추가해 최종 원장은 30개다. 각 entry는 현행 SSOT, 구현, test/fixture, 문서·배포, 소비자 증거를 모두 가진다. 키워드가 같아도 release artifact의 `--contract`처럼 의미가 다른 적중은 `현재 실사용`으로 명시해 false positive를 버리지 않고 분류했다.

### #1093 설계 cleanup 상태 전이

`DES-002`는 `제거 가능`에서 `퇴역 완료`로 이동했다. module-architect의 legacy contract sync mode·추가 write 경계·전용 sweep report를 함께 제거했고, 현행 module/decision 작성 경로와 실제 활성 프로젝트가 소비하는 `DES-003`~`DES-005` reader/leniency는 분리해 유지했다. 이에 따라 전체 compatibility 후보는 15개에서 14개, design 영역 후보는 4개에서 3개로 감소한다.

초기 탐색의 설계 후보 25개는 다음처럼 닫힌다.

| 관계 | 파일 | #1093 판정 |
|---|---|---|
| legacy authoring/sweep | `agents/module-architect.md`, `docs/plugin/agents/module-architect/module-architect-agent.md`, `docs/plugin/agents/module-architect/references/contract-amendment.md`, `docs/plugin/agents/module-architect/templates/contract-sweep-report.md` | mode·권한·보고서·작성 지침을 함께 퇴역하고 report 파일을 plugin payload에서 제거 |
| warning/reader | `scripts/check_design_artifact_structure.mjs`, `scripts/aggregate_architecture_map.mjs` | legacy artifact warning과 architecture map 입력 호환을 유지 (`DES-003`, `DES-004`) |
| validator/reference leniency | `codex/skills/dcness-architecture-validator/SKILL.md`, `docs/plugin/agents/architecture-validator/architecture-validator-agent.md`, `docs/plugin/agents/architecture-validator/references/finding-examples.md`, `docs/plugin/agents/system-architect/references/contract-ledger.md`, `docs/plugin/agents/system-architect/references/system-freeze.md` | 구양식 존재만으로 Must/FAIL하지 않는 read-side 계약과 해석 참고를 유지 (`DES-005`) |
| current authoring/docs | `docs/plugin/agents/system-architect/system-architect-agent.md`, `docs/plugin/agents/system-architect/templates/root-architecture.md`, `docs/plugin/deliverables-map.md`, `docs/plugin/hooks.md`, `docs/plugin/init-dcness.md`, `skills/design/SKILL.md`, `skills/design/design-routing.md` | module responsibility·decision 진본, 신규 legacy 사본 금지, doc-sync warning 배포 설명을 유지 (`DES-001`, `DES-003`~`DES-005`) |
| test/fixture | `tests/test_agent_operability_contract.py`, `tests/test_architecture_cartography.py`, `tests/test_architecture_map_aggregate.py`, `tests/test_contract_pointer_model.py`, `tests/test_design_artifact_audit.py`, `tests/test_design_surface.py`, `tests/test_surface_docs_sync.py` | 현행 writer 부정선행, legacy reader fixture, agent/docs/Codex mirror 정합을 분리 검증하며 sweep report 양성 fixture는 제거 |

배포 경로는 plugin 본체다. `agents/**`, `docs/plugin/**`, `skills/**`, `scripts/**`, `codex/**` 변경은 다음 plugin 버전 업데이트로 활성 프로젝트에 도달하며, `/init-dcness`가 복사하는 generated file이나 workflow 계약은 바뀌지 않아 재실행 migration은 필요하지 않다. release artifact candidate는 삭제된 sweep report를 더 이상 포함하지 않는지 smoke로 확인한다.

### #1094 run/ledger cleanup 상태 전이

`RUN-006`은 `제거 가능`에서 `퇴역 완료`로 이동했다. `harness.session_state`가 2026-07-05 모듈 분리 뒤 임시로 다시 노출하던 private CLI 이름 53개는 runtime import가 0건이었고, 테스트만 facade를 소비했다. 동적 `_CLI_REEXPORT_NAMES`·`__getattr__`를 제거하고 테스트가 실제 owner인 `session_state_cli`·`session_state_cli_finalize`를 직접 사용하게 했다. facade 부재 회귀 테스트도 추가했다. code+test diff는 73줄 추가·154줄 삭제로 81 LOC 순감이고, 전체 compatibility 후보는 14개에서 13개, run/ledger 후보는 5개에서 4개로 감소한다.

나머지 `RUN-002`·`RUN-003`·`RUN-005`·`RUN-008`은 실제 legacy sample이 있어 종료 trigger가 충족되지 않았다. `RUN-004`·`RUN-007`은 legacy가 아니라 현재 crash·hook failure 안전 경계이므로 감량 대상으로 재분류하지 않는다. run-state 8개 후보의 저장·소비 계약은 다음과 같다.

| ID | 저장 형식·생성 주체·도입 버전 | 실제 소비자·read/write | #1094 판정·제거 trigger | 확인 fixture |
|---|---|---|---|---|
| RUN-001 | helper가 쓰는 `ledger.jsonl` event와 prose receipt, v0.5.0부터 canonical | session state·hooks·run review·benchmark·headless worker가 read, `harness.ledger`만 append | 현재 실사용 유지; canonical ledger 자체는 제거 대상 아님 | `tests.test_ledger`, `tests.test_session_state` |
| RUN-002 | v0.2.2~v0.4 계열 helper의 `.steps.jsonl`; v0.5.0 update 중 두 파일이 생기는 mixed run | ledger/session state/run review가 read-only 호환, current writer는 `.steps.jsonl`을 쓰지 않음 | 한시 유지; 보존기간 확정·migration 뒤 legacy/mixed 표본과 reader hit 0 | `tests.test_ledger`, `tests.test_run_review` |
| RUN-003 | legacy step row와 현행 receipt의 `prose_file`·`prose_excerpt`·`must_fix`·`enum`; end-step helper가 생성 | run review·benchmark·outcome가 read, current receipt writer도 같은 field vocabulary를 write | 한시 유지; canonical schema·migration 확정과 reader 전환 뒤 archive reader 격리 | ledger·benchmark·outcome tests |
| RUN-004 | malformed/partial ledger line, invalid receipt, `live.json` tombstone; 현행 writer crash·cleanup에서도 발생 가능 | ledger/session state가 손상 row를 skip/drop하고 tombstone을 read/write | 현재 안전 경계 유지; append·cleanup이 crash/partial 상태를 만들 수 없다는 별도 계약 전에는 제거 불가 | `tests.test_ledger`, `tests.test_session_state`, `tests.test_state_cleanup` |
| RUN-005 | v0.2.16 시기 persisted `validator` agent name; 구 writer가 생성 | run review·agent boundary가 read 시 `impl-validator`로 normalize, current writer는 canonical name만 write | 한시 유지; archive migration 뒤 alias 표본과 hit telemetry 0 | `tests.test_run_review`, `tests.test_agent_boundary` |
| RUN-006 | persisted 형식 없음; v0.13.0 모듈 분리 때 생긴 Python private import facade | 저장소 테스트만 import했고 runtime reader/writer 0 | 퇴역 완료; canonical CLI owner 직접 import와 facade 부재를 검증 | `SplitModuleImportTests`, `tests.test_agent_routing` |
| RUN-007 | hook auto-stage 실패 뒤 run-dir에 남은 current prose; hook/end-step이 생성 | finalize helper가 recovery read, staging/prose writer는 현행 | 현재 안전 경계 유지; best-effort staging failure 가능성이 제거되기 전 삭제 불가 | `tests.test_session_state`, `tests.test_hooks` |
| RUN-008 | legacy row의 stored verdict와 현행 `PROSE_LOGGED`+prose 결론; v0.5.0 이후 canonical writer는 sentinel만 write | run review·benchmark·outcome가 두 세대를 read | 한시 유지; legacy verdict를 canonical prose verdict로 migration하고 old sample 0 | run-review·benchmark·outcome tests |
| RUN-009 | persisted 형식 없음; 한 세션 worker fan-out/fan-in 시절의 result aggregation helper | runtime·script·문서 caller 0, tests만 옛 `fan_in_check` API를 호출 | #1099 퇴역 완료; 현행 독립 peer는 claim board+merge lock 사용 | `rg 'fan_in_check|WorkerResult|FanInResult'`와 `tests.test_parallel_wave` |

등록 활성 프로젝트의 persisted run은 registry path를 출력하지 않고 다음 명령으로 형식별 집계한다.

```sh
registry="$HOME/.claude/plugins/data/dcness-dcness/projects.json"
{
  jq -r '.projects[]' "$registry" | while IFS= read -r root; do
    state="$root/.claude/harness-state"
    find "$state" -type f -name ledger.jsonl 2>/dev/null | while IFS= read -r file; do
      if [ -f "$(dirname "$file")/.steps.jsonl" ]; then echo mixed; else echo current-only; fi
    done
    find "$state" -type f -name .steps.jsonl 2>/dev/null | while IFS= read -r file; do
      [ -f "$(dirname "$file")/ledger.jsonl" ] || echo legacy-only
    done
  done
} | sort | uniq -c
```

확인 가능한 plugin/cache·과거 checkout의 지원 표본은 host path를 출력하지 않고 다음 명령으로 형식과 legacy field를 집계한다.

```sh
support_files() {
  for root in "$HOME/.claude" "$(dirname "$(git rev-parse --show-toplevel)")"; do
    rg --hidden --no-ignore --files "$root" 2>/dev/null |
      awk '/\/(ledger\.jsonl|\.steps\.jsonl)$/ {print}'
  done | sort -u
}

support_files | while IFS= read -r file; do
  dir="$(dirname "$file")"
  case "$(basename "$file")" in
    ledger.jsonl)
      if [ -f "$dir/.steps.jsonl" ]; then echo mixed; else echo current-only; fi ;;
    .steps.jsonl)
      [ -f "$dir/ledger.jsonl" ] || echo legacy-only ;;
  esac
done | sort | uniq -c

support_files | awk '/\/\.steps\.jsonl$/' | while IFS= read -r file; do
  jq -r '[.agent // "<missing>", .enum // "<missing>",
          (has("prose_file") | tostring)] | @tsv' "$file"
done | awk -F '\t' '
  { agents[$1]++; enums[$2]++; prose_file[$3]++; rows++ }
  END {
    print "rows", rows
    for (key in agents) print "agent", key, agents[key]
    for (key in enums) print "enum", key, enums[key]
    for (key in prose_file) print "prose_file_present", key, prose_file[key]
  }'
```

2026-07-14 #1094 실행 결과는 등록 프로젝트 5곳 모두 state root가 있었고 `current-only 32`, `legacy-only 0`, `mixed 0`이었다. #1099 재실행에서는 active `current-only 35`, 지원 범위 전체 `current-only 36`·`legacy-only 62`·`mixed 0`이었다. legacy 62개·339행의 핵심 잔존값도 `validator` 58행, `CHANGES_REQUESTED` 4행, `LGTM` 33행, `prose_file` 없는 row 125개로 동일했다. 따라서 현재 active snapshot의 legacy 0건만으로 read-side 지원 종료를 선언하지 않는다.

### #1095 provider routing cleanup 상태 전이

`ROUTE-003`의 `codex-first` preset·CLI·provider chain과 `ROUTE-004`의 소비자 없는 `VALID_PROVIDERS` export를 구현·테스트·문서에서 함께 제거해 `퇴역 완료`로 이동했다. 지원 custom implementation route는 `headless-chain`, `claude-headless`, `claude` 세 값이며 추천 role split과 migration 순서는 [`docs/plugin/init-dcness.md`](../plugin/init-dcness.md#provider-routing)가 한 곳에서 소유한다. 전체 compatibility 후보는 13개에서 11개, routing 후보는 3개에서 1개로 감소한다.

`ROUTE-002`는 둘로 나눠 판정했다. 설치 data와 확인 가능한 지원 범위에서 schema v1·v2는 0건이라 지원을 종료하고, version이 3이 아니면 runtime이 safe Claude route를 사용하며 doctor가 migration 필요를 보고한다. 반면 등록 프로젝트 5곳이 공유하는 schema v3 config에는 retired key 3개가 실제 남아 있어 이 부분은 `한시적 호환 필요`를 유지한다. 추천 preset은 두 route map을 현행 key로 덮어쓰므로 `routing enable-role-split-routing` 뒤 필요한 custom override를 다시 적용하고 `routing doctor` PASS를 확인하는 migration 경로다.

host path를 출력하지 않는 설치 config 재현 명령은 다음과 같다.

```sh
python3.11 - <<'PY'
import json
from collections import Counter
from pathlib import Path

registry = json.loads((Path.home() / ".claude/plugins/data/dcness-dcness/projects.json").read_text())
files = sorted((Path.home() / ".claude").rglob("routing.json"))
versions = Counter()
validation_keys = Counter()
implementation_keys = Counter()
implementation_values = Counter()
for path in files:
    data = json.loads(path.read_text())
    versions[str(data.get("version"))] += 1
    validation_keys.update((data.get("routes") or {}).keys())
    implementation_keys.update((data.get("implementation_routes") or {}).keys())
    implementation_values.update((data.get("implementation_routes") or {}).values())
print("registered_projects", len(registry["projects"]))
print("routing_files", len(files))
print("versions", dict(sorted(versions.items())))
print("validation_keys", dict(sorted(validation_keys.items())))
print("implementation_keys", dict(sorted(implementation_keys.items())))
print("implementation_values", dict(sorted(implementation_values.items())))
PY
```

2026-07-14 실행 결과는 등록 프로젝트 5곳, routing file 1개, version 3 한 건, validation key `architecture-validator`·`code-validator`·`pr-reviewer` 각 1건, implementation key `test-engineer` 1건, implementation value `claude` 1건이었다. `codex-first`와 schema v1·v2는 0건이다. 현행 role split·custom route 회귀와 provider 성공·변경 전 실패·변경 후 실패 안전 경계는 `tests.test_agent_routing`과 `tests.test_provider_chain`이 분리 검증한다. Python code+test diff는 93줄 추가·97줄 삭제로 4 LOC 순감이다.

| ID | 실제 소비자·지원 경계 | 유지 또는 종료 이유 | 제거 trigger | 확인 명령 |
|---|---|---|---|---|
| ROUTE-001 | schema v3 `routes`/`implementation_routes`; init preset·validator·build-worker | 현행 role split과 custom route 진본 | 대체 routing 계약과 config migration이 별도로 승인될 때 | `python3.11 -m unittest tests.test_agent_routing -v` |
| ROUTE-002 | schema v3 retired key 3종은 migration 대상; schema v1·v2 지원 종료 | 설치 data 실재 config를 조용히 삭제하지 않고 doctor로 식별 | 등록 config retired-key scan 0 | `dcness-helper routing enable-role-split-routing` 후 `routing doctor` |
| ROUTE-003 | `codex-first` 설치 config 0건; 이 변경부터 미지원 | 소비자 없는 preset·CLI·chain을 terminal 제거 | 완료 — runtime·docs·tests active surface 0 | `rg 'codex-first|enable-codex-implementation|disable-codex-implementation'` active surface와 routing/provider tests |
| ROUTE-004 | 저장 형식과 무관한 Python export; repo caller 0 | backward-compatible 이름만 남은 read surface | 완료 — export·`__all__`·assertion 제거 | `rg 'VALID_PROVIDERS' harness scripts`와 `tests.test_agent_routing` |
| ROUTE-005 | schema v3 `headless-chain`; implementation runtime | pre-mutation 실패만 복구하고 mutation 후 자동 덮어쓰기를 막는 현행 safety | 동등한 mutation 감지·중단 보장으로 chain을 대체할 때 | `python3.11 -m unittest tests.test_provider_chain -v` |

### #1096 설치·hook·경로 cleanup 상태 전이

`INST-004`의 루트 `design-variants/` prefix는 v0.11.0에서 canonical `docs/design-variants/`로 이동할 때 stale reference를 잡던 validation-only 경로였다. 2026-07-14 등록 프로젝트 5곳을 비식별 재조사한 결과 legacy directory와 markdown reference가 모두 0건이었고, current generator·TDD skip·배포 inventory는 canonical path만 쓴다. 따라서 `LEGACY_PATH_PREFIXES`, 구 migration 안내, 존재 예상 test를 함께 제거하고 `퇴역 완료`로 전이한다. 전체 compatibility 후보는 11개에서 10개, install/path 후보는 1개에서 0개로 감소한다.

나머지 경로는 단순히 오래됐다는 이유로 제거하지 않는다. generated hook은 v0.12.0+의 현행 계약이고, v0.19.0+의 in-place·linked-worktree 도달성 판정과 함께 쓴다. git thin shim의 repo-local·`CLAUDE_PLUGIN_ROOT`·cache 탐색은 v0.2.2+ self/external 실행 topology를, central TDD fallback은 현재 partial generated install을 보호한다.

| ID | 소비 설치 상태·지원 버전 | #1096 판정·유지 이유 | 제거 trigger | 확인 명령·fixture |
|---|---|---|---|---|
| INST-001 | fresh init, re-run, plugin update, 5/5 generated install; v0.12.0+, Git 도달성은 v0.19.0+ | 현재 writer·self-test·impl preflight와 5/5 활성 소비자가 있어 유지 | 대체 계약 migration 후 generated file·runtime hit 0 | `tests.test_generated_tdd_hooks`, `dcness-tdd-hooks status/ensure` |
| INST-002 | 현재 0/5 partial 4곳과 update 중간 1/5·2/5 fixture; v0.12.0+ | 5곳 중 4곳이 partial이며 generated hook 없는 TS/JS TDD safety를 보호해 유지 | 전항 5/5 migration + update 중간 safety 대체 | `tests.test_generated_tdd_hooks`, `tests.test_tdd_guard`, `tests.test_hooks` |
| INST-003 | explicit headless/self-test, Claude env, plugin cache, dcNess self repo-local; thin shim v0.2.2+, generated resolver v0.12.0+ | 실행 surface별 root 신호가 달라 유지 | 검증된 active root 단일 신호 전환 + self/cache hit 0 | `tests.test_generated_tdd_hooks`, `tests.test_git_hook_guard_telemetry`, `tests.test_hook_wrapper_exit` |
| INST-004 | v0.11.0~v0.23.0 validation-only legacy prefix; 디렉터리·reference 0 | 퇴역 완료; canonical generator는 `docs/design-variants/`만 쓰며 소비자 없음 | 2026-07-14 등록 프로젝트 directory 0 + reference 0으로 충족 | `rg 'LEGACY_PATH_PREFIXES'`, canvas/doc-path/policy inventory tests |
| INST-005 | primary/linked worktree, common hooks, generated commit state, primary receipt; v0.19.0+ | 현행 impl/design worktree의 오차단·미차단 방지로 유지 | worktree workflow 종료 또는 Git hook/state root 단일화 + migration | `tests.test_hooks`, `tests.test_session_state`, `tests.test_hook_wrapper_exit` |

배포 경로는 두 가지다. `harness/**`, `hooks/**`, `scripts/**`, `commands/**`, `docs/plugin/**`는 plugin 본체와 release artifact를 통해 다음 plugin update 시 활성 프로젝트에 도달한다. 선택형 `doc-path-integrity.yml`은 `Daeguk-Sun/dcNess/.github/actions/doc-path-integrity@main`의 현행 script를 호출하므로 legacy prefix 제거를 위한 workflow 재배포는 필요 없다. git thin shim 내용이 바뀌는 후속 변경만 `/init-dcness` 재실행이 필요하며, 이 변경은 shim과 generated file 바이트를 바꾸지 않는다.

### 활성 소비자 snapshot

등록 파일 `~/.claude/plugins/data/dcness-dcness/projects.json`의 경로는 문서에 공개하지 않고 registry 순번으로만 조사했다.

| 관찰 영역 | 2026-07-14 read-only 결과 | inventory 영향 |
|---|---|---|
| legacy design artifact | 5개 중 2개 프로젝트, marker 포함 문서 72개 | `DES-003`~`DES-005` 한시 호환 |
| persisted run | active `ledger.jsonl` 35개, `.steps.jsonl` 0개; 지원 표본 legacy 62개 | `RUN-001` 현행; 과거/cache 형식인 `RUN-002`는 종료 trigger 필요 |
| routing config | schema 3이지만 retired `code-validator`, `pr-reviewer`, `test-engineer` key 잔존 | `ROUTE-002` migration 대상 실재 |
| generated install | 프로젝트별 5개 대상 파일 보유량 `0/5, 0/5, 0/5, 0/5, 5/5` | partial install fallback인 `INST-002` 현행 |
| stories | 3개 프로젝트의 `stories.md` 10개가 모두 Story AC 없는 구양식 | `LIFE-002` 한시 호환 |
| open issue acceptance | 1개 프로젝트의 open issue 14개: 검증 주체 미기재 8, no-AC 6; 무분류 중 사람 판단 가능 항목 5 | `LIFE-003` REVIEW reader 한시 호환 |
| legacy `design-variants/` prefix | 등록 프로젝트 directory·markdown reference 모두 0건 | `INST-004` 제거 trigger 충족·퇴역 완료 |

절대경로·프로젝트명은 근거가 아니라 민감한 host 정보라 기록하지 않았다. 후속 이슈는 같은 registry 순번과 해당 이슈의 확인 명령으로 재조사한다.

### #1097 story·issue acceptance cleanup 상태 전이

신규 writer와 legacy reader를 분리해 조사했다. typed Story AC·issue checklist는 2026-07-11 도입됐고 신규 생성기는 `[command]`/`[agent-read]`만 checklist로 만든다. 반면 등록 프로젝트에는 2026-05-24~2026-07-03에 생성된 legacy stories 10개와 2026-06-05~2026-06-21에 생성된 open legacy issue 14개가 남아 reader 제거 trigger를 충족하지 못했다.

`LIFE-003` reader는 유지하되 자동 close 신호만 퇴역했다. 기존 `PASS — legacy/no AC`와 checked unclassified AC의 일반 `PASS`, impl/impl-loop의 무분류 AC 자동 재분류·본문 반영 지침을 제거했다. 이제 legacy body는 exit 0 `REVIEW`로 읽혀 migration 없는 접근은 유지하지만 agent 자동 close 권한을 주지 않는다. typed 전항목 완료 body만 `PASS`이며, legacy 의미·사람 판단은 agent가 추론·체크·재분류하지 않고 human verification으로 넘긴다.

| ID | 생성 시기·실제 소비자 | 지원 이유 | 제거 trigger | 확인 fixture |
|---|---|---|---|---|
| LIFE-001 | 2026-07-11 도입; spec template, story issue generator, to-issue, pre-create/close audit | 신규 작성이 typed agent-verifiable checklist만 생성하는 현행 계약 | 대체 schema와 writer/reader migration 승인 | create-issue, issue-body, spec-story tests |
| LIFE-002 | 확인 가능 2026-05-24~2026-07-03; 3/5 프로젝트 stories 10개 | 기존 설계·acceptance를 false fail하거나 coverage PASS로 오인하지 않음 | typed migration 뒤 legacy scan 0 | AC coverage와 product-acceptance fixture |
| LIFE-003 | 2026-06-05~2026-06-21; open issue 14개(무분류 8, no-AC 6) | migration 없이 읽되 사람·불명확 의미의 agent 자동 close를 차단 | typed migration 또는 human-confirmed close 뒤 scan 0 | issue-body typed PASS / legacy REVIEW fixture |
| LIFE-004 | 2026-07-11 도입; 모든 신규 issue와 close workflow | 사람 판단을 agent-verifiable checkbox에서 분리 | 동등한 human safety 계약 승인 | issue human-verification fixture |
| LIFE-005 | 2026-07-11 도입; design pre-final과 architecture-validator | 실제 문서 읽기 판정을 형식 hard fail로 대체하지 않음 | 동등한 trace reader 통합 | AC coverage advisory fixture |

compatibility 후보는 `LIFE-002`와 `LIFE-003` 두 개로 유지된다. 둘 다 활성 소비자가 0이 아니므로 감소시키지 않았으며, 대신 `LIFE-003` 안의 자동 PASS·agent inference writer surface만 구현·테스트·skill·SSOT에서 함께 제거했다. 신규 public command·agent·mode·gate는 만들지 않았고 변경은 plugin 본체 `scripts/**`, `skills/**`, `docs/plugin/**`를 통해 다음 plugin update에 도달한다. `/init-dcness`가 복사하는 generated file은 바뀌지 않는다.

비식별 fixture 재생 결과 legacy stories는 `10/10 REVIEW`, completed-copy open legacy issue는 `14/14 REVIEW`였고 `PASS`·실패는 각각 0건이었다. lifecycle script+test diff(`check_issue_body`, `report_ac_coverage`, 대응 두 test)는 31줄 추가·32줄 삭제로 1 LOC 순감이다. 전체 compatibility 후보는 10개, lifecycle 후보는 2개로 유지되며 감소 불가 근거는 위 `LIFE-002`·`LIFE-003` 활성 소비자 수다.

## 한시적 호환 4요소 감사

아래 10개 모두 대상, 유지 이유, 제거 trigger, 확인 방법을 가진다. 명령 전문과 trace path는 machine inventory에 있다.

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
| LIFE-002 | Story AC 없는 stories | 소급 의미 추론·false fail 방지 | typed AC migration + scan 0 | AC coverage + fixture |
| LIFE-003 | checklist 없거나 검증 주체 미기재인 legacy issue | migration 없는 read + agent false close 방지 | typed migration/human-confirmed close + scan 0 | typed PASS·legacy REVIEW close fixture |

종료 날짜를 근거 없이 임의 지정하지 않았다. trigger를 만족하지 못한 채 reader를 제거하는 것은 #1089 안전 경계를 위반한다.

## 500줄 이상 major text 책임 감사

단순 분할은 개선으로 세지 않는다. `265e538`에서 58개 전부를 다시 읽고 현재 책임, 중복·legacy 비중, 실제 감량 후보를 갱신했다. `후속/판정`이 #1098인 항목도 앞선 정책 이슈가 제거한 branch·fixture를 입력으로 받을 뿐, 크기만으로 쪼개지 않는다.

| 파일 | LOC | 현재 책임 | 중복·legacy 관찰 | 후속/판정 |
|---|---:|---|---|---|
| `PROGRESS.md` | 556 | self 진행 기록 | 누적 이력이며 runtime 아님 | #1098 입력 제외; 분할 무효 |
| `commands/init-dcness.md` | 513 | 활성화·재실행·제거 orchestration | install 설명이 사용자 SSOT와 일부 반복 | #1096에서 배포 계약 단위 감량 |
| `docs/archive/change_rationale_history.md` | 2,633 | 과거 결정 archive | legacy 비중 높지만 실행 surface 아님 | #1098에서 archive 보존정책 없이는 삭제 금지 |
| `docs/archive/conveyor-design.md` | 684 | 폐기 설계 archive | 현행 loop와 중복 가능 | #1098 후보, 단 runtime 감량으로 계산 X |
| `docs/archive/document_update_record.md` | 1,777 | 과거 변경 archive | Git history와 중복 | #1098 후보, 별도 archive 근거 필요 |
| `docs/archive/status-json-mutate-pattern.md` | 553 | 폐기 status JSON 참고 | 현행 prose-only와 legacy 비중 높음 | #1098 후보, 외부 링크 감사 후 |
| `docs/internal/marketplace-artifact-baseline.json` | 658 | release artifact inventory | generated data, 책임 중복 없음 | 유지; 분할 무효 |
| `docs/internal/policy-sunset-inventory.json` | 515 | 정책 slice machine inventory | markdown 감사와 표현은 겹치지만 machine validation 입력 | 유지; #1099 재측정 입력 |
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
| `harness/guard_telemetry.py` | 663 | guard hit telemetry | compatibility와 무관 | 현행 |
| `harness/hooks.py` | 1,671 | order/state hook 집약 | 여러 세대 enum·run assertion 포함 | #1094 후 #1098; order guard 보존 |
| `harness/ledger.py` | 642 | canonical + legacy run reader | legacy/mixed/field 호환 비중 큼 | #1094 핵심 감량 후보 |
| `harness/outcome_scorecard.py` | 739 | process·effectiveness·outcome 집계 | legacy verdict 소비 중복 | #1094 뒤 #1098 |
| `harness/parallel_wave.py` | 814 | peer wave 후보 계산 | 미사용 single-session fan-in model은 #1099에서 퇴역 | 현행 compute/claim/merge-lock 계약 유지 |
| `harness/product_journey.py` | 864 | 제품 journey runner | compatibility와 무관 | 현행 |
| `harness/run_review.py` | 1,853 | persisted run 분석·waste report | legacy name/verdict/prose 비중 큼 | #1094 핵심, 이후 #1098 |
| `harness/session_state.py` | 2,125 | run lifecycle/state owner | private CLI re-export는 #1094에서 퇴역; persisted state 안전 책임 유지 | #1094 완료 뒤 #1098, 단순 분할 무효 |
| `harness/session_state_cli.py` | 1,464 | CLI dispatch·routing | canonical CLI owner; legacy implementation preset CLI는 #1095에서 제거 | #1095 완료 뒤 #1098 |
| `harness/session_state_cli_finalize.py` | 595 | end-step/finalize/prose receipt | prose fallback과 old field 설명 | #1094 |
| `harness/session_state_status.py` | 501 | status/diagnostic view | state reader assertion과 중복 가능 | #1094 뒤 #1098 |
| `harness/story_runner.py` | 509 | story stack state | 현행 lifecycle | #1097 reader 정리 뒤 #1098 |
| `harness/tdd_hooks.py` | 1,356 | generated hook 생성·status·self-test | install 상태별 분기 큼, 실제 partial 소비자 존재 | #1096; 단순 분할 금지 |
| `scripts/github_project_lifecycle.mjs` | 1,444 | GitHub Project state lifecycle | legacy story reader와 직접 무관 | 현행; #1098 크기만으로 선택 금지 |
| `scripts/loop_diagnose.py` | 887 | cross-project 진단 | compatibility와 무관 | 현행 |
| `templates/design-variants/_lib/canvas.js` | 618 | static mockup canvas runtime | policy legacy와 무관 | 현행 |
| `tests/test_agent_boundary.py` | 2,642 | 권한 경계 회귀 | legacy alias assertion 일부, safety fixture 다수 | #1094 후 #1098 중복 assertion 검토 |
| `tests/test_agent_effectiveness.py` | 591 | effectiveness schema | compatibility와 무관 | 현행 |
| `tests/test_benchmark_aggregate.py` | 528 | aggregate verdict 회귀 | local current/legacy fixture writer를 #1098 공통 helper로 통합; verdict assertions 유지 | #1098 fixture 책임 감량 완료 |
| `tests/test_chain_view.py` | 522 | chain view 회귀 | run fixture 중복 가능 | #1094 후 #1098 |
| `tests/test_codex_sandbox_permission.py` | 564 | sandbox 승인 경계 | 현행 safety | 유지 |
| `tests/test_codex_validator_wrapper.py` | 1,522 | Codex wrapper/prose/boundary | 여러 wrapper fixture 중복 가능 | #1096 후 #1098, sandbox safety 보존 |
| `tests/test_design_surface.py` | 578 | design prompt/template sync | legacy authoring 부정 assertion 포함 | #1093 후 #1098 |
| `tests/test_evals_harness.py` | 688 | eval runner 격리·병렬·release strict 회귀 | policy compatibility와 무관 | 현행; 크기만으로 선택 금지 |
| `tests/test_generated_tdd_hooks.py` | 771 | generated install matrix | partial/install fixture가 실사용 | #1096 후 중복 fixture만 #1098 |
| `tests/test_github_project_lifecycle.py` | 1,544 | project lifecycle 스크립트 | compatibility와 무관 | 현행; #1098 크기만으로 선택 금지 |
| `tests/test_hooks.py` | 3,582 | order/state/hook 통합 회귀 | run·alias·fallback assertion 세대 다수 | #1094·#1096 뒤 #1098 핵심 |
| `tests/test_ledger.py` | 600 | ledger current/legacy/mixed/corrupt | compatibility fixture 비중 큼 | #1094 핵심; 4개 안전 시나리오 보존 |
| `tests/test_loop_diagnose.py` | 679 | cross-project 진단 | compatibility와 무관 | 현행 |
| `tests/test_multisession_smoke.py` | 647 | 동시 run smoke | 현행 concurrency safety | 유지 |
| `tests/test_outcome_scorecard.py` | 574 | outcome aggregation | legacy verdict fixture 일부 | #1094 후 #1098 |
| `tests/test_parallel_wave.py` | 833 | wave 후보 계산 회귀 | fan-in-only 12개 fixture를 제거하고 부재 계약 1개만 유지 | 현행 compute/claim/merge-lock 계약 유지 |
| `tests/test_product_journey.py` | 610 | journey runner | compatibility와 무관 | 현행 |
| `tests/test_provider_chain.py` | 1,466 | provider chain 상태전이 | 현행 provider 성공·변경 전 실패·변경 후 실패 안전 경계 | #1095에서 legacy route 제거, safety fallback 보존 |
| `tests/test_run_review.py` | 1,590 | run review current/legacy 분석 | local persisted-run writer를 #1098에서 공통 helper로 통합; reader별 assertion은 유지 | #1098 fixture 책임 감량 완료 |
| `tests/test_session_state.py` | 3,510 | state/CLI/run lifecycle | private re-export fixture는 #1094에서 canonical owner import로 전환; persisted safety fixture 유지 | #1094 완료 뒤 #1098 |
| `tests/test_story_runner.py` | 545 | story runner lifecycle | 현행 stack fixture | #1097 뒤 #1098 |
| `tests/test_surface_docs_sync.py` | 1,005 | agent/docs/Codex mirror sync | legacy design leniency 문자열 assertion 포함 | #1093 후 #1098 |
| `tests/test_tdd_guard.py` | 816 | central/generated TDD guard | partial install fallback fixture가 실사용 | #1096 후 #1098, TDD invariant 보존 |

실제 감량 우선순위는 `ledger/run_review/session_state`와 대응 테스트의 다세대 persisted 형식, provider routing의 소비자 없는 preset/export, design legacy authoring·reader, install partial-state 증거다. archive·release data·safety eval·concurrency·journey 파일은 크기만으로 선택하지 않는다.

## #1098 persisted-run fixture 책임 통합

#1094/PR #1119는 canonical `ledger.jsonl` writer와 실제 표본이 남은 legacy `.steps.jsonl` reader를 구분해 보존했다. 그 뒤 call/import scan에서 제품 호출자가 아닌 `tests/test_run_review.py`, `tests/test_benchmark_aggregate.py`, `tests/test_design_run_records.py`가 같은 run 경로 생성, prose 절대경로 치환, SHA-256 receipt 작성을 세 번 구현하고, legacy row writer도 두 번 구현한 사실을 확인했다. 크기 자체가 아니라 선행 정책 퇴역 결과와 3개 reader의 동일 persisted contract가 cleanup 근거다.

5개 로컬 fixture writer를 `tests/run_fixtures.py`의 canonical/legacy helper 2개로 통합했다. run review의 current·legacy·mixed·invalid receipt, fleet verdict 집계, design durable record 시나리오와 각 assertion은 그대로 두어 검증 범위를 줄이지 않았다. helper 책임 수는 5→2, code+test LOC는 70,710→70,689로 21줄 순감하며 단순 파일 분할은 없다. 새 public surface와 제품 동작 변경도 없다.

Safety invariant는 영향 경로를 달리해 보존한다. persisted state 관련 369개와 전체 1,980개 unit test가 통과했고, order gate·file/external-state boundary·TDD guard·install path는 각각 hooks, agent-boundary, tdd-guard, generated-hook 전체 회귀와 guard-efficacy 39/39로 확인했다. static quality, 문서·public-surface·manifest, release artifact smoke도 통과했으며 최종 명령은 #1098 PR Test Plan과 issue close audit에 남긴다.

## #1099 integration audit와 one-shot surface 퇴역

최종 main 재측정에서 #1092 baseline 69,865줄보다 #1098 merge 시점이 70,689줄로 824줄 많았다. 개별 cleanup의 순감만 나열해 이 차이를 숨기지 않고, 원인을 같은 정의로 분해했다. baseline을 재기 위해 추가한 `scripts/policy_cleanup_baseline.py`와 전용 테스트가 579줄을 차지했고, 병행 feature의 Python code/test 추가가 정책 cleanup의 감소분을 상쇄했다.

#1099는 측정을 마친 one-shot 구현·테스트 579줄을 lifecycle 단위로 종료했다. 전수 symbol/doc scan에서 runtime caller가 0이고 테스트만 소비하던 `parallel_wave.fan_in_check`·`WorkerResult`·`FanInResult`도, 현행 독립 peer의 claim board·merge lock 계약과 분리해 구현 134줄과 fan-in 전용 테스트 순 145줄을 제거했다. 이 PR의 code+test는 70,689→69,831로 858줄 순감하며, #1092 baseline보다도 34줄 작다. 파일 분할은 없고 compatibility 후보는 baseline 15→최종 10이다.

`RUN-009`는 #1092 원장에서 누락된 single-session fan-in policy fossil이다. #1099에서 미분류 상태를 숨기지 않고 machine inventory에 추가한 뒤 곧바로 `퇴역 완료`로 닫았다. 현행 `compute_waves`, 별도 interactive peer, claim board, merge lock과 관련 safety test는 유지한다. one-shot 측정 구현도 public command·agent·mode·gate가 아니며, 제거 뒤 외부 배포물에는 fan-in symbol과 self-only 계측 코드가 모두 남지 않는다.

## 후속 범위 완전성

| 후속 | inventory 입력 | 책임 |
|---|---|---|
| #1093 | DES-001~006 | design authoring·reader·warning·validator·배포 |
| #1094 | RUN-001~009 | ledger/prose/alias/verdict/session state + 누락 fan-in fossil |
| #1095 | ROUTE-001~005 | schema/preset/export/provider fallback |
| #1096 | INST-001~005 | generated hook/partial install/root/path/worktree |
| #1097 | LIFE-001~005 | current writer/legacy stories/no-AC issue/human/advisory |
| #1098 | 위 500줄 이상 감사의 정책 제거 후 중복 책임 | 단순 분할이 아닌 assertion/helper 통합 |
| #1099 | baseline JSON과 30개 원장 전항목 | 동일 정의 재측정·누락 fan-in 퇴역·전체 gate·부모 close audit |

machine validator 결과는 30/30 entry가 정확히 하나의 정책 영역에 배정되고 중복 ID가 없으며, 현재 남은 10/10 한시 호환 entry가 4요소를 갖춘다. `265e538`의 대형 파일 58/58도 표에서 유지·정책 cleanup·#1098 검토 중 하나로 판정했다. #1099에서 발견한 `RUN-009`까지 terminal 분류해 어느 범위에도 속하지 않은 후보는 없다.

## Codebase Sanity receipt

- revision: `b676140bcffdaa5843ce59198ecef4f997efddc9`
- semantic scope: full tracked repository의 policy compatibility와 500줄 이상 major text; archive와 external active-project 절대경로는 read-only·비식별 집계
- 기계 증거: baseline command exit 0, full unit suite exit 0, 118.693초, detached clean tree
- coverage: `UNKNOWN` — repository에 full-suite coverage 도구·리포트가 없어 test 수나 green으로 추정하지 않음
- 분류: removable 4, temporary compatibility 11, current 14; unknown 0
- replacement hygiene: 현행 writer와 legacy reader를 분리했고 새 writer가 legacy 형식을 생성한다고 판정한 항목은 없음
- warning 경계: legacy marker 자체는 warning/후속 입력이며 소비자 증거 없이 dead code로 승격하지 않음

새 public command·agent·mode·workflow·상설 hard gate는 만들지 않았다. baseline 스크립트는 #1092/#1099 비교 완료와 함께 퇴역했고, 현행 peer 배포 경로는 `harness/parallel_wave.py`의 `compute_waves` + `dcness-helper` claim board + `pr-finalize.sh` merge lock으로만 남는다.
