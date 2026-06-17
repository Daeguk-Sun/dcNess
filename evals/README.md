# eval 하네스

dcness 자체 QA 도구다. plug-in 배포물이 아니다.

eval 은 두 종류로 나눈다.

- **결정적 guard-efficacy** — hook/function 진입점을 LLM 없이 호출해 file boundary,
  Bash/MCP mutation, order gate, TDD guard 의 allow/block 동작을 fixture 로 확인한다.
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
EVAL_MODEL=opus bash evals/run.sh    # 검수/채점 모델 변경 (기본 sonnet)
```

`guard_efficacy.py` 는 범주별 pass/fail count 를 출력한다. `known-bypass-boundary`
범주는 "보호됨" 이 아니라 문서화된 한계가 실제로 한계로 남아 있음을 드러내는 항목이다.
예: TDD guard 는 `Edit`/`Write`/`NotebookEdit` 직접 파일 도구에만 걸리고 Bash 로 만든
구현 파일에는 매칭 테스트 존재 검사를 하지 않는다.

케이스마다 `정답 k/N` 표가 출력된다. 어떤 케이스든 정답 0회면 exit 1 — 방금 바꾼 지침이 보호를 깨먹었는지 확인한다.

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

> L3 실사고 케이스의 축 한계 — 정직하게 기록한다:
> - **순서 축은 깨끗하게 재현된다**: 핵심 약속(완성 쇼츠) 검증이 뒤 story 로 밀린 것을 지금 지침이 reliable 하게 잡는다(3/3). 이게 youTubeGenerator #214 의 설계단 원인이다.
> - **행동적 분할 축은 이 실 backlog 에서 경계선이라 MUST 로 두지 않았다**: 각 story 가 app 화면 하위 동작을 일부 내므로 "앞 story 에 동작이 전무"라는 주장이 깔끔하게 참이 아니다. 무리해서 MUST 로 두면 케이스가 1/3 로 흔들린다(실측). 깨끗한 신호만 잠근다.
> - **설계단 architecture-validator 수직 슬라이스 축에서는 재현되지 않는다**: 그 epic 의 impl 설계(Story 3 완전 세트)는 수직 슬라이스가 완결돼 validator 가 정합 PASS 했고, 실패는 런타임/검수 단계에서 났다. architecture-validator 축의 실데이터 케이스는 그 축에서 실제 사고가 나면 추가한다.
