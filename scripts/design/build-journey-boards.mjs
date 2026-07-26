#!/usr/bin/env node
/** Generate one journey board per declared, renderable journey. */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { join } from 'node:path';
import {
  escapeHtml,
  parseCli,
  readModel,
  regenerationCommand,
  resolveJourneys,
  scanScreens,
  screenMetadata,
  sha12,
  warnEngineDrift,
} from './ux-flow.mjs';

function shortenLabel(raw) {
  const words = raw
    .replace(/\([^)]*\)/g, ' ')
    .replace(/\bAC-\d+\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return words.length > 40 ? `${words.slice(0, 39).trim()}…` : words;
}

function renderBoard(journey, model, screens, command) {
  const screenHashes = journey.nodes.map(id => screens.get(id)?.hash ?? '').join(':');
  const sourceHash = sha12(
    `${model.uxFlowHash}:${model.nameSource.hash}:${screenHashes}:${journey.id}`,
  );
  const nodes = journey.nodes.map(id => {
    const screen = screens.get(id);
    const meta = screenMetadata(model, screen);
    const variants = screen.variants.map(variant => variant.id);
    const representative = variants[0];
    return [
      `    <div class="screen-node" data-node-id="${escapeHtml(id)}"`,
      `         data-title="${escapeHtml(meta.title)}"`,
      `         data-desc="${escapeHtml(meta.description)}"`,
      `         data-states="${escapeHtml(variants.join(' / '))}">`,
      `      <iframe src="../screens/${escapeHtml(screen.file)}#only=${encodeURIComponent(representative)}" title="${escapeHtml(meta.title)}"></iframe>`,
      '    </div>',
    ].join('\n');
  }).join('\n');
  const arrows = journey.arrows.map(arrow =>
    `      <path data-from="${escapeHtml(arrow.from)}" data-to="${escapeHtml(arrow.to)}"`
    + ` data-label="${escapeHtml(shortenLabel(arrow.label))}"`
    + ` data-label-full="${escapeHtml(arrow.label)}"/>`).join('\n');
  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${escapeHtml(journey.name)} · 저니</title>
  <style>
    html, body { margin: 0; height: 100%; font-family: system-ui, sans-serif; }
    .screen-node iframe { pointer-events: none; }
  </style>
</head>
<body>
  <!--
    생성물 — 손으로 고치지 않는다.
    재생성: ${command}
    진본: ${model.uxFlowRelative}; ${model.nameSource.relativePath}; docs/design-variants/screens/*.html
    진본 해시: ${sourceHash}
    노드 순서는 선언 경로의 마지막 등장 순서, 곡률과 간격은 엔진 파생이다.
  -->
  <div class="canvas" data-board-kind="journey">
${nodes}
    <svg class="flow-arrows">
${arrows}
    </svg>
  </div>
  <script defer src="../_lib/canvas.js"></script>
  <script defer src="../_lib/show-ids.js"></script>
</body>
</html>
`;
}

let options;
try {
  options = parseCli();
} catch (error) {
  console.error(`[journey-boards] ${error.message}`);
  process.exit(1);
}

try {
  const model = readModel(options.projectRoot, options.uxFlow);
  const scan = scanScreens(options.projectRoot, { validateDrafts: false });
  if (scan.problems.length) throw new Error(scan.problems.join('\n'));
  warnEngineDrift(options.projectRoot);
  const journeys = resolveJourneys(model, scan.screens);
  const boardsDir = join(options.projectRoot, 'docs', 'design-variants', 'boards');
  const command = regenerationCommand('build-journey-boards.mjs', model.uxFlowRelative);
  const targets = journeys.filter(journey => journey.wanted).map(journey => ({
    ...journey,
    content: renderBoard(journey, model, scan.screens, command),
    path: join(boardsDir, journey.file),
  }));
  const wantedFiles = new Set(targets.map(target => target.file));
  const stale = existsSync(boardsDir)
    ? readdirSync(boardsDir).filter(name =>
      /^journey-.*\.html$/.test(name) && !wantedFiles.has(name))
    : [];

  if (options.check) {
    const drift = [];
    for (const target of targets) {
      if (!existsSync(target.path)) drift.push(`${target.file} 없음`);
      else if (readFileSync(target.path, 'utf8') !== target.content) {
        drift.push(`${target.file}이 진본과 다름`);
      }
    }
    for (const name of stale) drift.push(`${name}은 선언된 여정이 아님`);
    if (drift.length) {
      console.error('[journey-boards] DRIFT');
      for (const problem of drift) console.error(`  - ${problem}`);
      console.error(`  재생성: ${command}`);
      process.exit(1);
    }
    console.log(`[journey-boards] OK — ${targets.length}개`);
    process.exit(0);
  }

  mkdirSync(boardsDir, { recursive: true });
  for (const target of targets) writeFileSync(target.path, target.content);
  for (const name of stale) unlinkSync(join(boardsDir, name));
  console.log(`[journey-boards] ${targets.length}개 생성`);
  for (const target of targets) {
    console.log(`  - ${target.name}: ${target.nodes.join(' → ')} (${target.arrows.length}전이)`);
  }
  const omitted = journeys.filter(journey => !journey.wanted);
  if (omitted.length) {
    console.log('[journey-boards] 보드를 만들지 않은 여정:');
    for (const journey of omitted) {
      console.log(`  - ${journey.name}: ${journey.reason}`);
      for (const skipped of journey.skipped) console.log(`      ${skipped}`);
    }
  }
  if (stale.length) console.log(`[journey-boards] 선언에서 빠져 삭제: ${stale.join(', ')}`);
} catch (error) {
  console.error(`[journey-boards] ${error.message}`);
  process.exit(1);
}
