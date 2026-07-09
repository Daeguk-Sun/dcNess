# Build Worker Report

`[task<i> · <slug>] PASS|SPEC_GAP_FOUND|TESTS_FAIL|VALIDATION_BLOCKED|IMPLEMENTATION_ESCALATE`

## Phase Summary

- build-test:
- build-impl:
- build-validate:
- phase prose ls:
- commit:

## 핵심 finding

-

## 동작 증거

- 핵심 AC별 증거:
- mock/stub/fake 경계:
- typecheck/compile warning:

## 메인 인계

- commit sha:
- 변경 단위:
- 메인이 다음에 할 일: `dcness-story-runner mark --status completed --commit <sha>` 또는 finding 처리
- PR trailer 판단에 필요한 정보:

## phase prose 파일

- `<run_dir>/build-test.md`
- `<run_dir>/build-impl.md`
- `<run_dir>/build-validate.md`

위 3개는 실제 `ls`로 확인한 경로만 쓴다. `<run_dir>`는 harness-state run_dir이며 `phases/<RUN_ID>/`를 쓰지 않는다.

마지막 단락에 결론 단어와 사유를 다시 쓴다.
