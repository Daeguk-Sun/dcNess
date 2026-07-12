# 2026-07 lean ablation — TOOL_REPEAT_HIGH lesson metadata

## 후보와 안전 경계

외부 활성 프로젝트 2곳의 finished run 26개에서 `TOOL_REPEAT_HIGH`가 42건
관측됐다. 이 신호가 재발하면 다음 같은 agent/mode의 prompt에 고정 행동 문장과
`hits/last/evidence`를 붙이는 프로젝트-로컬 `[LESSONS]`가 생성된다. 첫 후보는 행동
문장을 제거하는 것이 아니라 가변 메타데이터만 줄이는 선택형 context 축소다. 기대
절감 지표는 input token이며, fixture 기준 20 token과 전체 input의 0.05%를 사전
meaningful 경계로 뒀다.

order, file boundary, external-state mutation, TDD guard는 후보에서 제외했다. 활성
프로젝트의 live run이나 guard를 끄지 않았고, 동일 frozen fixture의 read-only `/tmp`
복사본에서만 shadow와 paired screening을 실행했다.

## deterministic → shadow → paired 결과

재현 명령:

```sh
python3.11 evals/lean_ablation.py \
  evals/lean-ablation/tool-repeat-lesson-metadata.json --json
```

tracked fixture 네 파일의 SHA-256을 record가 검증한다. baseline prompt는 683 bytes,
metadata를 뺀 variant는 576 bytes여서 shadow상 107 bytes가 줄었다. 두 조건의 task,
fixture, response schema, provider/model(`openai-codex` / `gpt-5.6-sol`, medium)은
동일했다.

| 조건 | 제품 AC | MUST-FIX / 회귀 / 사람 개입 | 동일 tool/input 반복 | input token (cached) | output token | wall-clock |
|---|---:|---:|---:|---:|---:|---:|
| baseline 1회 | 2/2 | 0 / 0 / 0 | 0 | 38,874 (24,064) | 355 | 15.36s |
| metadata 축소 1회 | 2/2 | 0 / 0 / 0 | 0 | 40,659 (26,112) | 366 | 13.81s |

variant는 품질 gap을 만들지 않았지만 사전 주지표 input token이 1,785 증가했다.
wall-clock 1.55초 감소는 단일 표본 변동과 충돌하며 remove 근거로 쓰지 않는다.
첫 pair에서 주지표 절감이 음수로 명확했으므로 추가 1+1을 실행하지 않았다.
2026-07 epic 공통 추가 LLM trial 누계는 2/4이고, #1070 paired screening은 같은 달에
실행하지 않았다. 지원되지 않는 모델명으로 inference 전에 HTTP 400이 난 preflight는
trial에 포함하지 않았다.

## 결정

결정은 **keep**이다. `TOOL_REPEAT_HIGH` 행동 문장과 `hits/last/evidence` 메타데이터를
현행 유지한다. 107-byte shadow 절감은 실제 총 input token 감소로 재현되지 않았고,
개인 판단용 단일 fixture라 일반 우위나 열위를 주장하지 않는다. 후속 조치는 남은
7월 trial을 소진하지 않고, 다른 달에 telemetry가 다시 후보로 올릴 때만 재평가하는
것이다. 원시 조건·수치·한계는
`evals/lean-ablation/tool-repeat-lesson-metadata.json`과 `evidence/`가 보존한다.
