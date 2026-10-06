# tests 모듈 안내

전역 작업 규칙은 [../CLAUDE.md](../CLAUDE.md)가 진본이다. 이 파일은 `tests/`에서 어떤
회귀 테스트를 먼저 볼지 좁혀 주는 컴퍼스다.

## 소유 범위

- Python `unittest` 기반 회귀 suite.
- `harness/`, `scripts/`, `templates/`, `agents/`, `skills/`, `docs/plugin/`의 공개 계약과
  guard 동작을 검증하는 테스트가 함께 있다.
- 테스트는 제품 계약을 고정해야 하며, 현재 구현의 우연한 출력 형식을 과하게 고정하지 않는다.

## 먼저 볼 파일

- [test_hooks.py](test_hooks.py), [test_tdd_guard.py](test_tdd_guard.py),
  [test_generated_tdd_hooks.py](test_generated_tdd_hooks.py): hook과 TDD guard.
- [test_agent_boundary.py](test_agent_boundary.py), [test_agent_routing.py](test_agent_routing.py):
  agent 권한 경계와 routing 판정.
- [test_signal_io.py](test_signal_io.py), [test_run_review.py](test_run_review.py):
  prose 결과와 run review 공개 계약.
- [test_git_naming.py](test_git_naming.py), [test_pr_body.py](test_pr_body.py),
  [test_pr_trailer.py](test_pr_trailer.py), [test_pr_finalize_non_default_base.py](test_pr_finalize_non_default_base.py):
  git/PR lifecycle 계약.
- [test_doc_path_integrity.py](test_doc_path_integrity.py), [test_index_map_aggregate.py](test_index_map_aggregate.py),
  [test_design_artifact_audit.py](test_design_artifact_audit.py): 문서/템플릿 gate.
- [test_canvas_design_workflow.py](test_canvas_design_workflow.py): design variant 템플릿과 canvas workflow.
- [test_public_surface.py](test_public_surface.py), [test_surface_docs_sync.py](test_surface_docs_sync.py):
  public surface와 문서 동기화.
- [test_product_journey.py](test_product_journey.py),
  [test_product_journey_scenarios.py](test_product_journey_scenarios.py),
  [test_product_journey_judgment_inputs.py](test_product_journey_judgment_inputs.py),
  [test_epic_outcome.py](test_epic_outcome.py): 제품 journey 실행 기록과 Epic 결과 요약.
- [test_provider_chain.py](test_provider_chain.py), [test_impl_loop_launch.py](test_impl_loop_launch.py),
  [test_provider_failure_cache.py](test_provider_failure_cache.py): `/impl-loop` provider 실행 체인.
  `test_provider_chain.py`는 이 모듈에서 가장 큰 파일이다.
- [test_design_variants_generator.py](test_design_variants_generator.py),
  [design_variants_browser_smoke.mjs](design_variants_browser_smoke.mjs): 디자인 보드 생성 스크립트와
  보드 런타임. 뒤 파일은 headless Chrome 이 필요하고 `unittest discover` 에 포함되지 않는다.
- [test_guard_core.py](test_guard_core.py), [test_ci_workflows_install.py](test_ci_workflows_install.py):
  guard 공통 판정 계약과 CI workflow 복사 설치.

## 의존 관계 (dependencies)

- 테스트는 `harness/`, `scripts/`, `templates/`, `skills/`, `docs/plugin/`의 실제 파일을 읽는다.
  그 파일의 경로나 문구를 바꾸면 해당 계약 테스트가 실패한다.
- 파일 이름에 `_contract`가 들어간 테스트는 대부분 `skills/`, `docs/plugin/agents/`, `codex/skills/` 문서의
  문구를 계약으로 고정한다. 그 문서를 고칠 때는 대응하는 계약 테스트를 함께 본다.
- CI 는 [../.github/workflows/python-tests.yml](../.github/workflows/python-tests.yml)에서 전체 suite 와
  브라우저 smoke test 를 순서대로 실행한다.

## 자주 하는 수정 (common change patterns)

- **문서 문구를 고쳤더니 계약 테스트가 실패한다.** 먼저 제품 계약이 바뀐 것인지 판단한다.
  계약이 바뀌었으면 테스트의 기대 문구를 고친다. 계약이 그대로면 문서를 되돌린다.
- **새 테스트 파일을 추가한다.** 파일 이름을 `test_*.py`로 하면 `unittest discover`가 자동으로 실행한다.
  등록할 목록은 없다.
- **테스트 대상이 새 디렉터리에 있다.** [../.github/workflows/python-tests.yml](../.github/workflows/python-tests.yml)의
  `paths`에 그 경로가 있는지 확인한다. 없으면 그 경로만 바꾼 PR 에서 CI 가 실행되지 않는다.

## 수정 시 주의점

- 테스트 fixture는 가능한 한 `TemporaryDirectory` 안에서 만들고 repo 상태나 네트워크에 의존하지 않는다.
- stdin을 읽는 코드 경로가 있으면 전체 suite 실행 시 hang 나지 않도록 `< /dev/null` 재현을 염두에 둔다.
- 실패한 테스트의 기대값만 바꾸기 전에 제품 계약이 바뀐 것인지, 구현 회귀인지 먼저 분리한다.
- shell/node script 테스트는 실제 CLI 호출과 stderr/stdout을 같이 본다. 사용자에게 보이는 실패 메시지는
  계약의 일부일 수 있다.
- 시간, PID, git 상태, GitHub CLI를 다루는 테스트는 deterministic fixture와 timeout을 둔다.

## 검증

```sh
python3.11 -m unittest tests.test_context_docs -v < /dev/null   # 단일 파일은 모듈명을 지정
python3.11 -m unittest discover -s tests -v < /dev/null         # 전체 suite
node tests/design_variants_browser_smoke.mjs                    # 브라우저 smoke test
```

- 주의: 로컬 macOS 에서는 Chrome 이 결과를 출력한 뒤 종료하지 않아 브라우저 smoke test 가 timeout 으로
  실패한다. 판정은 CI(`.github/workflows/python-tests.yml`) 결과로 한다.
- `templates/github-workflows/`, audited script, `harness/` 변경은 pre-commit hook
  (`scripts/check_python_tests.sh`)이 전체 unit suite를 실행할 수 있다.
