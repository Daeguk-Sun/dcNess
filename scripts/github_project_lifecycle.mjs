#!/usr/bin/env node
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { parseField } from './check_issue_body.mjs';
import { epicPhase } from './lib/epic_phase.mjs';

export const GH_MAX_BUFFER_BYTES = 64 * 1024 * 1024;

export const PROJECT_FIELDS = Object.freeze({
  Status: Object.freeze(['Todo', 'In progress', 'Done']),
  IssueType: Object.freeze(['epic', 'feature', 'story', 'task', 'subTask', 'bug']),
  Priority: Object.freeze(['blocker', 'critical', 'major', 'minor', 'trivial']),
});

export const ISSUE_TYPE_LABEL_META = Object.freeze({
  epic: ['7057ff', 'epic-level GitHub issue'],
  feature: ['a2eeef', 'feature-level GitHub issue'],
  story: ['0e8a16', 'story-level GitHub issue'],
  task: ['c5def5', 'task-level GitHub issue'],
  subTask: ['bfdadc', 'subTask-level GitHub issue'],
  bug: ['d73a4a', 'bug-level GitHub issue'],
});

export const IN_PROGRESS_LABEL = 'in-progress';
export const LIFECYCLE_LABEL_META = Object.freeze({
  ...ISSUE_TYPE_LABEL_META,
  [IN_PROGRESS_LABEL]: ['fbca04', 'dcNess lifecycle status: work is currently in progress'],
});

export const ISSUE_TYPE_LABELS = Object.freeze(PROJECT_FIELDS.IssueType);
export const LIFECYCLE_LABELS = Object.freeze([...ISSUE_TYPE_LABELS, IN_PROGRESS_LABEL]);
const COMPLETION_KEYWORD = String.raw`(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)`;
const ISSUE_REFERENCE = String.raw`(?:([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+))?#(\d+)`;

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.fields)) return value.fields;
  if (Array.isArray(value?.labels)) return value.labels;
  if (Array.isArray(value?.items)) return value.items;
  return [];
}

function optionNames(field) {
  return asArray(field?.options).map((option) => String(option?.name ?? option));
}

function isSingleSelect(field) {
  const dataType = String(field?.dataType ?? field?.type ?? '').toUpperCase();
  return dataType === 'SINGLE_SELECT' || dataType === 'PROJECTV2SINGLESELECTFIELD';
}

function labelNames(labels) {
  return asArray(labels).map((label) => String(label?.name ?? label));
}

export function validateProjectFields(fieldsInput) {
  const fields = asArray(fieldsInput);
  const byName = new Map(fields.map((field) => [String(field?.name ?? ''), field]));
  const missingFields = [];
  const wrongTypeFields = [];
  const missingOptions = [];

  for (const [fieldName, requiredOptions] of Object.entries(PROJECT_FIELDS)) {
    const field = byName.get(fieldName);
    if (!field) {
      missingFields.push(fieldName);
      continue;
    }
    if (!isSingleSelect(field)) {
      wrongTypeFields.push(fieldName);
    }
    const actualOptions = new Set(optionNames(field));
    for (const option of requiredOptions) {
      if (!actualOptions.has(option)) {
        missingOptions.push({ field: fieldName, option });
      }
    }
  }

  return {
    ok: missingFields.length === 0
      && wrongTypeFields.length === 0
      && missingOptions.length === 0,
    missingFields,
    wrongTypeFields,
    missingOptions,
  };
}

export function validateIssueTypeLabels(labelsInput) {
  const names = new Set(labelNames(labelsInput));
  const missingLabels = ISSUE_TYPE_LABELS.filter((label) => !names.has(label));
  return { ok: missingLabels.length === 0, missingLabels };
}

export function validateLifecycleLabels(labelsInput) {
  const names = new Set(labelNames(labelsInput));
  const missingLabels = LIFECYCLE_LABELS.filter((label) => !names.has(label));
  return { ok: missingLabels.length === 0, missingLabels };
}

export function parseCompletionIssueNumbers(body) {
  const refs = parseCompletionIssueRefs(body).refs;
  const numbers = [];
  const seen = new Set();
  for (const ref of refs) {
    if (!seen.has(ref.number)) {
      seen.add(ref.number);
      numbers.push(ref.number);
    }
  }
  return { numbers };
}

export function parsePartOfIssueNumbers(body) {
  const text = String(body ?? '');
  const referenceRegex = new RegExp(ISSUE_REFERENCE, 'g');
  const numbers = [];
  const seen = new Set();

  for (const line of text.split(/\r?\n/)) {
    const partOf = line.match(/\bpart\s+of\b/i);
    if (!partOf) continue;

    referenceRegex.lastIndex = 0;
    const segment = line.slice(partOf.index + partOf[0].length);
    for (const match of segment.matchAll(referenceRegex)) {
      const number = Number(match[2]);
      if (Number.isInteger(number) && !seen.has(number)) {
        seen.add(number);
        numbers.push(number);
      }
    }
  }

  return { numbers };
}

export function parseCompletionIssueRefs(body, defaultRepo = null) {
  const text = String(body ?? '');
  const refs = [];
  const seen = new Set();
  const referenceRegex = new RegExp(ISSUE_REFERENCE, 'g');
  const trailerRegex = new RegExp(
    String.raw`^\s*(?:[-*+]\s+)?(?:${COMPLETION_KEYWORD})\b(.*)$`,
    'i',
  );
  const partOfRegex = /\bpart\s+of\b/i;

  for (const line of text.split(/\r?\n/)) {
    const trailer = line.match(trailerRegex);
    if (!trailer) continue;
    const partOf = trailer[1].search(partOfRegex);
    const trailerText = partOf >= 0 ? trailer[1].slice(0, partOf) : trailer[1];
    referenceRegex.lastIndex = 0;
    for (const match of trailerText.matchAll(referenceRegex)) {
      const repo = normalizeRepoName(match[1] || defaultRepo);
      const number = Number(match[2]);
      const key = `${repo ?? ''}#${number}`;
      if (Number.isInteger(number) && !seen.has(key)) {
        seen.add(key);
        refs.push({ repo, number });
      }
    }
  }

  return { refs };
}

export function applyDefaultRepoToRefs(refs, defaultRepo) {
  const repo = normalizeRepoName(defaultRepo);
  return asArray(refs).map((ref) => ({
    ...ref,
    repo: normalizeRepoName(ref?.repo) ?? repo,
  }));
}

export function resolveCompletionRefsForProject(body, cliRepo, detectedRepo) {
  const refs = parseCompletionIssueRefs(body, cliRepo).refs;
  return applyDefaultRepoToRefs(refs, detectedRepo ?? cliRepo);
}

export function prViewArgs({ pr, repo }) {
  const args = ['pr', 'view', String(pr)];
  if (repo) args.push('--repo', repo);
  args.push('--json', 'body,closingIssuesReferences');
  return args;
}

export function detectIssueTypeDrift({ issueNumber, projectIssueType, labels }) {
  const issueTypeLabels = labelNames(labels).filter((label) => ISSUE_TYPE_LABELS.includes(label));
  const issueRef = issueNumber ? `issue #${issueNumber}` : 'issue';
  const projectValue = projectIssueType || '<unset>';
  const labelValue = issueTypeLabels.length ? issueTypeLabels.join(',') : '<missing>';

  if (
    projectIssueType
    && issueTypeLabels.length === 1
    && issueTypeLabels[0] === projectIssueType
  ) {
    return { ok: true, message: `${issueRef}: IssueType and repo label match (${projectIssueType})` };
  }

  return {
    ok: false,
    message: `${issueRef}: Project IssueType=${projectValue}, repo label=${labelValue}. `
      + 'Set Project IssueType and exactly one matching repo label to the same value.',
  };
}

export function validateLifecycleIssueLabels({ issueNumber, state = null, labels }) {
  const names = labelNames(labels);
  const issueTypeLabels = names.filter((label) => ISSUE_TYPE_LABELS.includes(label));
  const inProgressLabels = names.filter((label) => label === IN_PROGRESS_LABEL);
  const issueRef = issueNumber ? `issue #${issueNumber}` : 'issue';
  const messages = [];
  let ok = true;

  if (issueTypeLabels.length !== 1) {
    ok = false;
    messages.push(
      `${issueRef}: expected exactly one IssueType label, actual=${issueTypeLabels.length || 0} `
      + `(${issueTypeLabels.join(',') || '<none>'}).`,
    );
  } else {
    messages.push(`${issueRef}: IssueType label=${issueTypeLabels[0]}`);
  }

  if (inProgressLabels.length > 1) {
    ok = false;
    messages.push(`${issueRef}: expected at most one ${IN_PROGRESS_LABEL} label, actual=${inProgressLabels.length}.`);
  }

  if (String(state ?? '').toUpperCase() === 'CLOSED' && inProgressLabels.length > 0) {
    ok = false;
    messages.push(`${issueRef}: closed issue retains in-progress label; remove ${IN_PROGRESS_LABEL}.`);
  }

  return { ok, messages };
}

export function statusDriftMessage({ repo = null, issueNumber, field = 'Status', expected, actual }) {
  const issueRef = repo ? `${repo}#${issueNumber}` : `#${issueNumber}`;
  return `issue ${issueRef}: status drift on Project field ${field}. `
    + `expected=${expected}, actual=${actual ?? '<unset>'}.`;
}

function issueRef({ repo = null, issueNumber }) {
  return repo ? `${repo}#${issueNumber}` : `#${issueNumber}`;
}

function projectFieldDriftMessage({ repo = null, issueNumber, field, expected, actual }) {
  return `issue ${issueRef({ repo, issueNumber })}: Project ${field}=${actual ?? '<unset>'}, `
    + `expected=${expected}.`;
}

function validateExpectedValue({ fieldName, expected }) {
  if (!expected || expected === 'any') return;
  if (!PROJECT_FIELDS[fieldName].includes(expected)) {
    throw new Error(`${fieldName}=${expected} is not a supported Project option.`);
  }
}

export function validateIssueProjectRegistration({
  repo = null,
  issueNumber,
  item,
  labels,
  expectedStatus = 'Todo',
  expectedIssueType = null,
  expectedPriority = null,
}) {
  validateExpectedValue({ fieldName: 'Status', expected: expectedStatus });
  validateExpectedValue({ fieldName: 'IssueType', expected: expectedIssueType });
  validateExpectedValue({ fieldName: 'Priority', expected: expectedPriority });

  const messages = [];
  let ok = true;
  const projectIssueType = projectItemIssueType(item);
  const issueTypeDrift = detectIssueTypeDrift({
    issueNumber,
    projectIssueType,
    labels,
  });
  messages.push(issueTypeDrift.message);
  if (!issueTypeDrift.ok) ok = false;

  if (expectedIssueType && expectedIssueType !== 'any' && projectIssueType !== expectedIssueType) {
    ok = false;
    messages.push(projectFieldDriftMessage({
      repo,
      issueNumber,
      field: 'IssueType',
      expected: expectedIssueType,
      actual: projectIssueType,
    }));
  }

  if (expectedStatus && expectedStatus !== 'any') {
    const actualStatus = projectItemFieldValue(item, 'Status');
    if (actualStatus !== expectedStatus) {
      ok = false;
      messages.push(statusDriftMessage({
        repo,
        issueNumber,
        expected: expectedStatus,
        actual: actualStatus,
      }));
    }
  }

  const actualPriority = projectItemFieldValue(item, 'Priority');
  if (expectedPriority && expectedPriority !== 'any') {
    if (actualPriority !== expectedPriority) {
      ok = false;
      messages.push(projectFieldDriftMessage({
        repo,
        issueNumber,
        field: 'Priority',
        expected: expectedPriority,
        actual: actualPriority,
      }));
    }
  } else if (expectedPriority !== 'any' && !PROJECT_FIELDS.Priority.includes(actualPriority)) {
    ok = false;
    messages.push(projectFieldDriftMessage({
      repo,
      issueNumber,
      field: 'Priority',
      expected: PROJECT_FIELDS.Priority.join('|'),
      actual: actualPriority,
    }));
  }

  return { ok, messages };
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) {
      args._.push(token);
      continue;
    }
    const key = token.slice(2);
    if (key === 'apply' || key === 'help' || key === 'preserve-existing') {
      args[key] = true;
      continue;
    }
    args[key] = argv[i + 1];
    i += 1;
  }
  return args;
}

function gh(args, { json = false, allowFailure = false } = {}) {
  try {
    const output = execFileSync('gh', args, {
      encoding: 'utf8',
      maxBuffer: GH_MAX_BUFFER_BYTES,
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
    if (!json) return output;
    return output ? JSON.parse(output) : {};
  } catch (error) {
    if (allowFailure) return null;
    const stderr = error.stderr ? String(error.stderr).trim() : error.message;
    throw new Error(`gh ${args.join(' ')} failed: ${stderr}`);
  }
}

function detectRepo(repoArg) {
  if (repoArg) return repoArg;
  const repo = gh(['repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'], {
    allowFailure: true,
  });
  if (!repo) {
    throw new Error('repo not found. Pass --repo OWNER/REPO or run inside a GitHub repo.');
  }
  return repo;
}

function repoOwner(repo, ownerArg) {
  return ownerArg || repo.split('/')[0];
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (value !== null && value !== undefined && String(value).trim() !== '') {
      return String(value).trim();
    }
  }
  return null;
}

function readRepoVariable(name, repo) {
  const args = ['variable', 'get', name];
  if (repo) args.push('--repo', repo);
  return gh(args, { allowFailure: true });
}

export function resolveProjectCoordinatesFromSources({
  repo,
  ownerArg = null,
  projectArg = null,
  env = process.env,
  variables = {},
}) {
  const project = firstNonEmpty(
    projectArg,
    env?.DCNESS_PROJECT_NUMBER,
    variables?.DCNESS_PROJECT_NUMBER,
  );
  const owner = firstNonEmpty(
    ownerArg,
    env?.DCNESS_PROJECT_OWNER,
    variables?.DCNESS_PROJECT_OWNER,
    repoOwner(repo),
  );
  return { repo, owner, project };
}

export function resolveProjectCoordinates(args, { requireProject = false } = {}) {
  const repo = detectRepo(args.repo);
  const variables = {};
  if (!firstNonEmpty(args.project, process.env.DCNESS_PROJECT_NUMBER)) {
    variables.DCNESS_PROJECT_NUMBER = readRepoVariable('DCNESS_PROJECT_NUMBER', repo);
  }
  if (!firstNonEmpty(args.owner, process.env.DCNESS_PROJECT_OWNER)) {
    variables.DCNESS_PROJECT_OWNER = readRepoVariable('DCNESS_PROJECT_OWNER', repo);
  }
  const resolved = resolveProjectCoordinatesFromSources({
    repo,
    ownerArg: args.owner,
    projectArg: args.project,
    env: process.env,
    variables,
  });
  if (requireProject && !resolved.project) {
    throw new Error(
      '--project <number> is required. Set --project, DCNESS_PROJECT_NUMBER, '
        + 'or repo variable DCNESS_PROJECT_NUMBER.',
    );
  }
  return resolved;
}

function normalizeRepoName(value) {
  if (!value) return null;
  if (typeof value === 'object') {
    return normalizeRepoName(
      value.nameWithOwner
        ?? value.fullName
        ?? value.full_name
        ?? value.url
        ?? value.name,
    );
  }
  const text = String(value);
  const githubUrl = text.match(/^https:\/\/github\.com\/([^/]+\/[^/#?]+)/);
  return githubUrl ? githubUrl[1] : text;
}

function ensureLabel(repo, name) {
  const [color, description] = LIFECYCLE_LABEL_META[name];
  if (!color || !description) {
    throw new Error(`unknown lifecycle label: ${name}`);
  }
  const create = gh(
    ['label', 'create', name, '--color', color, '--description', description, '--repo', repo],
    { allowFailure: true },
  );
  if (create !== null) return;
  gh(['label', 'edit', name, '--color', color, '--description', description, '--repo', repo]);
}

function fieldByName(fields, name) {
  return asArray(fields).find((field) => field?.name === name);
}

function optionByName(field, name) {
  return asArray(field?.options).find((option) => option?.name === name);
}

function itemRepositoryName(item) {
  const content = item?.content ?? item;
  const fromRepository = normalizeRepoName(content?.repository ?? item?.repository);
  if (fromRepository) return fromRepository;

  const url = content?.url ?? item?.url;
  const match = typeof url === 'string'
    ? url.match(/^https:\/\/github\.com\/([^/]+\/[^/]+)\/issues\/\d+/)
    : null;
  return match ? match[1] : null;
}

export function findProjectItem(itemsInput, target) {
  const items = asArray(itemsInput);
  const targetNumber = Number(typeof target === 'object' ? target.number : target);
  const targetRepo = normalizeRepoName(typeof target === 'object' ? target.repo : null);
  return items.find((item) => {
    const content = item?.content ?? item;
    const itemNumber = Number(content?.number ?? item?.number);
    if (itemNumber !== targetNumber) return false;
    if (!targetRepo) return true;
    return itemRepositoryName(item) === targetRepo;
  });
}

function scalarFieldValue(value) {
  if (value && typeof value === 'object') {
    return value.name ?? value.value ?? value.text ?? value.title ?? null;
  }
  return value ?? null;
}

export function projectItemFieldValue(item, fieldName) {
  const topLevelKeys = {
    Status: 'status',
    IssueType: 'issueType',
    Priority: 'priority',
  };
  const topLevelKey = topLevelKeys[fieldName];
  if (topLevelKey && Object.prototype.hasOwnProperty.call(item ?? {}, topLevelKey)) {
    return scalarFieldValue(item[topLevelKey]);
  }
  const fieldValues = asArray(item?.fieldValues ?? item?.field_values);
  const value = fieldValues.find((entry) => entry?.field?.name === fieldName || entry?.name === fieldName);
  return value?.name ?? value?.value ?? value?.text ?? value?.optionName ?? null;
}

export function projectItemSummary(item) {
  const content = item?.content ?? item;
  const rawNumber = content?.number ?? item?.number;
  const parsedNumber = rawNumber === null || rawNumber === undefined || rawNumber === ''
    ? null
    : Number(rawNumber);
  return {
    repo: itemRepositoryName(item),
    number: Number.isInteger(parsedNumber) ? parsedNumber : null,
    title: String(content?.title ?? item?.title ?? '<untitled>'),
    url: content?.url ?? item?.url ?? null,
    status: projectItemFieldValue(item, 'Status'),
    issueType: projectItemFieldValue(item, 'IssueType'),
    priority: projectItemFieldValue(item, 'Priority'),
  };
}

export function summarizeBoard(itemsInput) {
  const summary = { inProgress: [], todo: [], done: [] };
  for (const item of asArray(itemsInput)) {
    const status = projectItemFieldValue(item, 'Status');
    const entry = projectItemSummary(item);
    if (status === 'In progress') summary.inProgress.push(entry);
    if (status === 'Todo') summary.todo.push(entry);
    if (status === 'Done') summary.done.push(entry);
  }
  return summary;
}

function issueNumber(issue) {
  const number = Number(issue?.number);
  return Number.isInteger(number) ? number : Number.MAX_SAFE_INTEGER;
}

function priorityMeta(body) {
  const priority = parseField(body, 'Priority');
  const rank = PROJECT_FIELDS.Priority.indexOf(priority);
  if (rank === -1) {
    return { priority: null, priorityRank: PROJECT_FIELDS.Priority.length, priorityMissing: true };
  }
  return { priority, priorityRank: rank, priorityMissing: false };
}

function epicSlugMeta(names) {
  const matches = names
    .map((name) => {
      const match = String(name).match(/^epic-(\d+)-[a-z0-9][a-z0-9-]*$/);
      if (!match) return null;
      return { epicSlugLabel: name, epicNumber: Number(match[1]) };
    })
    .filter(Boolean)
    .sort((a, b) => a.epicNumber - b.epicNumber || a.epicSlugLabel.localeCompare(b.epicSlugLabel));
  return matches[0] ?? { epicSlugLabel: null, epicNumber: null };
}

function normalizeNextCandidate(issue) {
  const names = labelNames(issue?.labels);
  const issueType = names.find((name) => ISSUE_TYPE_LABELS.includes(name)) ?? null;
  const priority = priorityMeta(issue?.body);
  const epicSlug = epicSlugMeta(names);
  const parentIssueNumbers = parsePartOfIssueNumbers(issue?.body).numbers;
  return {
    number: issueNumber(issue),
    title: String(issue?.title ?? '<untitled>'),
    url: issue?.url ?? null,
    issueType,
    labels: names,
    inProgress: names.includes(IN_PROGRESS_LABEL),
    parentIssueNumbers,
    subTasks: [],
    ...priority,
    ...epicSlug,
  };
}

function byIssueNumber(a, b) {
  return a.number - b.number;
}

function byPriorityThenNumber(a, b) {
  return a.priorityRank - b.priorityRank || byIssueNumber(a, b);
}

function groupStoryCandidates(stories) {
  const bySlug = new Map();
  for (const story of stories) {
    const key = story.epicSlugLabel ?? '';
    if (!bySlug.has(key)) {
      bySlug.set(key, {
        epicSlugLabel: story.epicSlugLabel,
        epicNumber: story.epicNumber,
        items: [],
      });
    }
    bySlug.get(key).items.push(story);
  }
  return [...bySlug.values()]
    .map((group) => ({ ...group, items: group.items.sort(byIssueNumber) }))
    .sort((a, b) => {
      if (a.epicSlugLabel === null && b.epicSlugLabel !== null) return 1;
      if (a.epicSlugLabel !== null && b.epicSlugLabel === null) return -1;
      return (a.epicNumber ?? Number.MAX_SAFE_INTEGER) - (b.epicNumber ?? Number.MAX_SAFE_INTEGER)
        || String(a.epicSlugLabel ?? '').localeCompare(String(b.epicSlugLabel ?? ''));
    });
}

export function selectNextCandidates(issuesInput) {
  const candidates = asArray(issuesInput)
    .map(normalizeNextCandidate)
    .filter((issue) => Number.isInteger(issue.number));

  const l1 = candidates.filter((issue) => issue.inProgress).sort(byIssueNumber);
  const l1Numbers = new Set(l1.map((issue) => issue.number));
  const remaining = candidates.filter((issue) => !l1Numbers.has(issue.number));
  const l1ByNumber = new Map(l1.map((issue) => [issue.number, issue]));
  const subTaskItems = remaining.filter((issue) => issue.issueType === 'subTask').sort(byIssueNumber);
  const attachedSubTaskNumbers = new Set();

  for (const subTask of subTaskItems) {
    const parent = subTask.parentIssueNumbers
      .map((number) => l1ByNumber.get(number))
      .find(Boolean);
    if (!parent) continue;
    parent.subTasks.push(subTask);
    attachedSubTaskNumbers.add(subTask.number);
  }

  const excluded = {
    epic: remaining.filter((issue) => issue.issueType === 'epic').sort(byIssueNumber),
    subTask: subTaskItems.filter((issue) => !attachedSubTaskNumbers.has(issue.number)),
  };
  const workItems = remaining.filter(
    (issue) => issue.issueType && !['epic', 'subTask'].includes(issue.issueType),
  );
  // story 는 priority 와 무관하게 소속 epic 의 설계 phase 로 다음 액션이 결정된다(설계 전이면
  // impl 후보가 아니라 /design). 그래서 blocker/critical 이어도 L2 긴급으로 승격하지 않고 항상
  // L3 phase-aware 그룹으로 흘려보낸다 — 승격하면 phase 판정을 우회해 설계 전 story 를 impl 로 오도.
  const l2 = workItems
    .filter((issue) => issue.issueType !== 'story' && issue.priorityRank <= 1)
    .sort(byPriorityThenNumber);
  const l2Numbers = new Set(l2.map((issue) => issue.number));
  const l3Items = workItems.filter((issue) => !l2Numbers.has(issue.number));

  return {
    l1,
    l2,
    l3: {
      storyGroups: groupStoryCandidates(l3Items.filter((issue) => issue.issueType === 'story')),
      feature: l3Items.filter((issue) => issue.issueType === 'feature').sort(byPriorityThenNumber),
      task: l3Items.filter((issue) => issue.issueType === 'task').sort(byPriorityThenNumber),
      bug: l3Items.filter((issue) => issue.issueType === 'bug').sort(byPriorityThenNumber),
    },
    excluded,
  };
}

function projectItemIssueType(item) {
  return projectItemFieldValue(item, 'IssueType');
}

function setProjectSingleSelect({ projectId, itemId, fields, fieldName, optionName }) {
  const field = fieldByName(fields, fieldName);
  const option = optionByName(field, optionName);
  if (!field?.id || !option?.id) {
    throw new Error(`Project ${fieldName}=${optionName} option id not found.`);
  }
  gh([
    'project',
    'item-edit',
    '--project-id',
    field.projectId ?? projectId,
    '--id',
    itemId,
    '--field-id',
    field.id,
    '--single-select-option-id',
    option.id,
  ]);
}

export function planRegistration({
  item = null,
  fields,
  issueType,
  expectedStatus = 'Todo',
  expectedPriority = 'major',
  preserveExisting = false,
}) {
  if (!issueType) {
    throw new Error('issueType is required for Project registration.');
  }
  validateExpectedValue({ fieldName: 'IssueType', expected: issueType });
  validateExpectedValue({ fieldName: 'Status', expected: expectedStatus });
  validateExpectedValue({ fieldName: 'Priority', expected: expectedPriority });

  // preservable: Status/Priority 는 사용자가 triage 하는 lifecycle 이라 백필 시 보존 대상.
  // IssueType 은 이슈의 정체성(epic/story)이라 preserve 모드여도 항상 drift 교정.
  const desired = [
    { fieldName: 'Status', optionName: expectedStatus, preservable: true },
    { fieldName: 'IssueType', optionName: issueType, preservable: false },
    { fieldName: 'Priority', optionName: expectedPriority, preservable: true },
  ];

  const sets = [];
  for (const { fieldName, optionName, preservable } of desired) {
    const field = fieldByName(fields, fieldName);
    const option = field ? optionByName(field, optionName) : null;
    if (!field?.id || !option?.id) {
      throw new Error(`Project ${fieldName}=${optionName} option id not found.`);
    }
    const current = item ? projectItemFieldValue(item, fieldName) : null;
    const currentEmpty = current === null || current === undefined || current === '';
    // preserveExisting (백필): 사용자가 triage 한 기존 값(In progress/Done/priority)은
    // 덮지 않고, 비어있는 필드(부분 등록 실패 잔여)만 채운다. 기본(초기 등록)은 drift 교정.
    const needsSet = (preserveExisting && preservable) ? currentEmpty : current !== optionName;
    if (needsSet) {
      sets.push({
        fieldName,
        optionName,
        fieldId: field.id,
        optionId: option.id,
      });
    }
  }

  return { needsAdd: !item, sets };
}

// register-issue 검증 기대값을 *필드 단위*로 결정한다 (#669 백필).
// preserve 모드라도, 완화('any')는 "원래 값이 있어 의도적으로 보존한 필드"에만 적용한다.
// 원래 비어있던 필드는 채우기 대상이므로 strict 검증 유지 → apply 실패/부분 백필을 잡는다.
// item 이 없으면(신규 add) 보존 대상이 없으니 전부 strict.
export function resolveValidationExpectations({
  item = null,
  preserveExisting = false,
  expectedStatus = 'Todo',
  expectedPriority = 'major',
}) {
  const fieldWasSet = (fieldName) => {
    const current = item ? projectItemFieldValue(item, fieldName) : null;
    return !(current === null || current === undefined || current === '');
  };
  return {
    validateStatus: (preserveExisting && fieldWasSet('Status')) ? 'any' : expectedStatus,
    validatePriority: (preserveExisting && fieldWasSet('Priority')) ? 'any' : expectedPriority,
  };
}

function printBootstrapRecovery({ repo, owner, project }) {
  console.error('[dcness-project] recovery commands:');
  console.error(`  gh project create --owner ${owner} --title "dcNess" --format json`);
  console.error(`  gh project link ${project || '<project-number>'} --owner ${owner} --repo ${repo.split('/')[1]}`);
  console.error(
    `  node scripts/github_project_lifecycle.mjs bootstrap --repo ${repo} --owner ${owner} --project ${project || '<project-number>'} --apply`,
  );
}

function commandBootstrap(args) {
  const { repo, owner, project: projectNumber } = resolveProjectCoordinates(args);
  const apply = Boolean(args.apply);

  const labels = gh(['label', 'list', '--repo', repo, '--limit', '200', '--json', 'name'], { json: true });
  const labelValidation = validateLifecycleLabels(labels);
  if (!labelValidation.ok) {
    console.error(`[dcness-project] missing repo labels: ${labelValidation.missingLabels.join(', ')}`);
    if (apply) {
      for (const label of labelValidation.missingLabels) ensureLabel(repo, label);
      console.error('[dcness-project] repo labels created/updated.');
    }
  }

  if (!projectNumber) {
    console.error('[dcness-project] Project number is required for field validation.');
    printBootstrapRecovery({ repo, owner, project: null });
    return 1;
  }

  const fields = gh(
    ['project', 'field-list', projectNumber, '--owner', owner, '--format', 'json'],
    { json: true },
  );
  const fieldValidation = validateProjectFields(fields);
  if (!fieldValidation.ok) {
    console.error(`[dcness-project] missing fields: ${fieldValidation.missingFields.join(', ') || '-'}`);
    for (const miss of fieldValidation.missingOptions) {
      console.error(`[dcness-project] missing option: ${miss.field}=${miss.option}`);
    }
    if (apply) {
      for (const fieldName of fieldValidation.missingFields) {
        gh([
          'project',
          'field-create',
          projectNumber,
          '--owner',
          owner,
          '--name',
          fieldName,
          '--data-type',
          'SINGLE_SELECT',
          '--single-select-options',
          PROJECT_FIELDS[fieldName].join(','),
        ]);
        console.error(`[dcness-project] created Project field: ${fieldName}`);
      }
      if (fieldValidation.missingOptions.length > 0) {
        console.error('[dcness-project] existing Project fields with missing options need manual repair.');
      }
    } else {
      printBootstrapRecovery({ repo, owner, project: projectNumber });
    }
  }

  const finalLabels = apply
    ? gh(['label', 'list', '--repo', repo, '--limit', '200', '--json', 'name'], { json: true })
    : labels;
  const finalFields = apply && fieldValidation.missingFields.length
    ? gh(['project', 'field-list', projectNumber, '--owner', owner, '--format', 'json'], { json: true })
    : fields;
  const ok = validateLifecycleLabels(finalLabels).ok && validateProjectFields(finalFields).ok;
  console.log(ok ? '[dcness-project] bootstrap PASS' : '[dcness-project] bootstrap FAIL');
  return ok ? 0 : 1;
}

function projectContext(args) {
  const { repo, owner, project: projectNumber } = resolveProjectCoordinates(args, { requireProject: true });
  const project = gh(['project', 'view', projectNumber, '--owner', owner, '--format', 'json'], { json: true });
  const fields = gh(['project', 'field-list', projectNumber, '--owner', owner, '--format', 'json'], { json: true });
  return { repo, owner, projectNumber, project, fields };
}

function projectCoordinates(args) {
  const { repo, owner, project: projectNumber } = resolveProjectCoordinates(args);
  return { repo, owner, projectNumber };
}

function warnProjectMirror(message) {
  console.error(`[dcness-project] WARN: ${message}`);
}

function loadProjectMirrorContext({ owner, projectNumber }) {
  if (!projectNumber) {
    return { available: false, project: null, fields: null };
  }
  try {
    const project = gh(['project', 'view', projectNumber, '--owner', owner, '--format', 'json'], { json: true });
    const fields = gh(['project', 'field-list', projectNumber, '--owner', owner, '--format', 'json'], { json: true });
    return { available: true, project, fields };
  } catch (error) {
    warnProjectMirror(`Project ${projectNumber} mirror unavailable: ${error.message}`);
    return { available: false, project: null, fields: null };
  }
}

function getProjectItemForMirror({ owner, projectNumber, repo, issueNumber }) {
  try {
    const item = getProjectItem({ owner, projectNumber, repo, issueNumber });
    if (!item?.id) {
      warnProjectMirror(`issue ${repo ?? '<unknown-repo>'}#${issueNumber}: Project item missing in Project ${projectNumber}.`);
      return null;
    }
    return item;
  } catch (error) {
    warnProjectMirror(`issue ${repo ?? '<unknown-repo>'}#${issueNumber}: Project item lookup failed in Project ${projectNumber}: ${error.message}`);
    return null;
  }
}

function reportProjectStatusForMirror({
  owner,
  projectNumber,
  repo,
  issueNumber,
  expectedStatus,
  apply = false,
  mirrorContext = undefined,
}) {
  if (!projectNumber) {
    console.log('[dcness-project] Project 좌표 없음 — Status board update skipped; issue/label state is SSOT.');
    return;
  }

  const { available, project, fields } = mirrorContext ?? loadProjectMirrorContext({ owner, projectNumber });
  if (!available) return;

  const item = getProjectItemForMirror({ owner, projectNumber, repo, issueNumber });
  if (!item?.id) return;

  const actual = projectItemFieldValue(item, 'Status');
  if (actual === expectedStatus) {
    console.log(`issue ${repo ?? '<unknown-repo>'}#${issueNumber}: Status=${expectedStatus}`);
    return;
  }

  const drift = statusDriftMessage({
    repo,
    issueNumber,
    expected: expectedStatus,
    actual,
  });
  if (!apply) {
    warnProjectMirror(drift);
    return;
  }

  try {
    setProjectSingleSelect({
      projectId: project.id,
      itemId: item.id,
      fields,
      fieldName: 'Status',
      optionName: expectedStatus,
    });
    console.log(`issue ${repo ?? '<unknown-repo>'}#${issueNumber}: Status=${expectedStatus}`);
  } catch (error) {
    warnProjectMirror(`issue ${repo ?? '<unknown-repo>'}#${issueNumber}: Project Status mirror failed: ${error.message}`);
  }
}

function getIssue(repo, issueNumber) {
  return gh(['issue', 'view', String(issueNumber), '--repo', repo, '--json', 'number,labels,state,url'], { json: true });
}

function issueHasLabel(issue, labelName) {
  return labelNames(issue?.labels).includes(labelName);
}

function addIssueLabel({ repo, issueNumber, labelName }) {
  gh(['issue', 'edit', String(issueNumber), '--repo', repo, '--add-label', labelName]);
}

function removeIssueLabel({ repo, issueNumber, labelName }) {
  gh(['issue', 'edit', String(issueNumber), '--repo', repo, '--remove-label', labelName]);
}

function getProjectItems({ owner, projectNumber }) {
  return gh(
    ['project', 'item-list', String(projectNumber), '--owner', owner, '--format', 'json', '--limit', '1000'],
    { json: true },
  );
}

function getProjectItem({ owner, projectNumber, repo, issueNumber }) {
  const items = getProjectItems({ owner, projectNumber });
  return findProjectItem(items, { repo, number: issueNumber });
}

function formatNextCandidate(entry) {
  const ref = entry.number ? `#${entry.number}` : '<no-issue-number>';
  const priority = entry.priorityMissing ? 'priority 미기재' : entry.priority;
  const meta = [entry.issueType, priority].filter(Boolean).join(', ');
  const metaText = meta ? ` (${meta})` : '';
  const urlText = entry.url ? ` ${entry.url}` : '';
  return `- ${ref} ${entry.title}${metaText}${urlText}`;
}

function formatNextCandidateLines(entry) {
  const lines = [formatNextCandidate(entry)];
  for (const subTask of asArray(entry?.subTasks)) {
    lines.push(`  ${formatNextCandidate(subTask)}`);
  }
  return lines;
}

function formatFlatNextSection(title, entries, { emptyText = '없음', limit = null } = {}) {
  const visible = limit ? entries.slice(0, limit) : entries;
  const lines = [`## ${title}`];
  if (visible.length === 0) {
    lines.push(`- ${emptyText}`);
  } else {
    lines.push(...visible.flatMap(formatNextCandidateLines));
  }
  if (limit && entries.length > limit) {
    lines.push(`- 외 ${entries.length - limit}건`);
  }
  return lines.join('\n');
}

function resolveProjectRoot() {
  try {
    return execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
  } catch {
    return process.cwd();
  }
}

function sameRepo(a, b) {
  return Boolean(a) && Boolean(b) && String(a).trim().toLowerCase() === String(b).trim().toLowerCase();
}

// git remote URL 에서 OWNER/REPO slug 파싱 (https / ssh / `.git` 접미사 / 후행 슬래시 모두). 없으면 null.
export function parseRepoSlug(url) {
  const match = String(url).trim().match(/[:/]([^/:]+)\/([^/]+?)(?:\.git)?\/?$/);
  return match ? `${match[1]}/${match[2]}` : null;
}

// 현재 git checkout 의 origin remote slug. git 에서 직접 뽑으므로 `GH_REPO`/`gh` 기본 repo
// override 에 영향받지 않는다 (로컬 파일이 *어느 repo 것인지*의 진본). 확인 불가면 null.
function gitRemoteSlugOrNull() {
  try {
    const url = execFileSync('git', ['config', '--get', 'remote.origin.url'], { encoding: 'utf8' }).trim();
    return parseRepoSlug(url);
  } catch {
    return null;
  }
}

// 로컬 `docs/epics/...` 산출물은 *현재 git checkout* 의 repo 를 서술한다. 그래서 대상 repo
// (issue 출처)가 현재 checkout 의 git remote 와 일치할 때만 로컬 phase 판정을 쓴다. 로컬 식별을
// gh 가 아니라 git 에서 뽑는 이유: `gh repo view` 는 `GH_REPO`/기본 repo override 를 따르므로
// 다른 checkout/repo 밖에서도 대상 repo 를 반환해 가드를 우회시킨다. 불일치/미확인이면 보류.
export function shouldUseLocalPhaseRoot(targetRepo, localRepoSlug) {
  return sameRepo(targetRepo, localRepoSlug);
}

// next-work 는 GitHub issue 로 이미 등록된 story 를 나열하므로, 로컬 산출물이 없어도
// (repo 밖 실행 / stale checkout / 대상 repo != 로컬 checkout) story 자체는 존재한다.
// 그래서 로컬 근거가 없을 때(root 부재)와 epic_phase 의 'spec'(stories.md 부재)은 여기선
// "스펙 미작성" 이 아니라 "로컬 산출물 확인 불가 → 판정 보류" 로 해석한다 (오탐으로 /design 단정 X).
function epicGroupNextAction(epicSlugLabel, root) {
  if (!epicSlugLabel) return { kind: 'unlabeled' };
  if (!root) return { kind: 'unresolved' };
  const phaseInfo = epicPhase(join(root, 'docs', 'epics', epicSlugLabel));
  if (phaseInfo.phase === 'impl') return { kind: 'impl', label: phaseInfo.label };
  if (phaseInfo.phase === 'design') return { kind: 'design', label: phaseInfo.label };
  return { kind: 'unresolved' };
}

function storyGroupHeaderLine(epicSlugLabel, action) {
  switch (action.kind) {
    case 'impl':
      return `- ${epicSlugLabel} — ${action.label} → story impl 후보 (\`/impl\`)`;
    case 'design':
      return `- ${epicSlugLabel} — ${action.label} → 다음 액션 \`/design docs/epics/${epicSlugLabel}\` (아래 story 는 아직 impl 후보 아님)`;
    case 'unlabeled':
      return '- 미분류 story — epic 라벨 없음 → 판정 보류';
    default:
      return `- ${epicSlugLabel} — 설계 산출물 로컬 확인 불가 → 판정 보류 (\`/design\`/\`/impl\` 미결)`;
  }
}

export function formatStoryGroups(groups, root = null) {
  const lines = ['## L3 Story'];
  if (groups.length === 0) {
    lines.push('- 후보 없음');
    return lines.join('\n');
  }
  // root 부재 = 로컬 checkout 이 대상 repo 를 서술하지 않음 (--repo 불일치 / repo 밖). 이유를 밝혀 보류.
  if (!root && groups.some((group) => group.epicSlugLabel)) {
    lines.push('- 참고: 대상 repo 가 현재 로컬 checkout 과 달라 설계 phase(`/design` vs `/impl`) 판정을 보류한다.');
  }
  let anyDesignComplete = false;
  for (const group of groups) {
    const action = epicGroupNextAction(group.epicSlugLabel, root);
    if (action.kind === 'impl') anyDesignComplete = true;
    lines.push(storyGroupHeaderLine(group.epicSlugLabel, action));
    for (const item of group.items) {
      lines.push(`  ${formatNextCandidate(item)}`);
    }
  }
  // 각주는 "설계 산출물이 존재한다" 를 전제하므로 설계 완료 epic 이 하나라도 있을 때만 붙인다.
  if (anyDesignComplete) {
    lines.push('- 참고: 설계 완료 epic 의 story 구현 순서 진본은 epic 설계 산출물의 구현 순서 섹션이다.');
  }
  return lines.join('\n');
}

function formatNextWorkReport({ repo, candidates, limit, root = null }) {
  return [
    `[dcness-next-work] repo=${repo}`,
    '[dcness-next-work] read-only: GitHub issue/label 상태를 변경하지 않았습니다.',
    '',
    formatFlatNextSection('L1 이어하기 (in-progress)', candidates.l1),
    '',
    formatFlatNextSection('L2 긴급 끼어들기 (blocker/critical)', candidates.l2, {
      emptyText: '긴급 후보 없음',
      limit,
    }),
    '',
    formatStoryGroups(candidates.l3.storyGroups, root),
    '',
    formatFlatNextSection('L3 Feature', candidates.l3.feature, { emptyText: '후보 없음', limit }),
    '',
    formatFlatNextSection('L3 Task', candidates.l3.task, { emptyText: '후보 없음', limit }),
    '',
    formatFlatNextSection('L3 Bug', candidates.l3.bug, { emptyText: '후보 없음', limit }),
  ].join('\n');
}

function localNextFallbackLines() {
  const lines = [];
  if (existsSync('docs/index.md')) lines.push('- 로컬 포인터: docs/index.md');
  if (existsSync('docs/epics')) lines.push('- 로컬 epic 산출물: docs/epics/');
  if (existsSync('.dcness-work')) lines.push('- 로컬 작업 메모: .dcness-work/');
  return lines.length ? lines : ['- 로컬 대안 경로 없음'];
}

function getOpenIssues(repo) {
  return gh([
    'issue',
    'list',
    '--state',
    'open',
    '--repo',
    repo,
    '--json',
    'number,title,labels,body,url,createdAt',
    '--limit',
    '1000',
  ], { json: true, allowFailure: true });
}

function commandNext(args) {
  const repo = detectRepo(args.repo);
  const issues = getOpenIssues(repo);
  if (!issues) {
    console.log(`[dcness-next-work] GitHub issue 조회 실패: repo=${repo}`);
    console.log('[dcness-next-work] read-only: 외부 상태 변경 없음.');
    console.log('[dcness-next-work] 로컬 대안:');
    console.log(localNextFallbackLines().join('\n'));
    return 0;
  }
  const limit = Number.isInteger(Number(args.limit)) && Number(args.limit) > 0
    ? Number(args.limit)
    : 5;
  const candidates = selectNextCandidates(issues);
  // 로컬 git checkout 이 대상 repo(issue 출처)를 서술할 때만 로컬 산출물로 phase 를 판정한다.
  // `--repo`/`GH_REPO` 로 다른 repo 를 가리키면 로컬 파일이 무관하므로 root 없이 판정을 보류한다.
  const root = shouldUseLocalPhaseRoot(repo, gitRemoteSlugOrNull()) ? resolveProjectRoot() : null;
  console.log(formatNextWorkReport({ repo, candidates, limit, root }));
  return 0;
}

function commandValidateIssue(args) {
  if (!args.issue) throw new Error('--issue <number> is required.');
  const { repo, owner, projectNumber } = projectCoordinates(args);
  const issue = getIssue(repo, args.issue);
  const labelValidation = validateLifecycleIssueLabels({
    issueNumber: issue.number,
    state: issue.state,
    labels: issue.labels,
  });
  for (const message of labelValidation.messages) console.log(message);

  if (!projectNumber) {
    console.log('[dcness-project] Project 좌표 없음 — label drift 만 검사했습니다.');
    return labelValidation.ok ? 0 : 1;
  }

  const { available } = loadProjectMirrorContext({ owner, projectNumber });
  if (!available) return labelValidation.ok ? 0 : 1;

  const item = getProjectItemForMirror({ owner, projectNumber, repo, issueNumber: args.issue });
  if (!item) return labelValidation.ok ? 0 : 1;

  const validation = validateIssueProjectRegistration({
    repo,
    issueNumber: issue.number,
    item,
    labels: issue.labels,
    expectedStatus: args['expected-status'] ?? 'any',
    expectedIssueType: args['expected-issue-type'] ?? null,
    expectedPriority: args['expected-priority'] ?? 'any',
  });
  for (const message of validation.messages) {
    warnProjectMirror(message);
  }
  return labelValidation.ok ? 0 : 1;
}

function commandStartWork(args) {
  if (!args.issue) throw new Error('--issue <number> is required.');
  const { repo, owner, projectNumber } = projectCoordinates(args);
  const issue = getIssue(repo, args.issue);
  const hasInProgressLabel = issueHasLabel(issue, IN_PROGRESS_LABEL);
  if (!args.apply) {
    let ok = hasInProgressLabel;
    console.log(
      hasInProgressLabel
        ? `issue #${args.issue}: label ${IN_PROGRESS_LABEL} already present`
        : `issue #${args.issue}: missing label ${IN_PROGRESS_LABEL}`,
    );
    if (projectNumber) {
      const { available } = loadProjectMirrorContext({ owner, projectNumber });
      if (available) {
        const item = getProjectItemForMirror({ owner, projectNumber, repo, issueNumber: args.issue });
        if (item?.id) {
          const actual = projectItemFieldValue(item, 'Status');
          if (actual === 'In progress') {
            console.log(`issue ${repo}#${args.issue}: Status=In progress`);
          } else {
            warnProjectMirror(statusDriftMessage({
              repo,
              issueNumber: args.issue,
              expected: 'In progress',
              actual,
            }));
          }
        }
      }
    } else {
      console.log('[dcness-project] Project 좌표 없음 — label 상태만 검사했습니다.');
    }
    console.log(`Run again with --apply to add label ${IN_PROGRESS_LABEL} and best-effort mirror Project Status when configured.`);
    return ok ? 0 : 1;
  }
  ensureLabel(repo, IN_PROGRESS_LABEL);
  if (!hasInProgressLabel) {
    addIssueLabel({ repo, issueNumber: args.issue, labelName: IN_PROGRESS_LABEL });
  }
  console.log(`issue #${args.issue}: label ${IN_PROGRESS_LABEL}`);
  reportProjectStatusForMirror({
    owner,
    projectNumber,
    repo,
    issueNumber: args.issue,
    expectedStatus: 'In progress',
    apply: true,
  });
  return 0;
}

function commandRegisterIssue(args) {
  if (!args.issue) throw new Error('--issue <number> is required.');
  if (!args['issue-type']) throw new Error('--issue-type <epic|story|...> is required.');
  const { repo, owner, projectNumber, project, fields } = projectContext(args);
  const issueType = args['issue-type'];
  const expectedStatus = args.status ?? 'Todo';
  const expectedPriority = args.priority ?? 'major';
  // --preserve-existing (백필): 보드에 이미 있는 item 의 triage 상태를 보존한다 (#669 회귀 가드).
  const preserveExisting = Boolean(args['preserve-existing']);
  const issue = getIssue(repo, args.issue);

  let item = getProjectItem({ owner, projectNumber, repo, issueNumber: issue.number });
  // 검증 완화는 *필드 단위* + *apply 전 원본 item* 기준 — 원래 값이 있던 필드만 보존('any'),
  // 원래 비어있던 필드는 strict 로 두어 채우기 실패/부분 백필을 잡는다. IssueType 은 항상 strict.
  const { validateStatus, validatePriority } = resolveValidationExpectations({
    item, preserveExisting, expectedStatus, expectedPriority,
  });
  // plan throws early if the board lacks a required field/option (incomplete board signal).
  const plan = planRegistration({ item, fields, issueType, expectedStatus, expectedPriority, preserveExisting });

  if (!args.apply) {
    if (!item) {
      console.log(`issue #${issue.number}: missing in Project ${projectNumber} (needs item-add).`);
    }
    const validation = validateIssueProjectRegistration({
      repo,
      issueNumber: issue.number,
      item: item ?? {},
      labels: issue.labels,
      expectedStatus: validateStatus,
      expectedIssueType: issueType,
      expectedPriority: validatePriority,
    });
    for (const message of validation.messages) console.log(message);
    console.log('Run again with --apply to register the issue and set Project fields.');
    // 채울 빈 필드는 strict 검증에서 drift 로 잡혀 validation.ok=false → pending 으로 보고된다.
    return item && validation.ok ? 0 : 1;
  }

  if (plan.needsAdd) {
    item = gh(
      ['project', 'item-add', String(projectNumber), '--owner', owner, '--url', issue.url, '--format', 'json'],
      { json: true },
    );
  }
  if (!item?.id) {
    throw new Error(`issue #${issue.number}: could not resolve Project item id after add.`);
  }
  for (const entry of plan.sets) {
    setProjectSingleSelect({
      projectId: project.id,
      itemId: item.id,
      fields,
      fieldName: entry.fieldName,
      optionName: entry.optionName,
    });
  }

  const verifyItem = getProjectItem({ owner, projectNumber, repo, issueNumber: issue.number }) ?? item;
  const validation = validateIssueProjectRegistration({
    repo,
    issueNumber: issue.number,
    item: verifyItem,
    labels: issue.labels,
    expectedStatus: validateStatus,
    expectedIssueType: issueType,
    expectedPriority: validatePriority,
  });
  for (const message of validation.messages) console.log(message);
  if (validation.ok) {
    // preserve 모드에서 기존 값을 보존했을 수 있으므로 실제 보드 값을 보고한다.
    const finalStatus = projectItemFieldValue(verifyItem, 'Status') ?? expectedStatus;
    const finalPriority = projectItemFieldValue(verifyItem, 'Priority') ?? expectedPriority;
    console.log(
      `issue #${issue.number}: Project registered (Status=${finalStatus}, IssueType=${issueType}, Priority=${finalPriority})`,
    );
  }
  return validation.ok ? 0 : 1;
}

function bodyFromArgs(args) {
  if (args['body-file']) return readFileSync(args['body-file'], 'utf8');
  if (args['body-env']) return process.env[args['body-env']] ?? '';
  if (args.body) return args.body;
  if (args.pr) {
    const pr = gh(prViewArgs({ pr: args.pr, repo: args.repo }), { json: true });
    const fromReferences = asArray(pr.closingIssuesReferences)
      .map((issue) => ({
        repo: normalizeRepoName(issue?.repository ?? issue?.repositoryNameWithOwner ?? args.repo),
        number: Number(issue?.number),
      }))
      .filter((issue) => Number.isInteger(issue.number));
    return `${pr.body ?? ''}\n${fromReferences.map((issue) => {
      const repoPrefix = issue.repo ? `${issue.repo}` : '';
      return `Closes ${repoPrefix}#${issue.number}`;
    }).join('\n')}`;
  }
  return '';
}

function commandPrMerged(args) {
  const body = bodyFromArgs(args);
  const { refs } = parseCompletionIssueRefs(body, args.repo);
  if (refs.length === 0) {
    console.log('[dcness-project] no completion issue candidates. Part of #N is not a Done signal.');
    return 0;
  }
  const { repo, owner, projectNumber } = projectCoordinates(args);
  const resolvedRefs = resolveCompletionRefsForProject(body, args.repo, repo);
  let mirrorContext;
  let mirrorContextLoaded = false;

  let failures = 0;
  for (const ref of resolvedRefs) {
    const labelRepo = ref.repo ?? repo;
    const issue = getIssue(labelRepo, ref.number);
    const hasInProgressLabel = issueHasLabel(issue, IN_PROGRESS_LABEL);
    if (args.apply) {
      if (hasInProgressLabel) {
        removeIssueLabel({ repo: labelRepo, issueNumber: ref.number, labelName: IN_PROGRESS_LABEL });
      }
      console.log(`issue ${labelRepo}#${ref.number}: label ${IN_PROGRESS_LABEL} removed`);
    } else if (hasInProgressLabel) {
      failures += 1;
      console.error(`issue ${labelRepo}#${ref.number}: label ${IN_PROGRESS_LABEL} should be removed after merge.`);
    } else {
      console.log(`issue ${labelRepo}#${ref.number}: label ${IN_PROGRESS_LABEL} absent`);
    }

    if (projectNumber && !mirrorContextLoaded) {
      mirrorContext = loadProjectMirrorContext({ owner, projectNumber });
      mirrorContextLoaded = true;
    }
    reportProjectStatusForMirror({
      owner,
      projectNumber,
      repo: labelRepo,
      issueNumber: ref.number,
      expectedStatus: 'Done',
      apply: Boolean(args.apply),
      mirrorContext,
    });
  }
  return failures === 0 ? 0 : 1;
}

function help() {
  console.log(`Usage:
  node scripts/github_project_lifecycle.mjs bootstrap --repo OWNER/REPO --owner OWNER --project N [--apply]
  node scripts/github_project_lifecycle.mjs next-work [--repo OWNER/REPO] [--limit N]
  node scripts/github_project_lifecycle.mjs validate-issue --repo OWNER/REPO [--owner OWNER] [--project N] --issue N [--expected-status Todo|In progress|Done|any] [--expected-issue-type TYPE] [--expected-priority PRIORITY]
  node scripts/github_project_lifecycle.mjs start-work --repo OWNER/REPO [--owner OWNER] [--project N] --issue N [--apply]
  node scripts/github_project_lifecycle.mjs register-issue --repo OWNER/REPO --owner OWNER --project N --issue N --issue-type epic|story|... [--status Todo] [--priority major] [--preserve-existing] [--apply]
  node scripts/github_project_lifecycle.mjs pr-merged --repo OWNER/REPO [--owner OWNER] [--project N] (--pr N | --body-file FILE | --body-env ENV) [--apply]
`);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const [command] = args._;
  if (!command || args.help) {
    help();
    return 0;
  }
  switch (command) {
    case 'bootstrap':
      return commandBootstrap(args);
    case 'next-work':
      return commandNext(args);
    case 'validate-issue':
      return commandValidateIssue(args);
    case 'start-work':
      return commandStartWork(args);
    case 'register-issue':
      return commandRegisterIssue(args);
    case 'pr-merged':
      return commandPrMerged(args);
    default:
      throw new Error(`unknown command: ${command}`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    process.exitCode = main();
  } catch (error) {
    console.error(`[dcness-project] ${error.message}`);
    process.exitCode = 1;
  }
}
