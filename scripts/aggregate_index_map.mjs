#!/usr/bin/env node
/**
 * Generate/update docs/index.md epic table from docs/epics/*.
 *
 * Source of truth:
 * - docs/epics/epic-NN-<slug>/
 * - optional stories.md frontmatter milestone
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
const PLACEHOLDER = '—';

function usage() {
  return [
    'Usage: node scripts/aggregate_index_map.mjs [--root <path>] [--check]',
    '',
    'Updates docs/index.md ## 에픽 generated table from docs/epics/*.',
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
    rows
  );
}

function generatedSection(body) {
  return [
    `## ${SECTION_EPICS}`,
    '',
    '<!-- dcness-index-map:generated -->',
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

function noOpReason({ indexPath, epics }) {
  if (!existsSync(indexPath)) return 'docs/index.md missing';
  if (epics.length === 0) return 'no valid docs/epics/epic-NN-* directories';
  return '';
}

function nextIndex(root, epics) {
  const indexPath = join(root, 'docs', 'index.md');
  const content = readFileSync(indexPath, 'utf8');
  const nextContent = replaceSection(
    content,
    SECTION_EPICS,
    generatedSection(buildEpicTable(indexPath, epics))
  );

  return {
    path: indexPath,
    content: `${nextContent.trimEnd()}\n`,
    epicCount: epics.length,
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const indexPath = join(args.root, 'docs', 'index.md');
  const epics = collectEpics(args.root);
  const reason = noOpReason({ indexPath, epics });

  if (reason) {
    console.log(`[index-map] no-op PASS — ${reason}`);
    return;
  }

  const next = nextIndex(args.root, epics);
  const current = readFileSync(next.path, 'utf8');

  if (args.check) {
    if (current === next.content) {
      console.log(`[index-map] PASS — ${next.epicCount} epic`);
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
  console.log(`[index-map] updated ${slash(relative(args.root, next.path))} — ${next.epicCount} epic`);
}

try {
  main();
} catch (err) {
  console.error(`[index-map] ERROR — ${err.message}`);
  console.error(usage());
  process.exit(2);
}
