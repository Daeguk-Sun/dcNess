# Build Worker Report

`[task<i> · <slug>] PASS|SPEC_GAP_FOUND|TESTS_FAIL|VALIDATION_BLOCKED|IMPLEMENTATION_ESCALATE`

## Phase Summary

- build-test:
- build-impl:
- build-validate:
- phase prose ls:

## 핵심 finding

-

## PR 본문 초안

### 관련 이슈 번호

Part of #N

task-index: <i>/<total>

### 배경 및 문제

-

### 작업내용

-

### Test Plan

- [ ] 새 테스트 RED->GREEN 확인
- [ ] 회귀 검증

## phase prose 파일

- `<run_dir>/build-test.md`
- `<run_dir>/build-impl.md`
- `<run_dir>/build-validate.md`

위 3개는 실제 `ls`로 확인한 경로만 쓴다. `<run_dir>`는 harness-state run_dir이며 `phases/<RUN_ID>/`를 쓰지 않는다.

마지막 단락에 결론 단어와 사유를 다시 쓴다.
