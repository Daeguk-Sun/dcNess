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
  const booleanFlags = new Set([
    'stdin',
    'body-only',
    'acceptance-only',
    'require-complete',
  ]);
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

export function fieldRegex(fieldName) {
  return new RegExp(String.raw`^[ \t]*\*\*${escapeRegex(fieldName)}:\*\*[ \t]*(.*)$`, 'im');
}

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function parseField(body, fieldName) {
  const match = String(body ?? '').match(fieldRegex(fieldName));
  if (!match) return null;
  return match[1].trim();
}

export function parseFieldSection(body, fieldName) {
  const text = String(body ?? '');
  const match = fieldRegex(fieldName).exec(text);
  if (!match) return null;

  const start = match.index + match[0].length;
  const remainder = text.slice(start);
  const nextField = remainder.search(/^[ \t]*\*\*[^\n:]+:\*\*/m);
  return (nextField === -1 ? remainder : remainder.slice(0, nextField)).trim();
}

function parseHeadingSection(body, headingName) {
  const text = String(body ?? '');
  const headingRegex = new RegExp(
    String.raw`^[ \t]{0,3}#{1,6}[ \t]+${escapeRegex(headingName)}[ \t]*:?[ \t]*#*[ \t]*$`,
    'im',
  );
  const match = headingRegex.exec(text);
  if (!match) return null;

  const start = match.index + match[0].length;
  const remainder = text.slice(start);
  const nextHeading = remainder.search(/^[ \t]{0,3}#{1,6}[ \t]+\S/m);
  return (nextHeading === -1 ? remainder : remainder.slice(0, nextHeading)).trim();
}

function parseNamedSection(body, ...sectionNames) {
  for (const sectionName of sectionNames) {
    const section = (
      parseFieldSection(body, sectionName)
      ?? parseHeadingSection(body, sectionName)
    );
    if (section !== null) return section;
  }
  return null;
}

const CHECKBOX_ITEM = /^\s*[-*+]\s+\[([ xX])\]\s+(.+?)\s*$/;
const VERIFICATION_CLASS = /^\[(command|agent-read)\]\s+(.+)$/i;
const STORY_VERIFICATION_CLASS = /^(AC-\d{3,})\s+\[(command|agent-read)\]:?\s+(.+)$/i;
const GENERIC_ACCEPTANCE = /^(?:구현(?:이|은)?\s*완료(?:된다|되어야 한다)|정상(?:적으로)?\s*동작(?:한다|해야 한다)|문제없이\s*동작(?:한다|해야 한다)|works?\s+(?:correctly|as expected)|implementation\s+is\s+complete)[.!。]?$/i;

export function parseAcceptanceCriteria(body) {
  const section = parseNamedSection(body, 'Acceptance criteria') ?? '';
  return section
    .split(/\r?\n/)
    .map((line, index) => ({ line: index + 1, text: line.trim() }))
    .filter(({ text }) => CHECKBOX_ITEM.test(text))
    .map(({ line, text }) => {
      const checkbox = text.match(CHECKBOX_ITEM);
      const criterion = checkbox[2].trim();
      const classified = criterion.match(VERIFICATION_CLASS);
      const storyClassified = criterion.match(STORY_VERIFICATION_CLASS);
      return {
        line,
        checked: checkbox[1].toLowerCase() === 'x',
        text: criterion,
        verificationClass: (
          classified?.[1]?.toLowerCase()
          ?? storyClassified?.[2]?.toLowerCase()
          ?? null
        ),
        statement: classified?.[2]?.trim() ?? storyClassified?.[3]?.trim() ?? criterion,
      };
    });
}

function parseLabels(value) {
  if (!value || value === true) return [];
  return String(value)
    .split(',')
    .map((label) => label.trim())
    .filter(Boolean);
}

export function validateIssueBody({
  body,
  labels = [],
  requireLabels = false,
  requireComplete = false,
  acceptanceOnly = false,
}) {
  const text = String(body ?? '');
  const failures = [];

  if (!acceptanceOnly) {
    if (!/^##\s+Issue Brief\s*$/im.test(text)) {
      failures.push('missing required heading: ## Issue Brief');
    }

    for (const fieldName of REQUIRED_FIELDS) {
      if (!fieldRegex(fieldName).test(text)) {
        failures.push(`missing required Issue Brief field: ${fieldName}`);
      }
    }
  }

  const issueType = parseField(text, 'IssueType');
  const priority = parseField(text, 'Priority');

  if (!acceptanceOnly) {
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
  }

  const issueTypeLabels = labels.filter((label) => ISSUE_TYPE_LABELS.includes(label));
  if (!acceptanceOnly && (labels.length > 0 || requireLabels)) {
    if (issueTypeLabels.length !== 1) {
      failures.push(
        `expected exactly one IssueType label, actual=${issueTypeLabels.length || 0} `
        + `(${issueTypeLabels.join(',') || '<none>'})`,
      );
    } else if (issueType && issueTypeLabels[0] !== issueType) {
      failures.push(`IssueType=${issueType} does not match repo label=${issueTypeLabels[0]}`);
    }
  }

  const acceptanceCriteria = parseAcceptanceCriteria(text);
  if (acceptanceCriteria.length === 0) {
    failures.push('Acceptance criteria must contain at least one checklist item');
  }
  for (const criterion of acceptanceCriteria) {
    if (!criterion.verificationClass) {
      failures.push(
        `acceptance criterion must declare [command] or [agent-read]: ${criterion.text}`,
      );
    }
    if ((!acceptanceOnly || criterion.verificationClass) && GENERIC_ACCEPTANCE.test(criterion.statement)) {
      failures.push(`generic acceptance criterion is not verifiable: ${criterion.statement}`);
    }
  }

  const unclassifiedCriteria = acceptanceCriteria.filter((item) => !item.verificationClass);

  const humanVerification = parseNamedSection(
    text,
    'Human verification / 사람 확인 안내',
    'Human verification',
    '사람 확인 안내',
  );
  if (humanVerification && humanVerification.split(/\r?\n/).some((line) => CHECKBOX_ITEM.test(line))) {
    failures.push('human verification items must not use checkboxes');
  }

  const uncheckedCriteria = acceptanceCriteria.filter((criterion) => !criterion.checked);
  if (requireComplete && uncheckedCriteria.length > 0) {
    failures.push(`unchecked acceptance criteria remain: ${uncheckedCriteria.length}`);
  }

  return {
    ok: failures.length === 0,
    failures,
    issueType: issueType || null,
    priority: priority || null,
    issueTypeLabels,
    acceptanceCriteria,
    unclassifiedCriteria,
    uncheckedCriteria,
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
    console.error(
      '[issue-body] 사용법: --stdin | --body-file FILE | --body TEXT '
      + '(--labels feature | --body-only | --acceptance-only) [--require-complete]',
    );
    return 1;
  }

  const result = validateIssueBody({
    body,
    labels: parseLabels(args.labels),
    requireLabels: !args['body-only'] && !args['acceptance-only'],
    requireComplete: Boolean(args['require-complete']),
    acceptanceOnly: Boolean(args['acceptance-only']),
  });
  if (result.ok) {
    if (args['acceptance-only']) {
      console.log(`[issue-body] PASS — acceptance criteria complete (${result.acceptanceCriteria.length})`);
    } else {
      console.log(`[issue-body] PASS — IssueType=${result.issueType}, Priority=${result.priority}`);
    }
    return 0;
  }

  console.error(
    args['acceptance-only']
      ? '[issue-body] FAIL — issue acceptance close audit failed.'
      : '[issue-body] FAIL — issue body pre-create validation failed.',
  );
  for (const failure of result.failures) {
    console.error(`  - ${failure}`);
  }
  return 1;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exitCode = await main();
}
