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
 *   - 외부 배포 영역: docs/plugin/, commands/, agents/, hooks/, .claude-plugin/
 *   - 예외 파일: commands/smart-compact.md (sample 코드블록 안 historical 인용 — M1/N 동일 사유)
 *
 * Scope 외 (별 PR 후보):
 *   - prose `<filename>.md §N.M` heuristic 인용 (false positive 분류 부담)
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
const SCAN_ROOTS = ['README.md', 'AGENTS.md', 'PROGRESS.md', 'CLAUDE.md'];

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
    pattern: /agent\s+1[01]\s*종/,
    label: '옛 agent 카운트 (10 또는 11 종) — 현재 12 종 (designer / build-worker 포함)',
  },
  {
    pattern: /\b[68]\s*hook\s+(상세|전체|공유|충족|시점)/,
    label: '옛 hook 카운트 (6 또는 8) — 현재 7 hook (hooks.md §3 sub-section 정합)',
  },
  {
    pattern: /\b8\s+loop\s+(행별|풀스펙)/,
    label: '옛 loop 카운트 — 현재 7 loop (orchestration.md §4 sub-section 정합)',
  },
];

const EXTERNAL_DIRS = ['docs/plugin', 'commands', 'skills', 'agents', 'hooks', '.claude-plugin'];

const DENY_EXCLUDE = new Set([
  'commands/smart-compact.md',
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
  if (!isExternalFile(filePath)) return [];
  if (DENY_EXCLUDE.has(filePath)) return [];

  const violations = [];
  const lines = getContent(filePath).split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // historical annotation 은 통과 (옛/폐기/history 키워드 동반)
    if (HISTORICAL_CTX_RE.test(line)) continue;
    for (const { pattern, label } of DENY_LIST) {
      if (pattern.test(line)) {
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
