/**
 * design-variants 공용 파서.
 *
 * 화면·전이·여정·변형의 진본을 한 번만 읽어 세 생성기가 같은 모델을 쓴다.
 */
import {
  existsSync,
  readFileSync,
  readdirSync,
} from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const ENGINE_FILES = ['canvas.js', 'only-variant.js', 'report-size.js', 'show-ids.js'];
const SCREEN_HELPERS = ['only-variant.js', 'report-size.js', 'show-ids.js'];

export function parseCli(argv = process.argv.slice(2)) {
  const options = {
    projectRoot: process.cwd(),
    uxFlow: null,
    check: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--project-root') options.projectRoot = argv[++index];
    else if (arg === '--ux-flow') options.uxFlow = argv[++index];
    else if (arg === '--check') options.check = true;
    else throw new Error(`알 수 없는 인자: ${arg}`);
  }
  options.projectRoot = resolve(options.projectRoot);
  return options;
}

export function sha12(text) {
  return createHash('sha256').update(text).digest('hex').slice(0, 12);
}

export function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function walkForUxFlows(dir, found) {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) walkForUxFlows(path, found);
    else if (entry.name === 'ux-flow.md') found.push(path);
  }
}

function discoveredUxFlows(projectRoot) {
  const found = [];
  walkForUxFlows(join(projectRoot, 'docs', 'epics'), found);
  return found.sort();
}

export function resolveUxFlows(projectRoot, requested = null) {
  const found = discoveredUxFlows(projectRoot);
  if (requested) {
    const path = resolve(projectRoot, requested);
    if (!existsSync(path)) throw new Error(`ux-flow가 없습니다: ${relative(projectRoot, path)}`);
    return found.includes(path) ? found : [path];
  }
  if (found.length === 0) throw new Error('docs/epics/**/ux-flow.md를 찾지 못했습니다.');
  return found;
}

export function resolveUxFlow(projectRoot, requested = null) {
  if (requested) {
    const path = resolve(projectRoot, requested);
    if (!existsSync(path)) throw new Error(`ux-flow가 없습니다: ${relative(projectRoot, path)}`);
    return path;
  }
  const found = resolveUxFlows(projectRoot);
  if (found.length !== 1) {
    throw new Error(
      `ux-flow가 ${found.length}개입니다. --ux-flow로 대상을 지정하십시오:\n`
      + found.map(path => `  - ${relative(projectRoot, path)}`).join('\n'),
    );
  }
  return found[0];
}

function markdownSection(md, heading) {
  const lines = md.split('\n');
  let start = -1;
  let level = 0;
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^(#{1,6})\s+(.+?)\s*$/);
    if (match && match[2] === heading) {
      start = index + 1;
      level = match[1].length;
      break;
    }
  }
  if (start < 0) throw new Error(`이름 소스 절을 찾지 못했습니다: ${heading}`);
  let end = lines.length;
  for (let index = start; index < lines.length; index += 1) {
    const match = lines[index].match(/^(#{1,6})\s+/);
    if (match && match[1].length <= level) {
      end = index;
      break;
    }
  }
  return lines.slice(start, end);
}

function parseMarkdownTable(lines) {
  const rows = lines.filter(line => line.trim().startsWith('|')).map(line =>
    line.split('|').slice(1, -1).map(cell => cell.trim()));
  if (rows.length < 2) throw new Error('이름 소스 표가 비어 있습니다.');
  const headers = rows[0];
  return {
    headers,
    rows: rows.slice(2).filter(row => row.some(Boolean)),
  };
}

function resolveNameSource(projectRoot, uxFlowPath, contract) {
  const source = contract.nameSource;
  if (!source || !source.kind || !source.path) {
    throw new Error('journey contract의 nameSource.kind/path가 필요합니다.');
  }
  const sourcePath = resolve(dirname(uxFlowPath), source.path);
  if (!existsSync(sourcePath)) {
    throw new Error(`여정 이름 소스가 없습니다: ${relative(projectRoot, sourcePath)}`);
  }
  const text = readFileSync(sourcePath, 'utf8');
  const names = new Map();

  if (source.kind === 'table') {
    for (const key of ['section', 'idColumn', 'nameColumn']) {
      if (!source[key]) throw new Error(`table 이름 소스에 ${key}가 필요합니다.`);
    }
    const table = parseMarkdownTable(markdownSection(text, source.section));
    const idIndex = table.headers.indexOf(source.idColumn);
    const nameIndex = table.headers.indexOf(source.nameColumn);
    if (idIndex < 0 || nameIndex < 0) {
      throw new Error(
        `이름 소스 표에 ${source.idColumn}/${source.nameColumn} 열이 필요합니다.`,
      );
    }
    for (const row of table.rows) {
      const id = row[idIndex];
      const name = row[nameIndex];
      if (id && name) names.set(id, name);
    }
  } else if (source.kind === 'heading') {
    if (!source.headingPattern) {
      throw new Error('heading 이름 소스에 headingPattern이 필요합니다.');
    }
    const pattern = new RegExp(source.headingPattern);
    for (const line of text.split('\n')) {
      const heading = line.match(/^#{1,6}\s+(.+?)\s*$/);
      const matched = heading?.[1].match(pattern);
      if (matched?.groups?.id && matched.groups.name) {
        names.set(matched.groups.id, matched.groups.name);
      }
    }
  } else {
    throw new Error(`지원하지 않는 nameSource.kind: ${source.kind}`);
  }

  return {
    names,
    path: sourcePath,
    relativePath: relative(projectRoot, sourcePath),
    hash: sha12(text),
  };
}

function parseInventory(md) {
  const inventory = new Map();
  for (const line of md.split('\n')) {
    if (!line.trim().startsWith('|')) continue;
    const cells = line.split('|').slice(1, -1).map(cell => cell.trim());
    if (cells.length < 3 || /^[-:\s]+$/.test(cells[0])) continue;
    const pathCell = cells.find(cell => /screens\/[^`\s]+\.html/.test(cell));
    const matched = pathCell?.match(/screens\/([^/`\s]+)\.html/);
    if (!matched) continue;
    const id = cells[0].replace(/`/g, '');
    inventory.set(id, {
      id,
      name: cells[1],
      description: cells[2],
      screenId: matched[1],
    });
  }
  return inventory;
}

function parseFlow(md, inventory) {
  const screenFlow = md.match(/##\s+화면 흐름[\s\S]*?```mermaid\s*\n([\s\S]*?)```/);
  if (!screenFlow) throw new Error('## 화면 흐름 아래 mermaid 개요가 필요합니다.');
  const body = screenFlow[1];
  const aliasToInventoryId = new Map();
  for (const match of body.matchAll(/state\s+"([^"]*)"\s+as\s+([A-Za-z_]\w*)/g)) {
    const inventoryId = [...inventory.keys()].find(id => match[1].includes(`(${id})`));
    if (inventoryId) aliasToInventoryId.set(match[2], inventoryId);
  }
  const edges = [];
  for (const match of body.matchAll(
    /^\s*([A-Za-z_]\w*|\[\*\])\s*-->\s*([A-Za-z_]\w*|\[\*\])\s*:\s*(.+?)\s*$/gm,
  )) {
    edges.push({ fromAlias: match[1], toAlias: match[2], label: match[3] });
  }
  return { body, aliasToInventoryId, edges };
}

function parseJourneyContract(md) {
  const block = md.match(/```json\s+dcness-journey-contract\s*\n([\s\S]*?)```/);
  if (!block) return null;
  let contract;
  try {
    contract = JSON.parse(block[1]);
  } catch (error) {
    throw new Error(`dcness-journey-contract JSON 오류: ${error.message}`);
  }
  if (!contract.unit || !contract.journeyHeadingPattern) {
    throw new Error('journey contract의 unit/journeyHeadingPattern이 필요합니다.');
  }
  new RegExp(contract.journeyHeadingPattern);
  const token = '(?<id>';
  let hasIdGroup = false;
  for (
    let at = contract.journeyHeadingPattern.indexOf(token);
    at >= 0;
    at = contract.journeyHeadingPattern.indexOf(token, at + token.length)
  ) {
    let escapes = 0;
    for (let index = at - 1; index >= 0 && contract.journeyHeadingPattern[index] === '\\'; index -= 1) {
      escapes += 1;
    }
    if (escapes % 2 === 0) {
      hasIdGroup = true;
      break;
    }
  }
  if (!hasIdGroup) {
    throw new Error('journeyHeadingPattern은 id named group을 가져야 합니다.');
  }
  return contract;
}

function parseJourneyDeclarations(md, contract) {
  if (!contract) return [];
  const pattern = new RegExp(contract.journeyHeadingPattern);
  const journeys = [];
  let current = null;
  for (const line of md.split('\n')) {
    const heading = line.match(/^#{1,6}\s+(.+?)\s*$/);
    if (heading) {
      const matched = heading[1].match(pattern);
      current = matched?.groups?.id ? { id: matched.groups.id, steps: [] } : null;
      if (current) journeys.push(current);
      continue;
    }
    if (!current) continue;
    const step = line.match(
      /^-\s*([A-Za-z_]\w*)\s*-->\s*([A-Za-z_]\w*)\s*(?:\((.+)\))?\s*$/,
    );
    if (step) {
      current.steps.push({
        fromAlias: step[1],
        toAlias: step[2],
        hint: step[3]?.trim() ?? null,
      });
    }
  }
  return journeys;
}

function safeJourneyId(id) {
  const safe = id.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-|-$/g, '');
  if (!safe) throw new Error(`파일명으로 만들 수 없는 여정 ID입니다: ${id}`);
  return safe;
}

function orderNodes(arrows) {
  const lastAt = new Map();
  let position = 0;
  for (const arrow of arrows) {
    lastAt.set(arrow.from, position++);
    lastAt.set(arrow.to, position++);
  }
  return [...lastAt.entries()]
    .sort((left, right) => left[1] - right[1])
    .map(([id]) => id);
}

export function resolveJourneys(model, screens) {
  if (!model.contract) return [];
  const declarations = parseJourneyDeclarations(model.markdown, model.contract);
  const names = model.nameSource.names;
  const usedFiles = new Set();
  return declarations.map(declaration => {
    const name = names.get(declaration.id);
    if (!name) throw new Error(`여정 이름 소스에 ID가 없습니다: ${declaration.id}`);
    const arrows = [];
    const skipped = [];
    for (const step of declaration.steps) {
      const declared = `${step.fromAlias} --> ${step.toAlias}`;
      const candidates = model.flow.edges.filter(edge =>
        edge.fromAlias === step.fromAlias && edge.toAlias === step.toAlias);
      if (candidates.length === 0) {
        throw new Error(`${name}: 개요 다이어그램에 없는 전이입니다 — ${declared}`);
      }
      const matched = step.hint
        ? candidates.filter(edge => edge.label.includes(step.hint))
        : candidates;
      if (matched.length !== 1) {
        const listed = candidates.map(edge => `\n  - ${edge.label}`).join('');
        throw new Error(
          `${name}: ${declared} 전이를 하나로 구분하지 못했습니다. 후보:${listed}`,
        );
      }
      const fromInventory = model.flow.aliasToInventoryId.get(step.fromAlias);
      const toInventory = model.flow.aliasToInventoryId.get(step.toAlias);
      const from = model.inventory.get(fromInventory)?.screenId;
      const to = model.inventory.get(toInventory)?.screenId;
      const missing = [
        [step.fromAlias, from],
        [step.toAlias, to],
      ].filter(([, screenId]) => !screenId || !screens.has(screenId));
      if (missing.length) {
        skipped.push(
          `${declared} (확정본 없는 화면: ${missing.map(([alias]) => alias).join(', ')})`,
        );
        continue;
      }
      if (from === to) {
        skipped.push(`${declared} (자기 전이)`);
        continue;
      }
      arrows.push({ from, to, label: matched[0].label });
    }
    const file = `journey-${safeJourneyId(declaration.id)}.html`;
    if (usedFiles.has(file)) throw new Error(`여정 보드 파일명이 충돌합니다: ${file}`);
    usedFiles.add(file);
    return {
      id: declaration.id,
      unit: model.contract.unit,
      name,
      file,
      arrows,
      nodes: orderNodes(arrows),
      skipped,
      wanted: arrows.length >= 2,
      reason: arrows.length >= 2
        ? `확정본 사이 전이 ${arrows.length}개`
        : `확정본 사이 전이 ${arrows.length}개(2개 미만)${skipped.length ? ` · 건너뛴 전이 ${skipped.length}개` : ''}`,
    };
  });
}

function journeyScope(model) {
  const epicPath = dirname(model.uxFlowRelative)
    .replace(/^docs[/\\]epics[/\\]?/, '')
    .replace(/[/\\]+/g, '-');
  return safeJourneyId(epicPath || 'root');
}

export function resolveProjectJourneys(models, screens) {
  const journeys = models.flatMap(model =>
    resolveJourneys(model, screens).map(journey => ({ ...journey, model })));
  const byFile = new Map();
  for (const journey of journeys) {
    if (!byFile.has(journey.file)) byFile.set(journey.file, []);
    byFile.get(journey.file).push(journey);
  }
  for (const collisions of byFile.values()) {
    if (collisions.length < 2) continue;
    for (const journey of collisions) {
      journey.file = `journey-${journeyScope(journey.model)}-${safeJourneyId(journey.id)}.html`;
    }
  }
  const files = journeys.map(journey => journey.file);
  if (new Set(files).size !== files.length) {
    throw new Error('여러 ux-flow의 여정 보드 파일명이 충돌합니다.');
  }
  return journeys;
}

function parseAttributes(tag) {
  const attributes = new Map();
  for (const match of tag.matchAll(/([\w:-]+)\s*=\s*(["'])(.*?)\2/g)) {
    attributes.set(match[1], match[3]);
  }
  return attributes;
}

function parseAxisValues(raw) {
  const values = new Map();
  if (!raw) return values;
  for (const pair of raw.split(';')) {
    const [axis, ...rest] = pair.split('=');
    const value = rest.join('=').trim();
    const name = axis?.trim();
    if (!name || rest.length === 0 || !value) {
      throw new Error(`잘못된 data-variant-values 쌍입니다: ${pair}`);
    }
    if (values.has(name)) {
      throw new Error(`data-variant-values 축이 중복됩니다: ${name}`);
    }
    values.set(name, value);
  }
  return values;
}

export function scanScreens(projectRoot, { validateDrafts = true } = {}) {
  const designDir = join(projectRoot, 'docs', 'design-variants');
  const screensDir = join(designDir, 'screens');
  const draftsDir = join(designDir, 'drafts');
  const screens = new Map();
  const problems = [];
  if (!existsSync(screensDir)) return { screens, problems: ['screens/ 폴더가 없습니다.'] };

  for (const file of readdirSync(screensDir).filter(name => name.endsWith('.html')).sort()) {
    const screenId = file.slice(0, -5);
    const path = join(screensDir, file);
    const html = readFileSync(path, 'utf8');
    const variants = [];
    for (const match of html.matchAll(/<[^>]*\bdata-variant\s*=\s*(["']).*?\1[^>]*>/g)) {
      const attributes = parseAttributes(match[0]);
      variants.push({
        id: attributes.get('data-variant'),
        axes: parseAxisValues(attributes.get('data-variant-values')),
        representative: attributes.get('data-journey-representative') === 'true',
      });
    }
    for (const match of html.matchAll(/<[^>]*\bdata-variant-values\s*=[^>]*>/g)) {
      if (!parseAttributes(match[0]).has('data-variant')) {
        problems.push(`${file}: data-variant-values 블록에 data-variant가 없습니다.`);
      }
    }
    if (variants.length === 0) {
      problems.push(`${file}: 모든 변형 블록에 data-variant가 필요합니다.`);
    }
    if (variants.some(variant => !variant.id?.trim())) {
      problems.push(`${file}: data-variant 값은 비어 있을 수 없습니다.`);
    }
    const ids = variants.map(variant => variant.id);
    if (new Set(ids).size !== ids.length) problems.push(`${file}: data-variant 값이 중복됩니다.`);
    const representatives = variants.filter(variant => variant.representative);
    if (representatives.length > 1) {
      problems.push(
        `${file}: data-journey-representative="true"가 중복됩니다.`,
      );
    } else if (variants.length > 1 && representatives.length === 0) {
      problems.push(
        `${file}: 여러 변형 중 data-journey-representative="true"가 정확히 하나 필요합니다.`,
      );
    }
    const helperSources = [...html.matchAll(/<script\b[^>]*>/gi)]
      .map(match => parseAttributes(match[0]).get('src'))
      .filter(Boolean)
      .map(source => source.split(/[?#]/, 1)[0]);
    const missingHelpers = SCREEN_HELPERS.filter(name =>
      !helperSources.some(source => source.endsWith(`../_lib/${name}`)));
    if (missingHelpers.length) {
      problems.push(`${file}: 화면 helper가 없습니다 — ${missingHelpers.join(', ')}`);
    }
    const axes = [];
    for (const variant of variants) {
      for (const axis of variant.axes.keys()) if (!axes.includes(axis)) axes.push(axis);
    }
    for (const variant of variants) {
      const missingAxes = axes.filter(axis => !variant.axes.has(axis));
      if (missingAxes.length) {
        problems.push(`${file}: ${variant.id}에 변형 축 ${missingAxes.join(', ')} 값이 없습니다.`);
      }
    }
    if (/\bdraft\s*[-_ ]?\d+\b/i.test(html) || /dcness-draft-meta/i.test(html)) {
      problems.push(`${file}: 확정본에 draft 전용 메타가 남아 있습니다.`);
    }
    if (validateDrafts && existsSync(draftsDir)) {
      const escaped = screenId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const stale = readdirSync(draftsDir).filter(name =>
        new RegExp(`^${escaped}-draft\\d+\\.html$`, 'i').test(name));
      if (stale.length) {
        problems.push(`${file}: 승격 뒤 탈락 후보가 남아 있습니다 — ${stale.join(', ')}`);
      }
    }
    const nodeIds = [...html.matchAll(/\bdata-node-id\s*=\s*(["'])(.*?)\1/g)]
      .map(match => match[2]);
    screens.set(screenId, {
      id: screenId,
      file,
      path,
      relativePath: relative(projectRoot, path),
      html,
      hash: sha12(html),
      variants,
      representative: representatives[0]?.id ?? variants[0]?.id ?? null,
      axes,
      nodeIds,
      nodePrefix: commonNodePrefix(nodeIds),
    });
  }
  return { screens, problems };
}

function commonNodePrefix(nodeIds) {
  if (nodeIds.length === 0) return '없음';
  const prefixes = nodeIds.map(id => id.split(/[.-]/)[0]);
  return prefixes.every(prefix => prefix === prefixes[0]) ? prefixes[0] : '혼합';
}

function readModelPath(projectRoot, uxFlowPath) {
  const markdown = readFileSync(uxFlowPath, 'utf8');
  const inventory = parseInventory(markdown);
  const flow = parseFlow(markdown, inventory);
  const contract = parseJourneyContract(markdown);
  const nameSource = contract
    ? resolveNameSource(projectRoot, uxFlowPath, contract)
    : { names: new Map(), path: uxFlowPath, relativePath: relative(projectRoot, uxFlowPath), hash: sha12(markdown) };
  return {
    projectRoot,
    uxFlowPath,
    uxFlowRelative: relative(projectRoot, uxFlowPath),
    markdown,
    uxFlowHash: sha12(markdown),
    inventory,
    flow,
    contract,
    nameSource,
  };
}

export function readModels(projectRoot, requestedUxFlow = null) {
  return resolveUxFlows(projectRoot, requestedUxFlow)
    .map(uxFlowPath => readModelPath(projectRoot, uxFlowPath));
}

export function readModel(projectRoot, requestedUxFlow = null) {
  return readModelPath(projectRoot, resolveUxFlow(projectRoot, requestedUxFlow));
}

export function screenMetadata(modelsOrModel, screen) {
  const models = Array.isArray(modelsOrModel) ? modelsOrModel : [modelsOrModel];
  const declarations = models.flatMap(model =>
    [...model.inventory.values()]
      .filter(item => item.screenId === screen.id)
      .map(item => ({ model, item })));
  const signatures = new Set(declarations.map(({ item }) =>
    JSON.stringify([item.id, item.name, item.description])));
  if (signatures.size > 1) {
    const details = declarations.map(({ model, item }) =>
      `  - ${model.uxFlowRelative}: ${item.id} | ${item.name} | ${item.description}`);
    throw new Error(
      `여러 ux-flow의 화면 메타데이터가 충돌합니다: ${screen.id}\n`
      + details.join('\n'),
    );
  }
  const inventory = declarations[0]?.item;
  return {
    title: inventory ? `${inventory.id} ${inventory.name}` : screen.id,
    description: inventory?.description ?? '',
  };
}

export function validateScreenMetadata(models, screens) {
  for (const screen of screens.values()) screenMetadata(models, screen);
}

export function warnEngineDrift(projectRoot) {
  const projectLib = join(projectRoot, 'docs', 'design-variants', '_lib');
  const templateLib = join(PLUGIN_ROOT, 'templates', 'design-variants', '_lib');
  const warnings = [];
  for (const name of ENGINE_FILES) {
    const expected = join(templateLib, name);
    const actual = join(projectLib, name);
    if (!existsSync(actual)) warnings.push(`${name} 없음`);
    else if (readFileSync(actual, 'utf8') !== readFileSync(expected, 'utf8')) {
      warnings.push(`${name}이 배포본과 다름(구버전 또는 지역 수정)`);
    }
  }
  if (warnings.length) {
    console.error(`[design-variants] ENGINE WARNING — ${warnings.join('; ')}`);
    console.error('  엔진은 프로젝트에서 수정하지 않습니다. 갱신은 canvas-design의 명시적 동기화로 수행하십시오.');
  }
  return warnings;
}

export function regenerationCommand(scriptName, modelsOrUxFlow) {
  const base = `node "$CLAUDE_PLUGIN_ROOT/scripts/design/${scriptName}" --project-root .`;
  if (Array.isArray(modelsOrUxFlow)) {
    return modelsOrUxFlow.length === 1
      ? `${base} --ux-flow ${modelsOrUxFlow[0].uxFlowRelative}`
      : base;
  }
  return modelsOrUxFlow ? `${base} --ux-flow ${modelsOrUxFlow}` : base;
}
