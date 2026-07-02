#!/usr/bin/env node
/**
 * Audit generated `/design` artifacts for contract-ledger pointer semantics.
 *
 * This is intentionally read-only. It verifies that new impl/compact artifacts
 * refer to Contract Ledger row keys instead of copying ledger detail tables, and
 * it provides a deterministic cold-session lookup for a requested contract key.
 *
 * Usage:
 *   node scripts/check_design_artifact_structure.mjs --root /path/to/project
 *   node scripts/check_design_artifact_structure.mjs --json --contract AuthSession
 */
import {
  existsSync,
  readFileSync,
  readdirSync,
  statSync,
} from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';

const DESIGN_PACK_LINE_TARGET = 1500;
const DESIGN_PACK_LINE_HARD_WARNING = 2000;
const LEGACY_CONTRACT_DETAIL_COLUMNS = new Set([
  'invariant',
  'ordering',
  'error mode',
  'config',
  'forbidden alternative',
]);

function usage() {
  return [
    'Usage: node scripts/check_design_artifact_structure.mjs [--root <path>] [--json] [--contract <rowKey>]',
    '',
    'Audits docs/epics/* design artifacts for Contract Ledger row-key pointers.',
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
      if (!value) throw new Error('--contract requires a Contract Ledger row key');
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

function isBlankish(value) {
  const text = String(value ?? '').trim();
  return text === '' || text === '-' || text === '—';
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
  return parseFirstMarkdownTable(section).rows;
}

function parseFirstMarkdownTable(section) {
  return parseMarkdownTables(section)[0] ?? { header: [], rows: [] };
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
      const cells = splitTableLine(line);
      if (cells.every(isBlankish)) continue;

      const row = {};
      for (let c = 0; c < header.length; c += 1) {
        row[header[c]] = cells[c] ?? '';
      }
      rows.push(row);
    }

    tables.push({ header, rows });
    i = Math.max(i, cursor - 1);
  }

  return tables;
}

function normalizeHeader(value) {
  return String(value ?? '')
    .replace(/[`*_]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
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

function hasCanonicalHeader(table, names) {
  const normalizedNames = new Set(names.map((name) => normalizeHeader(name)));
  return table.header.some((header) => normalizedNames.has(normalizeHeader(header)));
}

function isContractDetailTable(table) {
  const headers = new Set(table.header.map(normalizeHeader));
  if (!headers.has('contract')) return false;
  for (const column of LEGACY_CONTRACT_DETAIL_COLUMNS) {
    if (headers.has(column)) return true;
  }
  return false;
}

function containsContractDetailTable(content) {
  return parseMarkdownTables(content).some(isContractDetailTable);
}

function hasContractReferencesSection(content) {
  return /^##\s+Contract References\s*$/m.test(content);
}

function hasContractReferencesMention(content) {
  return /\bContract References\b/i.test(content);
}

function extractFrontmatter(content) {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  return match?.[1] ?? '';
}

function cleanKeyToken(value) {
  return String(value ?? '')
    .replace(/#.*/, '')
    .replace(/^[\s"'`]+|[\s"',`]+$/g, '')
    .trim();
}

function isEmptyKey(value) {
  const text = cleanKeyToken(value).toLowerCase();
  return text === '' || text === '-' || text === '—' || text === 'none' || text === 'n/a' || text === '[]';
}

function parseScalarList(value) {
  const text = String(value ?? '').trim();
  if (isEmptyKey(text)) return [];
  if (text.startsWith('[') && text.endsWith(']')) {
    return text
      .slice(1, -1)
      .split(',')
      .map(cleanKeyToken)
      .filter((item) => !isEmptyKey(item));
  }
  return text
    .split(',')
    .map(cleanKeyToken)
    .filter((item) => !isEmptyKey(item));
}

function extractContractKeysFromFrontmatter(content) {
  const frontmatter = extractFrontmatter(content);
  if (!frontmatter) return [];

  const keys = new Set();
  const lines = frontmatter.split(/\r?\n/);
  let inContract = false;
  let contractIndent = 0;
  let activeList = false;

  for (const line of lines) {
    const indent = line.match(/^\s*/)?.[0].length ?? 0;
    if (/^\s*contract\s*:\s*$/.test(line)) {
      inContract = true;
      contractIndent = indent;
      activeList = false;
      continue;
    }

    if (!inContract) continue;
    if (line.trim() && indent <= contractIndent) break;

    const field = line.match(/^\s*(produces|consumes)\s*:\s*(.*)$/);
    if (field) {
      activeList = field[2].trim() === '';
      for (const key of parseScalarList(field[2])) keys.add(key);
      continue;
    }

    const item = line.match(/^\s*-\s*(.+)$/);
    if (activeList && item) {
      for (const key of parseScalarList(item[1])) keys.add(key);
    } else if (line.trim()) {
      activeList = false;
    }
  }

  return Array.from(keys);
}

function extractContractKeysFromReferences(content) {
  const keys = new Set();
  for (const line of content.split(/\r?\n/)) {
    const normalized = line.replace(/\*\*/g, '').trim();
    const inline = normalized.match(/^Contract References\s*:\s*(.+)$/i);
    if (!inline) continue;
    for (const key of parseScalarList(inline[1])) keys.add(key);
  }

  const section = extractSection(content, 'Contract References');
  if (!section) return Array.from(keys);

  for (const row of parseMarkdownTable(section)) {
    const key = pick(row, [
      'Ledger row key',
      'ledger row key',
      'Contract Ledger row key',
      'contract',
      'Contract',
    ]);
    for (const value of parseScalarList(key)) keys.add(value);
  }

  if (keys.size === 0) {
    for (const line of section.split(/\r?\n/)) {
      const item = line.match(/^\s*[-*]\s*(?:produces|consumes)?\s*:?\s*(.+)$/i);
      if (!item) continue;
      for (const key of parseScalarList(item[1])) keys.add(key);
    }
  }

  return Array.from(keys);
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

function parseEpic(root, epicDirName) {
  const epicDir = join(root, 'docs', 'epics', epicDirName);
  const architecturePath = join(epicDir, 'architecture.md');
  const content = readText(architecturePath);
  const contractLedgerTable = parseFirstMarkdownTable(extractSection(content, 'Contract Ledger'));
  const hasContractColumn = hasCanonicalHeader(contractLedgerTable, ['contract']);
  const contractRows = (hasContractColumn ? contractLedgerTable.rows : [])
    .map((row) => ({
      contract: pick(row, ['contract', 'Contract']),
      owner: pick(row, ['owner', 'Owner']),
      producer: pick(row, ['producer', 'Producer']),
      consumer: pick(row, ['consumer', 'Consumer']),
      invariant: pick(row, ['invariant', 'Invariant']),
      refs: pick(row, ['refs', 'Refs']),
    }))
    .filter((row) => !isBlankish(row.contract));

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
    contractLedgerHeader: contractLedgerTable.header,
    contractLedgerRowCount: contractLedgerTable.rows.length,
    contractLedgerHasContractColumn: hasContractColumn,
    contractRows,
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

function makeProblem(code, file, message, extra = {}) {
  return {
    code,
    file,
    message,
    ...extra,
  };
}

function auditArtifact({ root, path, epicName, ledgerKeys, globalLedgerKeys, violations, warnings }) {
  const content = readText(path);
  const frontmatterKeys = extractContractKeysFromFrontmatter(content);
  const referenceKeys = extractContractKeysFromReferences(content);
  const referencedKeys = Array.from(new Set([...frontmatterKeys, ...referenceKeys])).sort();
  const hasCanonicalReferences = hasContractReferencesSection(content);
  const hasReferencesMention = hasContractReferencesMention(content);
  const hasPointerMetadata = hasCanonicalReferences || frontmatterKeys.length > 0 || referenceKeys.length > 0;
  const hasDetailTable = containsContractDetailTable(content);
  const relativePath = rel(root, path);

  if (hasReferencesMention && !hasCanonicalReferences) {
    violations.push(
      makeProblem(
        'contract-references-shape',
        relativePath,
        `Contract References must be a level-2 section with Ledger row-key references, not inline prose; found inline keys: ${referencedKeys.join(', ') || '-'}`,
        { epic: epicName, contracts: referencedKeys }
      )
    );
  }

  if (hasPointerMetadata && hasDetailTable) {
    violations.push(
      makeProblem(
        'contract-detail-copy',
        relativePath,
        'new pointer-style artifact must not copy Contract Ledger detail tables',
        { epic: epicName }
      )
    );
  } else if (!hasPointerMetadata && hasDetailTable) {
    warnings.push(
      makeProblem(
        'legacy-contract-table',
        relativePath,
        'legacy contract detail table retained for backward compatibility',
        { epic: epicName }
      )
    );
  }

  for (const key of referencedKeys) {
    if (!globalLedgerKeys.has(key)) {
      violations.push(
        makeProblem(
          'unknown-ledger-row-key',
          relativePath,
          `Contract Ledger row key is not defined: ${key}`,
          { epic: epicName, contract: key }
        )
      );
    } else if (epicName && !ledgerKeys.has(key)) {
      warnings.push(
        makeProblem(
          'external-ledger-row-key',
          relativePath,
          `Contract Ledger row key is defined outside this epic: ${key}`,
          { epic: epicName, contract: key }
        )
      );
    }
  }

  return { path, epicName, referencedKeys };
}

function buildLedger(root, epics, violations) {
  const entries = [];
  const byKey = new Map();

  for (const epic of epics) {
    if (epic.contractLedgerRowCount > 0 && !epic.contractLedgerHasContractColumn) {
      violations.push(
        makeProblem(
          'contract-ledger-missing-contract-column',
          rel(root, epic.architecturePath),
          `Contract Ledger table must use canonical \`contract\` column as the stable row key; found columns: ${epic.contractLedgerHeader.join(', ') || '-'}`,
          {
            epic: epic.name,
            headers: epic.contractLedgerHeader,
          }
        )
      );
    }

    for (const row of epic.contractRows) {
      const key = row.contract.trim();
      const entry = {
        contract: key,
        epic: epic.name,
        ledgerPath: epic.architecturePath,
        row,
      };
      entries.push(entry);
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key).push(entry);
    }
  }

  for (const [key, matches] of byKey.entries()) {
    if (matches.length <= 1) continue;
    violations.push(
      makeProblem(
        'duplicate-ledger-row-key',
        rel(root, matches[0].ledgerPath),
        `Contract Ledger row key is duplicated: ${key}`,
        {
          contract: key,
          locations: matches.map((match) => rel(root, match.ledgerPath)),
        }
      )
    );
  }

  return { entries, byKey, keys: new Set(byKey.keys()) };
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

function buildRecovery({ root, contract, ledger, artifacts, violations, warnings }) {
  const indexPath = join(root, 'docs', 'index.md');
  if (!existsSync(indexPath)) {
    violations.push(
      makeProblem(
        'cold-session-index-missing',
        rel(root, indexPath),
        'docs/index.md is required as the cold-session entrypoint',
        { contract }
      )
    );
    return null;
  }

  const matches = ledger.byKey.get(contract) ?? [];
  if (matches.length === 0) {
    violations.push(
      makeProblem(
        'contract-not-found',
        rel(root, indexPath),
        `Contract Ledger row key was not found: ${contract}`,
        { contract }
      )
    );
    return null;
  }
  if (matches.length > 1) {
    violations.push(
      makeProblem(
        'contract-ambiguous',
        rel(root, indexPath),
        `Contract Ledger row key is ambiguous: ${contract}`,
        { contract, locations: matches.map((match) => rel(root, match.ledgerPath)) }
      )
    );
    return null;
  }

  const match = matches[0];
  const indexContent = readText(indexPath);
  if (!indexContent.includes(match.epic) && !indexContent.includes(`epics/${match.epic}`)) {
    warnings.push(
      makeProblem(
        'cold-session-index-missing-epic-link',
        rel(root, indexPath),
        `docs/index.md does not visibly link the contract epic: ${match.epic}`,
        { contract, epic: match.epic }
      )
    );
  }

  return {
    contract,
    index_path: rel(root, indexPath),
    epic: match.epic,
    ledger_path: rel(root, match.ledgerPath),
    referencing_impl: artifacts
      .filter((artifact) => artifact.referencedKeys.includes(contract))
      .map((artifact) => rel(root, artifact.path))
      .sort(),
    validation_paths: [
      'agents/architecture-validator/architecture-validator-agent.md',
      'agents/module-architect/templates/impl-task.md',
    ],
  };
}

function audit(root, contract = '') {
  const violations = [];
  const warnings = [];
  const epics = collectEpics(root);
  const ledger = buildLedger(root, epics, violations);
  const artifacts = [];

  auditDesignPackBudgets(root, epics, warnings);

  for (const epic of epics) {
    const ledgerKeys = new Set(epic.contractRows.map((row) => row.contract.trim()));
    for (const implPath of epic.implPaths) {
      artifacts.push(
        auditArtifact({
          root,
          path: implPath,
          epicName: epic.name,
          ledgerKeys,
          globalLedgerKeys: ledger.keys,
          violations,
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
        ledgerKeys: ledger.keys,
        globalLedgerKeys: ledger.keys,
        violations,
        warnings,
      })
    );
  }

  const recovery = contract
    ? buildRecovery({ root, contract, ledger, artifacts, violations, warnings })
    : null;

  return {
    ok: violations.length === 0,
    root,
    epics: epics.map((epic) => ({
      name: epic.name,
      ledger_path: rel(root, epic.architecturePath),
      contract_count: epic.contractRows.length,
      impl_count: epic.implPaths.length,
      design_pack_line_count: epic.designPackLineCount,
    })),
    violations,
    warnings,
    recovery,
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

  const contractMessage = result.recovery
    ? `, contract ${result.recovery.contract} -> ${result.recovery.ledger_path}`
    : '';
  console.log(
    `[design-artifact] PASS - ${result.epics.length} epic(s), ${result.warnings.length} warning(s)${contractMessage}`
  );
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!existsSync(args.root) || !statSync(args.root).isDirectory()) {
    throw new Error(`--root is not a directory: ${args.root}`);
  }

  const result = audit(args.root, args.contract);
  if (args.json) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    renderText(result);
  }

  process.exit(result.ok ? 0 : 1);
}

try {
  main();
} catch (error) {
  console.error(`[design-artifact] ERROR ${error.message}`);
  process.exit(2);
}
