#!/usr/bin/env node

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { basename, join, relative } from 'node:path';
import { pathToFileURL } from 'node:url';


function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const next = argv[index + 1];
    if (next && !next.startsWith('--')) {
      args[key] = next;
      index += 1;
    } else {
      args[key] = true;
    }
  }
  return args;
}


function numericId(value) {
  const match = String(value).match(/(\d+)$/);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}


function sortedIds(values) {
  return [...new Set(values)].sort((left, right) => {
    const numeric = numericId(left) - numericId(right);
    return numeric || left.localeCompare(right);
  });
}


export function parseStoryAcceptance(markdown) {
  const stories = new Map();
  const duplicateIds = new Set();
  const ownerByAc = new Map();
  let currentStory = null;

  for (const line of String(markdown).split(/\r?\n/)) {
    const storyMatch = line.match(/^#{2,3}\s+Story\s+(\d+)\b/i);
    if (storyMatch) {
      currentStory = storyMatch[1];
      if (!stories.has(currentStory)) stories.set(currentStory, new Set());
      continue;
    }
    if (!currentStory) continue;

    const declaration = line.match(
      /^\s*-\s+(AC-\d{3,})\s+\[(?:command|agent-read)\]\s*:?\s+.+$/i,
    );
    if (!declaration) continue;

    const acId = declaration[1];
    if (ownerByAc.has(acId)) duplicateIds.add(acId);
    else ownerByAc.set(acId, currentStory);
    stories.get(currentStory).add(acId);
  }

  return { stories, duplicateIds: sortedIds(duplicateIds) };
}


function markdownFiles(root) {
  if (!existsSync(root)) return [];
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) files.push(...markdownFiles(path));
    else if (entry.isFile() && entry.name.endsWith('.md')) files.push(path);
  }
  return files.sort();
}


function frontmatterValue(markdown, key) {
  const frontmatter = String(markdown).match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!frontmatter) return null;
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = frontmatter[1].match(new RegExp(`^${escaped}:\\s*(.+?)\\s*$`, 'm'));
  return match ? match[1].trim() : null;
}


function sourceIds(row) {
  const ids = [];
  for (const match of row.matchAll(/\(from\s+([^)]+)\)/gi)) {
    ids.push(...(match[1].match(/\bAC-\d{3,}\b/g) ?? []));
  }
  return sortedIds(ids);
}


export function parseImplRequirements(implDir) {
  const requirements = [];
  const finalTaskFiles = new Map();

  for (const path of markdownFiles(implDir)) {
    const markdown = readFileSync(path, 'utf8');
    const story = frontmatterValue(markdown, 'story');
    const taskIndex = frontmatterValue(markdown, 'task_index');
    const taskMatch = taskIndex?.match(/^(\d+)\s*\/\s*(\d+)$/);
    if (story && taskMatch && taskMatch[1] === taskMatch[2]) {
      if (!finalTaskFiles.has(story)) finalTaskFiles.set(story, []);
      finalTaskFiles.get(story).push(path);
    }

    for (const line of markdown.split(/\r?\n/)) {
      if (!line.trimStart().startsWith('|')) continue;
      const firstCell = line.split('|')[1]?.trim().replace(/^`|`$/g, '');
      const reqId = firstCell?.match(/^REQ(?:-[A-Z]+)*-\d{3,}$/)?.[0];
      if (!reqId) continue;
      const sources = sourceIds(line);
      const technical = /\(technical:\s*[^)]+\)/i.test(line);
      requirements.push({
        id: reqId,
        story,
        path,
        sources,
        technical,
      });
    }
  }

  return { requirements, finalTaskFiles };
}


function percent(numerator, denominator) {
  if (denominator === 0) return '100.0';
  return ((numerator / denominator) * 100).toFixed(1);
}


function formatReq(req, implDir) {
  const file = relative(implDir, req.path) || basename(req.path);
  return `${req.id} (${file})`;
}


export function buildCoverageReport({ storyData, implData, implDir }) {
  const allAcceptance = sortedIds(
    [...storyData.stories.values()].flatMap((ids) => [...ids]),
  );
  if (allAcceptance.length === 0) {
    return '[ac-coverage] FAIL — Story AC is required.';
  }

  const knownAcceptance = new Set(allAcceptance);
  const coverage = new Map(allAcceptance.map((acId) => [acId, []]));
  const sourceLess = [];
  const technical = [];
  const unknown = new Set();

  for (const req of implData.requirements) {
    if (req.technical) {
      technical.push(req);
      continue;
    }
    if (req.sources.length === 0) sourceLess.push(req);
    for (const acId of req.sources) {
      if (!knownAcceptance.has(acId)) unknown.add(acId);
      else coverage.get(acId).push(req);
    }
  }

  const coveredAcceptance = allAcceptance.filter((acId) => coverage.get(acId).length > 0);
  const uncoveredAcceptance = allAcceptance.filter((acId) => coverage.get(acId).length === 0);
  const lines = [
    '[ac-coverage] Story AC -> task REQ advisory report',
    '| AC | Has REQ? | REQ IDs |',
    '|---|---|---|',
  ];

  for (const acId of allAcceptance) {
    const reqs = coverage.get(acId);
    lines.push(`| ${acId} | ${reqs.length > 0 ? 'yes' : 'no'} | ${reqs.map((req) => formatReq(req, implDir)).join(', ') || '-'} |`);
  }

  lines.push(`Coverage: ${coveredAcceptance.length}/${allAcceptance.length} (${percent(coveredAcceptance.length, allAcceptance.length)}%)`);
  lines.push(`Uncovered AC: ${uncoveredAcceptance.join(', ') || 'none'}`);
  lines.push(`Source-less REQ: ${sourceLess.map((req) => formatReq(req, implDir)).join(', ') || 'none'}`);
  lines.push(`Unknown AC references: ${sortedIds(unknown).join(', ') || 'none'}`);
  lines.push(`Technical REQ: ${technical.map((req) => req.id).join(', ') || 'none'}`);
  lines.push(`Duplicate AC IDs: ${storyData.duplicateIds.join(', ') || 'none'}`);

  const finalCovered = new Set();
  const finalMissing = new Set();
  for (const [story, acceptanceIds] of storyData.stories) {
    if (acceptanceIds.size === 0) continue;
    const finalFiles = new Set(implData.finalTaskFiles.get(story) ?? []);
    const finalSources = new Set(
      implData.requirements
        .filter((req) => finalFiles.has(req.path) && !req.technical)
        .flatMap((req) => req.sources),
    );
    for (const acId of acceptanceIds) {
      if (finalSources.has(acId)) finalCovered.add(acId);
      else finalMissing.add(acId);
    }
  }

  lines.push(`Final task coverage: ${finalCovered.size}/${allAcceptance.length} (${percent(finalCovered.size, allAcceptance.length)}%)`);
  lines.push(`Final task missing AC: ${sortedIds(finalMissing).join(', ') || 'none'}`);
  lines.push('[ac-coverage] Gaps are an advisory report for architecture review; this command does not block by exit code.');
  return lines.join('\n');
}


async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.stories || !args['impl-dir']) {
    console.error('[ac-coverage] Usage: report_ac_coverage.mjs --stories <stories.md> --impl-dir <impl-dir>');
    return 2;
  }
  if (!existsSync(args.stories)) {
    console.error(`[ac-coverage] stories file not found: ${args.stories}`);
    return 2;
  }
  if (!existsSync(args['impl-dir'])) {
    console.log(`[ac-coverage] impl directory not found: ${args['impl-dir']}`);
  }

  const storyData = parseStoryAcceptance(readFileSync(args.stories, 'utf8'));
  const implData = parseImplRequirements(args['impl-dir']);
  console.log(buildCoverageReport({ storyData, implData, implDir: args['impl-dir'] }));
  if ([...storyData.stories.values()].every((ids) => ids.size === 0)) return 1;
  return 0;
}


if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main();
}
