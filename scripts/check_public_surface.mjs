#!/usr/bin/env node
/**
 * dcNess public workflow surface contract.
 *
 * Checks that user-facing skill/command inventory and internal agent inventory
 * match the expected product surface documented in docs/plugin/positioning.md.
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';

const POSITIONING = 'docs/plugin/positioning.md';

const EXPECTED = {
  defaultSkills: ['impl', 'issue-report', 'product-plan', 'spec'],
  advancedSkills: ['acceptance', 'architect-loop', 'design', 'impl-loop', 'tech-review', 'ux'],
  utilityCommands: ['efficiency', 'init-dcness', 'run-review', 'smart-compact'],
  internalAgents: [
    'architecture-validator',
    'build-worker',
    'code-validator',
    'designer',
    'engineer',
    'module-architect',
    'pr-reviewer',
    'product-acceptance',
    'qa',
    'system-architect',
    'tech-reviewer',
    'test-engineer',
    'ux-architect',
  ],
};

const violations = [];

function frontmatterName(path) {
  const text = readFileSync(path, 'utf8');
  const m = text.match(/^name:\s*([^\n]+)$/m);
  if (!m) {
    violations.push(`${path}: frontmatter name missing`);
    return null;
  }
  return m[1].trim().replace(/^['"]|['"]$/g, '');
}

function listSkills() {
  if (!existsSync('skills')) return [];
  return readdirSync('skills', { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => join('skills', entry.name, 'SKILL.md'))
    .filter((path) => existsSync(path))
    .map((path) => {
      const name = frontmatterName(path);
      const dir = basename(dirname(path));
      if (name && dir !== name) {
        violations.push(`${path}: frontmatter name ${name} must match skill directory ${dir}`);
      }
      return { path, name };
    })
    .filter((item) => item.name)
    .sort((a, b) => a.name.localeCompare(b.name));
}

function listCommands() {
  if (!existsSync('commands')) return [];
  return readdirSync('commands', { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.md'))
    .map((entry) => join('commands', entry.name))
    .map((path) => {
      const name = frontmatterName(path);
      const file = basename(path, '.md');
      if (name && file !== name) {
        violations.push(`${path}: frontmatter name ${name} must match command file ${file}`);
      }
      return { path, name };
    })
    .filter((item) => item.name)
    .sort((a, b) => a.name.localeCompare(b.name));
}

function listAgents() {
  if (!existsSync('agents')) return [];
  return readdirSync('agents', { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.md'))
    .map((entry) => join('agents', entry.name))
    .map((path) => {
      const name = frontmatterName(path);
      const file = basename(path, '.md');
      if (name && file !== name) {
        violations.push(`${path}: frontmatter name ${name} must match agent file ${file}`);
      }
      return { path, name };
    })
    .filter((item) => item.name)
    .sort((a, b) => a.name.localeCompare(b.name));
}

function assertSet(label, actual, expected) {
  const a = [...actual].sort();
  const e = [...expected].sort();
  const missing = e.filter((x) => !a.includes(x));
  const extra = a.filter((x) => !e.includes(x));
  if (missing.length) violations.push(`${label}: missing ${missing.join(', ')}`);
  if (extra.length) violations.push(`${label}: unexpected ${extra.join(', ')}`);
}

function assertDocsMention(label, names, prefix = '') {
  if (!existsSync(POSITIONING)) {
    violations.push(`${POSITIONING}: file not found`);
    return;
  }
  const text = readFileSync(POSITIONING, 'utf8');
  for (const name of names) {
    const needle = prefix ? `\`${prefix}${name}\`` : `\`${name}\``;
    if (!text.includes(needle)) {
      violations.push(`${POSITIONING}: missing ${label} mention ${needle}`);
    }
  }
}

const skills = listSkills();
const commands = listCommands();
const agents = listAgents();

const expectedSkills = [...EXPECTED.defaultSkills, ...EXPECTED.advancedSkills];
assertSet('skills', skills.map((item) => item.name), expectedSkills);
assertSet('commands', commands.map((item) => item.name), EXPECTED.utilityCommands);
assertSet('agents', agents.map((item) => item.name), EXPECTED.internalAgents);

assertDocsMention('default skill', EXPECTED.defaultSkills, '/');
assertDocsMention('advanced skill', EXPECTED.advancedSkills, '/');
assertDocsMention('utility command', EXPECTED.utilityCommands, '/');
assertDocsMention('internal agent', EXPECTED.internalAgents);

if (violations.length) {
  console.error('[public-surface] FAIL');
  for (const violation of violations) console.error(`  - ${violation}`);
  process.exit(1);
}

console.log(
  `[public-surface] PASS — defaults: ${EXPECTED.defaultSkills.map((s) => `/${s}`).join(', ')}`
);
