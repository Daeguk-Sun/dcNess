#!/usr/bin/env node
/**
 * Audit generated `/design` artifacts for the agent-first design contract.
 *
 * This script is intentionally read-only and audits only the current
 * agent-first design contract.
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
import { spawnSync } from 'node:child_process';
import { join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const DESIGN_PACK_LINE_TARGET = 1500;
const DESIGN_PACK_LINE_HARD_WARNING = 2000;
const STORY_RUNNER = fileURLToPath(new URL('./dcness-story-runner', import.meta.url));
function usage() {
  return [
    'Usage: node scripts/check_design_artifact_structure.mjs [--root <path>] [--json]',
    '',
    'Audits docs/epics/* design artifacts for agent-first structure.',
  ].join('\n');
}

function parseArgs(argv) {
  const args = {
    root: process.cwd(),
    json: false,
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

function hasSection(content, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^##\\s+${escaped}\\s*$`, 'm').test(content);
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

function auditImplStoryOrder(root, epic, violations) {
  if (epic.implPaths.length === 0) return;

  const implDir = join(epic.dir, 'impl');
  const result = spawnSync(STORY_RUNNER, ['plan', implDir], {
    cwd: root,
    encoding: 'utf8',
  });
  if (result.status === 0) return;

  const detail = (result.stderr || result.stdout || result.error?.message || '')
    .trim()
    .replace(/^story-runner:\s*/, '');
  const nonContiguous = detail.includes('non-contiguous story group');
  violations.push(
    makeProblem(
      nonContiguous ? 'impl-story-non-contiguous' : 'impl-runner-plan-invalid',
      rel(root, implDir),
      detail || 'dcness-story-runner plan failed without diagnostic output',
      {
        epic: epic.name,
        runner_exit_code: result.status,
      }
    )
  );
}

function audit(root) {
  const violations = [];
  const warnings = [];
  const epics = collectEpics(root);

  auditDesignPackBudgets(root, epics, warnings);

  for (const epic of epics) {
    auditArchitecture(root, epic, warnings);
    auditImplStoryOrder(root, epic, violations);
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
    const result = audit(args.root);
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
