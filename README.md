# dcNess

> Claude Code와 Codex를 실제 제품 개발 루프에 묶는 agent workflow harness.

> **Spec(SSOT)**: [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)

dcNess는 Claude Code와 Codex를 제품 개발 루프로 묶는 agent workflow harness입니다.

프롬프트로 "잘 지켜달라"고 부탁하는 대신 — hook, 역할 경계, 순서 게이트, TDD guard, 검증 가능한 작업 기록으로 설계 → 구현 → 검증 → 리뷰 흐름을 강제합니다.

dcNess는 Git, PR, CI 흐름 안에서 Claude Code와 Codex를 실제 제품 개발에 쓰려는 개발자를 위한 도구입니다.

모델의 코딩 능력을 의심해서 가두는 도구가 아니다. 실제 팀에서 되돌리기 어려운 경계만 코드로 붙든다. 어떤 해법을 고를지는 모델에게 맡기고, 어떤 순서로 어디까지 손댈지는 harness가 막는다.

## 무엇을 강제하나

| Claude Code 가 하려는 것 | dcNess 의 반응 |
|---|---|
| 테스트 없이 구현 코드부터 작성 | **TDD guard**: 매칭 test/spec 파일이 없으면 구현 파일 쓰기를 막는다 |
| 검증을 건너뛰고 리뷰/PR 로 이동 | **순서 게이트(order gate)**: 앞 단계 완료 기록이 없으면 다음 agent 단계로 못 넘어간다 |
| 맡은 범위 밖 파일 수정 | **역할 경계(role boundary)**: agent 별 write/read 허용 경계 밖이면 차단한다 |
| `main` 에 바로 커밋·push | `branch → PR` 경로로만 통과 |

여기서 hook은 Claude Code의 tool 호출 전후, git commit/push, CI event 같은 실행 지점에 붙는 작은 검사다. order gate는 현재 run의 단계 기록을 보고 "지금 이 agent가 호출될 차례인가"를 확인한다. TDD guard는 테스트를 실행하는 장치가 아니라, 구현 파일을 쓰기 전에 대응 test/spec 파일이 먼저 존재하는지를 확인하는 장치다.

## 어떻게 작동하나

dcNess가 개입하는 지점은 좁다. 코드 구조, 라이브러리 선택, 구현 전략은 모델 판단에 맡기고, 지금 대충 넘어가면 나중에 수정 비용이 커지는 경계만 막는다.

1. `/spec → /design → /impl → /acceptance` 흐름에서 필요한 단계만 올린다.
2. 각 단계는 agent 역할과 파일 경계를 갖는다.
3. agent가 낸 판단은 자유 prose로 남기고, 메인 Claude가 직접 읽고 다음 단계를 정한다.
4. run 단위 기록을 남겨 나중에 어떤 판단과 단계가 있었는지 되짚을 수 있게 한다.

## 모델을 과소평가하지 않는다

모델은 빠르게 좋아지고 있다. 예전이라면 사람이 방향을 하나하나 정해 주고 규칙으로 못 박아야 했던 판단도, 요즘 모델은 스스로 충분히 해낸다. dcNess 는 그 변화에 맞춰, 모델이 좋아질수록 그 자율성을 최대한 존중하는 쪽으로 설계했다. 지시를 과하게 채우거나 두꺼운 페르소나를 씌우면 모델이 자기 판단을 접고 시키는 대로만 움직이기 쉽고, 프롬프트가 길어진 만큼 토큰도 더 든다. 그래서 꼭 필요한 경계만 코드로 남기고, 나머지 판단은 모델에게 맡긴다.

구체적으로는, 코드로 막는 건 위에서 말한 두 경계(작업 순서·접근 영역)뿐이고, 나머지 방향은 전부 자연어 지침으로만 준다. 에이전트에게 주는 지침도 "이 양식대로 출력해라" 가 아니라 "이런 걸 살펴봐라" 에 가깝다. 예를 들어 구현 에이전트에게는 "요구에 없는 추상화나 방어 로직을 덧붙이지 마라" 정도로 방향만 주고, 실제로 어떻게 할지는 모델이 정한다.

- 에이전트에 억지 페르소나를 씌우지 않는다. 지침은 역할과 봐야 할 판단 기준만 담는다.
- 결과를 정해진 양식(JSON 등)에 채우게 하지 않는다. 에이전트는 판단과 근거를 자연어로 쓴다.
- 그 글은 메인 Claude 가 직접 읽고 다음 단계를 정한다. 결론을 뽑으려 정규식이나 별도 판정용 모델을 끼우지 않는다.
- 분기 규칙마저 강제가 아니라 권고다. 되돌리기 힘든 순서·경계만 코드로 막고, 그 안의 판단은 모델에게 맡긴다.

## 코드만 남기지 않는다

잘 굴러가는 팀은 결과물만 남기지 않는다. 왜 그렇게 정했는지는 이슈에, 무엇을 어떻게 바꿨는지는 PR 에 남긴다. dcNess 의 작업 흐름도 그대로다. 모든 작업이 이슈 하나와 PR 하나로 묶여서, 결정의 근거와 변경 내용이 저장소 히스토리에 함께 쌓인다. 나중에 "이 코드가 왜 이렇게 됐지" 를 물으면, 따로 관리하는 ADR 문서가 아니라 실제 이슈와 PR 이 답이 된다.

## 지금 제대로 물려 있는지 확인

설치 후에는 `/init-dcness`가 출력하는 진단표를 먼저 본다. 핵심 항목이 `PASS`, `FAIL`이 0이면 harness가 현재 프로젝트에 정상 연결된 상태다. `WARN`은 선택형 CI workflow 미설치, 최근 fail-open 감지처럼 즉시 차단은 아니지만 확인할 신호다.

```text
[dcness] === 외부 활성 프로젝트 진단 ===
  [PASS] whitelist 활성: 활성
  [PASS] git hook 정합: 설치됨
  [PASS] Codex skill 정합: 설치됨
  [WARN] hook fail-open 진단: 최근 24시간 1건
  [PASS] routing 설정: 유효
[dcness] 요약: 4 PASS / 1 WARN / 0 FAIL
```

fail-open은 hook이 정책 판단을 못 해서 차단 대신 통과한 의심 이벤트다. dcNess는 이런 이벤트를 `<project>/.claude/harness-state/fail-open-events.jsonl`에 기록하고, 진단표에서 최근 24시간 count와 reason category를 `WARN`으로 보여준다.

## Evidence

[![guard-efficacy](https://github.com/Daeguk-Sun/dcNess/actions/workflows/guard-efficacy.yml/badge.svg)](https://github.com/Daeguk-Sun/dcNess/actions/workflows/guard-efficacy.yml)

<!-- public-evidence-snapshot {"plugin_version":"0.23.0","measured_at":"2026-07-15","unit_tests":{"passed":1901,"total":1901},"guard":{"passed":39,"total":39},"source_project_count":2} -->

현재 공개 snapshot은 **v0.23.0, 2026-07-15 측정**이다. 숫자마다 분모와 source 수를
붙이고, 서로 다른 evidence 영역을 합산하거나 대신 쓰지 않는다.

| evidence 영역 | 관측 결과 | denominator / source | 재현 명령 | 이 수치가 말하지 않는 것 |
|---|---|---|---|---|
| 하네스·기계적 guard | unittest 1,901/1,901 PASS, 결정적 guard 39/39 PASS | test 1,901, guard case 39 / dcNess checkout 1 | `node scripts/check_public_evidence.mjs` | 보안 증명이나 제품 성공률이 아니다 |
| Agent effectiveness | 실측 개선 관측 — 오경로 `1→0`, 영향 과다 포함 `2→0`, 전체 탐색 tool `15→13`; fixture task AC `7/8→8/8` | task×variant run 4, task 2 / 실측 fixture 1 | [`docs/internal/outcome-baseline.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/docs/internal/outcome-baseline.md#2026-07-13-agent-effectiveness-실측-paired-screening)의 trace→record 재현 명령 | model `claude-sonnet-4-6` 단일 frozen fixture 1회 paired 실측(1+1). downstream MUST-FIX·회귀·사람 복구·context 재작업·cross-session은 실행하지 않아 측정 불가다. 1차 거부와 2차 채택 trace는 host metadata를 비식별화했고 세션 ID·SHA-256·capture/rebuild 명령이 provenance에 있다. 공개 우위 주장이 아니다 |
| PR·validator 운영 | finished run 26/28, measurable PR merge 7/7, validator verdict 33건 | candidate run 28 / 외부 활성 프로젝트 2 | [`docs/internal/outcome-baseline.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/docs/internal/outcome-baseline.md#재현-명령)의 source-ref 고정 명령 | merge와 validator FAIL은 과정 evidence이지 제품 outcome이 아니다 |
| 실제 제품 outcome | non-UI journey 1/1 PASS, 제품 AC 1/1 | journey 1, AC 1 / 외부 활성 프로젝트 1 | [`docs/internal/outcome-baseline.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/docs/internal/outcome-baseline.md#2026-07-12-non-ui-제품-journey-pilot)의 receipt 집계 명령 | 단일 pilot이며 일반 제품 성공률이나 공개 우위가 아니다 |
| 비용·경량화 | prompt 107 bytes 축소에도 input token 38,874→40,659; **keep** | baseline/variant trial 2 / frozen fixture 1 | `python3.11 evals/lean_ablation.py evals/lean-ablation/tool-repeat-lesson-metadata.json --json` | 단일 pair의 wall-clock·token 변동을 일반 비용 우위로 쓰지 않는다 |

결정 완전성 회고는 실제 작업 2건에서 불필요한 재질문 없이 구현 방향을 바꾸는 미결정
각 1건을 드러냈고 사람이 확인했다. 행동 eval judge 보정은 고정 report 2건의 사람 판정과
저장 judge 판정 9/9가 일치했다. 각각
[`decision-completeness-pilots.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/docs/internal/decision-completeness-pilots.md)와
[`core-incidents-v1`](https://github.com/Daeguk-Sun/dcNess/blob/main/evals/calibration/core-incidents-v1/README.md)에 표본·재현 절차·한계를
보존한다. 두 결과도 제품 outcome이나 다중 프로젝트 우위 근거로 승격하지 않는다.

`node scripts/check_public_evidence.mjs`는 설치 cache가 아니라 dcNess source checkout에서만 실행하는
self evidence gate다. 실제 전체 unittest와 guard eval을 실행하고,
manifest version·test 수·guard 수가 이 표와
[`benchmark.md`](docs/plugin/benchmark.md#현재-공개-evidence-snapshot)에서 어긋나면 실패한다.
개별 원명령도 그대로 통과해야 한다.

```sh
python3.11 -m unittest discover -s tests -v < /dev/null
python3.11 evals/guard_efficacy.py
```

최근 릴리즈별 변경 상세는 [`docs/internal/release-notes.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/docs/internal/release-notes.md)에 남긴다.

## Safety 범위

dcNess의 file boundary와 mutation denylist는 보안 sandbox가 아니다. 목표는 신뢰하지 않는 코드를 격리하는 것이 아니라, 활성화된 개발 프로젝트에서 agent가 실수로 순서·역할·외부 상태 경계를 넘는 일을 줄이는 것이다. shell command substitution, 새 CLI 우회 패턴, OS 권한 밖 격리는 이 범위가 아니다.

정확한 한계와 fail-open 기록 정책은 [`docs/plugin/hooks.md#safety-범위`](docs/plugin/hooks.md#safety-범위)를 본다.

## 누구에게 맞나

**맞다** — Claude Code 로 실제 제품을 만들면서, `테스트 → 구현 → 리뷰 → PR` 순서와 파일 경계를 매번 지키고 싶은 사람. 끝난 작업을 나중에 다시 들여다보며 어디서 낭비가 났는지 잡아 절차를 다듬으려는 사람.

**안 맞다** — 여러 모델·provider 를 갈아 끼우는 범용 런타임이 필요한 경우(그건 dcNess 의 목적이 아니다). 한 번 쓰고 버릴 스크립트나 탐색용 프로토타입만 만드는 경우엔 오히려 거추장스럽다.

dcNess 는 무거운 절차를 항상 켜 두지 않는다. 문서 수정이나 한 줄 버그픽스는 가볍게 지나가고, 새 기능이나 위험이 큰 작업일 때만 설계·검토 절차를 끌어올린다. 그래서 작은 작업에는 부담이 적고, 큰 작업에는 안전하다.

다른 스킬 기반 하네스([Superpowers](https://github.com/obra/superpowers), [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) 등)와 비교할 때 기능 개수나 관심도 지표를 품질 대리값으로 쓰지 않는다. 강제 경계, Agent effectiveness, 실행 검수, eval, 운영 표본, 생태계를 서로 다른 축으로 비교해야 한다. dcNess 는 그중 작업 순서·파일 경계를 코드로 지키는 거버넌스와 run 단위 replay 에 집중한다. 실측 수치와 재현 명령은 [`docs/plugin/benchmark.md`](docs/plugin/benchmark.md)에 있다.

## 설치 & 활성화

```sh
# marketplace 등록 + plugin 설치 (Claude Code CLI)
claude plugin marketplace add Daeguk-Sun/dcNess
claude plugin install dcness@dcness
```

설치만으로는 아무것도 걸리지 않는다. 기본값은 **비활성**(그냥 통과)이다. 적용할 프로젝트에서 Claude Code 세션을 열고 활성화해야 한다.

```
/init-dcness        # 현 프로젝트를 활성 대상에 등록 (+ 파일 읽기 권한 / git hook 자동 셋업). 비활성화("dcness 꺼줘")도 같은 스킬이 처리
```

`/init-dcness` 가 출력하는 진단표에서 `whitelist 활성` 이 PASS 이고 FAIL 이 0 이면 정상이다(INFO·선택 WARN 은 정상).

```
[dcness] === 외부 활성 프로젝트 진단 ===
  [PASS] whitelist 활성: 활성
  ...
[dcness] 요약: N PASS / 0 WARN / 0 FAIL
```

> 갱신: `claude plugin update dcness@dcness` (문서·skill·hook 만 받는 경우 `/init-dcness` 재실행 불필요)

작은 작업은 가볍게 지나가고, 위험 신호는 먼저 경고한다. 문서 수정이나 명확한 한 줄 버그픽스는 direct 구현으로 짧게 끝내고, 새 기능·공개 contract·복잡한 설계 변경은 `/spec`·`/design` 선행을 권장한다. 사용자가 명시적으로 구현 진행을 선택하면 `/impl` 이 safety gate 를 유지한 채 진행한다.

## 작업 흐름

기본으로 기억할 흐름은 `/spec → /design → /impl → /acceptance` 넷이면 된다. 공개 lifecycle 표기 기준은 `/spec -> /design -> /impl -> /acceptance` 다.

| 기본 진입점 | 언제 쓰나 |
|---|---|
| `/spec` | 새 기능·큰 기획·PRD 변경처럼 무엇을 만들지 먼저 합의해야 할 때 |
| `/design` | PRD 이후 구현 전 product/technical design, 즉 화면 흐름·시스템·모듈 설계가 필요할 때 (구현 없이 visual design 만 먼저 보려면 `/ux`) |
| `/impl` | 구현·수정·버그픽스를 실제 PR 로 끝낼 때 |
| `/acceptance` | PRD / Epic / Story 기준으로 "정말 다 됐는지" 제품 검수할 때 |

`/impl` 은 설계도를 직접 그리지 않고, 들어온 요청을 보고 **가장 작은 안전한 경로** 를 스스로 고른다. 파일·이슈·테스트 같은 concrete signal 이 있으면 메인이 바로 `테스트 → 구현 → 리뷰 → PR` 로 끝내고(direct), 설계도 경로가 있으면 그 설계도대로 구현한다(design-doc). 새 기능이나 위험이 큰 작업은 설계 선행을 권장하지만, 사용자가 그대로 진행을 택하면 구현한다.

`/impl` 이 내부적으로 issue-intake/direct/design-doc echo 와 review provider 를 고른다. 일반 `/impl` 구현은 메인이 맡고, 격리되는 것은 `impl-validator` 검토다.

보조 진입점 — `/to-issue`(자연어를 GitHub 이슈로), `/next-work`(issue/label 에서 다음 할 일 조회), `/tech-review`(위험한 설계의 사전 기술 검증), `/impl-loop`(deep task 파일 단위 구현 러너), `/ux`(구현 없이 시안·흐름·디자인 시스템/토큰 베이스라인 먼저).

각 단계에서 agent 가 낸 결론(`PASS` / `SPEC_GAP_FOUND` / `TESTS_FAIL` 등)이 다음 어느 단계로 이어지는지는 skill 별 `<skill>-routing.md`(mermaid 분기도 + 표 + retry + escalate)가 진본이다 — 예: [`skills/impl/impl-routing.md`](skills/impl/impl-routing.md).

## 진행 중 (로드맵)

다음 릴리즈 후보 이슈는 GitHub Issue와 Project board를 기준으로 갱신한다.

## Provider와 기록

검증·리뷰 단계를 어느 provider 로 돌릴지는 프로젝트별로 고를 수 있다(Claude 서브에이전트 / Codex headless / Claude headless). provider 를 바꿔도 순서·파일 경계 규칙은 그대로 걸린다. 일반 `/impl` 구현은 메인이 맡고, story/epic deep task runner 인 `/impl-loop` 만 구현 worker provider 를 사용한다. provider 구성을 새로 켜거나 바꿀 때만 `/init-dcness` 를 다시 실행한다.

`/impl-loop` deep task 는 `build-worker → impl-validator` 흐름을 사용한다. build-worker 는 task 별 로컬 커밋까지 만들고, 모든 대상 task 구현 뒤 merge candidate diff 를 impl-validator 가 1회 통합 리뷰한다. 각 run의 단계 완료는 `ledger.jsonl`에 기록되며, prose 파일과 sha256 receipt로 검증 가능한 작업 기록을 남긴다.

## 핵심 특징

| 항목 | 내용 |
|---|---|
| 판단 방식 | agent 가 자연어로 결과를 쓰고, 메인 Claude 가 그 글을 직접 읽어 분기한다. 기계적 값 추출·별도 LLM 호출 없음 |
| 형식 강제 | 없음 — 형식·flag·schema 는 agent 자율. 강제는 작업 순서 + 접근 영역 |
| 컨텍스트 구조 | 2 layer (`CLAUDE.md` + agent 지침) |
| 게이트 | 거버넌스 + 10개 CI (cross-ref · doc-sync · git-naming · plugin-manifest · pr-body · public-surface · python-tests · static-quality · release-sync · github-project-lifecycle) |
| provider 선택 | 검증·리뷰 단계를 Claude 서브에이전트 또는 Codex 로 돌릴 수 있고, provider 가 바뀌어도 규칙은 동일. 일반 `/impl` 구현은 메인이 맡음 |

## 공개 진입점

기본/support/고급/유틸리티/내부 agent 분류는 public surface gate 의 계약이다.

| 분류 | 발화 | 역할 |
|---|---|---|
| 기본 workflow | `/spec` | 새 기능 spec + 검수 체크포인트 |
| 기본 workflow | `/design` | 화면·시스템·모듈 설계 |
| 기본 workflow | `/impl` | 구현 진입 — issue-intake/direct/design-doc echo 와 review provider 를 내부 판정 |
| 기본 workflow | `/acceptance` | story/epic 제품 검수 |
| support | `/to-issue` | 자연어 → Issue Brief → 승인 대기 없이 GitHub 선등록 (web 에서 확인·수정) |
| 고급 | `/tech-review` | 위험한 설계의 사전 기술 검증 |
| 고급 | `/impl-loop` | deep impl task 파일 단위 구현 러너 |
| 유틸 | `/ux` | 구현 없이 목업·흐름·디자인 시스템/토큰 베이스라인 먼저 탐색, PICK 확정본은 canvas 에 등록 |
| 유틸 | `/init-dcness` | 현 프로젝트를 활성 대상에 등록·해제 |
| 유틸 | `/next-work` | issue/label 기반 진행 중 / 다음 할 일 조회 |
| 유틸 | `/run-review` | 끝난 run 을 되짚어 단계별 비용·차단 분석 |
| 유틸 | `/smart-compact` | 컨텍스트 압축 + 다음 세션 resume prompt 생성 |
| 유틸 | `/efficiency` | 세션 토큰·비용 분석 + HTML 대시보드 |

Sub-agent(`agents/`, architect / validator / worker / reviewer / acceptance 계열)는 사용자가 직접 부르는 게 아니라 workflow 안에서 gate·worker·reviewer 로 호출된다.

## 거버넌스 (dcNess 저장소 자체 작업 기준)

이 저장소의 모든 변경은 [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md)(SSOT)를 따른다.

- **게이트**: main-block · git-naming · pytest(pre-commit hook) + 위 10개 CI
- **branch → PR → merge** 필수, `main` 직접 push 금지
- PR 절차: [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#커밋-pr-절차)

## 개발자 셋업 (dcNess 에 기여)

검증 기준은 Python 3.11 이다. macOS 기본 `python3` 는 3.9 일 수 있으니 로컬에서는 `python3.11` 을 명시한다.

```sh
git clone https://github.com/Daeguk-Sun/dcNess.git
cd dcNess
cp scripts/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

python3.11 -m unittest discover -s tests -v   # 단위 테스트
node scripts/check_public_surface.mjs         # 공개 진입점 계약 검증
node scripts/check_cross_refs.mjs             # link/anchor + 옛 명칭 게이트
python3.11 -m pip install -r requirements-quality.txt
bash scripts/check_static_quality.sh          # ruff + mypy + bandit
```

- 런타임 의존성: Python 3.11+, Node.js 20+, **외부 패키지 0**(표준 라이브러리만)

## 참조 문서

| 문서 | 역할 |
|---|---|
| [`CLAUDE.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) | 정체성·강제 원칙 SSOT |
| [`docs/plugin/terms.md`](docs/plugin/terms.md) | 사용자-facing 용어 사전 |
| [`docs/plugin/positioning.md`](docs/plugin/positioning.md) | 공개 진입점 계약 (기본/보조/고급/유틸/내부 분류) |
| [`docs/plugin/workflow-router.md`](docs/plugin/workflow-router.md) | 자유 형식 요청을 어떤 workflow 로 보낼지 판정 |
| [`docs/plugin/benchmark.md`](docs/plugin/benchmark.md) | 측정 재현 가이드 + 표본 한계 |
| [`docs/plugin/loop-procedure.md`](docs/plugin/loop-procedure.md#진입-모델) | loop 실행 절차 (Step 0~8) |
| [`docs/plugin/hooks.md`](docs/plugin/hooks.md#catastrophic-gatesh) | 순서 차단 훅 + hook SSOT |
| [`PROGRESS.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/PROGRESS.md) | 현재 상태 / TODO / Blockers |
| [`AGENTS.md`](https://github.com/Daeguk-Sun/dcNess/blob/main/AGENTS.md) | 외부 에이전트(Codex 등) 지침 |

## License

MIT — see [`LICENSE`](LICENSE).
