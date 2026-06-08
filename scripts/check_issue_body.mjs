#!/usr/bin/env node
/**
 * Issue Brief pre-create validation gate.
 *
 * This is an agent workflow guard, not a GitHub UI hard gate. Run it before
 * `gh issue create` so malformed agent-created issues fail before creation.
 */
import { readFileSync } from 'node:fs';
import { PROJECT_FIELDS, ISSUE_TYPE_LABELS } from './github_project_lifecycle.mjs';

const REQUIRED_FIELDS = Object.freeze([
  'IssueType',
  'Priority',
  'Summary',
  'Current behavior / Context',
  'Desired behavior / What to build',
  'Key interfaces / Contracts',
  'Acceptance criteria',
  'Blocked by',
  'Out of scope',
]);

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

function parseArgs(argv) {
  const args = { _: [] };
  const booleanFlags = new Set(['stdin', 'body-only']);
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) {
      args._.push(token);
      continue;
    }
    const key = token.slice(2);
    if (booleanFlags.has(key)) {
      args[key] = true;
      continue;
    }
    args[key] = argv[i + 1] ?? true;
    if (args[key] !== true) i += 1;
  }
  return args;
}

function fieldRegex(fieldName) {
  return new RegExp(String.raw`^[ \t]*\*\*${escapeRegex(fieldName)}:\*\*[ \t]*(.*)$`, 'im');
}

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function parseField(body, fieldName) {
  const match = String(body ?? '').match(fieldRegex(fieldName));
  if (!match) return null;
  return match[1].trim();
}

function parseLabels(value) {
  if (!value || value === true) return [];
  return String(value)
    .split(',')
    .map((label) => label.trim())
    .filter(Boolean);
}

export function validateIssueBody({ body, labels = [], requireLabels = false }) {
  const text = String(body ?? '');
  const failures = [];

  if (!/^##\s+Issue Brief\s*$/im.test(text)) {
    failures.push('missing required heading: ## Issue Brief');
  }

  for (const fieldName of REQUIRED_FIELDS) {
    if (!fieldRegex(fieldName).test(text)) {
      failures.push(`missing required Issue Brief field: ${fieldName}`);
    }
  }

  const issueType = parseField(text, 'IssueType');
  const priority = parseField(text, 'Priority');

  if (issueType === '') {
    failures.push(`invalid IssueType=<empty>; expected one of ${PROJECT_FIELDS.IssueType.join(', ')}`);
  } else if (issueType && !PROJECT_FIELDS.IssueType.includes(issueType)) {
    failures.push(`invalid IssueType=${issueType}; expected one of ${PROJECT_FIELDS.IssueType.join(', ')}`);
  }

  if (priority === '') {
    failures.push(`invalid Priority=<empty>; expected one of ${PROJECT_FIELDS.Priority.join(', ')}`);
  } else if (priority && !PROJECT_FIELDS.Priority.includes(priority)) {
    failures.push(`invalid Priority=${priority}; expected one of ${PROJECT_FIELDS.Priority.join(', ')}`);
  }

  const issueTypeLabels = labels.filter((label) => ISSUE_TYPE_LABELS.includes(label));
  if (labels.length > 0 || requireLabels) {
    if (issueTypeLabels.length !== 1) {
      failures.push(
        `expected exactly one IssueType label, actual=${issueTypeLabels.length || 0} `
        + `(${issueTypeLabels.join(',') || '<none>'})`,
      );
    } else if (issueType && issueTypeLabels[0] !== issueType) {
      failures.push(`IssueType=${issueType} does not match repo label=${issueTypeLabels[0]}`);
    }
  }

  return {
    ok: failures.length === 0,
    failures,
    issueType: issueType || null,
    priority: priority || null,
    issueTypeLabels,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  let body = '';

  if (args.stdin) {
    body = await readStdin();
  } else if (args['body-file']) {
    body = readFileSync(args['body-file'], 'utf8');
  } else if (args.body) {
    body = String(args.body);
  } else {
    console.error('[issue-body] 사용법: --stdin | --body-file FILE | --body TEXT (--labels feature | --body-only)');
    return 1;
  }

  const result = validateIssueBody({
    body,
    labels: parseLabels(args.labels),
    requireLabels: !args['body-only'],
  });
  if (result.ok) {
    console.log(`[issue-body] PASS — IssueType=${result.issueType}, Priority=${result.priority}`);
    return 0;
  }

  console.error('[issue-body] FAIL — issue body pre-create validation failed.');
  for (const failure of result.failures) {
    console.error(`  - ${failure}`);
  }
  return 1;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exitCode = await main();
}
