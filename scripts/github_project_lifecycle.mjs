#!/usr/bin/env node
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

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

export const ISSUE_TYPE_LABELS = Object.freeze(PROJECT_FIELDS.IssueType);
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

export function parseCompletionIssueRefs(body, defaultRepo = null) {
  const text = String(body ?? '');
  const refs = [];
  const seen = new Set();
  const actionRegex = new RegExp(String.raw`\b(${COMPLETION_KEYWORD}|part\s+of)\b`, 'gi');
  const completionRegex = new RegExp(String.raw`^${COMPLETION_KEYWORD}$`, 'i');
  const referenceRegex = new RegExp(ISSUE_REFERENCE, 'g');

  for (const line of text.split(/\r?\n/)) {
    const actions = [...line.matchAll(actionRegex)];
    for (let index = 0; index < actions.length; index += 1) {
      const action = actions[index];
      const keyword = action[1];
      if (!completionRegex.test(keyword)) continue;

      const segmentStart = action.index + action[0].length;
      const segmentEnd = actions[index + 1]?.index ?? line.length;
      const trailerText = line.slice(segmentStart, segmentEnd);
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
  const [color, description] = ISSUE_TYPE_LABEL_META[name];
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
  const repo = detectRepo(args.repo);
  const owner = repoOwner(repo, args.owner);
  const apply = Boolean(args.apply);

  const labels = gh(['label', 'list', '--repo', repo, '--limit', '200', '--json', 'name'], { json: true });
  const labelValidation = validateIssueTypeLabels(labels);
  if (!labelValidation.ok) {
    console.error(`[dcness-project] missing repo labels: ${labelValidation.missingLabels.join(', ')}`);
    if (apply) {
      for (const label of labelValidation.missingLabels) ensureLabel(repo, label);
      console.error('[dcness-project] repo labels created/updated.');
    }
  }

  if (!args.project) {
    console.error('[dcness-project] Project number is required for field validation.');
    printBootstrapRecovery({ repo, owner, project: null });
    return 1;
  }

  const fields = gh(
    ['project', 'field-list', args.project, '--owner', owner, '--format', 'json'],
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
          args.project,
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
      printBootstrapRecovery({ repo, owner, project: args.project });
    }
  }

  const finalLabels = apply
    ? gh(['label', 'list', '--repo', repo, '--limit', '200', '--json', 'name'], { json: true })
    : labels;
  const finalFields = apply && fieldValidation.missingFields.length
    ? gh(['project', 'field-list', args.project, '--owner', owner, '--format', 'json'], { json: true })
    : fields;
  const ok = validateIssueTypeLabels(finalLabels).ok && validateProjectFields(finalFields).ok;
  console.log(ok ? '[dcness-project] bootstrap PASS' : '[dcness-project] bootstrap FAIL');
  return ok ? 0 : 1;
}

function projectContext(args) {
  const repo = detectRepo(args.repo);
  const owner = repoOwner(repo, args.owner);
  if (!args.project) throw new Error('--project <number> is required.');
  const project = gh(['project', 'view', args.project, '--owner', owner, '--format', 'json'], { json: true });
  const fields = gh(['project', 'field-list', args.project, '--owner', owner, '--format', 'json'], { json: true });
  return { repo, owner, project, fields };
}

function getIssue(repo, issueNumber) {
  return gh(['issue', 'view', String(issueNumber), '--repo', repo, '--json', 'number,labels,url'], { json: true });
}

function getProjectItem({ owner, projectNumber, repo, issueNumber }) {
  const items = gh(
    ['project', 'item-list', String(projectNumber), '--owner', owner, '--format', 'json', '--limit', '1000'],
    { json: true },
  );
  return findProjectItem(items, { repo, number: issueNumber });
}

function commandValidateIssue(args) {
  if (!args.issue) throw new Error('--issue <number> is required.');
  const { repo, owner } = projectContext(args);
  const issue = getIssue(repo, args.issue);
  const item = getProjectItem({ owner, projectNumber: args.project, repo, issueNumber: args.issue });

  if (!item) {
    console.error(`issue #${args.issue}: Project item missing in Project ${args.project}.`);
    return 1;
  }

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
    console.log(message);
  }
  return validation.ok ? 0 : 1;
}

function commandStartWork(args) {
  if (!args.issue) throw new Error('--issue <number> is required.');
  const { repo, owner, project, fields } = projectContext(args);
  const item = getProjectItem({ owner, projectNumber: args.project, repo, issueNumber: args.issue });
  if (!item?.id) {
    console.error(`issue #${args.issue}: Project item missing in Project ${args.project}.`);
    return 1;
  }
  if (!args.apply) {
    console.log(statusDriftMessage({
      repo,
      issueNumber: args.issue,
      expected: 'In progress',
      actual: projectItemFieldValue(item, 'Status'),
    }));
    console.log('Run again with --apply to set Status=In progress.');
    return 1;
  }
  setProjectSingleSelect({
    projectId: project.id,
    itemId: item.id,
    fields,
    fieldName: 'Status',
    optionName: 'In progress',
  });
  console.log(`issue #${args.issue}: Status=In progress`);
  return 0;
}

function commandRegisterIssue(args) {
  if (!args.issue) throw new Error('--issue <number> is required.');
  if (!args['issue-type']) throw new Error('--issue-type <epic|story|...> is required.');
  const { repo, owner, project, fields } = projectContext(args);
  const issueType = args['issue-type'];
  const expectedStatus = args.status ?? 'Todo';
  const expectedPriority = args.priority ?? 'major';
  // --preserve-existing (백필): 보드에 이미 있는 item 의 triage 상태를 보존한다 (#669 회귀 가드).
  const preserveExisting = Boolean(args['preserve-existing']);
  const issue = getIssue(repo, args.issue);

  let item = getProjectItem({ owner, projectNumber: args.project, repo, issueNumber: issue.number });
  // 검증 완화는 *필드 단위* + *apply 전 원본 item* 기준 — 원래 값이 있던 필드만 보존('any'),
  // 원래 비어있던 필드는 strict 로 두어 채우기 실패/부분 백필을 잡는다. IssueType 은 항상 strict.
  const { validateStatus, validatePriority } = resolveValidationExpectations({
    item, preserveExisting, expectedStatus, expectedPriority,
  });
  // plan throws early if the board lacks a required field/option (incomplete board signal).
  const plan = planRegistration({ item, fields, issueType, expectedStatus, expectedPriority, preserveExisting });

  if (!args.apply) {
    if (!item) {
      console.log(`issue #${issue.number}: missing in Project ${args.project} (needs item-add).`);
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
      ['project', 'item-add', String(args.project), '--owner', owner, '--url', issue.url, '--format', 'json'],
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

  const verifyItem = getProjectItem({ owner, projectNumber: args.project, repo, issueNumber: issue.number }) ?? item;
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
  const { repo, owner, project, fields } = projectContext(args);
  const resolvedRefs = resolveCompletionRefsForProject(body, args.repo, repo);

  let failures = 0;
  for (const ref of resolvedRefs) {
    const item = getProjectItem({
      owner,
      projectNumber: args.project,
      repo: ref.repo,
      issueNumber: ref.number,
    });
    if (!item?.id) {
      failures += 1;
      console.error(`issue ${ref.repo ?? '<unknown-repo>'}#${ref.number}: Project item missing in Project ${args.project}.`);
      continue;
    }
    const actual = projectItemFieldValue(item, 'Status');
    if (actual === 'Done') {
      console.log(`issue ${ref.repo ?? '<unknown-repo>'}#${ref.number}: Status=Done`);
      continue;
    }
    if (!args.apply) {
      failures += 1;
      console.error(statusDriftMessage({
        repo: ref.repo,
        issueNumber: ref.number,
        expected: 'Done',
        actual,
      }));
      continue;
    }
    setProjectSingleSelect({
      projectId: project.id,
      itemId: item.id,
      fields,
      fieldName: 'Status',
      optionName: 'Done',
    });
    console.log(`issue ${ref.repo ?? '<unknown-repo>'}#${ref.number}: Status=Done`);
  }
  return failures === 0 ? 0 : 1;
}

function help() {
  console.log(`Usage:
  node scripts/github_project_lifecycle.mjs bootstrap --repo OWNER/REPO --owner OWNER --project N [--apply]
  node scripts/github_project_lifecycle.mjs validate-issue --repo OWNER/REPO --owner OWNER --project N --issue N [--expected-status Todo|In progress|Done|any] [--expected-issue-type TYPE] [--expected-priority PRIORITY]
  node scripts/github_project_lifecycle.mjs start-work --repo OWNER/REPO --owner OWNER --project N --issue N [--apply]
  node scripts/github_project_lifecycle.mjs register-issue --repo OWNER/REPO --owner OWNER --project N --issue N --issue-type epic|story|... [--status Todo] [--priority major] [--preserve-existing] [--apply]
  node scripts/github_project_lifecycle.mjs pr-merged --repo OWNER/REPO --owner OWNER --project N (--pr N | --body-file FILE | --body-env ENV) [--apply]
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
