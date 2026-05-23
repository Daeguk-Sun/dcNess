#!/usr/bin/env node
/**
 * PR body 안 issue 트레일러 (`Closes #N` / `Fixes #N` / `Resolves #N` / `Part of #N`) 검증 게이트.
 * 규칙 정의: docs/plugin/git-spec.md §8.1 (SSOT)
 *
 * 본 프로젝트(및 dcness 활성 프로젝트) 는 regular merge 채택 (squash 금지).
 * regular merge 시 GitHub auto-close 는 *PR body* 또는 *squash merge commit message* 만 인식.
 * 따라서 commit message 안 `Closes #N` 만으론 issue 자동 close 안 됨 — PR body 에 반드시 써야 함.
 *
 * 트레일러 종류:
 *   - Closes #N / Fixes #N / Resolves #N — auto-close 발동 (story / epic 마지막 task PR)
 *   - Part of #N                          — 단순 언급, auto-close 발동 X (중간 task PR default)
 * 게이트 의미 = "이슈 트레일러 1+ 강제" (이슈 추적 누락 차단). close-keyword 단독 강제는 over-firing.
 *
 * 사용:
 *   node scripts/check_pr_body.mjs --body "<PR body 전체>"
 *   echo "<PR body>" | node scripts/check_pr_body.mjs --stdin
 *
 * exit 0: 통과 (트레일러 1+ 매치 OR 명시적 예외 마커 1+ 매치)
 * exit 1: 위반 (둘 다 0 매치)
 *
 * 예외 우회 — body 안에 다음 line 쓰면 통과:
 *   Document-Exception-PR-Close: <사유>
 *   사유 예) "infra-only — issue 없음", "follow-up split — close 별도 PR"
 */

const TRAILER_RE = /(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?|part\s+of)\s*#\d+/i;
const EXCEPTION_RE = /^\s*Document-Exception-PR-Close:\s*\S+/im;

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

async function main() {
  const args = process.argv.slice(2);
  const mode = args[0];

  let body;
  if (mode === '--body') {
    body = args.slice(1).join(' ');
  } else if (mode === '--stdin') {
    body = await readStdin();
  } else {
    console.error('[pr-body] 사용법: --body "<text>" | --stdin');
    process.exit(1);
  }

  if (typeof body !== 'string' || body.length === 0) {
    console.error('[pr-body] FAIL — PR body 가 비어있음. 최소 트레일러 1건 또는 Document-Exception-PR-Close 마커 쓸 것.');
    process.exit(1);
  }

  if (EXCEPTION_RE.test(body)) {
    console.log('[pr-body] PASS — Document-Exception-PR-Close 마커 매치 (트레일러 검사 우회).');
    process.exit(0);
  }

  if (TRAILER_RE.test(body)) {
    const match = body.match(TRAILER_RE)[0];
    console.log(`[pr-body] PASS — 트레일러 매치: "${match}"`);
    process.exit(0);
  }

  console.error('[pr-body] FAIL — PR body 에 issue 트레일러 부재.');
  console.error('  허용 패턴 (대소문자 무관, 1+ 매치):');
  console.error('    Closes #N   |  Close #N   |  Closed #N        ← auto-close 발동 (마지막 task PR)');
  console.error('    Fixes #N    |  Fix #N     |  Fixed #N         ← auto-close 발동');
  console.error('    Resolves #N |  Resolve #N |  Resolved #N      ← auto-close 발동');
  console.error('    Part of #N                                     ← 단순 언급 (중간 task PR default)');
  console.error('');
  console.error('  근거: 본 프로젝트는 regular merge 채택 — GitHub auto-close 는 *PR body* 만 인식.');
  console.error('       commit message 안 Closes #N 만으론 issue 자동 close 안 됨.');
  console.error('  SSOT: docs/plugin/git-spec.md §8.1');
  console.error('');
  console.error('  예외 우회 — issue 없는 infra/follow-up PR 등은 다음 line 쓸 것:');
  console.error('    Document-Exception-PR-Close: <사유>');
  process.exit(1);
}

main().catch((err) => {
  console.error(`[pr-body] 예기치 못한 오류: ${err.message}`);
  process.exit(2);
});
