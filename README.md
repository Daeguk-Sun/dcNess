# dcNess

> 검증된 시니어 팀의 개발 워크플로우를 AI 코딩 에이전트에게 입히는 Claude Code 플러그인.
> 규율은 팀 워크플로우로 지키게 하고, 그 안의 판단은 발전하는 모델의 자율에 맡긴다.

> **Origin**: [`alruminum/realworld-harness`](https://github.com/alruminum/realworld-harness) fork-and-refactor
> **Spec(SSOT)**: [`CLAUDE.md`](CLAUDE.md#dcness-강제-원칙-룰-추가설계-시-가드레일)

Claude Code 는 일 잘하는 동료다. 맥락만 제대로 주면 웬만한 작업은 알아서 끝까지 해낸다. 문제는 실력이 아니다.

아무리 잘하는 친구라도 혼자 오래 달리다 보면 팀의 순서에서 벗어날 때가 있다 — 테스트를 뒤로 미루고 구현부터, 검증을 건너뛰고 PR 부터, 맡은 범위 밖 파일까지. 사람이라면 코드 리뷰나 PR 규칙에서 잡히지만, 혼자 달리는 AI 옆에는 그걸 잡아 줄 사람이 없다.

시니어 팀은 이런 걸 오래 쌓인 순서로 거른다. 테스트 먼저, 리뷰를 통과해야 머지, 각자 맡은 영역만. 시니어일수록 이 순서가 몸에 배어 있다.

dcNess 는 그 순서를 유능한 AI 동료에게 입힌다. 업무 방식은 잘 굴러가는 시니어 팀을 따르게 하되, 실제 코딩은 AI 가 가장 안전하고 빠르게 할 수 있는 방향으로 잡아 준다. 어떻게 짤지는 AI 가 정하고, 어떤 순서로 어디까지 손댈지는 팀 규칙이 정한다.

그래서 dcNess 가 붙드는 축은 둘이다 — **검증된 팀 워크플로우를 지키는 것**, 그리고 그 안에서 **모델의 자율성을 최대한 존중하는 것**.

## 어떤 순서를 지키나

AI 가 이 순서를 벗어나려 하면, dcNess 가 그 자리에서 붙잡고 빠뜨린 단계를 먼저 하게 한다.

| Claude Code 가 하려는 것 | dcNess 의 반응 |
|---|---|
| 테스트 없이 구현 코드부터 작성 | 매칭되는 테스트가 없으면 그 파일 쓰기를 막는다 |
| 코드 검증을 건너뛰고 리뷰/PR 로 | 앞 단계 통과 기록이 없으면 다음 단계로 못 넘어간다 |
| 맡은 범위 밖 파일 수정 | 그 agent 에게 허용된 파일 경계 밖이면 차단 |
| `main` 에 바로 커밋·push | `branch → PR` 경로로만 통과 |

## 어디까지 개입하나

dcNess 가 개입하는 지점은 좁다. 코드를 어떻게 짤지, 어떤 도구를 쓸지, 어떤 접근을 택할지는 AI 의 판단에 맡긴다. 지금 대충 넘어가면 나중에 수정 비용이 몇 배로 불어나는 자리만 잡는다.

- **작업 순서** — 검증 → 구현 → 리뷰 → PR 시퀀스를 건너뛰지 못하게
- **접근 영역** — agent 마다 손댈 수 있는 파일 범위 + 외부 상태 변경(push, 이슈 생성 등) 차단

## 모델을 과소평가하지 않는다

모델은 빠르게 좋아지고 있다. 예전이라면 사람이 방향을 하나하나 정해 주고 규칙으로 못 박아야 했던 판단도, 요즘 모델은 스스로 충분히 해낸다. dcNess 는 그 변화에 맞춰, 모델이 좋아질수록 그 자율성을 최대한 존중하는 쪽으로 설계했다. 지시를 과하게 채우거나 두꺼운 페르소나를 씌우면 모델이 자기 판단을 접고 시키는 대로만 움직이기 쉽고, 프롬프트가 길어진 만큼 토큰도 더 든다. 그래서 꼭 필요한 경계만 코드로 남기고, 나머지 판단은 모델에게 맡긴다.

구체적으로는, 코드로 막는 건 위에서 말한 두 경계(작업 순서·접근 영역)뿐이고, 나머지 방향은 전부 자연어 지침으로만 준다. 에이전트에게 주는 지침도 "이 양식대로 출력해라" 가 아니라 "이런 걸 살펴봐라" 에 가깝다. 예를 들어 구현 에이전트에게는 "요구에 없는 추상화나 방어 로직을 덧붙이지 마라" 정도로 방향만 주고, 실제로 어떻게 할지는 모델이 정한다.

- 에이전트에 억지 페르소나를 씌우지 않는다. 지침은 역할과 봐야 할 판단 기준만 담는다.
- 결과를 정해진 양식(JSON 등)에 채우게 하지 않는다. 에이전트는 판단과 근거를 자연어로 쓴다.
- 그 글은 메인 Claude 가 직접 읽고 다음 단계를 정한다. 결론을 뽑으려 정규식이나 별도 판정용 모델을 끼우지 않는다.
- 분기 규칙마저 강제가 아니라 권고다. 되돌리기 힘든 순서·경계만 코드로 막고, 그 안의 판단은 모델에게 맡긴다.

## 코드만 남기지 않는다

잘 굴러가는 팀은 결과물만 남기지 않는다. 왜 그렇게 정했는지는 이슈에, 무엇을 어떻게 바꿨는지는 PR 에 남긴다. dcNess 의 작업 흐름도 그대로다. 모든 작업이 이슈 하나와 PR 하나로 묶여서, 결정의 근거와 변경 내용이 저장소 히스토리에 함께 쌓인다. 나중에 "이 코드가 왜 이렇게 됐지" 를 물으면, 따로 관리하는 ADR 문서가 아니라 실제 이슈와 PR 이 답이 된다.

## 누구에게 맞나

**맞다** — Claude Code 로 실제 제품을 만들면서, `테스트 → 구현 → 리뷰 → PR` 순서와 파일 경계를 매번 지키고 싶은 사람. 끝난 작업을 나중에 다시 들여다보며 어디서 낭비가 났는지 잡아 절차를 다듬으려는 사람.

**안 맞다** — 여러 모델·provider 를 갈아 끼우는 범용 런타임이 필요한 경우(그건 dcNess 의 목적이 아니다). 한 번 쓰고 버릴 스크립트나 탐색용 프로토타입만 만드는 경우엔 오히려 거추장스럽다.

dcNess 는 무거운 절차를 항상 켜 두지 않는다. 문서 수정이나 한 줄 버그픽스는 가볍게 지나가고, 새 기능이나 위험이 큰 작업일 때만 설계·검토 절차를 끌어올린다. 그래서 작은 작업에는 부담이 적고, 큰 작업에는 안전하다.

다른 스킬 기반 하네스([Superpowers](https://github.com/obra/superpowers), [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) 등)와 결이 다르다. 그쪽은 방법론과 다양한 도구 연동이 강점이다. dcNess 는 노출하는 표면을 작게 유지하는 대신, 작업 순서·파일 경계를 코드로 지키는 거버넌스와 run 단위로 되짚어 보는 replay 에 집중한다. 실측 수치와 재현 명령은 [`docs/plugin/benchmark.md`](docs/plugin/benchmark.md) 에 있다.

## 설치 & 활성화

```sh
# marketplace 등록 + plugin 설치 (Claude Code CLI)
claude plugin marketplace add alruminum/dcNess
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

검증·구현·리뷰 단계를 어느 엔진으로 돌릴지는 프로젝트별로 고를 수 있다(Claude 서브에이전트 / Codex). 엔진을 바꿔도 순서·파일 경계 규칙은 그대로 걸린다. 엔진 구성을 새로 켜거나 바꿀 때만 `/init-dcness` 를 다시 실행한다.

## 작업 흐름

기본으로 기억할 흐름은 `/spec → /design → /impl → /acceptance` 넷이면 된다.

| 진입점 | 언제 쓰나 |
|---|---|
| `/spec` | 새 기능·큰 기획·PRD 변경처럼 무엇을 만들지 먼저 합의해야 할 때 |
| `/design` | 구현 전에 화면 흐름·시스템·모듈 설계가 필요할 때 (구현 없이 시안만 먼저 보려면 `/ux`) |
| `/impl` | 구현·수정·버그픽스를 실제 PR 로 끝낼 때 |
| `/acceptance` | PRD / Epic / Story 기준으로 "정말 다 됐는지" 제품 검수할 때 |

`/impl` 은 설계도를 직접 그리지 않고, 들어온 요청을 보고 **가장 작은 안전한 경로** 를 스스로 고른다. 설계 문서가 없고 파일·이슈 같은 구체적 단서가 명확하면 메인이 바로 `테스트 → 구현 → 리뷰 → PR` 로 끝내고(Lite), 설계도가 있으면 그 설계도대로 구현한다(Standard). 새 기능이나 위험이 큰 작업은 `/impl` 안에서 처리하지 않고 `/spec`·`/design` 으로 먼저 돌린 뒤, 나온 설계도를 들고 다시 들어온다.

보조 진입점 — `/to-issue`(자연어를 GitHub 이슈로), `/next`(보드에서 다음 할 일 조회), `/tech-review`(위험한 설계의 사전 기술 검증), `/impl-loop`(deep task 파일 단위 구현 러너), `/ux`(구현 없이 시안·흐름 먼저).

각 단계에서 agent 가 낸 결론(`PASS` / `IMPL_DONE` / `SPEC_GAP_FOUND` 등)이 다음 어느 단계로 이어지는지는 skill 별 `<skill>-routing.md`(mermaid 분기도 + 표 + retry + escalate)가 진본이다 — 예: [`skills/impl/impl-routing.md`](skills/impl/impl-routing.md).

## 최근 정비 (2026-07)

**설계 루프 개편** — `/design` 을 epic 단위 배치 흐름으로 다시 짰다. 설계 산출물을 계약 기반으로 감사해서, 설계가 실제로 끝났는지를 사람 눈이 아니라 게이트가 확인한다(빠진 산출물, 형식만 맞고 내용이 빈 "false-clean" 차단). ([#831](https://github.com/alruminum/dcNess/issues/831) · [#832](https://github.com/alruminum/dcNess/issues/832) · [#833](https://github.com/alruminum/dcNess/issues/833) · [#834](https://github.com/alruminum/dcNess/issues/834) · [#847](https://github.com/alruminum/dcNess/issues/847))

**디자인 매체 교체** — 외부 pencil 의존을 걷어내고, 확정된 UI 시안을 저장소 안 canvas 로 관리한다. `/ux` 는 구현 없이 목업과 흐름만 먼저 탐색하는 유틸리티로 재정의했다. ([#842](https://github.com/alruminum/dcNess/issues/842) · [#843](https://github.com/alruminum/dcNess/issues/843) · [#845](https://github.com/alruminum/dcNess/issues/845))

**머지·종료 가드 보강** — 자동 머지 직전 확인 창([#851](https://github.com/alruminum/dcNess/issues/851)), worktree 종료 시 변경이 main 에 흡수됐는지 확인한 뒤 정리([#852](https://github.com/alruminum/dcNess/issues/852)), UI 작업은 목업과 실제 화면 정합까지 검수([#844](https://github.com/alruminum/dcNess/issues/844)).

**엔진 무관 게이트** — 순서·TDD 강제가 Claude 서브에이전트뿐 아니라 headless(Codex 등) 경로에서도 똑같이 걸리도록 강제 지점을 재배치했다. 예전에는 순서·TDD 게이트가 Claude 서브에이전트 경로에서만 발화하고, 자기 프로세스 안에서 직접 파일을 쓰는 headless 경로는 게이트 밖이었다. 이제 어느 엔진으로 구현·검증을 돌려도 같은 규칙이 적용된다. ([#859](https://github.com/alruminum/dcNess/issues/859))

## 진행 중 (로드맵)

게이트를 엔진 무관하게 만든 작업([#859](https://github.com/alruminum/dcNess/issues/859))에 이어, 그 위에서 실행 엔진의 선택폭을 넓히는 단계다.

- **구현 엔진 3단 폴백** ([#860](https://github.com/alruminum/dcNess/issues/860)) — codex headless → claude headless → claude 메인. Codex 가 안 깔린 사람도 격리 실행 혜택을 받게 한다.
- **기본 엔진을 경량 build-worker 로** ([#861](https://github.com/alruminum/dcNess/issues/861)) — 풀 4-agent 는 위험이 큰 작업 승격 전용으로 남긴다.

## 핵심 특징

| 항목 | 내용 |
|---|---|
| 판단 방식 | agent 가 자연어로 결과를 쓰고, 메인 Claude 가 그 글을 직접 읽어 분기한다. 기계적 값 추출·별도 LLM 호출 없음 |
| 형식 강제 | 없음 — 형식·flag·schema 는 agent 자율. 강제는 작업 순서 + 접근 영역 |
| 컨텍스트 구조 | 2 layer (`CLAUDE.md` + agent 지침) |
| 게이트 | 거버넌스 + 10개 CI (cross-ref · doc-sync · git-naming · plugin-manifest · pr-body · public-surface · python-tests · static-quality · release-sync · github-project-lifecycle) |
| 엔진 선택 | 검증·구현·리뷰 단계를 Claude 서브에이전트 또는 Codex 로 돌릴 수 있고, 엔진이 바뀌어도 규칙은 동일 |

## 공개 진입점

| 분류 | 발화 | 역할 |
|---|---|---|
| 기본 | `/spec` | 새 기능 spec + 검수 체크포인트 |
| 기본 | `/design` | 화면·시스템·모듈 설계 |
| 기본 | `/impl` | 구현 진입 — 경로(Lite/Standard)와 엔진을 내부 판정 |
| 기본 | `/acceptance` | story/epic 제품 검수 |
| 보조 | `/to-issue` | 자연어 → Issue Brief 초안 → 승인 후 GitHub 등록 |
| 고급 | `/tech-review` | 위험한 설계의 사전 기술 검증 |
| 고급 | `/impl-loop` | deep impl task 파일 단위 구현 러너 |
| 유틸 | `/ux` | 구현 없이 목업·흐름 먼저 탐색, PICK 확정본은 canvas 에 등록 |
| 유틸 | `/init-dcness` | 현 프로젝트를 활성 대상에 등록 |
| 유틸 | `/next` | 보드의 진행 중 / 다음 할 일 조회 |
| 유틸 | `/run-review` | 끝난 run 을 되짚어 단계별 비용·차단 분석 |
| 유틸 | `/smart-compact` | 컨텍스트 압축 + 다음 세션 resume prompt 생성 |
| 유틸 | `/efficiency` | 세션 토큰·비용 분석 + HTML 대시보드 |

12개 sub-agent(`agents/`, architect / validator / engineer / reviewer / acceptance 계열)는 사용자가 직접 부르는 게 아니라 workflow 안에서 gate·worker·reviewer 로 호출된다.

## 거버넌스 (dcNess 저장소 자체 작업 기준)

이 저장소의 모든 변경은 [`CLAUDE.md`](CLAUDE.md)(SSOT)를 따른다.

- **게이트**: main-block · git-naming · pytest(pre-commit hook) + 위 10개 CI
- **branch → PR → merge** 필수, `main` 직접 push 금지
- PR 절차: [`CLAUDE.md`](CLAUDE.md#커밋-pr-절차)

## 개발자 셋업 (dcNess 에 기여)

검증 기준은 Python 3.11 이다. macOS 기본 `python3` 는 3.9 일 수 있으니 로컬에서는 `python3.11` 을 명시한다.

```sh
git clone https://github.com/alruminum/dcNess.git
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
| [`docs/plugin/hooks.md`](docs/plugin/hooks.md#catastrophic-gatesh) | 순서 차단 훅 + 8 hook SSOT |
| [`PROGRESS.md`](PROGRESS.md) | 현재 상태 / TODO / Blockers |
| [`AGENTS.md`](AGENTS.md) | 외부 에이전트(Codex 등) 지침 |

## License

MIT — see [`LICENSE`](LICENSE).
