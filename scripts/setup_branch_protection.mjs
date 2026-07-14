#!/usr/bin/env node
/**
 * dcNess main branch protection 적용 스크립트 (현재 비활성 — 옵션 도구)
 * 참고: docs/plugin/hooks.md 의 CI workflow / branch protection 관계.
 *
 * ⚠️ 현재 상태 (DCN-CHG-20260501-06 이후): main protection OFF.
 *   doc-sync 만 실질 강제하면 충분 + paths 필터 폐기 트레이드오프 회피.
 *   본 스크립트는 필요 시 재활성용 보존.
 *
 * 목적:
 *   proposal §5 Phase 3 "Gate 5 (PASS flag) → branch protection required reviewers"
 *   를 GitHub Repository Settings 로 외부화. RWHarness 의 in-process PASS flag 폐기 정합.
 *
 * 사용:
 *   gh auth status                              # 인증 확인 (admin 권한 필요)
 *   node scripts/setup_branch_protection.mjs    # main 브랜치에 적용
 *   node scripts/setup_branch_protection.mjs --dry-run   # 실제 호출 X, 페이로드만 출력
 *
 * 멱등성: 같은 페이로드 반복 적용 안전 (PUT). diff 없이 200 반환.
 *
 * 의존: gh CLI 인증 + 본 저장소 admin 권한.
 *   - 비-admin 실행 시: HTTP 403 / "Resource not accessible by integration".
 *   - 그 경우 GitHub Settings > Branches/Rulesets 에서 required check 를 수동 설정한다 (docs/plugin/hooks.md 참조).
 */
import { execSync } from 'node:child_process';

const REPO = 'alruminum/dcNess'; // hardcoded — fork 시 본 라인만 정정
const BRANCH = 'main';

// 필수 status checks (.github/workflows/*.yml 의 jobs.<name>.name 필드 기준)
// #182 머지 후: Document Sync / Task-ID gate 폐기. unittest / manifest 는 paths-filter 로 conditional → required 부적합.
const REQUIRED_CHECKS = [
  'git-naming-spec gate',
];

const PAYLOAD = {
  required_status_checks: {
    strict: true, // 머지 전 base 와 sync 필수
    contexts: REQUIRED_CHECKS,
  },
  enforce_admins: false, // governance 운영자(자기) 가 hot-fix 가능
  // DCN-CHG-20260501-04: 1인 운영 — PR author self-approve 불가 (GitHub 정책).
  // CI 4 checks 가 게이트 본질 → review approve 의무 폐기. CI 통과만 강제.
  required_pull_request_reviews: null,
  restrictions: null, // push 권한 제한 없음 (PR 만 강제)
  required_linear_history: true, // squash merge 전제
  allow_force_pushes: false,
  allow_deletions: false,
  required_conversation_resolution: true,
  lock_branch: false,
  allow_fork_syncing: false,
};

const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');

console.log(`[branch-protection] target: ${REPO}/branches/${BRANCH}/protection`);
console.log(`[branch-protection] required checks: ${REQUIRED_CHECKS.join(', ')}`);
console.log(`[branch-protection] required reviewers: 0 (1인 운영 — CI 4 checks 가 게이트 본질, DCN-30-04)`);

if (dryRun) {
  console.log('[branch-protection] --dry-run — payload 만 출력:');
  console.log(JSON.stringify(PAYLOAD, null, 2));
  process.exit(0);
}

// gh auth 확인
try {
  execSync('gh auth status', { stdio: ['ignore', 'pipe', 'pipe'] });
} catch {
  console.error('[branch-protection] FAIL — gh CLI 인증 필요. `gh auth login` 후 재시도.');
  process.exit(1);
}

const payloadJson = JSON.stringify(PAYLOAD);
const cmd = `gh api -X PUT repos/${REPO}/branches/${BRANCH}/protection --input -`;

try {
  const result = execSync(cmd, {
    input: payloadJson,
    encoding: 'utf8',
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  console.log('[branch-protection] PASS — 브랜치 보호 적용 완료');
  // 응답은 큼 — 핵심 필드만 출력
  try {
    const parsed = JSON.parse(result);
    console.log(`  required_status_checks.strict: ${parsed.required_status_checks?.strict}`);
    console.log(`  required_approving_review_count: ${parsed.required_pull_request_reviews?.required_approving_review_count}`);
    console.log(`  allow_force_pushes: ${parsed.allow_force_pushes?.enabled}`);
  } catch {
    console.log('  (응답 파싱 실패 — gh api raw 출력 생략)');
  }
} catch (e) {
  console.error('[branch-protection] FAIL — gh api 호출 실패:');
  console.error(`  ${e.stderr?.toString() || e.message}`);
  console.error('');
  console.error('가능한 원인:');
  console.error('  1. admin 권한 부족 → GitHub Settings > Branches/Rulesets 에서 수동 적용 (docs/plugin/hooks.md)');
  console.error('  2. 필수 check 이름 mismatch → 실제 워크플로우 jobs.<id>.name 확인');
  console.error('  3. branch protection plan 제한 (private repo + free plan 일부 기능 제한)');
  process.exit(1);
}
