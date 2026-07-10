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
- [lib/](../scripts/lib/): 여러 Node checker와 shell wrapper가 공유하는 helper.

## 수정 시 주의점

- `sh` shebang 파일은 POSIX shell 기준으로 유지한다. Bash 기능이 필요하면 shebang과 호출 문서를 같이 본다.
- Node checker는 외부 패키지 없이 동작하는 경로가 기본이다. CI clean checkout에서도 같은 결과가 나야 한다.
- stdout/stderr 문구는 테스트와 사용자 디버깅 경로가 소비할 수 있다. 실패 메시지를 바꾸면 관련 테스트도
  의미 기준으로 갱신한다.
- 외부 프로젝트로 복사되는 workflow/script contract를 바꾸면 [../commands/init-dcness.md](../commands/init-dcness.md)와
  [../docs/plugin/init-dcness.md](../docs/plugin/init-dcness.md)의 inventory가 맞는지 확인한다.
- git/gh 명령은 가능하면 non-interactive로 두고, destructive 동작은 helper의 기존 guard 흐름을 따른다.

## 검증

- Node checker: `node scripts/check_cross_refs.mjs`처럼 해당 checker를 직접 실행한다.
- Shell wrapper: `bash -n scripts/pr-finalize.sh` 또는 shebang에 맞는 syntax check를 먼저 돌린다.
- Python gate 영향: `python3.11 -m unittest discover -s tests -v < /dev/null`.
- static-quality 관련 변경은 `PYTHON_BIN=/tmp/dcness-quality-venv/bin/python bash scripts/check_static_quality.sh`
  형태로 venv Python을 명시해 재현한다.
