#!/usr/bin/env node
/**
 * Generate/update docs/architecture.md from epic architecture documents.
 *
 * Source of truth:
 * - docs/epics/epic-NN-<slug>/architecture.md
 * - "## 모듈 목록" markdown table
 * - "## Contract Ledger" markdown table
 *
 * Usage:
 *   node scripts/aggregate_architecture_map.mjs
 *   node scripts/aggregate_architecture_map.mjs --root /path/to/project
 *   node scripts/aggregate_architecture_map.mjs --check
 */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const SECTION_EPIC_MAP = '에픽 간 지도';
const SECTION_TOPOLOGY = '전역 모듈 토폴로지';
const SECTION_CONTRACTS = '공유 계약 인덱스';
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const TEMPLATE_PATH = resolve(
  SCRIPT_DIR,
  '..',
  'agents',
  'system-architect',
  'templates',
  'root-architecture.md'
);

function usage() {
  return [
    'Usage: node scripts/aggregate_architecture_map.mjs [--root <path>] [--check]',
    '',
    'Updates docs/architecture.md generated sections from docs/epics/*/architecture.md.',
  ].join('\n');
}

function parseArgs(argv) {
  const args = {
    root: process.cwd(),
    check: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--root') {
      const value = argv[i + 1];
      if (!value) throw new Error('--root requires a path');
      args.root = value;
      i += 1;
    } else if (arg === '--check') {
      args.check = true;
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

function buildSections(rootArchitecturePath, epics) {
  const epicMapRows = epics.map((epic) => [
    mdLink(epic.name, rootArchitecturePath, epic.architecturePath),
    existsSync(epic.domainModelPath)
      ? mdLink('domain-model.md', rootArchitecturePath, epic.domainModelPath)
      : '-',
    epic.moduleRows.map((row) => row.name).join(', ') || '-',
    epic.decisionRows
      .map((decision) => rebaseMarkdownLinks(decision, epic.architecturePath, rootArchitecturePath))
      .join(', ') || '-',
  ]);

  const topologyRows = [];
  const contractRows = [];

  for (const epic of epics) {
    const epicLink = mdLink(epic.name, rootArchitecturePath, epic.architecturePath);
    for (const row of epic.moduleRows) {
      topologyRows.push([
        rebaseMarkdownLinks(row.name, epic.architecturePath, rootArchitecturePath),
        rebaseMarkdownLinks(row.responsibility, epic.architecturePath, rootArchitecturePath),
        rebaseMarkdownLinks(row.dependencies, epic.architecturePath, rootArchitecturePath),
        rebaseMarkdownLinks(row.publicSurface, epic.architecturePath, rootArchitecturePath),
        epicLink,
      ]);
    }

    for (const row of epic.contractRows) {
      contractRows.push([
        rebaseMarkdownLinks(row.contract, epic.architecturePath, rootArchitecturePath),
        rebaseMarkdownLinks(row.owner, epic.architecturePath, rootArchitecturePath),
        rebaseMarkdownLinks(row.producer, epic.architecturePath, rootArchitecturePath),
        rebaseMarkdownLinks(row.consumer, epic.architecturePath, rootArchitecturePath),
        rebaseMarkdownLinks(row.invariant, epic.architecturePath, rootArchitecturePath),
        rebaseMarkdownLinks(row.refs, epic.architecturePath, rootArchitecturePath),
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

function replaceSection(content, heading, replacement) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = content.match(new RegExp(`^##\\s+${escaped}\\s*$`, 'm'));
  if (!match || match.index === undefined) {
    return `${content.trimEnd()}\n\n${replacement}`;
  }

  const start = match.index;
  const restStart = match.index + match[0].length;
  const rest = content.slice(restStart);
  const next = rest.search(/\n##\s+/);
  const end = next === -1 ? content.length : restStart + next + 1;
  return `${content.slice(0, start)}${replacement}${content.slice(end)}`;
}

function baseRootArchitecture(rootArchitecturePath) {
  if (existsSync(rootArchitecturePath)) {
    return readFileSync(rootArchitecturePath, 'utf8');
  }
  if (existsSync(TEMPLATE_PATH)) {
    return readFileSync(TEMPLATE_PATH, 'utf8');
  }
  return '# 전역 아키텍처 지도\n';
}

function nextRootArchitecture(root, epics = collectEpics(root)) {
  const rootArchitecturePath = join(root, 'docs', 'architecture.md');
  const sections = buildSections(rootArchitecturePath, epics);
  let content = baseRootArchitecture(rootArchitecturePath);

  for (const [heading, body] of sections.entries()) {
    content = replaceSection(content, heading, generatedSection(heading, body));
  }

  return {
    path: rootArchitecturePath,
    content: `${content.trimEnd()}\n`,
    epicCount: epics.length,
    moduleCount: epics.reduce((sum, epic) => sum + epic.moduleRows.length, 0),
    contractCount: epics.reduce((sum, epic) => sum + epic.contractRows.length, 0),
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const rootArchitecturePath = join(args.root, 'docs', 'architecture.md');
  const epics = collectEpics(args.root);
  if (!existsSync(rootArchitecturePath) || epics.length === 0) {
    const reason = !existsSync(rootArchitecturePath)
      ? 'docs/architecture.md missing'
      : 'no valid docs/epics/*/architecture.md files';
    console.log(`[architecture-map] no-op PASS — ${reason}`);
    return;
  }

  const next = nextRootArchitecture(args.root, epics);
  const current = existsSync(next.path) ? readFileSync(next.path, 'utf8') : null;

  if (args.check) {
    if (current === next.content) {
      console.log(
        `[architecture-map] PASS — ${next.epicCount} epic, ${next.moduleCount} module, ${next.contractCount} contract`
      );
      return;
    }
    console.error(
      '[architecture-map] FAIL — docs/architecture.md is stale. Run this script without --check from the project root.'
    );
    process.exit(1);
  }

  mkdirSync(dirname(next.path), { recursive: true });
  if (current !== next.content) {
    writeFileSync(next.path, next.content, 'utf8');
  }
  console.log(
    `[architecture-map] updated ${slash(relative(args.root, next.path))} — ${next.epicCount} epic, ${next.moduleCount} module, ${next.contractCount} contract`
  );
}

try {
  main();
} catch (err) {
  console.error(`[architecture-map] ERROR — ${err.message}`);
  console.error(usage());
  process.exit(2);
}
