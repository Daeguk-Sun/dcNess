# scripts 모듈 안내

전역 작업 규칙은 [../CLAUDE.md](../CLAUDE.md)가 진본이다. 이 파일은 `scripts/`에서 gate,
helper, 배포용 wrapper를 고칠 때의 컴퍼스다.

## 소유 범위

- dcness self와 외부 활성 프로젝트가 호출하는 로컬/CI gate, PR helper, GitHub helper, wrapper.
- `commands/init-dcness.md`가 사용자 프로젝트로 복사하거나 안내하는 스크립트와 workflow template의
  실행 진입점.
- shell, Node.js, Python 스크립트가 섞여 있으므로 shebang과 런타임 의존성이 곧 계약이다.

## 먼저 볼 파일

- [hooks/](hooks/): git hook shim과 Claude Code pre-commit gate.
- [check_git_naming.mjs](check_git_naming.mjs), [check_pr_body.mjs](check_pr_body.mjs),
  [check_public_surface.mjs](check_public_surface.mjs), [check_cross_refs.mjs](check_cross_refs.mjs):
  CI와 local gate의 핵심 checker.
- [check_python_tests.sh](check_python_tests.sh), [check_static_quality.sh](check_static_quality.sh):
  Python test/static-quality 실행 wrapper.
- [pr-create.sh](pr-create.sh), [pr-finalize.sh](pr-finalize.sh), [pr-trailer.sh](pr-trailer.sh):
  PR 생성/마감/trailer 보조 흐름.
- [dcness-helper](dcness-helper), [dcness-context-docs](dcness-context-docs),
  [dcness-codex-validator](dcness-codex-validator), [dcness-codex-worker](dcness-codex-worker):
  사용자-facing CLI wrapper.
- [dcness-implementation-chain](dcness-implementation-chain), [dcness-story-runner](dcness-story-runner),
  [dcness-claude-worker](dcness-claude-worker), [dcness-claude-validator](dcness-claude-validator):
  `/impl-loop` 구현 체인과 Claude headless 실행 wrapper.
- [dcness-product-journey](dcness-product-journey), [dcness-review](dcness-review),
  [dcness-tdd-hooks](dcness-tdd-hooks), [dcness-ci-workflows](dcness-ci-workflows):
  journey 실행, run 복기, TDD guard 설치, CI workflow 설치 wrapper.
- [design/](design/): 디자인 보드와 진입점 생성 스크립트. 진본 모델은 [design/ux-flow.mjs](design/ux-flow.mjs)가 읽는다.
- [release_preflight.py](release_preflight.py), [release_artifact.py](release_artifact.py),
  [release_artifact.json](release_artifact.json), [sync_release.sh](sync_release.sh):
  릴리즈 사전 검사, 배포 파일 목록, 배포 브랜치 동기화.
- [github_project_lifecycle.mjs](github_project_lifecycle.mjs), [check_issue_body.mjs](check_issue_body.mjs):
  GitHub Project 상태 전이와 issue 본문 검사.
- [measure_main_turns.py](measure_main_turns.py), [loop_diagnose.py](loop_diagnose.py): 측정과 진단 전용 스크립트.
- [lib/](../scripts/lib/): 여러 Node checker와 shell wrapper가 공유하는 helper.

## 의존 관계 (dependencies)

- `dcness-*` wrapper 는 대부분 `harness/`의 Python 모듈 하나를 실행한다. 예: `dcness-helper` →
  `harness.session_state`, `dcness-product-journey` → `harness.product_journey`.
- `dcness-implementation-chain`은 `harness`의 5개 모듈(`agent_routing`, `provider_failure_cache`,
  `run_review`, `session_state`, `story_runner`)을 함께 쓴다.
- `design/` 생성 스크립트는 `templates/design-variants/_lib/`의 엔진 파일과 프로젝트 사본을 비교한다.
- `.github/workflows/*.yml`과 `templates/github-workflows/*.yml`이 이 디렉터리의 checker 를 호출한다.
  checker 의 인자나 종료코드를 바꾸면 두 위치를 함께 본다.

## 자주 하는 수정 (common change patterns)

- **새 checker 를 추가한다.**
  1. `check_*.mjs`를 만들고 `tests/`에 대응 테스트를 추가한다.
  2. `.github/workflows/`에 실행 workflow 를 추가하고 루트 [../CLAUDE.md](../CLAUDE.md)의 "게이트 요약"에 적는다.
  3. 외부 활성 프로젝트에도 적용할 checker 면 `templates/github-workflows/`에 template 을 추가하고
     [../harness/ci_workflows.py](../harness/ci_workflows.py)의 `CHECKS`에 등록한다.
- **새 `dcness-*` wrapper 를 추가한다.** [release_artifact.json](release_artifact.json)의 `include_paths`에
  추가한다. 목록에 없는 wrapper 는 사용자 환경에 도달하지 않는다.
- **checker 의 실패 문구를 바꾼다.** 그 문구를 기대하는 테스트를 함께 고친다.

## 수정 시 주의점

- `sh` shebang 파일은 POSIX shell 기준으로 유지한다. Bash 기능이 필요하면 shebang과 호출 문서를 같이 본다.
- Node checker는 외부 패키지 없이 동작하는 경로가 기본이다. CI clean checkout에서도 같은 결과가 나야 한다.
- stdout/stderr 문구는 테스트와 사용자 디버깅 경로가 소비할 수 있다. 실패 메시지를 바꾸면 관련 테스트도
  의미 기준으로 갱신한다.
- 외부 프로젝트로 복사되는 workflow/script contract를 바꾸면 [../commands/init-dcness.md](../commands/init-dcness.md)와
  [../docs/plugin/init-dcness.md](../docs/plugin/init-dcness.md)의 inventory가 맞는지 확인한다.
- git/gh 명령은 가능하면 non-interactive로 두고, destructive 동작은 helper의 기존 guard 흐름을 따른다.

## 검증

```sh
node scripts/check_cross_refs.mjs                          # Node checker 는 해당 checker 를 직접 실행
bash -n scripts/pr-finalize.sh                             # shell wrapper 는 shebang 에 맞는 syntax check 먼저
python3.11 -m unittest discover -s tests -v < /dev/null    # Python gate 영향
PYTHON_BIN=/tmp/dcness-quality-venv/bin/python bash scripts/check_static_quality.sh   # static-quality 는 venv Python 명시
```
