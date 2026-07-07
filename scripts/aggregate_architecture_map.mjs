#!/usr/bin/env node
/**
 * Generate an on-demand architecture map report from epic architecture documents.
 *
 * Source of truth:
 * - docs/epics/epic-NN-<slug>/architecture.md
 * - "## 모듈 목록" markdown table
 * - "## Contract Ledger" markdown table
 *
 * Usage:
 *   node scripts/aggregate_architecture_map.mjs
 *   node scripts/aggregate_architecture_map.mjs --root /path/to/project
 *   node scripts/aggregate_architecture_map.mjs --stdout
 *   node scripts/aggregate_architecture_map.mjs --out .dcness-work/reports/architecture-map.md
 */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';

const SECTION_EPIC_MAP = '에픽 간 지도';
const SECTION_TOPOLOGY = '전역 모듈 토폴로지';
const SECTION_CONTRACTS = '공유 계약 인덱스';
const DEFAULT_REPORT_PATH = join('.dcness-work', 'reports', 'architecture-map.md');

function usage() {
  return [
    'Usage: node scripts/aggregate_architecture_map.mjs [--root <path>] [--out <path>] [--stdout]',
    '',
    'Generates an on-demand architecture report from docs/epics/*/architecture.md.',
    `Default output: ${DEFAULT_REPORT_PATH}`,
  ].join('\n');
}

function parseArgs(argv) {
  const args = {
    root: process.cwd(),
    out: DEFAULT_REPORT_PATH,
    stdout: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--root') {
      const value = argv[i + 1];
      if (!value) throw new Error('--root requires a path');
      args.root = value;
      i += 1;
    } else if (arg === '--out') {
      const value = argv[i + 1];
      if (!value) throw new Error('--out requires a path');
      args.out = value;
      i += 1;
    } else if (arg === '--stdout') {
      args.stdout = true;
    } else if (arg === '-h' || arg === '--help') {
      console.log(usage());
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }

  args.root = resolve(args.root);
  return args;
}

function slash(path) {
  return path.split(sep).join('/');
}

function mdLink(label, fromFile, toFile) {
  return `[${label}](${slash(relative(dirname(fromFile), toFile))})`;
}

function isExternalUrl(url) {
  return /^(?:https?:|mailto:|tel:|ftp:)/i.test(url);
}

function rebaseMarkdownLinks(text, sourceFile, targetFile) {
  return String(text ?? '').replace(
    /\[([^\]]+)\]\(([^)#]+)(#[^)]+)?\)/g,
    (match, label, url, hash = '') => {
      if (isExternalUrl(url) || url.startsWith('#')) return match;
      const absolute = resolve(dirname(sourceFile), url);
      return `[${label}](${slash(relative(dirname(targetFile), absolute))}${hash})`;
    }
  );
}

function cleanCell(value) {
  const normalized = String(value ?? '')
    .replace(/\r?\n/g, ' ')
    .replace(/\|/g, '\\|')
    .trim();
  return normalized || '-';
}

function isBlankish(value) {
  const text = String(value ?? '').trim();
  return text === '' || text === '-';
}

function splitTableLine(line) {
  const trimmed = line.trim();
  const withoutEdges = trimmed.replace(/^\|/, '').replace(/\|$/, '');
  return withoutEdges.split('|').map((cell) => cell.trim());
}

function isSeparatorRow(cells) {
  return cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function extractSection(content, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = content.match(new RegExp(`^##\\s+${escaped}\\s*$`, 'm'));
  if (!match || match.index === undefined) return '';

  const start = match.index + match[0].length;
  const rest = content.slice(start);
  const next = rest.search(/\n##\s+/);
  return next === -1 ? rest : rest.slice(0, next);
}

function parseMarkdownTable(section) {
  const lines = section.split(/\r?\n/);
  let tableStart = -1;

  for (let i = 0; i < lines.length - 1; i += 1) {
    const current = lines[i].trim();
    const next = lines[i + 1].trim();
    if (current.startsWith('|') && next.startsWith('|')) {
      const nextCells = splitTableLine(next);
      if (isSeparatorRow(nextCells)) {
        tableStart = i;
        break;
      }
    }
  }

  if (tableStart === -1) return [];

  const header = splitTableLine(lines[tableStart]);
  const rows = [];
  for (let i = tableStart + 2; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (!line.startsWith('|')) break;
    const cells = splitTableLine(line);
    if (cells.every(isBlankish)) continue;

    const row = {};
    for (let c = 0; c < header.length; c += 1) {
      row[header[c]] = cells[c] ?? '';
    }
    rows.push(row);
  }

  return rows;
}

function pick(row, names) {
  const lowerNames = new Set(names.map((name) => name.toLowerCase()));
  for (const [key, value] of Object.entries(row)) {
    if (names.includes(key) || lowerNames.has(key.toLowerCase())) {
      return value;
    }
  }
  return '';
}

function parseEpicArchitecture(root, epicDirName) {
  const epicDir = join(root, 'docs', 'epics', epicDirName);
  const architecturePath = join(epicDir, 'architecture.md');
  const content = readFileSync(architecturePath, 'utf8');

  const moduleRows = parseMarkdownTable(extractSection(content, '모듈 목록'))
    .map((row) => ({
      name: pick(row, ['모듈', 'module', 'Module']),
      responsibility: pick(row, ['책임', 'responsibility', 'Responsibility']),
      dependencies: pick(row, ['의존 모듈', '의존', 'dependencies', 'Dependencies']),
      publicSurface: pick(row, ['공개 API', '공개 표면', 'public API', 'Public API']),
    }))
    .filter((row) => !isBlankish(row.name));

  const contractRows = parseMarkdownTable(extractSection(content, 'Contract Ledger'))
    .map((row) => ({
      contract: pick(row, ['contract', 'Contract']),
      owner: pick(row, ['owner', 'Owner']),
      producer: pick(row, ['producer', 'Producer']),
      consumer: pick(row, ['consumer', 'Consumer']),
      invariant: pick(row, ['invariant', 'Invariant']),
      refs: pick(row, ['refs', 'Refs']),
    }))
    .filter((row) => !isBlankish(row.contract));

  const decisionRows = parseMarkdownTable(extractSection(content, 'Decisions'))
    .map((row) => pick(row, ['Decision', 'decision']))
    .filter((value) => !isBlankish(value));

  return {
    name: epicDirName,
    architecturePath,
    domainModelPath: join(epicDir, 'domain-model.md'),
    moduleRows,
    contractRows,
    decisionRows,
  };
}

function collectEpics(root) {
  const epicsRoot = join(root, 'docs', 'epics');
  if (!existsSync(epicsRoot)) return [];

  return readdirSync(epicsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => /^epic-\d+-[a-z0-9][a-z0-9_-]*$/.test(name))
    .filter((name) => existsSync(join(epicsRoot, name, 'architecture.md')))
    .sort()
    .map((name) => parseEpicArchitecture(root, name));
}

function table(header, rows) {
  const mismatchedRow = rows.find((row) => row.length !== header.length);
  if (mismatchedRow) {
    throw new Error(
      `table row width mismatch: header has ${header.length} cells but row has ${mismatchedRow.length} cells`
    );
  }

  const lines = [
    `| ${header.join(' | ')} |`,
    `| ${header.map(() => '---').join(' | ')} |`,
  ];
  lines.push(...rows.map((row) => `| ${row.map(cleanCell).join(' | ')} |`));
  return lines.join('\n');
}

function placeholderRow(width) {
  return Array.from({ length: width }, () => '-');
}

function buildSections(reportPath, epics) {
  const epicMapRows = epics.map((epic) => [
    mdLink(epic.name, reportPath, dirname(epic.architecturePath)),
    mdLink('architecture.md', reportPath, epic.architecturePath),
    existsSync(epic.domainModelPath)
      ? mdLink('domain-model.md', reportPath, epic.domainModelPath)
      : '-',
    epic.moduleRows.map((row) => row.name).join(', ') || '-',
    epic.decisionRows
      .map((decision) => rebaseMarkdownLinks(decision, epic.architecturePath, reportPath))
      .join(', ') || '-',
  ]);

  const topologyRows = [];
  const contractRows = [];

  for (const epic of epics) {
    const epicLink = mdLink(epic.name, reportPath, epic.architecturePath);
    for (const row of epic.moduleRows) {
      topologyRows.push([
        rebaseMarkdownLinks(row.name, epic.architecturePath, reportPath),
        rebaseMarkdownLinks(row.responsibility, epic.architecturePath, reportPath),
        rebaseMarkdownLinks(row.dependencies, epic.architecturePath, reportPath),
        rebaseMarkdownLinks(row.publicSurface, epic.architecturePath, reportPath),
        epicLink,
      ]);
    }

    for (const row of epic.contractRows) {
      contractRows.push([
        rebaseMarkdownLinks(row.contract, epic.architecturePath, reportPath),
        rebaseMarkdownLinks(row.owner, epic.architecturePath, reportPath),
        rebaseMarkdownLinks(row.producer, epic.architecturePath, reportPath),
        rebaseMarkdownLinks(row.consumer, epic.architecturePath, reportPath),
        rebaseMarkdownLinks(row.invariant, epic.architecturePath, reportPath),
        rebaseMarkdownLinks(row.refs, epic.architecturePath, reportPath),
        epicLink,
      ]);
    }
  }

  return new Map([
    [
      SECTION_EPIC_MAP,
      table(
        ['에픽', 'Architecture', 'Domain Model', '핵심 모듈', '결정'],
        epicMapRows.length > 0 ? epicMapRows : [placeholderRow(5)]
      ),
    ],
    [
      SECTION_TOPOLOGY,
      table(
        ['모듈', '책임', '의존', '공개 표면', '소유 에픽'],
        topologyRows.length > 0 ? topologyRows : [placeholderRow(5)]
      ),
    ],
    [
      SECTION_CONTRACTS,
      table(
        ['Contract', 'Owner', 'Producer', 'Consumer', 'Invariant', 'Refs', '소유 에픽'],
        contractRows.length > 0 ? contractRows : [placeholderRow(7)]
      ),
    ],
  ]);
}

function generatedSection(heading, body) {
  return [
    `## ${heading}`,
    '',
    '<!-- dcness-architecture-map:generated -->',
    '<!-- 수정하지 말고 plugin script `aggregate_architecture_map.mjs` 로 갱신한다. -->',
    body,
    '',
    '',
  ].join('\n');
}

function resolveOutPath(root, out) {
  return resolve(root, out);
}

function nextArchitectureReport(root, reportPath, epics = collectEpics(root)) {
  const sections = buildSections(reportPath, epics);
  const content = [
    '# 전역 아키텍처 온디맨드 리포트',
    '',
    '> docs/epics/*/architecture.md 에서 생성한 임시 리포트다. PR 본문이나 checked-in architecture anchor 에 복제하지 않는다.',
    '',
    ...Array.from(sections.entries()).map(([heading, body]) => generatedSection(heading, body).trimEnd()),
    '',
  ].join('\n');

  return {
    path: reportPath,
    content: `${content.trimEnd()}\n`,
    epicCount: epics.length,
    moduleCount: epics.reduce((sum, epic) => sum + epic.moduleRows.length, 0),
    contractCount: epics.reduce((sum, epic) => sum + epic.contractRows.length, 0),
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const reportPath = resolveOutPath(args.root, args.out);
  const epics = collectEpics(args.root);
  if (epics.length === 0) {
    const reason = 'no valid docs/epics/*/architecture.md files';
    console.log(`[architecture-map] no-op PASS — ${reason}`);
    return;
  }

  const next = nextArchitectureReport(args.root, reportPath, epics);
  const current = existsSync(next.path) ? readFileSync(next.path, 'utf8') : null;

  if (args.stdout) {
    process.stdout.write(next.content);
    return;
  }

  mkdirSync(dirname(next.path), { recursive: true });
  if (current !== next.content) {
    writeFileSync(next.path, next.content, 'utf8');
  }
  console.log(
    `[architecture-map] wrote ${slash(relative(args.root, next.path))} — ${next.epicCount} epic, ${next.moduleCount} module, ${next.contractCount} contract`
  );
}

try {
  main();
} catch (err) {
  console.error(`[architecture-map] ERROR — ${err.message}`);
  console.error(usage());
  process.exit(2);
}
