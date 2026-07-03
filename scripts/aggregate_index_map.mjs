#!/usr/bin/env node
/**
 * Generate/update docs/index.md generated tables from docs/epics/* and docs/modules/*.
 *
 * Source of truth:
 * - docs/epics/epic-NN-<slug>/
 * - optional stories.md frontmatter milestone
 * - docs/modules/<module-id>/
 *
 * Usage:
 *   node scripts/aggregate_index_map.mjs
 *   node scripts/aggregate_index_map.mjs --root /path/to/project
 *   node scripts/aggregate_index_map.mjs --check
 */
import {
  existsSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';

const SECTION_EPICS = '에픽';
const SECTION_MODULES = '모듈';
const MARKER_EPICS = 'dcness-index-map:generated';
const MARKER_MODULES = 'dcness-module-map:generated';
const PLACEHOLDER = '—';

function usage() {
  return [
    'Usage: node scripts/aggregate_index_map.mjs [--root <path>] [--check]',
    '',
    'Updates docs/index.md generated tables from docs/epics/* and docs/modules/*.',
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

function mdLinkDir(label, fromFile, toDir) {
  const link = slash(relative(dirname(fromFile), toDir)).replace(/\/?$/, '/');
  return `[${label}](${link})`;
}

function cleanCell(value) {
  const normalized = String(value ?? '')
    .replace(/\r?\n/g, ' ')
    .replace(/\|/g, '\\|')
    .trim();
  return normalized || PLACEHOLDER;
}

function parseFrontmatterValue(content, key) {
  const match = String(content ?? '').match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) return '';

  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const line = match[1].match(new RegExp(`^${escaped}:\\s*(.+?)\\s*$`, 'm'));
  if (!line) return '';
  return line[1].replace(/^['"]|['"]$/g, '').trim();
}

function collectEpics(root) {
  const epicsRoot = join(root, 'docs', 'epics');
  if (!existsSync(epicsRoot)) return [];

  return readdirSync(epicsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => /^epic-\d+-[a-z0-9][a-z0-9_-]*$/.test(name))
    .sort()
    .map((name) => {
      const epicDir = join(epicsRoot, name);
      const storiesPath = join(epicDir, 'stories.md');
      const storiesContent = existsSync(storiesPath) ? readFileSync(storiesPath, 'utf8') : '';
      return {
        name,
        epicDir,
        storiesPath,
        architecturePath: join(epicDir, 'architecture.md'),
        domainModelPath: join(epicDir, 'domain-model.md'),
        uxFlowPath: join(epicDir, 'ux-flow.md'),
        techReviewPath: join(epicDir, 'tech-review.md'),
        milestone: parseFrontmatterValue(storiesContent, 'milestone') || PLACEHOLDER,
      };
    });
}

function collectModules(root) {
  const modulesRoot = join(root, 'docs', 'modules');
  if (!existsSync(modulesRoot)) return [];

  return readdirSync(modulesRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => /^[a-z0-9][a-z0-9_-]*$/.test(name))
    .sort()
    .map((name) => {
      const moduleDir = join(modulesRoot, name);
      return {
        name,
        moduleDir,
        architecturePath: join(moduleDir, 'architecture.md'),
        conventionsPath: join(moduleDir, 'conventions.md'),
        techReviewPath: join(moduleDir, 'tech-review.md'),
      };
    });
}

function optionalFileLink(label, fromFile, toFile) {
  return existsSync(toFile) ? mdLink(label, fromFile, toFile) : PLACEHOLDER;
}

function table(header, rows) {
  const lines = [
    `| ${header.join(' | ')} |`,
    `| ${header.map(() => '---').join(' | ')} |`,
  ];
  lines.push(...rows.map((row) => `| ${row.map(cleanCell).join(' | ')} |`));
  return lines.join('\n');
}

function buildEpicTable(indexPath, epics) {
  const rows = epics.map((epic) => [
    mdLinkDir(epic.name, indexPath, epic.epicDir),
    epic.milestone,
    optionalFileLink('stories.md', indexPath, epic.storiesPath),
    optionalFileLink('architecture.md', indexPath, epic.architecturePath),
    optionalFileLink('domain-model.md', indexPath, epic.domainModelPath),
    optionalFileLink('ux-flow.md', indexPath, epic.uxFlowPath),
    optionalFileLink('tech-review.md', indexPath, epic.techReviewPath),
  ]);

  return table(
    ['에픽', '마일스톤', 'Stories', 'Architecture', 'Domain Model', 'UX Flow', 'Tech Review'],
    rows.length > 0
      ? rows
      : [[PLACEHOLDER, PLACEHOLDER, PLACEHOLDER, PLACEHOLDER, PLACEHOLDER, PLACEHOLDER, PLACEHOLDER]]
  );
}

function buildModuleTable(indexPath, modules) {
  const rows = modules.map((module) => [
    mdLinkDir(module.name, indexPath, module.moduleDir),
    optionalFileLink('architecture.md', indexPath, module.architecturePath),
    optionalFileLink('conventions.md', indexPath, module.conventionsPath),
    optionalFileLink('tech-review.md', indexPath, module.techReviewPath),
  ]);

  return table(
    ['모듈', 'Architecture', 'Conventions', 'Tech Review'],
    rows.length > 0
      ? rows
      : [[PLACEHOLDER, PLACEHOLDER, PLACEHOLDER, PLACEHOLDER]]
  );
}

function generatedSection(heading, marker, body) {
  return [
    `## ${heading}`,
    '',
    `<!-- ${marker} -->`,
    '<!-- 수정하지 말고 plugin script `aggregate_index_map.mjs` 로 갱신한다. -->',
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

function noOpReason({ indexPath, epics, modules }) {
  if (!existsSync(indexPath)) return 'docs/index.md missing';
  const content = readFileSync(indexPath, 'utf8');
  const hasGeneratedEpicSection = content.includes(`<!-- ${MARKER_EPICS} -->`);
  const hasGeneratedModuleSection = content.includes(`<!-- ${MARKER_MODULES} -->`);
  if (
    epics.length === 0
    && modules.length === 0
    && !hasGeneratedEpicSection
    && !hasGeneratedModuleSection
  ) {
    return 'no valid docs/epics/epic-NN-* or docs/modules/* directories';
  }
  return '';
}

function nextIndex(root, epics, modules) {
  const indexPath = join(root, 'docs', 'index.md');
  let nextContent = readFileSync(indexPath, 'utf8');

  if (epics.length > 0 || nextContent.includes(`<!-- ${MARKER_EPICS} -->`)) {
    nextContent = replaceSection(
      nextContent,
      SECTION_EPICS,
      generatedSection(
        SECTION_EPICS,
        MARKER_EPICS,
        buildEpicTable(indexPath, epics)
      )
    );
  }

  if (modules.length > 0 || nextContent.includes(`<!-- ${MARKER_MODULES} -->`)) {
    nextContent = replaceSection(
      nextContent,
      SECTION_MODULES,
      generatedSection(
        SECTION_MODULES,
        MARKER_MODULES,
        buildModuleTable(indexPath, modules)
      )
    );
  }

  return {
    path: indexPath,
    content: `${nextContent.trimEnd()}\n`,
    epicCount: epics.length,
    moduleCount: modules.length,
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const indexPath = join(args.root, 'docs', 'index.md');
  const epics = collectEpics(args.root);
  const modules = collectModules(args.root);
  const reason = noOpReason({ indexPath, epics, modules });

  if (reason) {
    console.log(`[index-map] no-op PASS — ${reason}`);
    return;
  }

  const next = nextIndex(args.root, epics, modules);
  const current = readFileSync(next.path, 'utf8');

  if (args.check) {
    if (current === next.content) {
      console.log(`[index-map] PASS — ${next.epicCount} epic, ${next.moduleCount} module`);
      return;
    }
    console.error(
      '[index-map] FAIL — docs/index.md is stale. Run this script without --check from the project root.'
    );
    process.exit(1);
  }

  if (current !== next.content) {
    writeFileSync(next.path, next.content, 'utf8');
  }
  console.log(
    `[index-map] updated ${slash(relative(args.root, next.path))} — ${next.epicCount} epic, ${next.moduleCount} module`
  );
}

try {
  main();
} catch (err) {
  console.error(`[index-map] ERROR — ${err.message}`);
  console.error(usage());
  process.exit(2);
}
