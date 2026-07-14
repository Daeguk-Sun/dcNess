# eval 하네스

dcness 자체 QA 도구다. plug-in 배포물이 아니다.

eval 은 두 종류로 나눈다.

- **결정적 guard-efficacy** — hook/function/wrapper 진입점을 LLM 없이 호출해 file boundary,
  Bash/MCP mutation, order gate, TDD guard, headless provider 경로의 allow/block 동작을
  fixture 로 확인한다.
- **LLM 행동 eval** — agent 지침 변경이 기존 보호를 깨먹는지, 실제 agent 실행으로
  "agent 가 그 기준대로 실제 판정하는가"를 확인한다.

문서 계약 테스트(`tests/` — 문구가 살아있는가), 결정적 guard-efficacy, LLM 행동 eval 은
서로 다른 범위다. guard 성능 주장은 결정적 suite 로 재현하고, agent 지침 회귀는 LLM
행동 eval 로 본다.

## 언제 돌리나

- guard/hook 동작, 순서 차단, 외부 상태 변경 차단, TDD guard 를 수정하는 PR 의 머지 전
  `python3 evals/guard_efficacy.py` 1회
- `agents/**` 또는 `skills/**` 지침을 변경하는 PR 의 머지 전 1회
- 플러그인 릴리즈 직전 1회

권고이며 CI 차단 게이트가 아니다. 결정적 suite 는 비용 없이 재현 가능하지만 adversarial
fixture 범위만 보며, LLM 행동 eval 은 매 실행 조금씩 다르고 비용이 든다. 그래서 둘 다
측정 + 사용자 개입 영역에 둔다.

## 어떻게 돌리나

```sh
python3 evals/guard_efficacy.py        # 결정적 guard-efficacy suite (LLM 호출 없음)
python3 evals/guard_efficacy.py --json # 범주별 pass/fail JSON

bash evals/run.sh                    # 전 케이스 1회씩
bash evals/run-core.sh               # versioned 핵심 실사고 subset만 1회씩
EVAL_RUNS=3 bash evals/run.sh        # 케이스당 3회 반복 (릴리즈 전 권장)
EVAL_RUNS=3 EVAL_RELEASE_CHECK=1 bash evals/run.sh  # 핵심 실사고 케이스 N/N 확인
EVAL_MODEL=opus bash evals/run.sh    # 검수/채점 모델 변경 (기본 sonnet)
EVAL_OUTPUT_DIR=/tmp/dcness-evals bash evals/run.sh # 산출물 저장 위치 지정
EVAL_PARALLEL=8 bash evals/run.sh    # (case, run) 셀을 최대 8개까지 병렬 실행 (기본 4, 1=직렬 안전판)

# judge 보정 — blind report 생성 후 사람이 versioned golden을 작성·확인한다
python3 evals/calibrate_judge.py .metrics/evals/run-YYYYMMDDTHHMMSSZ-PID --expect-golden-version example-human-v1 --expect-subset-version example-subset-v1
python3 evals/calibrate_judge.py /tmp/dcness-evals --golden /tmp/dcness-evals/judge-golden.json --expect-golden-version example-human-v1 --expect-subset-version example-subset-v1 --min-agreement 0.9 --report-file /tmp/dcness-evals/judge-calibration.md

# 저장된 core 후보 — owner 확인 전에는 의도적으로 exit 2
python3 evals/calibrate_judge.py evals/calibration/core-incidents-v1 --golden evals/golden/core-incidents-v1.json --expect-golden-version core-incidents-v1-human-v1 --expect-subset-version core-incidents-v1
```

`run.sh` 는 `(case, run)` 셀이 서로 독립인 점을 이용해 셀 단위로 병렬 실행한다. 셀 내부의
report→judge 순서만 유지하고, 동시 셀 상한은 `EVAL_PARALLEL`(기본 4)로 조절한다.
`EVAL_PARALLEL=1` 은 셀을 하나씩 도는 직렬 실행이며 병렬화 회귀가 의심될 때의 안전판이다.
headless `claude -p` quota 는 메인 세션과 공유되므로 상한은 보수적으로 둔다. 집계는 shell
카운터가 아니라 셀별 marker 파일로 하므로 병렬/직렬 pass·fail 판정은 동일하다.

`guard_efficacy.py` 는 범주별 pass/fail count 를 출력한다. `provider-agnostic-order-gate`
와 `provider-agnostic-tdd` 범주는 Claude Agent hook 이 아닌 `begin-step`/headless worker
경로에서도 같은 불변식이 발화하는지 재현한다. `known-bypass-boundary` 범주는 "보호됨" 이
아니라 문서화된 한계가 실제로 한계로 남아 있음을 드러내는 항목이다.

케이스마다 `정답 k/N` 표가 출력된다. 어떤 케이스든 정답 0회면 exit 1 — 방금 바꾼 지침이 보호를 깨먹었는지 확인한다.
릴리즈 기본 subset은 [`core-incident-subset.json`](core-incident-subset.json)의
`shorts-real-spec`, `headless-prose-quality`다. 첫 케이스는 실제 제품 순서 사고를, 두 번째는
근거 없는 headless PASS와 rigid output 회귀를 함께 잡는다. 나머지는 전체 suite의 합성 대조군,
cartography 확장 회귀, 또는 중복 축으로 유지하되 개인 릴리즈 기본 calibration 비용에서는 뺀다.
`bash evals/run-core.sh`는 manifest에서 case 목록을 읽고 N/N을 요구한다. 이 기준은 새 CI 게이트가 아니라
[`docs/internal/self-improvement-loop.md`](../docs/internal/self-improvement-loop.md)의
Verify 슬롯을 사람이 도는 릴리즈 전 권고다.
저장된 v1 사람 확인 후보와 report/judge 대조 순서는
[`calibration/core-incidents-v1/README.md`](calibration/core-incidents-v1/README.md)에 있다.

실행 산출물은 기본적으로 `.metrics/evals/run-<timestamp>-<pid>/`에 저장된다. 각 케이스
디렉터리 아래 `run-<N>-report.md`는 블라인드 검수 보고, `run-<N>-judge.md`는 judge 채점
출력이다. MISS가 나면 두 파일을 대조해 agent 결함인지 judge 결함인지 분리한다. 이 파일은
[#875](https://github.com/alruminum/dcNess/issues/875)의 추세 집계와
[#894](https://github.com/alruminum/dcNess/issues/894)의 judge 보정 입력으로 소비된다.
동시에 `guard-telemetry.jsonl` 에 케이스별 `eval_case_result` 이벤트를 append 한다.
이 이벤트에는 pass/fail 뿐 아니라 블라인드 검수와 judge 호출 2회를 기준으로 한
`llm_turns`, 보고서/judge 출력 길이, 추정 출력 token 이 함께 기록된다.
`dcness-helper guard-telemetry` 는 이 이벤트를 읽어 최근 window 에서 장기간 만점인
케이스를 **노후 후보**로, 정답률이 흔들리는(min_runs 이상 시도에서 일부만 통과한)
케이스를 **flaky 후보**로 표시하고 평균 turn/token effort 를 함께 보여준다. 두 표시는
상호배타이며(만점=노후, 부분 통과=flaky, 전패=회귀), 케이스 삭제나 비활성화를 자동
실행하지 않는다. flaky 후보는 `scripts/loop_diagnose.py`(스케줄 sweep·`/run-review`)의
자동 후보 표에도 노후 후보와 함께 올라오므로 사람이 리포트를 직접 치지 않아도 표면화된다.
기본 산출 위치인 `.metrics/evals/**` 는 자동 집계 대상이다. `EVAL_OUTPUT_DIR` 를 repo 밖으로
지정한 경우에는 `dcness-helper guard-telemetry --base-dir <EVAL_OUTPUT_DIR>` 로 그 산출물을 직접 볼 수
있지만, `scripts/loop_diagnose.py` 의 자동 후보 집계에는 포함되지 않는다.

## 실패·재실행 처리 규범

이 절은 행동 eval을 실행하거나 판정하는 모든 dcness 작업 에이전트(Claude·Codex 등)에 동일하게
적용한다.

단발 실패를 뒤이은 재실행 PASS로 덮어 "통과"로 닫지 않는다. 재실행은 flaky 여부를 판별하는
수단이지 통과 표본을 고르는 수단이 아니다. 판정이 흔들리면 최초 MISS를 포함하도록 `EVAL_RUNS`를
높여 전체 정답률(`k/N`)을 측정하고, 일부만 통과하면 결과를 flaky로 보고한다. 방금 변경한 diff의
회귀가 아니라는 근거가 있더라도 해당 flaky 신호 자체를 없던 것으로 취급하지 않는다.

flaky로 확정한 후보는 gate 통과 여부와 무관하게 처분을 남긴다. [#1123](https://github.com/alruminum/dcNess/pull/1123)의
flaky 후보 자동 표면화를 거쳐 `scripts/loop_diagnose.py record-decision`으로 `fixed`·`hold`·`rejected`
중 하나를 기록하거나, 근본 원인을 다룰 follow-up을 등록한다. "비결정적 judge miss"처럼 원인을
분류하거나 현재 PR을 계속 진행해도 된다고 판단한 것만으로는 처분이 끝나지 않는다. 후보 소비와
결정 원장은 [`docs/internal/self-improvement-loop.md`](../docs/internal/self-improvement-loop.md)를 따른다.

flaky 판별 재실행은 자동 표면화가 이어지는 기본 `.metrics/evals/**` 위치를 사용한다. 불가피하게
`EVAL_OUTPUT_DIR`를 `/tmp` 등 repo 밖으로 지정하면 위 자동 집계에서 빠지므로, 그 실행을 근거로 한
`record-decision`을 명시적으로 남겨 신호 소실을 막는다.

## judge 보정 — 사람 golden 과 채점 모델 대조

`run-N-judge.md` 자체가 맞는지도 소수 케이스에서 따로 확인한다. 절차는 표면화까지만 한다.
`calibrate_judge.py` 는 judge 모델, prompt, eval 설정을 수정하지 않는다.

1. `bash evals/run.sh` 또는 `bash evals/run-core.sh`를 실행해 `.metrics/evals/run-.../<case>/run-N-report.md` 와
   `run-N-judge.md` 를 남긴다.
2. `evals/judge-golden.example.json` 을 해당 run 디렉터리의 `judge-golden.json` 으로 복사한 뒤,
   사람이 `run-N-report.md` 를 읽고 각 기대 ID 의 정답 라벨을 `OK` / `MISS` 로 채운다.
   각 라벨의 구체적 이유와 report SHA256을 함께 기록하고, golden/subset version, model,
   prompt version, 측정일을 고정한다. 자동 judge 결과를 golden 작성 근거로 사용하지 않는다.
   소유자 확인 전 `verification_status`는 `pending_owner_confirmation`으로 두며 이 상태는 PASS할 수 없다.
   `result` 는 생략 가능하다. 생략하면 모든 기대가 `OK` 일 때 `PASS`, 하나라도 `MISS` 면
   `FAIL` 로 파생한다.
3. `python3 evals/calibrate_judge.py <run-dir> --expect-golden-version <version> --expect-subset-version <version>` 를 실행한다. 두 expected version은 필수이며, 기본 임계는 `--min-agreement 1.0`
   이며, 일치도가 임계 미만이면 `judge_review_candidate: YES` 로 표시하고 exit 1 을 반환한다.
   임계는 `--min-agreement 0.9` 처럼 조정할 수 있다.

전체 schema 예시는 [`judge-golden.example.json`](judge-golden.example.json)에 있다. 필수 상위 필드는
`schema_version: 2`, `golden_version`, `subset_version`, `verification_status`, `measurement`, `labels`다.
각 label은 `report_sha256`, 기대별 `OK`/`MISS`, 같은 기대 ID의 사람 판단 이유를 가져야 한다.
필수 expected golden/subset version이 실제 값과 다르거나 report digest가 달라지면 calibration은
`판정 불가`와 exit 2를 반환하며 PASS하지 않는다.

`case` + `run` 은 `<run-dir>/<case>/run-<run>-judge.md` 를 가리킨다. 특수 경로를 비교할 때는
`judge_file` 에 run 디렉터리 기준 상대 경로나 절대 경로를 넣을 수 있다. 리포트는 stdout 으로
나오며, `--report-file <path>` 를 주면 같은 내용을 파일로도 남긴다. JSON 소비가 필요하면
`--json` 을 사용한다. 출력은 케이스/attempt별 `일치`·`불일치`·`판정 불가`, 전체 분자·분모와
attempt 수를 보여준다. 사람이 report 자체에서 `MISS`로 판정한 항목은
`agent_behavior_regression`, 사람과 judge가 다르게 판정한 항목은
`judge_or_criteria_disagreement`로 분리한다. 어느 결과도 model, prompt, 강제 규칙을 자동 변경하지 않는다.

## 채점 원리 — 정답표는 계약 수준으로만 쓴다

각 케이스의 `expected.md` 는 **제품이 뭘 막아야 하는가**만 적는다. 어떤 agent 가 어떤 문구로 잡는지는 적지 않는다 — agent 역할과 지침 문구는 계속 바뀌지만 제품 약속은 바뀌지 않으므로, 정답표를 계약 수준에 두면 역할 개편에서 살아남는다.

- `[MUST]` — 그 취지의 결함이 보고 어딘가에서 지적돼야 충족.
- `[MUST_NOT]` — 그 취지의 결함을 지적하지 않아야 충족. **다른 이유의 결함 지적은 무관** (최종 PASS/FAIL 글자가 아니라 축별로 채점하는 이유).

실행은 2단이다: (1) 블라인드 검수 — `prompt.md` 의 prompt 로 agent 를 실행하되 기대 결과를 누설하지 않는다. fixture 는 정답표를 뺀 불투명 이름의 sandbox 로 복사해 전달한다. (2) judge 채점 — 검수 보고와 정답표만 주고 기대별 OK/MISS 를 판정시킨다.

블라인드 검수 agent는 원본 repo가 아니라 `docs/`, `skills/`, `agents/`만 복제한 임시
instruction snapshot을 작업 디렉터리로 사용하며, 별도 fixture sandbox만 추가로 읽는다.
따라서 `evals/cases/**`, `evals/golden/**`, calibration 산출물과 원본 repo는 Read/Glob
접근 범위에 들어가지 않는다. judge는 정답표와 보고를 인라인으로 받고 도구를 쓰지 않는다.

## 케이스 추가 절차 — 사고 1건 = 케이스 1개

평소에 케이스를 미리 만들지 않는다. 실제 운영에서 하네스가 못 잡은 사고가 났을 때, 그 입력을 박제한다.

1. `evals/cases/<slug>/` 생성 — 사고 당시의 입력(또는 그 구조를 재현한 fixture)을 넣는다.
2. `prompt.md` 작성 — 검수 대상 agent 지침 파일을 Read 시키는 블라인드 prompt. `{{REPO_ROOT}}`/`{{CASE_DIR}}` placeholder 사용. 기대 결과를 누설하지 않는다.
3. `expected.md` 작성 — 계약 수준 기대만. agent 이름·지침 문구 금지 (회귀 테스트가 검사한다).
4. 가능하면 반대쪽 대조 케이스(잡히면 안 되는 입력)도 쌍으로 만든다.
5. `bash evals/run.sh` 로 현재 지침 기준 정답이 나오는지 확인 후 커밋.

## 케이스 목록

| 케이스 | 입력 | 기대 |
|---|---|---|
| `story-slice-partfirst` | (합성) 기능 영역(인테이크/템플릿/오디오/렌더/업로드) 부품 단위로 잘려 마지막 story 까지 동작이 안 나오는 backlog | 분할·순서 결함이 지적돼야 한다 |
| `story-slice-skeleton` | (합성) 첫 story 가 얇은 end-to-end 골격이고 매 story 가 확인 가능한 증분인 backlog | 분할·순서를 이유로 퇴짜 놓으면 안 된다 |
| `shorts-real-spec` | (L3 실사고) youTubeGenerator v03 쇼츠 epic 의 실제 stories.md — 완성 쇼츠 동작 검증이 Story 3 까지 밀려 런타임 gap(youTubeGenerator #214)이 났던 backlog. 합성 케이스보다 미묘함(각 story 가 표면상 멀쩡) | 순서 결함(첫 완성 동작이 뒤 story 로 밀림)이 지적돼야 한다 (옛 지침은 통과시켰던 입력) |
| `flow-ownership-entrypoint-bad` | (합성) 새 panel/state/helper 가 기존 entrypoint 에 append 되어 owner module, state owner, validation path 가 흐려지는 diff | agent 작업성 결함이 지적돼야 한다 |
| `flow-ownership-owner-good` | (합성) 새 flow owner module 을 만들고 entrypoint 는 dispatch 만 바꾸는 diff | owner module + dispatch 구조 자체를 결함으로 지적하면 안 된다 |
| `module-state-contract-bad` | (합성) same-identity update·source failure 보존·idempotence·producer/consumer scope가 빠진 cross-story 설계 초안 | module-architect가 task 분할 전에 계약/owner/scope/acceptance gap을 보강하거나 적절히 escalate해야 한다 |
| `module-state-contract-good` | (합성) full-state update·source failure 보존·반복 no-change와 producer/consumer scope가 닫힌 설계 초안 | module-architect가 상태성만으로 불필요하게 재설계하거나 checkpoint를 요구하면 안 된다 |
| `cartography-validator-drift` | (합성) Application lifecycle이 data observer를 직접 wiring했지만 Root graph에는 edge가 없는 구현 diff | impl-validator가 as-built drift를 찾고 route-only refresh 범위를 보고하되 직접 문서를 수정하지 않아야 한다 |
| `cartography-refresh` | (합성) system boundary 변화 없이 scheduler entrypoint가 `planned → landed`가 됐고 Root는 stale인 local-only docs 프로젝트 | route-only refresh와 durable handoff를 요구하되 private docs를 code PR에 강제 포함하지 않아야 한다 |
| `cartography-system-checkpoint` | (합성) landed public REST boundary 제거와 capability owner 이동이 섞인 구현 diff | route-only refresh로 흡수하지 않고 system checkpoint 또는 `/design` backpressure를 요구해야 한다 |
| `cartography-no-impact` | (합성) 기존 retry entrypoint 내부 계산만 고치고 route·owner·상태는 Root와 일치하는 diff | 불필요한 refresh 없이 PASS해야 한다 |
| `cartography-mms-system-impact` | (합성) SMS-only topology에 MMS 수신·송신과 multipart storage policy를 추가하는 design 입력 | system checkpoint로 선승격하거나 기존 fallback에서 회수해야 한다 |
| `cartography-acceptance-stale-state` | (합성) 제품 동작 증거는 capability의 landed를 입증하지만 Root에는 planned가 남은 epic acceptance | 사용자 동작 PASS만으로 끝내지 않고 route-only 상태 refresh를 요구해야 한다 |
| `cartography-lifecycle-smoke` | (외부 활성 프로젝트 fixture) design planned/stub부터 impl landed, drift 검출, bounded refresh, acceptance, 다음 design 재대조까지의 전체 trace | #1058 agent 책임과 #1057 workflow 연결이 합쳐져 durable boundary를 순서대로 닫아야 한다 |
| `cartography-producer-contract` | prewritten refreshed Root 없이 module-architect `CARTOGRAPHY_REFRESH`가 직접 bounded patch와 system backpressure를 생산 | workflow routing 문자열이 아니라 실제 producer mode의 입력·write 제한·landed 증거·재검증 handoff를 검증해야 한다 |
| `sanity-lint-green-with-warning` | lint exit 0이지만 unused resource와 redundant scaffold warning이 남은 final candidate | exit code와 warning-free를 구분하고 rework surface를 보고해야 한다 |
| `sanity-coverage-unknown` | test green과 test count만 있고 coverage 도구·리포트가 없는 repo | coverage를 `UNKNOWN`으로 두고 test count로 추정하지 않아야 한다 |
| `sanity-framework-entrypoint` | caller 검색에는 없지만 manifest와 runtime smoke로 도달되는 entrypoint | `framework-reachable`로 분류하고 자동 삭제하지 않아야 한다 |
| `sanity-planned-stub` | 다음 Epic owner와 ADR이 보존 근거인 unused port | intentional stub/planned seam으로 분류하고 자동 삭제하지 않아야 한다 |
| `sanity-stale-old-path` | 새 coordinator landing 뒤 old manifest/resource/test 경로가 남은 replacement | 구현자 self-report와 독립적으로 stale path를 찾아 quality-gap/rework로 연결해야 한다 |
| `sanity-clean-refactor` | old surface 전부 제거, 현재 owner seam과 실제 coverage 근거가 있는 refactor | 근거 없는 dead-code finding 없이 clean PASS해야 한다 |
| `sanity-next-design-stale-receipt` | 직전 receipt 이후 affected module hotfix가 들어온 다음 Epic design | stale receipt를 재사용하지 않고 affected scope Sanity와 별도 Cartography 현재 코드 대조를 수행해야 한다 |
| `sanity-lifecycle-smoke` | Sanity PASS, bounded Cartography refresh/revalidation, acceptance 뒤 code commit이 추가된 trace | 정해진 순서를 인정하되 code change가 모든 code review evidence를 stale하게 만들어 Sanity부터 재진입시켜야 한다 |

> L3 실사고 케이스의 축 한계 — 정직하게 기록한다:
> - **순서 축은 깨끗하게 재현된다**: 핵심 약속(완성 쇼츠) 검증이 뒤 story 로 밀린 것을 지금 지침이 reliable 하게 잡는다(3/3). 이게 youTubeGenerator #214 의 설계단 원인이다.
> - **행동적 분할 축은 이 실 backlog 에서 경계선이라 MUST 로 두지 않았다**: 각 story 가 app 화면 하위 동작을 일부 내므로 "앞 story 에 동작이 전무"라는 주장이 깔끔하게 참이 아니다. 무리해서 MUST 로 두면 케이스가 1/3 로 흔들린다(실측). 깨끗한 신호만 잠근다.
> - **설계단 architecture-validator 수직 슬라이스 축에서는 재현되지 않는다**: 그 epic 의 impl 설계(Story 3 완전 세트)는 수직 슬라이스가 완결돼 validator 가 정합 PASS 했고, 실패는 런타임/검수 단계에서 났다. architecture-validator 축의 실데이터 케이스는 그 축에서 실제 사고가 나면 추가한다.
