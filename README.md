# dcNess

> Claude Code와 Codex를 실제 제품 개발 루프에 묶는 agent workflow harness.

> **Spec(SSOT)**: [`CLAUDE.md`](CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)

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

as of v0.12.0 + Unreleased (2026-07-05), 로컬 실측 기준:

| 항목 | 결과 | 재현 명령 |
|---|---:|---|
| 단위 테스트 | 1627 tests PASS | `python3.11 -m unittest discover -s tests -v < /dev/null` |
| 결정적 guard eval | 33/33 PASS | `python3 evals/guard_efficacy.py --json` |
| GitHub Actions gate | 11 workflows | `find .github/workflows -maxdepth 1 -type f -name '*.yml' \| wc -l` |

최근 릴리즈별 변경 상세는 [`docs/internal/release-notes.md`](docs/internal/release-notes.md)에 남긴다.

## Safety 범위

dcNess의 file boundary와 mutation denylist는 보안 sandbox가 아니다. 목표는 신뢰하지 않는 코드를 격리하는 것이 아니라, 활성화된 개발 프로젝트에서 agent가 실수로 순서·역할·외부 상태 경계를 넘는 일을 줄이는 것이다. shell command substitution, 새 CLI 우회 패턴, OS 권한 밖 격리는 이 범위가 아니다.

정확한 한계와 fail-open 기록 정책은 [`docs/plugin/hooks.md#safety-범위`](docs/plugin/hooks.md#safety-범위)를 본다.

## 누구에게 맞나

**맞다** — Claude Code 로 실제 제품을 만들면서, `테스트 → 구현 → 리뷰 → PR` 순서와 파일 경계를 매번 지키고 싶은 사람. 끝난 작업을 나중에 다시 들여다보며 어디서 낭비가 났는지 잡아 절차를 다듬으려는 사람.

**안 맞다** — 여러 모델·provider 를 갈아 끼우는 범용 런타임이 필요한 경우(그건 dcNess 의 목적이 아니다). 한 번 쓰고 버릴 스크립트나 탐색용 프로토타입만 만드는 경우엔 오히려 거추장스럽다.

dcNess 는 무거운 절차를 항상 켜 두지 않는다. 문서 수정이나 한 줄 버그픽스는 가볍게 지나가고, 새 기능이나 위험이 큰 작업일 때만 설계·검토 절차를 끌어올린다. 그래서 작은 작업에는 부담이 적고, 큰 작업에는 안전하다.

다른 스킬 기반 하네스([Superpowers](https://github.com/obra/superpowers), [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) 등)와 결이 다르다. 그쪽은 방법론과 다양한 도구 연동이 강점이다. dcNess 는 노출하는 표면을 작게 유지하는 대신, 작업 순서·파일 경계를 코드로 지키는 거버넌스와 run 단위 replay 에 집중한다. 실측 수치와 재현 명령은 [`docs/plugin/benchmark.md`](docs/plugin/benchmark.md)에 있다.

## 설치 & 활성화

```sh
# marketplace 등록 + plugin 설치 (Claude Code CLI)
claude plugin marketplace add Daeguk-Sun/dcNess
claude plugin install dcness@dcness
```

설치만으로는 아무것도 걸리지 않는다. 기본값은 **비활성**(그냥 통과)이다. 적용할 프로젝트에서 Claude Code 세션을 열고 활성화해야 한다.

```
/init-dcness        # 현 프로젝트를 활성 대상에 등록 (+ 파일 읽기 권한 / git hook 자동 셋업)
```

`/init-dcness` 가 출력하는 진단표에서 `whitelist 활성` 이 PASS 이고 FAIL 이 0 이면 정상이다(INFO·선택 WARN 은 정상).

```
[dcness] === 외부 활성 프로젝트 진단 ===
  [PASS] whitelist 활성: 활성
  ...
[dcness] 요약: N PASS / 0 WARN / 0 FAIL
```

> 갱신: `claude plugin update dcness@dcness` (문서·skill·hook 만 받는 경우 `/init-dcness` 재실행 불필요)

작은 작업은 가볍게 지나가고, 위험이 큰 작업만 절차가 올라간다. 문서 수정이나 명확한 한 줄 버그픽스는 Lite 경로로 짧게 끝내고, 새 기능·공개 contract·복잡한 설계 변경은 `/spec`·`/design` 쪽으로 올린다.

## 작업 흐름

기본으로 기억할 흐름은 `/spec → /design → /impl → /acceptance` 넷이면 된다. 공개 lifecycle 표기 기준은 `/spec -> /design -> /impl -> /acceptance` 다.

| 기본 진입점 | 언제 쓰나 |
|---|---|
| `/spec` | 새 기능·큰 기획·PRD 변경처럼 무엇을 만들지 먼저 합의해야 할 때 |
| `/design` | PRD 이후 구현 전 product/technical design, 즉 화면 흐름·시스템·모듈 설계가 필요할 때 (구현 없이 visual design 만 먼저 보려면 `/ux`) |
| `/impl` | 구현·수정·버그픽스를 실제 PR 로 끝낼 때 |
| `/acceptance` | PRD / Epic / Story 기준으로 "정말 다 됐는지" 제품 검수할 때 |

`/impl` 은 설계도를 직접 그리지 않고, 들어온 요청을 보고 **가장 작은 안전한 경로** 를 스스로 고른다. 설계 문서가 없고 파일·이슈 같은 구체적 단서가 명확하면 메인이 바로 `테스트 → 구현 → 리뷰 → PR` 로 끝내고(Lite), 설계도가 있으면 그 설계도대로 구현한다(Standard). 새 기능이나 위험이 큰 작업은 `/impl` 안에서 처리하지 않고 `/spec`·`/design` 으로 먼저 돌린 뒤, 나온 설계도를 들고 다시 들어온다.

`/impl` 이 내부적으로 구현 경로(설계도 유무 — Lite / Standard)와 검증 엄정도를 직교로 고른다.

보조 진입점 — `/to-issue`(자연어를 GitHub 이슈로), `/next-work`(issue/label 에서 다음 할 일 조회), `/tech-review`(위험한 설계의 사전 기술 검증), `/impl-loop`(deep task 파일 단위 구현 러너), `/ux`(구현 없이 시안·흐름 먼저).

각 단계에서 agent 가 낸 결론(`PASS` / `IMPL_DONE` / `SPEC_GAP_FOUND` 등)이 다음 어느 단계로 이어지는지는 skill 별 `<skill>-routing.md`(mermaid 분기도 + 표 + retry + escalate)가 진본이다 — 예: [`skills/impl/impl-routing.md`](skills/impl/impl-routing.md).

## 진행 중 (로드맵)

다음 릴리즈 후보 이슈는 GitHub Issue와 Project board를 기준으로 갱신한다.

## 엔진과 기록

검증·구현·리뷰 단계를 어느 엔진으로 돌릴지는 프로젝트별로 고를 수 있다(Claude 서브에이전트 / Codex headless / Claude headless). 엔진을 바꿔도 순서·파일 경계 규칙은 그대로 걸린다. 구현 기본값은 `headless-chain`(Codex headless → Claude headless → Claude main)이고, 엔진 구성을 새로 켜거나 바꿀 때만 `/init-dcness` 를 다시 실행한다.

Standard 구현 경로의 기본은 `build-worker → pr-reviewer` 이고, 풀 4-agent 는 고위험 trigger 나 사용자 엄정 override 때만 승격한다. 각 run의 단계 완료는 `ledger.jsonl`에 기록되며, prose 파일과 sha256 receipt로 검증 가능한 작업 기록을 남긴다.

## 핵심 특징

| 항목 | 내용 |
|---|---|
| 판단 방식 | agent 가 자연어로 결과를 쓰고, 메인 Claude 가 그 글을 직접 읽어 분기한다. 기계적 값 추출·별도 LLM 호출 없음 |
| 형식 강제 | 없음 — 형식·flag·schema 는 agent 자율. 강제는 작업 순서 + 접근 영역 |
| 컨텍스트 구조 | 2 layer (`CLAUDE.md` + agent 지침) |
| 게이트 | 거버넌스 + 10개 CI (cross-ref · doc-sync · git-naming · plugin-manifest · pr-body · public-surface · python-tests · static-quality · release-sync · github-project-lifecycle) |
| 엔진 선택 | 검증·구현·리뷰 단계를 Claude 서브에이전트 또는 Codex 로 돌릴 수 있고, 엔진이 바뀌어도 규칙은 동일 |

## 공개 진입점

기본/support/고급/유틸리티/내부 agent 분류는 public surface gate 의 계약이다.

| 분류 | 발화 | 역할 |
|---|---|---|
| 기본 workflow | `/spec` | 새 기능 spec + 검수 체크포인트 |
| 기본 workflow | `/design` | 화면·시스템·모듈 설계 |
| 기본 workflow | `/impl` | 구현 진입 — 경로(Lite/Standard)와 엔진을 내부 판정 |
| 기본 workflow | `/acceptance` | story/epic 제품 검수 |
| support | `/to-issue` | 자연어 → Issue Brief 초안 → 승인 후 GitHub 등록 |
| 고급 | `/tech-review` | 위험한 설계의 사전 기술 검증 |
| 고급 | `/impl-loop` | deep impl task 파일 단위 구현 러너 |
| 유틸 | `/ux` | 구현 없이 목업·흐름 먼저 탐색, PICK 확정본은 canvas 에 등록 |
| 유틸 | `/init-dcness` | 현 프로젝트를 활성 대상에 등록 |
| 유틸 | `/next-work` | issue/label 기반 진행 중 / 다음 할 일 조회 |
| 유틸 | `/run-review` | 끝난 run 을 되짚어 단계별 비용·차단 분석 |
| 유틸 | `/smart-compact` | 컨텍스트 압축 + 다음 세션 resume prompt 생성 |
| 유틸 | `/efficiency` | 세션 토큰·비용 분석 + HTML 대시보드 |

Sub-agent(`agents/`, architect / validator / engineer / reviewer / acceptance 계열)는 사용자가 직접 부르는 게 아니라 workflow 안에서 gate·worker·reviewer 로 호출된다.

## 거버넌스 (dcNess 저장소 자체 작업 기준)

이 저장소의 모든 변경은 [`CLAUDE.md`](CLAUDE.md)(SSOT)를 따른다.

- **게이트**: main-block · git-naming · pytest(pre-commit hook) + 위 10개 CI
- **branch → PR → merge** 필수, `main` 직접 push 금지
- PR 절차: [`CLAUDE.md`](CLAUDE.md#커밋-pr-절차)

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
| [`CLAUDE.md`](CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일) | 정체성·강제 원칙 SSOT |
| [`docs/plugin/terms.md`](docs/plugin/terms.md) | 사용자-facing 용어 사전 |
| [`docs/plugin/positioning.md`](docs/plugin/positioning.md) | 공개 진입점 계약 (기본/보조/고급/유틸/내부 분류) |
| [`docs/plugin/workflow-router.md`](docs/plugin/workflow-router.md) | 자유 형식 요청을 어떤 workflow 로 보낼지 판정 |
| [`docs/plugin/benchmark.md`](docs/plugin/benchmark.md) | 측정 재현 가이드 + 표본 한계 |
| [`docs/plugin/loop-procedure.md`](docs/plugin/loop-procedure.md#진입-모델) | loop 실행 절차 (Step 0~8) |
| [`docs/plugin/hooks.md`](docs/plugin/hooks.md#catastrophic-gatesh) | 순서 차단 훅 + hook SSOT |
| [`PROGRESS.md`](PROGRESS.md) | 현재 상태 / TODO / Blockers |
| [`AGENTS.md`](AGENTS.md) | 외부 에이전트(Codex 등) 지침 |

## License

MIT — see [`LICENSE`](LICENSE).
