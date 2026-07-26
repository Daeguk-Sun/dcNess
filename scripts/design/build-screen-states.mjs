#!/usr/bin/env node
/** Generate the one screen-state board from confirmed screen sources. */
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import { join } from 'node:path';
import {
  escapeHtml,
  parseCli,
  readModels,
  regenerationCommand,
  scanScreens,
  screenMetadata,
  sha12,
  validateScreenMetadata,
  warnEngineDrift,
} from './ux-flow.mjs';

function facetKey(variant, facetAxes) {
  return facetAxes.map(axis => `${axis}=${variant.axes.get(axis)}`).join(';');
}

function renderGrid(screen) {
  const columnAxis = screen.axes[0] ?? 'variant';
  const rowAxis = screen.axes[1] ?? '';
  const facetAxes = screen.axes.slice(2);
  const groups = new Map();
  for (const variant of screen.variants) {
    const key = facetKey(variant, facetAxes);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(variant);
  }
  return [...groups.entries()].map(([facet, variants]) => {
    const frames = variants.map(variant => {
      const column = variant.axes.get(columnAxis) ?? variant.id;
      const row = rowAxis ? variant.axes.get(rowAxis) : '';
      return [
        `          <figure class="variant-frame" data-variant-id="${escapeHtml(variant.id)}" data-axis-column="${escapeHtml(column)}" data-axis-row="${escapeHtml(row)}">`,
        `            <figcaption>${escapeHtml(variant.id)}</figcaption>`,
        `            <iframe src="../screens/${escapeHtml(screen.file)}#only=${encodeURIComponent(variant.id)}" title="${escapeHtml(screen.id)} ${escapeHtml(variant.id)}"></iframe>`,
        '          </figure>',
      ].join('\n');
    }).join('\n');
    const facetLabel = facet
      ? `        <h3 class="variant-facet">${escapeHtml(facet)}</h3>\n`
      : '';
    return `${facetLabel}        <div class="variant-grid" data-column-axis="${escapeHtml(columnAxis)}" data-row-axis="${escapeHtml(rowAxis)}">
${frames}
        </div>`;
  }).join('\n');
}

function sourcePaths(models) {
  return [...new Set(models.map(model => model.uxFlowRelative))].join('; ');
}

function renderBoard(models, screens, command) {
  const sourceHash = sha12(
    `${models.map(model => model.uxFlowHash).join(':')}:`
    + [...screens.values()].map(screen => screen.hash).join(':'),
  );
  const nodes = [...screens.values()].map(screen => {
    const meta = screenMetadata(models, screen);
    return [
      `    <section class="screen-node" data-node-id="${escapeHtml(screen.id)}"`,
      `             data-title="${escapeHtml(meta.title)}"`,
      `             data-desc="${escapeHtml(meta.description)}"`,
      `             data-screen-src="../screens/${escapeHtml(screen.file)}"`,
      `             data-variants="${escapeHtml(screen.variants.map(variant => variant.id).join(' / '))}">`,
      renderGrid(screen),
      '    </section>',
    ].join('\n');
  }).join('\n');
  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>화면 변형 전수 보드</title>
  <style>
    html, body { margin: 0; height: 100%; font-family: system-ui, sans-serif; }
    .variant-grid { display: grid; grid-auto-flow: row; gap: 1rem; }
    .variant-frame { margin: 0; }
    .variant-frame figcaption { margin-bottom: .35rem; font-size: .8rem; }
    .variant-frame iframe { display: block; pointer-events: none; }
    .variant-facet { margin: 0 0 .5rem; font-size: .9rem; }
  </style>
</head>
<body>
  <!--
    생성물 — 손으로 고치지 않는다.
    재생성: ${command}
    진본: ${sourcePaths(models)}; docs/design-variants/screens/*.html
    진본 해시: ${sourceHash}
    변형 축 순서의 첫 축은 열, 둘째 축은 행, 나머지는 facet으로 파생한다.
    프레임 크기와 화면 그룹 배치는 런타임 보고와 엔진이 결정한다.
  -->
  <div class="canvas" data-board-kind="screen-states">
${nodes}
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
  console.error(`[screen-states] ${error.message}`);
  process.exit(1);
}

try {
  const models = readModels(options.projectRoot, options.uxFlow);
  const scan = scanScreens(options.projectRoot);
  if (scan.problems.length) throw new Error(scan.problems.join('\n'));
  validateScreenMetadata(models, scan.screens);
  warnEngineDrift(options.projectRoot);
  const boardsDir = join(options.projectRoot, 'docs', 'design-variants', 'boards');
  const target = join(boardsDir, 'screen-states.html');
  const command = regenerationCommand('build-screen-states.mjs', models);
  const content = renderBoard(models, scan.screens, command);

  if (options.check) {
    if (!existsSync(target) || readFileSync(target, 'utf8') !== content) {
      console.error(`[screen-states] DRIFT — 재생성: ${command}`);
      process.exit(1);
    }
    console.log(`[screen-states] OK — 화면 ${scan.screens.size}개`);
    process.exit(0);
  }

  mkdirSync(boardsDir, { recursive: true });
  writeFileSync(target, content);
  const variants = [...scan.screens.values()]
    .reduce((count, screen) => count + screen.variants.length, 0);
  console.log(`[screen-states] 화면 ${scan.screens.size}개 · 변형 ${variants}개 생성`);
} catch (error) {
  console.error(`[screen-states] ${error.message}`);
  process.exit(1);
}
