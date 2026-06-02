# enum 시스템 ROI 실측 베이스라인

> **이슈**: #277 (improve)
> **측정 일자**: 2026-05-08
> **데이터**: jajang (4 경로) + dcTest (1 경로) `.metrics/heuristic-calls.jsonl` 합산
> **기간**: 2026-04-30 ~ 2026-05-04
> **총 records**: 242

## 1. 요약

| 항목 | 값 |
|---|---|
| 총 interpret 호출 | 242 |
| `heuristic_hit` | 240 (**99.2%**) |
| `heuristic_ambiguous` | 2 (0.8%) |
| `heuristic_not_found` | 0 |
| `heuristic_empty` | 0 |

**임계 가설** (이슈 #277): agent 별 ambiguous > 10% → 폐기 우세.
**결과**: 전체 0.8%, 최대 agent 8.0% — 임계 미도달. **단순 cascade 비용 가설로는 폐기 명분 약함**.

다만 별도로 **handoff-matrix.md `§1` 과 실제 agent prompt enum 셋의 drift 9 건** 이 발견됨 — enum 시스템의 *유지보수 비용* 가설을 실측으로 입증.

## 2. Agent 별 outcome 분포

`harness/signal_io.py` 의 telemetry record 에 agent 이름이 없어 `allowed` enum 셋 시그니처로 분류 (handoff-matrix.md §1 매트릭스 기준).

| Agent (추론) | total | hit | ambiguous | 비고 |
|---|---:|---:|---:|---|
| pr-reviewer | 37 | 100.0% | 0.0% | binary |
| engineer (정상 셋) | 26 | 100.0% | 0.0% | 6 분기 hub |
| **architect.module-plan (drift)** | **25** | **92.0%** | **8.0%** | matrix=[READY_FOR_IMPL] / 실제=[READY_FOR_IMPL, SPEC_GAP_FOUND, TECH_CONSTRAINT_CONFLICT] |
| validator.code | 24 | 100.0% | 0.0% | 3 분기 |
| test-engineer (drift) | 21 | 100.0% | 0.0% | matrix=[TESTS_WRITTEN, SPEC_GAP_FOUND] / 실제=[TESTS_WRITTEN, SPEC_GAP_FOUND] (정상) |
| validator.ux-or-bugfix | 16 | 100.0% | 0.0% | binary, 두 mode 합산 |
| validator.design | 11 | 100.0% | 0.0% | 3 분기 |
| **미식별 [PLAN_READY, SPEC_GAP_FOUND, SPEC_GAP_FIXED]** | **11** | 100.0% | 0.0% | matrix 에 없음 — 옛 PLAN_VALIDATION 잔재 의심 |
| architect.system-design / tech-epic | 10 | 100.0% | 0.0% | binary 결과 |
| product-planner | 7 | 100.0% | 0.0% | 5 분기 hub |
| architect.module-plan (변종) | 7 | 100.0% | 0.0% | matrix=[READY_FOR_IMPL] / 실제 동일 |
| **미식별 [TESTS_READY, SPEC_INSUFFICIENT_FOR_TEST]** | **7** | 100.0% | 0.0% | test-engineer 의 또 다른 enum 셋 |
| ux-architect | 6 | 100.0% | 0.0% | 4 분기 |
| **architect.light-plan (drift)** | **6** | 100.0% | 0.0% | matrix=[LIGHT_PLAN_READY] / 실제=[+ SPEC_GAP_FOUND, TECH_CONSTRAINT_CONFLICT] |
| plan-reviewer | 5 | 100.0% | 0.0% | binary |
| **engineer 변종 [IMPL_DONE, IMPL_BLOCKED]** | **5** | 100.0% | 0.0% | matrix=[IMPL_DONE, IMPL_PARTIAL, SPEC_GAP_FOUND, TESTS_FAIL, IMPLEMENTATION_ESCALATE, POLISH_DONE] / IMPL_BLOCKED 는 matrix 에 없음 |
| qa | 5 | 100.0% | 0.0% | 5 분기 hub |
| **engineer 변종 [IMPL_DONE, IMPL_PARTIAL, IMPL_BLOCKED]** | 4 | 100.0% | 0.0% | drift |
| **engineer.polish 변종 [POLISH_DONE, IMPLEMENTATION_ESCALATE]** | 3 | 100.0% | 0.0% | matrix=[POLISH_DONE only — pr-reviewer 행에 통합] |
| **engineer 변종 [IMPL_DONE, SPEC_GAP_FOUND, TESTS_FAIL, IMPLEMENTATION_ESCALATE]** | 2 | 100.0% | 0.0% | drift |
| **engineer.polish 변종 [POLISH_DONE, TESTS_FAIL]** | 2 | 100.0% | 0.0% | drift |
| **architect.tech-epic 변종** | 1 | 100.0% | 0.0% | matrix=[SYSTEM_DESIGN_READY] / 실제=[TECH_EPIC_READY, TECH_EPIC_CHANGES_REQUESTED, TECH_EPIC_ESCALATE] |
| **architect.module-plan 변종 [DECOMPOSE_ESCALATE]** | 1 | 100.0% | 0.0% | matrix 에 없음 |

## 3. ambiguous 사례 분석

총 2 건 모두 `architect.module-plan` 의 새 enum 셋 `[READY_FOR_IMPL, SPEC_GAP_FOUND, TECH_CONSTRAINT_CONFLICT]`:

```
2026-04-30T15:41:57  ambiguous: no allowed enum found in tail
2026-05-04T15:09:45  ambiguous: no allowed enum found in tail
```

- 둘 다 `not_found` 성격 (휴리스틱이 prose 끝 2000 자에서 enum 단어 0 매칭)
- 즉 LLM 이 *결론 enum 을 prose 에 안 박음*. 사용자 가설 ("LLM 이 enum 안 박는 케이스") 의 실제 사례.
- 25 건 중 2 건 = 8% — 임계 10% 미만이지만 *MODULE_PLAN 단일 agent 한정* 으론 가장 높음.

## 4. drift 발견 — 진짜 비용 증거

`docs/plugin/handoff-matrix.md §1` 과 실제 agent prompt 의 enum 셋이 9 종류 drift:

### 4.1 architect.module-plan
- matrix `§1.4`: `READY_FOR_IMPL` 만 (1 enum)
- 실제 (코드 telemetry 기반): `[READY_FOR_IMPL, SPEC_GAP_FOUND, TECH_CONSTRAINT_CONFLICT]` (25 건) / `[READY_FOR_IMPL, SPEC_GAP_FOUND, DECOMPOSE_ESCALATE]` (1 건) / `[READY_FOR_IMPL]` 단일 (7 건)
- **drift 폭**: 1 → 3 종 변종

### 4.2 architect.light-plan
- matrix: `LIGHT_PLAN_READY` 만 (1 enum)
- 실제: `[LIGHT_PLAN_READY, SPEC_GAP_FOUND, TECH_CONSTRAINT_CONFLICT]` (6 건)

### 4.3 architect.tech-epic
- matrix: `SYSTEM_DESIGN_READY` 만 (system-design 와 통합 표기)
- 실제: `[TECH_EPIC_READY, TECH_EPIC_CHANGES_REQUESTED, TECH_EPIC_ESCALATE]` (1 건)

### 4.4 test-engineer
- matrix `§1.6`: `[TESTS_WRITTEN, SPEC_GAP_FOUND]`
- 실제 변종: `[TESTS_READY, SPEC_INSUFFICIENT_FOR_TEST]` (7 건) — 다른 enum 명

### 4.5 engineer
- matrix `§1.5`: `[IMPL_DONE, IMPL_PARTIAL, SPEC_GAP_FOUND, TESTS_FAIL, IMPLEMENTATION_ESCALATE, POLISH_DONE]`
- 실제 변종 4 종: `[IMPL_DONE, IMPL_BLOCKED]` (5 건) / `[IMPL_DONE, IMPL_PARTIAL, IMPL_BLOCKED]` (4 건) / `[IMPL_DONE, SPEC_GAP_FOUND, TESTS_FAIL, IMPLEMENTATION_ESCALATE]` (2 건) / `[POLISH_DONE, IMPLEMENTATION_ESCALATE]` (3 건) / `[POLISH_DONE, TESTS_FAIL]` (2 건)
- IMPL_BLOCKED 는 matrix 에 부재. 다양한 mode 별 부분 enum 셋이 코드에 흩어져 있음.

### 4.6 미식별 enum 셋 (matrix 에 없음)
- `[PLAN_READY, SPEC_GAP_FOUND, SPEC_GAP_FIXED]` (11 건) — 옛 PLAN_VALIDATION 폐기 (`§1.9 note`) 후 잔재? `agents/architect/module-plan.md` 등 어디서 사용 중일 가능성.

## 5. 해석

### 5.1 cascade 비용 가설 (이슈 #277 임계)
- ambiguous 0.8% (전체) / 8% (최악 agent) — 임계 10% 미달
- enum 시스템 자체는 LLM 이 거의 100% 박음. 형식 강제 효과 강함.
- **이 단일 가설로는 enum 폐기 명분 약함**.

### 5.2 결정성 환상 가설 (대화 검토)
- 입력 (서브 에이전트 emit) 자체가 LLM 비결정. 휴리스틱 추출 결정성은 형식.
- 99.2% hit rate 는 *결정성* 이 아니라 *prompt 강제력 (LLM 순응도)* 의 측정.
- 메인 CC 가 prose 직접 분류하는 시스템도 LLM 자연어 분류 — 단계만 한 번 줄어듦. 동등한 비결정성.
- **결정성 측면에선 enum 의 가치 부재 — 사용자 가설 유효**.

### 5.3 자율 vs 가이드레일 가설
- agent prompt 의 enum 표 = 결론 표현 N 개 옵션 강제 = `orchestration.md §0` 의 안티패턴 1 (룰이 룰을 부르는 reactive cycle) + 안티패턴 3 (에이전트 자율성 침해) 와 충돌.
- 폐기 시: 자유 prose + 메인 분류 → 자율도 ↑.
- **유지 시 정당화 가능 영역**: 다중 분기 hub (engineer 6, qa 5, product-planner 5) 에서 LLM 이 사고할 옵션 카탈로그 역할.

### 5.4 유지보수 비용 가설 — **실측 입증**
- handoff-matrix.md `§1` 과 실제 코드 drift **9 종류** (위 §4)
- enum 추가/변경 시 4 곳 동기 의무 (agent prompt + matrix + 코드 + telemetry) — 실제로는 안 지켜지고 있음.
- matrix 가 SSOT 라고 박혀 있지만 **실제 SSOT 는 코드의 `agents/*.md`**. matrix 는 stale.
- **이 비용은 enum 수가 늘수록 곱셈으로 증가**. drift 가 누적되면 더 이상 매트릭스를 신뢰할 수 없게 됨 (이미 그 단계).

## 6. 결론

| 가설 | 검증 결과 | 폐기 명분 |
|---|---|---|
| cascade 비용 (ambiguous > 10%) | **기각** (0.8%) | 약함 |
| 결정성 환상 | **유효** (LLM 입력 비결정) | 중간 |
| 자율 vs 가이드레일 | **유효** (원칙 2 와 충돌) | 중간 |
| 유지보수 비용 (drift) | **실측 입증** (9 종 drift) | 강함 |

**종합 판단**: 단순 cascade 비용으로는 폐기 못 해도, **drift 누적 + 자율 원칙 + 결정성 환상의 합** 으로 폐기 우세. 다만 *전면 폐기* vs *부분 환원* 은 별도 결정 필요.

### 6.1 권장안 후보 (별도 이슈로 결정)

**옵션 A — 전면 폐기 (prose-only routing)** ✅ **채택·완결** (이슈 #280/#284)
- agent prompt: "마지막 단락에 결론 + 권장 다음 단계 자유롭게 명시" — 완료 (이슈 #283, enum 단어는 *권장 표현* 으로 보존)
- 메인 CC: prose 읽고 routing — 완료
- handoff-matrix.md `§1` 을 자연어 routing 가이드로 재포맷 — 완료 (PR #544)
- `interpret_strategy.py` / `signal_io.interpret_signal` (기계 enum 추출) 폐기 — 완료. enum *어휘* 는 권장 표현으로 보존 (어휘 ≠ 기계추출)
- 비용: 메인 분류 부담 ↑, ambiguous 명시적 검출 상실
- 가치: drift 비용 0, 자율 ↑, 코드 -200 LOC

**옵션 B — drift 정정만 (보수적)**
- handoff-matrix.md `§1` 을 실제 코드 기준으로 재작성
- agent.md 에 enum 표 SSOT 명시
- 코드 ↔ 매트릭스 정합 검증 CI 추가 (예: `agents/*.md` 의 enum 표 vs matrix vs `interpret_with_fallback` allowed 비교)
- 비용: 새 검증 인프라
- 가치: enum 시스템 유지하되 drift 재발 방지

**옵션 C — 부분 환원 (binary 만 폐기)**
- 다중 분기 hub (engineer / qa / product-planner / ux-architect / architect.spec-gap / architect.docs-sync / design-critic / validator.code / validator.design) — enum 유지
- binary agent (pr-reviewer / security-reviewer / validator BUGFIX·UX) — prose-only 환원
- 비용: 이중 시스템 복잡도
- 가치: 핵심 분기 로직 결정성 유지, 단순 영역만 자율화

## 7. 다음 단계

1. 본 보고서 검토 (alruminum)
2. 옵션 A/B/C 중 결정
3. 결정에 따라 별도 이슈 생성 (구현 작업)

## 8. 참조

- 이슈 #277 (본 측정의 트리거)
- [`harness/signal_io.py`](../../harness/signal_io.py) — prose 파일 I/O (옛 `interpret_signal` / `_heuristic_interpret` 휴리스틱은 폐기, 이슈 #284)
- [`docs/plugin/handoff-matrix.md`](../plugin/handoff-matrix.md) `§1` — drift 발견된 매트릭스
- [`docs/plugin/orchestration.md`](../plugin/orchestration.md) `§0` — LLM 자율 + 최소 가이드레일 (강제 영역 2 + 안티패턴 4, dcness-rules.md 폐기 후 흡수처)
- 분석 방식: manual — 본 보고서는 telemetry 샘플 + heuristic 룰 매핑을 수동으로 정리. 재현용 스크립트는 미작성 (필요 시 별 PR).
