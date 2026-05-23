# Issue Lifecycle

> **Status**: ACTIVE
> **Scope**: GitHub 이슈 lifecycle 운영·메커니즘 SSOT. 등록 양식·트레일러 키워드·완료 *룰* 은 [`git-spec.md`](git-spec.md) §7~§9 참조 — 본 문서는 *어떻게 실행하느냐* (gh API 호출 / 멱등성 / pre-flight gate) 만 다룬다.

## 0. 이슈 계층

```
epic issue ─┬─ story issue ── (task: PR 기반, 이슈 없음)
            └─ story issue ── (task: PR 기반, 이슈 없음)
```

- **epic** = 1개 stories.md 단위
- **story** = stories.md 안의 Story N 단위
- **task** = impl/NN-*.md 단위. PR 1개 = task 1개. GitHub 이슈 X — PR 자체가 추적 단위

> 양식 (레이블 / 마일스톤 / 제목 / 본문 / stories.md 기록 형식) 은 [`git-spec.md`](git-spec.md) §7 SSOT.

## 1. Sub-issue 연결 (epic ↔ story, gh API 메커니즘)

자동화 = [`scripts/create_epic_story_issues.sh`](../../scripts/create_epic_story_issues.sh) — stories.md parse + epic/story 이슈 생성 + sub-issue API 연결 한 명령으로 처리. 별도 호출 (구 ISSUE_SYNC) X.

수동 호출 시 (script 미사용):

```bash
# story_id = mcp__github__create_issue 응답의 .id 필드 (database id, NOT .number)
gh api -X POST repos/{owner}/{repo}/issues/{epic_number}/sub_issues \
  -F sub_issue_id={story_id}
# 주의: -f (string) 아닌 -F (typed) — -f 시 422 Invalid property
```

멱등성: 재호출 전 `gh api repos/{owner}/{repo}/issues/{epic_number} --jq '.sub_issues_summary.total'` 로 연결 상태 조회. 누락 story 만 추가 (이미 연결된 story 재추가 시 422).

task 는 GitHub 이슈 X — [`git-spec.md`](git-spec.md) §8 PR 트레일러로만 추적.

## 2. 미등록 허용 모드

프로젝트가 미등록 모드 (spike / 잡탕 epic 등) 채택 시 stories.md 상단:

```
**GitHub Epic Issue:** 미등록 (사유: <spike / 잡탕 / …>)
```

명시 없는 미등록 = 위반. 발견 시 backfill 의무 — 메인이 [`git-spec.md`](git-spec.md) §7 따라 `mcp__github__create_issue` 1회 호출 + stories.md 번호 patch.

## 3. 멱등성 (등록 전 매치 체크)

`mcp__github__create_issue` 전: stories.md 의 `**GitHub Epic Issue:**` / `**GitHub Issue:**` 매치 검사. 링크 있으면 skip. stories.md 가 이슈 등록 상태의 SSOT.

## 4. 마일스톤 number 조회

`mcp__github__create_issue` 의 `milestone` 파라미터는 **이름이 아닌 숫자(number)** 요구. 매 세션 1회 조회:

```bash
gh api repos/{owner}/{repo}/milestones --jq '.[] | {number, title}'
```

프로젝트별 number 다를 수 있음 — 캐싱 X.

## 5. mid-flow 누락 차단 (pre-flight gate)

`/impl` / `/impl-loop` / `/architect-loop` (ux-architect / system-architect / module-architect × K) 진입 시 부모 epic stories.md 상단 매치 강제:

- `**GitHub Epic Issue:** [#\d+]` (정식 등록), 또는
- `**GitHub Epic Issue:** 미등록 (사유: …)` (§2 허용 모드)

매치 0건 → 즉시 STOP + 사용자 보고. silent skip ("이슈 번호 없음 — 생략하고 진행") 금지.

story 이슈 부재 시 동일 패턴 (Story N 헤더 직하 `**GitHub Issue:** [#\d+]` 매치).

## 6. 참조

- 등록·트레일러·완료 *룰* SSOT: [`git-spec.md`](git-spec.md) §7~§9
- 시퀀스 / 핸드오프: [`orchestration.md`](orchestration.md)
- loop spec (7 loop 행별 풀스펙): [`orchestration.md`](orchestration.md) §4
- product-plan skill (메인 직접): [`../../commands/product-plan.md`](../../commands/product-plan.md)
- system-architect (impl 목차 표 SSOT): [`../../agents/system-architect.md`](../../agents/system-architect.md)
- module-architect (impl 본문 detail per task): [`../../agents/module-architect.md`](../../agents/module-architect.md)
- engineer: [`../../agents/engineer.md`](../../agents/engineer.md) §1 task = 1 PR
