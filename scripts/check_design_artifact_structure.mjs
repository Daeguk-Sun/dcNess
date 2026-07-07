#!/usr/bin/env node
/**
 * Audit generated `/design` artifacts for the agent-first design contract.
 *
 * This script is intentionally read-only. The current contract no longer uses
 * Contract Ledger row-key infrastructure as a CI-enforced format. Legacy Ledger
 * and Contract References artifacts remain valid for existing active projects;
 * this audit reports them as warnings while keeping the gate green.
 *
 * Usage:
 *   node scripts/check_design_artifact_structure.mjs --root /path/to/project
 *   node scripts/check_design_artifact_structure.mjs --json
 */
import {
  existsSync,
  readFileSync,
  readdirSync,
} from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';

const DESIGN_PACK_LINE_TARGET = 1500;
const DESIGN_PACK_LINE_HARD_WARNING = 2000;
const LEGACY_CONTRACT_DETAIL_COLUMNS = new Set([
  'contract',
  'owner',
  'producer',
  'consumer',
  'invariant',
  'ordering',
  'error mode',
  'config',
  'forbidden alternative',
]);

function usage() {
  return [
    'Usage: node scripts/check_design_artifact_structure.mjs [--root <path>] [--json] [--contract <legacyRowKey>]',
    '',
    'Audits docs/epics/* design artifacts for agent-first structure and legacy contract-surface warnings.',
    '--contract is accepted for backward compatibility and now emits a deprecation warning.',
  ].join('\n');
}

function parseArgs(argv) {
  const args = {
    root: process.cwd(),
    json: false,
    contract: '',
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--root') {
      const value = argv[i + 1];
      if (!value) throw new Error('--root requires a path');
      args.root = value;
      i += 1;
    } else if (arg === '--json') {
      args.json = true;
    } else if (arg === '--contract') {
      const value = argv[i + 1];
      if (!value) throw new Error('--contract requires a legacy Contract Ledger row key');
      args.contract = value;
      i += 1;
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

function rel(root, path) {
  return slash(relative(root, path));
}

function readText(path) {
  return readFileSync(path, 'utf8');
}

function splitTableLine(line) {
  const trimmed = line.trim();
  const withoutEdges = trimmed.replace(/^\|/, '').replace(/\|$/, '');
  return withoutEdges.split('|').map((cell) => cell.trim());
}

function isSeparatorRow(cells) {
  return cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function normalizeHeader(value) {
  return String(value ?? '')
    .replace(/[`*_]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
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

function hasSection(content, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^##\\s+${escaped}\\s*$`, 'm').test(content);
}

function parseMarkdownTables(content) {
  const lines = content.split(/\r?\n/);
  const tables = [];

  for (let i = 0; i < lines.length - 1; i += 1) {
    const current = lines[i].trim();
    const next = lines[i + 1].trim();
    if (!current.startsWith('|') || !next.startsWith('|')) continue;

    const separatorCells = splitTableLine(next);
    if (!isSeparatorRow(separatorCells)) continue;

    const header = splitTableLine(current);
    const rows = [];
    let cursor = i + 2;
    for (; cursor < lines.length; cursor += 1) {
      const line = lines[cursor].trim();
      if (!line.startsWith('|')) break;
      rows.push(splitTableLine(line));
    }

    tables.push({ header, rows });
    i = Math.max(i, cursor - 1);
  }

  return tables;
}

function isLegacyContractDetailTable(table) {
  const headers = new Set(table.header.map(normalizeHeader));
  let matches = 0;
  for (const column of LEGACY_CONTRACT_DETAIL_COLUMNS) {
    if (headers.has(column)) matches += 1;
  }
  return matches >= 5;
}

function containsLegacyContractDetailTable(content) {
  return parseMarkdownTables(content).some(isLegacyContractDetailTable);
}

function hasContractFrontmatter(content) {
  const frontmatter = content.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  return Boolean(frontmatter && /^\s*contract\s*:/m.test(frontmatter[1]));
}

function countLines(path) {
  if (!existsSync(path)) return 0;
  const content = readText(path);
  if (content === '') return 0;
  return content.split(/\r?\n/).length;
}

function listMarkdownFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.md'))
    .map((entry) => join(dir, entry.name))
    .sort();
}

function makeProblem(code, file, message, extra = {}) {
  return {
    code,
    file,
    message,
    ...extra,
  };
}

function parseEpic(root, epicDirName) {
  const epicDir = join(root, 'docs', 'epics', epicDirName);
  const architecturePath = join(epicDir, 'architecture.md');
  const content = readText(architecturePath);
  const implPaths = listMarkdownFiles(join(epicDir, 'impl'));
  const designPackPaths = [
    join(epicDir, 'stories.md'),
    architecturePath,
    join(epicDir, 'domain-model.md'),
    join(epicDir, 'ux-flow.md'),
    join(epicDir, 'tech-review.md'),
    ...implPaths,
  ];
  const designPackLineCount = designPackPaths.reduce(
    (total, path) => total + countLines(path),
    0
  );

  return {
    name: epicDirName,
    dir: epicDir,
    architecturePath,
    architectureContent: content,
    implPaths,
    designPackLineCount,
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
    .map((name) => parseEpic(root, name));
}

function collectCompactPlanPaths(root) {
  const compactPlanRoot = join(root, 'docs', 'compact-plans');
  if (!existsSync(compactPlanRoot)) return [];
  return readdirSync(compactPlanRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.md'))
    .map((entry) => join(compactPlanRoot, entry.name))
    .sort();
}

function auditArchitecture(root, epic, warnings) {
  const relativePath = rel(root, epic.architecturePath);
  const content = epic.architectureContent;

  if (!hasSection(content, '모듈 목록')) {
    warnings.push(
      makeProblem(
        'module-list-missing',
        relativePath,
        'epic architecture has no module list section',
        { epic: epic.name }
      )
    );
  }
  if (!hasSection(content, '의존 그래프')) {
    warnings.push(
      makeProblem(
        'dependency-graph-missing',
        relativePath,
        'epic architecture has no dependency graph section',
        { epic: epic.name }
      )
    );
  }
  if (!hasSection(content, 'Story -> 모듈 매핑')) {
    warnings.push(
      makeProblem(
        'story-module-map-missing',
        relativePath,
        'epic architecture has no Story -> module mapping section',
        { epic: epic.name }
      )
    );
  }
  if (hasSection(content, 'Contract Ledger')) {
    warnings.push(
      makeProblem(
        'legacy-contract-ledger',
        relativePath,
        'legacy Contract Ledger retained for backward compatibility; new design artifacts use module responsibilities and decision links',
        { epic: epic.name }
      )
    );
  }
  if (hasSection(content, 'Flow Ownership Map')) {
    warnings.push(
      makeProblem(
        'legacy-flow-ownership-map',
        relativePath,
        'legacy Flow Ownership Map retained for backward compatibility; new design artifacts place ownership in module responsibilities and impl Agent Workability',
        { epic: epic.name }
      )
    );
  }
  if (hasSection(content, 'Decisions')) {
    const section = extractSection(content, 'Decisions');
    if (parseMarkdownTables(section).length > 0) {
      warnings.push(
        makeProblem(
          'legacy-decisions-table',
          relativePath,
          'legacy Decisions table retained for backward compatibility; new design artifacts link docs/decisions directly',
          { epic: epic.name }
        )
      );
    }
  }
}

function auditArtifact({ root, path, epicName, warnings }) {
  const content = readText(path);
  const relativePath = rel(root, path);

  if (hasContractFrontmatter(content)) {
    warnings.push(
      makeProblem(
        'legacy-contract-frontmatter',
        relativePath,
        'legacy contract frontmatter retained for backward compatibility; new artifacts cite modules and decision ids instead',
        { epic: epicName }
      )
    );
  }
  if (hasSection(content, 'Contract References') || /\bContract References\b/i.test(content)) {
    warnings.push(
      makeProblem(
        'legacy-contract-references',
        relativePath,
        'legacy Contract References retained for backward compatibility; new artifacts cite modules and decision ids instead',
        { epic: epicName }
      )
    );
  }
  if (containsLegacyContractDetailTable(content)) {
    warnings.push(
      makeProblem(
        'legacy-contract-detail-table',
        relativePath,
        'legacy contract detail table retained for backward compatibility',
        { epic: epicName }
      )
    );
  }

  return { path, epicName };
}

function auditDesignPackBudgets(root, epics, warnings) {
  for (const epic of epics) {
    if (epic.designPackLineCount > DESIGN_PACK_LINE_TARGET) {
      warnings.push(
        makeProblem(
          'design-pack-over-target',
          rel(root, epic.dir),
          `design pack line count exceeds ${DESIGN_PACK_LINE_TARGET}`,
          {
            epic: epic.name,
            line_count: epic.designPackLineCount,
            limit: DESIGN_PACK_LINE_TARGET,
          }
        )
      );
    }
    if (epic.designPackLineCount > DESIGN_PACK_LINE_HARD_WARNING) {
      warnings.push(
        makeProblem(
          'design-pack-over-hard-warning',
          rel(root, epic.dir),
          `design pack line count exceeds ${DESIGN_PACK_LINE_HARD_WARNING}`,
          {
            epic: epic.name,
            line_count: epic.designPackLineCount,
            limit: DESIGN_PACK_LINE_HARD_WARNING,
          }
        )
      );
    }
  }
}

function audit(root, contract = '') {
  const violations = [];
  const warnings = [];
  const epics = collectEpics(root);
  const artifacts = [];

  if (contract) {
    warnings.push(
      makeProblem(
        'deprecated-contract-lookup',
        'docs/index.md',
        `--contract ${contract} is deprecated because Contract Ledger row-key lookup is no longer the design recovery path`,
        { contract }
      )
    );
  }

  auditDesignPackBudgets(root, epics, warnings);

  for (const epic of epics) {
    auditArchitecture(root, epic, warnings);
    for (const implPath of epic.implPaths) {
      artifacts.push(
        auditArtifact({
          root,
          path: implPath,
          epicName: epic.name,
          warnings,
        })
      );
    }
  }

  for (const compactPlanPath of collectCompactPlanPaths(root)) {
    artifacts.push(
      auditArtifact({
        root,
        path: compactPlanPath,
        epicName: '',
        warnings,
      })
    );
  }

  return {
    ok: violations.length === 0,
    root,
    epics: epics.map((epic) => ({
      name: epic.name,
      architecture_path: rel(root, epic.architecturePath),
      impl_count: epic.implPaths.length,
      design_pack_line_count: epic.designPackLineCount,
    })),
    artifacts: artifacts.map((artifact) => ({
      path: rel(root, artifact.path),
      epic: artifact.epicName,
    })),
    violations,
    warnings,
    recovery: null,
  };
}

function renderProblem(problem) {
  const target = problem.file ? `${problem.file}: ` : '';
  return `${target}${problem.code} - ${problem.message}`;
}

function renderText(result) {
  for (const warning of result.warnings) {
    console.error(`[design-artifact] WARN ${renderProblem(warning)}`);
  }

  if (!result.ok) {
    console.error(`[design-artifact] FAIL - ${result.violations.length} violation(s)`);
    for (const violation of result.violations) {
      console.error(`[design-artifact] ${renderProblem(violation)}`);
    }
    return;
  }

  console.log(
    `[design-artifact] PASS - ${result.epics.length} epic(s), ${result.warnings.length} warning(s)`
  );
}

function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    const result = audit(args.root, args.contract);
    if (args.json) {
      console.log(JSON.stringify(result, null, 2));
    } else {
      renderText(result);
    }
    process.exit(result.ok ? 0 : 1);
  } catch (error) {
    console.error(`[design-artifact] ERROR ${error.message}`);
    process.exit(2);
  }
}

main();
