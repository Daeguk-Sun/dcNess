#!/usr/bin/env node
/**
 * dcNess cross-ref validator (CI 게이트).
 *
 * 검증 A — markdown link 무결성
 *   - `[text](path)`             → path 파일 실존
 *   - `[text](path#anchor)`      → 파일 실존 + target 파일 heading slug 매칭
 *   - `[text](#same-doc-anchor)` → 자기 파일 heading slug 매칭
 *   - 외부 URL (http(s)/mailto/tel/ftp) → skip
 *   - .md 외 파일의 #anchor (예: harness/foo.py#L10) → skip
 *
 * 검증 B — 옛 명칭 deny-list (외부 배포 영역 한정)
 *   - 폐기 명령어 / 옛 loop 명 / 옛 SSOT 파일명
 *   - 위치번호 §N 참조 금지 (doc-conventions.md 규약) — `§3.2` 류 prose 위치번호.
 *     예외: 코드펜스/인라인코드 · historical(옛/폐기/...) 라인.
 *   - 외부 배포 영역: docs/plugin/, commands/, agents/, hooks/, .claude-plugin/
 *   - 예외 파일: commands/smart-compact.md (sample 코드블록 안 historical 인용 — M1/N 동일 사유)
 *
 * 사용:
 *   node scripts/check_cross_refs.mjs
 *
 * exit 0: PASS
 * exit 1: FAIL — dead link / dead anchor / 옛 명칭 매치
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { dirname, resolve, join, relative } from 'node:path';

const REPO_ROOT = process.cwd();

// ─── 검사 대상 ─────────────────────────────────────────────────
const SCAN_DIRS = ['docs/plugin', 'docs/internal', 'commands', 'skills', 'agents'];
const SCAN_ROOTS = ['README.md', 'AGENTS.md', 'PROGRESS.md', 'CLAUDE.md', '.github/PULL_REQUEST_TEMPLATE.md'];

// ─── 옛 명칭 deny-list ────────────────────────────────────────
// historical annotation (navigation hint) 은 통과:
//   keyword "옛|폐기|history|deprecated|legacy" 가 동일 라인에 있으면 valid context
const HISTORICAL_CTX_RE = /(옛|폐기|history|deprecated|legacy)/i;

const DENY_LIST = [
  {
    pattern: /(?<![\w/])\/auto-loop\b/,
    label: '폐기 명령어 `/auto-loop` — 현존 X (`/impl` / `/impl-loop` 만)',
  },
  {
    pattern: /\bdirect-impl-loop\b/,
    label: '폐기 loop 명 `direct-impl-loop` — 현재 `impl-task-loop` / `impl-ui-design-loop` 만',
  },
  {
    pattern: /prose-only-principle\.md/,
    label: '폐기 SSOT `prose-only-principle.md` — `orchestration.md §0` 로 흡수',
  },
  {
    pattern: /dcness-rules\.md/,
    label: '폐기 SSOT `dcness-rules.md` — `orchestration.md §0` 안티패턴 1+3 로 흡수',
  },
  {
    pattern: /docs\/ui-spec\b/,
    label: '옛 디자인 SSOT `docs/ui-spec*` — 현재 `docs/design.md` SSOT',
  },
  {
    pattern: /\.steps\.jsonl/,
    label: '옛 step 로그 `.steps.jsonl` — `ledger.jsonl` 의 step_completed event 로 흡수 (이슈 #587). legacy/폴백 맥락(옛·legacy 키워드 동반)만 허용.',
  },
  {
    pattern: /agent\s+1[0-2]\s*종/,
    label: '옛 agent 카운트 (10, 11, 12 종) — 현재 13 종 (product-acceptance / designer / build-worker 포함)',
  },
  {
    pattern: /\b[79]\s*hook\s+(상세|전체|공유|충족|시점)/,
    label: '옛 hook 카운트 (7 또는 9) — 현재 8 hook (hooks.md §3 sub-section 정합, issue #598 SubagentStop 추가)',
  },
  {
    pattern: /\b8\s+loop\s+(행별|풀스펙)/,
    label: '옛 loop 카운트 — 현재 7 loop (orchestration.md §4 sub-section 정합)',
  },
  {
    // `architect-loop-routing.md` 등 skill 라우팅 파일은 앞에 `-`/단어문자가 붙어 제외.
    pattern: /(?<![\w-])routing\.md/,
    label: '폐기 SSOT `docs/plugin/routing.md` — Phase 3 (#564) 폐기, 라우팅은 각 skill `<skill>-routing.md` 로 분산',
  },
  {
    // 위치번호 §N 참조 금지 (doc-conventions.md). §2.1.N 룰 번호 체계 폐기 → 예외 없음.
    // codeExempt: 코드펜스/인라인코드 안 § 는 검사 제외 (sample·런타임 에러 메시지).
    pattern: /§\d/,
    codeExempt: true,
    label: '위치번호 §N 참조 — 제목 anchor 링크로 전환 (doc-conventions.md). 코드펜스/인라인코드·historical 은 예외.',
  },
];

const EXTERNAL_DIRS = ['docs/plugin', 'commands', 'skills', 'agents', 'hooks', '.claude-plugin'];

const DENY_EXCLUDE = new Set([
  'commands/smart-compact.md',
]);

// §N (codeExempt) deny 는 외부 배포 영역 + 아래 루트 규약·contributor 문서까지 적용
// (doc-conventions.md 적용 범위). 옛 명칭 패턴은 여전히 외부 배포 영역 한정.
// PROGRESS.md 는 self 운영 changelog 라 §N deny 비대상.
const DENY_ROOT_DOCS = new Set([
  'CLAUDE.md',
  'README.md',
  'AGENTS.md',
  '.github/PULL_REQUEST_TEMPLATE.md',
]);

// ─── 헬퍼 ────────────────────────────────────────────────────
function walkMd(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walkMd(p));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      out.push(p);
    }
  }
  return out;
}

function collectFiles() {
  const out = [];
  for (const d of SCAN_DIRS) {
    if (existsSync(d)) out.push(...walkMd(d));
  }
  for (const f of SCAN_ROOTS) {
    if (existsSync(f)) out.push(f);
  }
  return out.sort();
}

const fileCache = new Map();
function getContent(filePath) {
  if (!fileCache.has(filePath)) {
    fileCache.set(filePath, readFileSync(filePath, 'utf8'));
  }
  return fileCache.get(filePath);
}

// GitHub-flavored anchor slug (단순 모사)
//   - lowercase
//   - 영숫자/공백/dash/한글/한글자모 유지, 나머지 제거
//   - 공백 → dash (연속 공백도 단일 dash)
function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^\w\s\-가-힣ㄱ-ㅎㅏ-ㅣ]/gu, '')
    .trim()
    .replace(/\s+/g, '-');
}

const anchorCache = new Map();
function getAnchors(filePath) {
  if (anchorCache.has(filePath)) return anchorCache.get(filePath);
  const content = getContent(filePath);
  const slugs = new Set();
  let inCodeBlock = false;
  for (const line of content.split('\n')) {
    if (line.trim().startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) continue;
    const m = line.match(/^(#{1,6})\s+(.+?)\s*$/);
    if (m) slugs.add(slugify(m[2]));
  }
  anchorCache.set(filePath, slugs);
  return slugs;
}

// inline code 영역 mask out — 백틱 안 [text](url) 은 placeholder 예시일 가능성 높음
// `` ` `` ~ `` ` `` 사이 영역을 공백으로 치환 (라인 길이 보존, 정규식 위치 유지)
function maskInlineCode(line) {
  // 백틱 1개 (또는 2개) 로 둘러싼 영역. ``` (3개) 는 code fence 라 별도 처리.
  // 짝수 번째 백틱까지의 영역을 같은 길이 공백으로 치환.
  let out = '';
  let i = 0;
  while (i < line.length) {
    if (line[i] === '`') {
      // 백틱 시작 — 닫는 백틱까지 찾아 mask
      const close = line.indexOf('`', i + 1);
      if (close === -1) {
        out += line.slice(i);
        break;
      }
      out += ' '.repeat(close - i + 1);
      i = close + 1;
    } else {
      out += line[i];
      i++;
    }
  }
  return out;
}

function extractLinks(filePath) {
  const content = getContent(filePath);
  const links = [];
  let lineNo = 0;
  let inCodeBlock = false;
  for (const line of content.split('\n')) {
    lineNo++;
    if (line.trim().startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) continue;
    const masked = maskInlineCode(line);
    const re = /\[([^\]]+)\]\(([^)\s]+)\)/g;
    let m;
    while ((m = re.exec(masked)) !== null) {
      links.push({ text: m[1], url: m[2], lineNo });
    }
  }
  return links;
}

function isExternalUrl(url) {
  return /^(https?:|mailto:|tel:|ftp:|#?$)/i.test(url);
}

function validateLinks(filePath) {
  const violations = [];
  const sourceDir = dirname(filePath);

  for (const { url, lineNo } of extractLinks(filePath)) {
    if (isExternalUrl(url)) continue;

    const hashIdx = url.indexOf('#');
    const pathPart = hashIdx === -1 ? url : url.slice(0, hashIdx);
    const anchor = hashIdx === -1 ? '' : url.slice(hashIdx + 1);

    if (!pathPart) {
      // same-doc anchor
      if (anchor && !getAnchors(filePath).has(anchor)) {
        violations.push({
          file: filePath,
          lineNo,
          url,
          reason: `same-doc anchor #${anchor} not found in heading slugs`,
        });
      }
      continue;
    }

    const target = resolve(sourceDir, pathPart);
    if (!existsSync(target)) {
      violations.push({
        file: filePath,
        lineNo,
        url,
        reason: `file not found at ${relative(REPO_ROOT, target)}`,
      });
      continue;
    }

    if (anchor && target.endsWith('.md')) {
      if (!getAnchors(target).has(anchor)) {
        violations.push({
          file: filePath,
          lineNo,
          url,
          reason: `anchor #${anchor} not found in ${relative(REPO_ROOT, target)}`,
        });
      }
    }
  }

  return violations;
}

function isExternalFile(filePath) {
  return EXTERNAL_DIRS.some(
    (d) => filePath === d || filePath.startsWith(d + '/')
  );
}

function validateDenyList(filePath) {
  if (DENY_EXCLUDE.has(filePath)) return [];
  const external = isExternalFile(filePath);
  const rootDoc = DENY_ROOT_DOCS.has(filePath);
  // 외부 배포 영역도 아니고 루트 규약 문서도 아니면 deny 비대상
  if (!external && !rootDoc) return [];

  const violations = [];
  const lines = getContent(filePath).split('\n');
  let inCodeBlock = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // 코드펜스 토글 — fence 마커 줄은 검사 skip
    if (line.trim().startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      continue;
    }
    // historical annotation 은 통과 (옛/폐기/history 키워드 동반)
    if (HISTORICAL_CTX_RE.test(line)) continue;
    // codeExempt 패턴(§N)용 — 인라인 코드(백틱) 제거판
    const codeStripped = line.replace(/`[^`]*`/g, '');
    for (const { pattern, label, codeExempt } of DENY_LIST) {
      // 옛 명칭 패턴 = 외부 배포 영역 한정; §N(codeExempt) = 루트 규약 문서까지 포함
      if (!external && !codeExempt) continue;
      // codeExempt 패턴은 코드펜스 안 / 인라인코드 안 § 를 검사 제외
      if (codeExempt && inCodeBlock) continue;
      const target = codeExempt ? codeStripped : line;
      if (pattern.test(target)) {
        violations.push({
          file: filePath,
          lineNo: i + 1,
          snippet: line.trim().slice(0, 120),
          label,
        });
      }
    }
  }
  return violations;
}

// ─── main ────────────────────────────────────────────────────
function main() {
  const files = collectFiles();
  const linkViolations = [];
  const denyViolations = [];

  for (const f of files) {
    linkViolations.push(...validateLinks(f));
    denyViolations.push(...validateDenyList(f));
  }

  console.log(`[cross-ref] 검사 대상: ${files.length} 파일`);

  if (linkViolations.length === 0 && denyViolations.length === 0) {
    console.log('[cross-ref] PASS — dead link / dead anchor / 옛 명칭 0건');
    process.exit(0);
  }

  if (linkViolations.length > 0) {
    console.error(`\n[cross-ref] FAIL — dead link / dead anchor ${linkViolations.length} 건:`);
    for (const v of linkViolations) {
      console.error(`  ${v.file}:${v.lineNo}  [${v.url}]`);
      console.error(`    → ${v.reason}`);
    }
  }

  if (denyViolations.length > 0) {
    console.error(`\n[cross-ref] FAIL — 옛 명칭 deny-list ${denyViolations.length} 건:`);
    for (const v of denyViolations) {
      console.error(`  ${v.file}:${v.lineNo}  ${v.snippet}`);
      console.error(`    → ${v.label}`);
    }
  }

  console.error('');
  console.error('  Scope:');
  console.error('    - 검증 A (link)   : markdown link 형식만 (`[text](path)` / `[text](#anchor)`).');
  console.error('                       prose `<file>.md §N.M` heuristic 인용은 별 PR 후보.');
  console.error('    - 검증 B (deny)   : 외부 배포 영역 (docs/plugin/, commands/, agents/, hooks/, .claude-plugin/) 한정.');
  console.error('                       예외: commands/smart-compact.md (sample 코드블록 안 historical).');
  console.error('  SSOT: 본 스크립트 헤더 주석 + .github/workflows/cross-ref-validation.yml 헤더.');

  process.exit(1);
}

main();
