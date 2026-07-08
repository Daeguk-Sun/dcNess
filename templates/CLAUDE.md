# templates 모듈 안내

전역 작업 규칙은 [../CLAUDE.md](../CLAUDE.md)가 진본이다. 이 파일은 `templates/` 안의 배포
seed와 workflow snippet을 고칠 때의 컴퍼스이며, 그 자체가 외부 활성 프로젝트의 공개 계약은 아니다.

## 소유 범위

- `/init-dcness`가 사용자 프로젝트로 복사할 수 있는 GitHub workflow snippet.
- `/design` 계열에서 사용하는 design variant canvas seed.
- 템플릿은 dcness self 안의 파일이지만, 내용은 사용자 프로젝트에서 실행되거나 편집될 수 있다.

## 먼저 볼 파일

- [github-workflows/](github-workflows/): git naming, PR body, doc path, doc sync, GitHub Project
  lifecycle workflow snippets.
- [design-variants/canvas.html](../templates/design-variants/canvas.html): design variant static HTML seed.
- [design-variants/_lib/canvas.js](../templates/design-variants/_lib/canvas.js)와
  [design-variants/_lib/show-ids.js](../templates/design-variants/_lib/show-ids.js): canvas 동작 helper.
- [design-variants/drafts/.gitkeep](../templates/design-variants/drafts/.gitkeep): draft directory seed 유지 파일.
- [../commands/init-dcness.md](../commands/init-dcness.md): workflow template 복사와 사용자 프로젝트 배포 흐름.
- [../tests/test_canvas_design_workflow.py](../tests/test_canvas_design_workflow.py),
  [../tests/test_doc_path_integrity.py](../tests/test_doc_path_integrity.py),
  [../tests/test_index_map_aggregate.py](../tests/test_index_map_aggregate.py): 주요 회귀 테스트.

## 수정 시 주의점

- workflow template은 사용자 repo의 `.github/workflows/`로 복사된다. dcness self 전용 경로나 개인 환경
  가정을 넣지 않는다.
- workflow가 호출하는 action/script 경로, checkout pin, repo owner 표기는 관련 테스트가 계약으로 본다.
- design variant seed는 사람이 바로 열어보고 편집하는 시작점이다. 생성된 draft 산출물과 seed 파일을 섞지
  않는다.
- 새 template을 추가하면 `/init-dcness` copy step, 문서 inventory, 테스트 fixture 중 누락된 경로가 없는지
  같이 확인한다.
- 외부 배포 영역에 내부 추적 ID나 dcness self만 아는 표현을 노출하지 않는다.

## 검증

- workflow template 변경: `python3.11 -m unittest tests.test_doc_path_integrity tests.test_index_map_aggregate -v < /dev/null`.
- design variant 변경: `python3.11 -m unittest tests.test_canvas_design_workflow -v < /dev/null`.
- 문서/링크 영향: `node scripts/check_cross_refs.mjs`.
- 범위가 섞이면 전체 suite `python3.11 -m unittest discover -s tests -v < /dev/null`를 돌린다.
