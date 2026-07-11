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
EVAL_RUNS=3 bash evals/run.sh        # 케이스당 3회 반복 (릴리즈 전 권장)
EVAL_RUNS=3 EVAL_RELEASE_CHECK=1 bash evals/run.sh  # 핵심 실사고 케이스 N/N 확인
EVAL_MODEL=opus bash evals/run.sh    # 검수/채점 모델 변경 (기본 sonnet)
EVAL_OUTPUT_DIR=/tmp/dcness-evals bash evals/run.sh # 산출물 저장 위치 지정

# judge 보정 — 먼저 run 출력 디렉터리에 사람이 judge-golden.json 을 작성한다
python3 evals/calibrate_judge.py .metrics/evals/run-YYYYMMDDTHHMMSSZ-PID
python3 evals/calibrate_judge.py /tmp/dcness-evals --golden /tmp/dcness-evals/judge-golden.json --min-agreement 0.9 --report-file /tmp/dcness-evals/judge-calibration.md
```

`guard_efficacy.py` 는 범주별 pass/fail count 를 출력한다. `provider-agnostic-order-gate`
와 `provider-agnostic-tdd` 범주는 Claude Agent hook 이 아닌 `begin-step`/headless worker
경로에서도 같은 불변식이 발화하는지 재현한다. `known-bypass-boundary` 범주는 "보호됨" 이
아니라 문서화된 한계가 실제로 한계로 남아 있음을 드러내는 항목이다.

케이스마다 `정답 k/N` 표가 출력된다. 어떤 케이스든 정답 0회면 exit 1 — 방금 바꾼 지침이 보호를 깨먹었는지 확인한다.
릴리즈 점검에서는 `EVAL_RELEASE_CHECK=1`을 함께 켜고 `shorts-real-spec`, `headless-prose-quality`
같은 핵심 실사고 케이스가 N/N으로 통과해야 한다. 이 기준은 새 CI 게이트가 아니라
[`docs/internal/self-improvement-loop.md`](../docs/internal/self-improvement-loop.md)의
Verify 슬롯을 사람이 도는 릴리즈 전 권고다.

실행 산출물은 기본적으로 `.metrics/evals/run-<timestamp>-<pid>/`에 저장된다. 각 케이스
디렉터리 아래 `run-<N>-report.md`는 블라인드 검수 보고, `run-<N>-judge.md`는 judge 채점
출력이다. MISS가 나면 두 파일을 대조해 agent 결함인지 judge 결함인지 분리한다. 이 파일은
[#875](https://github.com/alruminum/dcNess/issues/875)의 추세 집계와
[#894](https://github.com/alruminum/dcNess/issues/894)의 judge 보정 입력으로 소비된다.
동시에 `guard-telemetry.jsonl` 에 케이스별 `eval_case_result` 이벤트를 append 한다.
이 이벤트에는 pass/fail 뿐 아니라 블라인드 검수와 judge 호출 2회를 기준으로 한
`llm_turns`, 보고서/judge 출력 길이, 추정 출력 token 이 함께 기록된다.
`dcness-helper guard-telemetry` 는 이 이벤트를 읽어 최근 window 에서 장기간 만점인
케이스를 **노후 후보**로 표시하고 평균 turn/token effort 를 함께 보여준다. 이 표시는
케이스 삭제나 비활성화를 자동 실행하지 않는다.
기본 산출 위치인 `.metrics/evals/**` 는 자동 집계 대상이다. `EVAL_OUTPUT_DIR` 를 repo 밖으로
지정한 경우에는 `dcness-helper guard-telemetry --base-dir <EVAL_OUTPUT_DIR>` 로 그 산출물을 직접 본다.

## judge 보정 — 사람 golden 과 채점 모델 대조

`run-N-judge.md` 자체가 맞는지도 소수 케이스에서 따로 확인한다. 절차는 표면화까지만 한다.
`calibrate_judge.py` 는 judge 모델, prompt, eval 설정을 수정하지 않는다.

1. `bash evals/run.sh` 를 실행해 `.metrics/evals/run-.../<case>/run-N-report.md` 와
   `run-N-judge.md` 를 남긴다.
2. `evals/judge-golden.example.json` 을 해당 run 디렉터리의 `judge-golden.json` 으로 복사한 뒤,
   사람이 `run-N-report.md` 를 읽고 각 기대 ID 의 정답 라벨을 `OK` / `MISS` 로 채운다.
   `result` 는 생략 가능하다. 생략하면 모든 기대가 `OK` 일 때 `PASS`, 하나라도 `MISS` 면
   `FAIL` 로 파생한다.
3. `python3 evals/calibrate_judge.py <run-dir>` 를 실행한다. 기본 임계는 `--min-agreement 1.0`
   이며, 일치도가 임계 미만이면 `judge_review_candidate: YES` 로 표시하고 exit 1 을 반환한다.
   임계는 `--min-agreement 0.9` 처럼 조정할 수 있다.

golden 파일 형식:

```json
{
  "labels": [
    {
      "case": "shorts-real-spec",
      "run": 1,
      "expectations": {
        "E1": "OK",
        "E2": "OK"
      }
    }
  ]
}
```

`case` + `run` 은 `<run-dir>/<case>/run-<run>-judge.md` 를 가리킨다. 특수 경로를 비교할 때는
`judge_file` 에 run 디렉터리 기준 상대 경로나 절대 경로를 넣을 수 있다. 리포트는 stdout 으로
나오며, `--report-file <path>` 를 주면 같은 내용을 파일로도 남긴다. JSON 소비가 필요하면
`--json` 을 사용한다.

## 채점 원리 — 정답표는 계약 수준으로만 쓴다

각 케이스의 `expected.md` 는 **제품이 뭘 막아야 하는가**만 적는다. 어떤 agent 가 어떤 문구로 잡는지는 적지 않는다 — agent 역할과 지침 문구는 계속 바뀌지만 제품 약속은 바뀌지 않으므로, 정답표를 계약 수준에 두면 역할 개편에서 살아남는다.

- `[MUST]` — 그 취지의 결함이 보고 어딘가에서 지적돼야 충족.
- `[MUST_NOT]` — 그 취지의 결함을 지적하지 않아야 충족. **다른 이유의 결함 지적은 무관** (최종 PASS/FAIL 글자가 아니라 축별로 채점하는 이유).

실행은 2단이다: (1) 블라인드 검수 — `prompt.md` 의 prompt 로 agent 를 실행하되 기대 결과를 누설하지 않는다. fixture 는 정답표를 뺀 불투명 이름의 sandbox 로 복사해 전달한다. (2) judge 채점 — 검수 보고와 정답표만 주고 기대별 OK/MISS 를 판정시킨다.

블라인드의 한계: 검수 agent 는 지침 문서를 읽기 위해 repo 접근 권한을 가지므로, 일부러 `evals/cases/**` 의 정답표를 찾아가 읽는 것까지 막지는 않는다. 본 eval 의 위협 모델은 우리 자신의 지침 회귀 측정이지 적대 agent 방어가 아니다 — prompt 가 지시하지 않은 경로 탐색이 의심되면 judge 입력의 검수 보고에서 근거 인용을 확인한다.

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

> L3 실사고 케이스의 축 한계 — 정직하게 기록한다:
> - **순서 축은 깨끗하게 재현된다**: 핵심 약속(완성 쇼츠) 검증이 뒤 story 로 밀린 것을 지금 지침이 reliable 하게 잡는다(3/3). 이게 youTubeGenerator #214 의 설계단 원인이다.
> - **행동적 분할 축은 이 실 backlog 에서 경계선이라 MUST 로 두지 않았다**: 각 story 가 app 화면 하위 동작을 일부 내므로 "앞 story 에 동작이 전무"라는 주장이 깔끔하게 참이 아니다. 무리해서 MUST 로 두면 케이스가 1/3 로 흔들린다(실측). 깨끗한 신호만 잠근다.
> - **설계단 architecture-validator 수직 슬라이스 축에서는 재현되지 않는다**: 그 epic 의 impl 설계(Story 3 완전 세트)는 수직 슬라이스가 완결돼 validator 가 정합 PASS 했고, 실패는 런타임/검수 단계에서 났다. architecture-validator 축의 실데이터 케이스는 그 축에서 실제 사고가 나면 추가한다.
