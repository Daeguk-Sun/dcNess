#!/usr/bin/env node
/**
 * Active-project doc path integrity validator.
 *
 * The gate scans context/SSOT docs that agents commonly read first and fails
 * when repo-relative path references point to files or directories that do not
 * exist. It is intentionally narrower than check_cross_refs.mjs: active
 * projects have arbitrary docs, so this script validates path integrity without
 * enforcing dcNess self-repo naming or orphan-document rules.
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, resolve, relative, join } from 'node:path';

const DEFAULT_DOC_ENTRIES = [
  'CLAUDE.md',
  'AGENTS.md',
  'architecture.md',
  'docs/index.md',
  'docs/project-context.md',
  'docs/architecture.md',
  'docs/conventions.md',
  'docs/decisions/**',
];

const ROOT_FILES = new Set([
  'AGENTS.md',
  'CLAUDE.md',
  'PROGRESS.md',
  'README.md',
  'architecture.md',
]);

const PATH_PREFIXES = [
  '.claude/',
  '.dcness-work/',
  '.github/',
  'agents/',
  'app/',
  'codex/',
  'commands/',
  'design-variants/',
  'docs/',
  'harness/',
  'hooks/',
  'lib/',
  'scripts/',
  'skills/',
  'src/',
  'templates/',
  'tests/',
];

const OPTIONAL_SEED_PATHS = new Set([
  '.dcness-work/',
  'docs/tech-review.md',
]);

const DCNESS_SELF_ACTIVE_PROJECT_PATHS = new Set([
  'docs/index.md',
  'docs/decisions/',
]);

function parseArgs(argv) {
  const args = { root: process.cwd(), docs: null };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--root') {
      args.root = argv[++i];
    } else if (arg === '--docs') {
      args.docs = argv[++i];
    } else if (arg === '-h' || arg === '--help') {
      printUsage();
      process.exit(0);
    } else {
      console.error(`[doc-path] unknown argument: ${arg}`);
      printUsage();
      process.exit(1);
    }
  }
  return args;
}

function printUsage() {
  console.error('Usage: node scripts/check_doc_path_integrity.mjs [--root DIR] [--docs "CLAUDE.md,docs/index.md,docs/decisions/**"]');
}

function splitDocEntries(value) {
  if (!value) return DEFAULT_DOC_ENTRIES;
  return value
    .split(/[,\n]/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function walkMarkdown(dir) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walkMarkdown(path));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      out.push(path);
    }
  }
  return out;
}

function expandDocEntries(root, entries) {
  const files = new Set();
  for (const entry of entries) {
    if (entry.endsWith('/**/*.md')) {
      const dir = resolve(root, entry.slice(0, -'/**/*.md'.length));
      for (const file of walkMarkdown(dir)) files.add(file);
      continue;
    }
    if (entry.endsWith('/**')) {
      const dir = resolve(root, entry.slice(0, -3));
      for (const file of walkMarkdown(dir)) files.add(file);
      continue;
    }
    if (entry.endsWith('/*.md')) {
      const dir = resolve(root, entry.slice(0, -'/*.md'.length));
      if (existsSync(dir)) {
        for (const item of readdirSync(dir, { withFileTypes: true })) {
          const file = resolve(dir, item.name);
          if (item.isFile() && file.endsWith('.md')) files.add(file);
        }
      }
      continue;
    }
    if (entry.includes('*')) {
      throw new Error(`unsupported docs glob: ${entry}`);
    }
    const target = resolve(root, entry);
    if (!existsSync(target)) continue;
    const stat = statSync(target);
    if (stat.isDirectory()) {
      for (const file of walkMarkdown(target)) files.add(file);
    } else if (stat.isFile() && target.endsWith('.md')) {
      files.add(target);
    }
  }
  return [...files].sort();
}

function isExternalUrl(value) {
  return /^(https?:|mailto:|tel:|ftp:)/i.test(value);
}

function stripLinkTitle(value) {
  const trimmed = value.trim();
  if (trimmed.startsWith('<')) {
    const end = trimmed.indexOf('>');
    return end === -1 ? trimmed : trimmed.slice(1, end);
  }
  return trimmed.split(/\s+/)[0];
}

function cleanCandidate(value) {
  let out = value.trim();
  out = out.replace(/^['"]|['"]$/g, '');
  out = out.replace(/[),.;:!?]+$/g, '');
  const hashIdx = out.indexOf('#');
  if (hashIdx !== -1) out = out.slice(0, hashIdx);
  const queryIdx = out.indexOf('?');
  if (queryIdx !== -1) out = out.slice(0, queryIdx);
  if (out.startsWith('./')) out = out.slice(2);
  return out;
}

function shouldIgnoreCandidate(value) {
  if (!value) return true;
  if (isExternalUrl(value)) return true;
  if (value.startsWith('#')) return true;
  if (value.startsWith('/')) return true;
  if (value.startsWith('~') || value.startsWith('$') || value.startsWith('@')) return true;
  if (value.startsWith('-')) return true;
  if (/[<>{}*]/.test(value)) return true;
  if (/\s/.test(value)) return true;
  return false;
}

function looksLikeRepoPath(value) {
  if (ROOT_FILES.has(value)) return true;
  return PATH_PREFIXES.some((prefix) => value.startsWith(prefix));
}

function isSeedPlaceholderPath(value) {
  return value === 'docs/decisions/NNNN-slug.md';
}

function isOptionalSeedPath(value) {
  return OPTIONAL_SEED_PATHS.has(value) || value.startsWith('.dcness-work/');
}

function isDcnessSelfRepo(root) {
  return existsSync(resolve(root, '.claude-plugin/plugin.json'))
    && existsSync(resolve(root, 'docs/plugin/deliverables-map.md'))
    && existsSync(resolve(root, 'scripts/check_cross_refs.mjs'));
}

function isDcnessSelfActiveProjectPath(root, value) {
  return isDcnessSelfRepo(root) && DCNESS_SELF_ACTIVE_PROJECT_PATHS.has(value);
}

function resolveInside(root, sourceDir, candidate, relativeToSource) {
  const base = relativeToSource ? sourceDir : root;
  const abs = resolve(base, candidate);
  const rel = relative(root, abs);
  if (rel.startsWith('..') || rel === '..') return null;
  return abs;
}

function recordCandidate(out, root, file, lineNumber, raw, kind, relativeToSource) {
  const sourceDir = dirname(file);
  const cleaned = cleanCandidate(raw);
  if (shouldIgnoreCandidate(cleaned)) return;
  if (isSeedPlaceholderPath(cleaned)) return;
  if (isOptionalSeedPath(cleaned)) return;
  if (isDcnessSelfActiveProjectPath(root, cleaned)) return;
  if (!looksLikeRepoPath(cleaned)) return;
  const abs = resolveInside(root, sourceDir, cleaned, relativeToSource);
  if (!abs) {
    out.push({ file, lineNumber, path: cleaned, kind, reason: 'escapes repository root' });
    return;
  }
  if (!existsSync(abs)) {
    out.push({ file, lineNumber, path: cleaned, kind, reason: 'missing' });
  }
}

function collectViolations(root, files) {
  const violations = [];
  for (const file of files) {
    const lines = readFileSync(file, 'utf8').split('\n');
    let inFence = false;
    for (let idx = 0; idx < lines.length; idx += 1) {
      const line = lines[idx];
      const trimmed = line.trim();
      if (trimmed.startsWith('```') || trimmed.startsWith('~~~')) {
        inFence = !inFence;
        continue;
      }
      if (inFence) continue;

      const linkRe = /!?\[[^\]]*\]\(([^)\n]+)\)/g;
      for (const match of line.matchAll(linkRe)) {
        const url = stripLinkTitle(match[1]);
        recordCandidate(violations, root, file, idx + 1, url, 'markdown-link', false);
      }

      const inlineCodeRe = /`([^`\n]+)`/g;
      for (const match of line.matchAll(inlineCodeRe)) {
        recordCandidate(violations, root, file, idx + 1, match[1], 'inline-code', false);
      }
    }
  }
  return violations;
}

function repoRelative(root, file) {
  return relative(root, file) || '.';
}

const args = parseArgs(process.argv.slice(2));
const root = resolve(args.root);
let docFiles;
try {
  docFiles = expandDocEntries(root, splitDocEntries(args.docs));
} catch (error) {
  console.error(`[doc-path] FAIL - ${error.message}`);
  process.exit(1);
}
const violations = collectViolations(root, docFiles);

if (violations.length) {
  console.error(`[doc-path] FAIL - ${violations.length} broken path reference(s)`);
  for (const v of violations) {
    console.error(
      `  - ${repoRelative(root, v.file)}:${v.lineNumber}: ${v.kind} \`${v.path}\` ${v.reason}`,
    );
  }
  process.exit(1);
}

console.log(`[doc-path] PASS - scanned ${docFiles.length} context doc(s)`);
