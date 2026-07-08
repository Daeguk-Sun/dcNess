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
- [test_signal_io.py](test_signal_io.py), [test_run_review.py](test_run_review.py),
  [test_sub_eval.py](test_sub_eval.py): prose 결과, run review, validator helper.
- [test_git_naming.py](test_git_naming.py), [test_pr_body.py](test_pr_body.py),
  [test_pr_trailer.py](test_pr_trailer.py), [test_pr_finalize_integration.py](test_pr_finalize_integration.py):
  git/PR lifecycle 계약.
- [test_doc_path_integrity.py](test_doc_path_integrity.py), [test_index_map_aggregate.py](test_index_map_aggregate.py),
  [test_design_artifact_audit.py](test_design_artifact_audit.py): 문서/템플릿 gate.
- [test_canvas_design_workflow.py](test_canvas_design_workflow.py): design variant 템플릿과 canvas workflow.
- [test_public_surface.py](test_public_surface.py), [test_surface_docs_sync.py](test_surface_docs_sync.py):
  public surface와 문서 동기화.

## 수정 시 주의점

- 테스트 fixture는 가능한 한 `TemporaryDirectory` 안에서 만들고 repo 상태나 네트워크에 의존하지 않는다.
- stdin을 읽는 코드 경로가 있으면 전체 suite 실행 시 hang 나지 않도록 `< /dev/null` 재현을 염두에 둔다.
- 실패한 테스트의 기대값만 바꾸기 전에 제품 계약이 바뀐 것인지, 구현 회귀인지 먼저 분리한다.
- shell/node script 테스트는 실제 CLI 호출과 stderr/stdout을 같이 본다. 사용자에게 보이는 실패 메시지는
  계약의 일부일 수 있다.
- 시간, PID, git 상태, GitHub CLI를 다루는 테스트는 deterministic fixture와 timeout을 둔다.

## 검증

- 단일 파일: `python3.11 -m unittest tests.test_context_docs -v < /dev/null`처럼 모듈명을 지정한다.
- 전체 suite: `python3.11 -m unittest discover -s tests -v < /dev/null`.
- `templates/github-workflows/`, audited script, `harness/` 변경은 pre-commit hook이 전체 unit suite를
  실행할 수 있다.
