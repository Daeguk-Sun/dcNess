# Build Worker Report

`[task<i> · <slug>] PASS|SPEC_GAP_FOUND|TESTS_FAIL|VALIDATION_BLOCKED|IMPLEMENTATION_ESCALATE`

- mode: `task | JOURNEY_ENV_PREFLIGHT | JOURNEY_CONVERGENCE`

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

## Journey evidence (해당 mode만)

- acceptance_environment / worker probe:
- 자동 준비 또는 검출 불확실 근거:
- harness_paths:
- iteration별 실패 서명 / 수정 / 진행 여부:
- final tip 실행 결과:
- 수렴 commit sha:

## Cartography impact

- runtime entrypoint:
- capability/state owner:
- dependency edge:
- public surface:
- 상태 before/after와 증거:
- 관련 epic/decision:
- 변화 없음이면 그 근거:
- tracked/local-only 문서 정책과 durable handoff:

## replacement/refactor hygiene (해당 task만)

- old/new surface 관계:
- 제거한 call site / DI / route / registration / resource / test double / suppression:
- 보존한 seam과 이유 / owner:
- unknown 또는 후속 감사 필요 지점:

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
