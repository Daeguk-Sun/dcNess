#!/usr/bin/env node
/**
 * git-spec 형식 검증 게이트
 * 규칙 정의: docs/plugin/git-spec.md (SSOT)
 *
 * 사용:
 *   node scripts/check_git_naming.mjs --branch <branch-name>
 *   node scripts/check_git_naming.mjs --title <commit-or-pr-title>
 *
 * exit 0: 통과
 * exit 1: 위반
 */

// 통일 기본 제약: 소문자 시작 + [a-z0-9_-] + 최소 3자 (= 첫 1자 + {2,})
// 4 패턴 — feature/epic{N}_story{N}_* (스토리 강제) / feature/<desc> (자유·통합·공통 epic{N}_common_*) / fix/issue_* / docs/<desc>
// generic feature 에 (?!epic\d+_story) 부정선행 — "epic{N}_story" 로 시작하는 malformed 스토리 브랜치(desc<3자 / story 비숫자)가
// generic 으로 새는 것 차단 → 스토리 작업은 strict 패턴만 통과. 공통 task 의 epic{N}_common_* 은 _story 아니라 generic 통과.
const BRANCH_RE = /^(feature\/(epic\d+_story\d+_[a-z][a-z0-9_-]{2,}|(?!epic\d+_story)[a-z][a-z0-9_-]{2,})|fix\/issue\d+(?:_\d+)*_[a-z][a-z0-9_-]{2,}|docs\/[a-z][a-z0-9_-]{2,})$/;
// 5 형식 — [epic{N}][story{N}] (스토리 단위) / [epic{N}] (epic 단위, 통합 → main 머지) / [issue-{N}] / [docs] / [feature]
const TITLE_RE  = /^(\[epic\d+\](\[story\d+\])?|\[issue-\d+\]|\[docs\]|\[feature\]) .+/;

const args = process.argv.slice(2);
const mode = args[0];
const value = args.slice(1).join(' ');

if (!mode || !value) {
  console.error('[git-naming] 사용법: --branch <name> | --title <title>');
  process.exit(1);
}

if (mode === '--branch') {
  if (!BRANCH_RE.test(value)) {
    console.error(`[git-naming] FAIL — 브랜치명 형식 위반: "${value}"`);
    console.error('  허용 패턴:');
    console.error('    feature/epic{N}_story{N}_{desc}    (스토리 작업 impl — strict 강제)');
    console.error('    feature/epic{N}_common_{desc}      (epic 공통 task — story 없음)');
    console.error('    feature/{desc}                     (자유 feature / 통합 브랜치)');
    console.error('    fix/issue{N}_{desc}                (단일 이슈)');
    console.error('    fix/issue{N}_{M}_{desc}            (복수 이슈)');
    console.error('    docs/{desc}                        (문서)');
    console.error('  공통: {desc} = 소문자 + [a-z0-9_-] + 최소 3자. feature/<desc> 의 desc 는 "epic{N}_story" 로 시작 불가(malformed 스토리 차단).');
    process.exit(1);
  }
  console.log(`[git-naming] PASS — branch: ${value}`);

} else if (mode === '--title') {
  if (!TITLE_RE.test(value)) {
    console.error(`[git-naming] FAIL — 커밋/PR 제목 형식 위반: "${value}"`);
    console.error('  허용 패턴:');
    console.error('    [epic{N}][story{N}] {설명}    (스토리 단위)');
    console.error('    [epic{N}] {설명}              (epic 단위, 통합 → main 머지)');
    console.error('    [issue-{N}] {설명}            (버그픽스)');
    console.error('    [docs] {설명}                 (문서)');
    console.error('    [feature] {설명}              (자유 feature)');
    process.exit(1);
  }
  console.log(`[git-naming] PASS — title: ${value}`);

} else {
  console.error(`[git-naming] 알 수 없는 모드: ${mode}`);
  process.exit(1);
}
