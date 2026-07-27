#!/usr/bin/env node

import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import {
  cp,
  mkdtemp,
  mkdir,
  readFile,
  rm,
  writeFile,
} from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const GENERATORS = path.join(ROOT, 'scripts', 'design');
const TEMPLATE = path.join(ROOT, 'templates', 'design-variants');

function chromeExecutable() {
  const candidates = [
    process.env.CHROME_BIN,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  for (const command of ['google-chrome', 'google-chrome-stable', 'chromium']) {
    const result = spawnSync('which', [command], { encoding: 'utf8' });
    if (result.status === 0 && result.stdout.trim()) return result.stdout.trim();
  }
  throw new Error('Headless Chrome executable not found');
}

function screenHtml(screenId, variants) {
  const sections = variants.map(({ id, axes, representative = false }) => (
    `<section data-variant="${id}" data-variant-values="${axes}" `
    + `${representative ? 'data-journey-representative="true" ' : ''}`
    + `data-node-id="${screenId}.${id}">${screenId} · ${id}</section>`
  )).join('\n');
  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>${screenId}</title>
  <style>
    html, body { margin: 0; padding: 0; }
    body { width: 260px; min-height: 180px; font: 16px system-ui, sans-serif; }
    section { box-sizing: border-box; width: 260px; height: 180px; padding: 24px; }
  </style>
</head>
<body>
${sections}
<script>
  const loadKey = location.pathname + location.hash;
  parent.__dcnessSmokeFrameLoads ||= {};
  parent.__dcnessSmokeFrameLoads[loadKey] =
    (parent.__dcnessSmokeFrameLoads[loadKey] || 0) + 1;
</script>
<script defer src="../_lib/only-variant.js"></script>
<script defer src="../_lib/report-size.js"></script>
<script defer src="../_lib/show-ids.js"></script>
</body>
</html>
`;
}

function uxFlow() {
  return `# UX flow

## 화면 인벤토리

| 화면 ID | 화면명 | 역할 | 확정 목업 경로 |
|---|---|---|---|
| S01 | 수신함 | 알림 목록 | \`docs/design-variants/screens/inbox.html\` |
| S02 | 검토 | 알림 검토 | \`docs/design-variants/screens/review.html\` |
| S03 | 완료 | 처리 완료 | \`docs/design-variants/screens/done.html\` |
| S04 | facet 증가 | 런타임 facet 증가 검증 | \`docs/design-variants/screens/facet-grow.html\` |
| S05 | facet 감소 | 런타임 facet 감소 검증 | \`docs/design-variants/screens/facet-shrink.html\` |

## 화면 흐름

\`\`\`mermaid
stateDiagram-v2
  state "수신함 (S01)" as Inbox
  state "검토 (S02)" as Review
  state "완료 (S03)" as Done
  Inbox --> Review: 알림 선택
  Review --> Done: 검토 완료
\`\`\`

\`\`\`json dcness-journey-contract
{
  "unit": "user-goal",
  "journeyHeadingPattern": "^Goal (?<id>[a-z0-9-]+)$",
  "nameSource": {
    "kind": "table",
    "path": "ux-flow.md",
    "section": "여정 카탈로그",
    "idColumn": "여정 ID",
    "nameColumn": "이름"
  }
}
\`\`\`

### 여정 카탈로그

| 여정 ID | 이름 |
|---|---|
| handle-notice | 알림 처리 |

### 여정 경로

#### Goal handle-notice

- Inbox --> Review
- Review --> Done
`;
}

function runGenerator(project, uxPath, name, extra = []) {
  return spawnSync(
    process.execPath,
    [
      path.join(GENERATORS, name),
      '--project-root',
      project,
      '--ux-flow',
      path.relative(project, uxPath),
      ...extra,
    ],
    { encoding: 'utf8' },
  );
}

function requireSuccess(result, name) {
  assert.equal(
    result.status,
    0,
    `${name} failed\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
  );
}

async function injectProbe(file) {
  const html = await readFile(file, 'utf8');
  const probe = `<script>
(async function () {
  let diagnostics = null;
  let previous = '';
  let stable = 0;
  for (let attempt = 0; attempt < 50; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 100));
    if (typeof window.dcnessCanvasDiagnostics !== 'function') continue;
    diagnostics = window.dcnessCanvasDiagnostics();
    diagnostics.frameLoads = window.__dcnessSmokeFrameLoads || {};
    const signature = JSON.stringify(diagnostics);
    stable = signature === previous ? stable + 1 : 0;
    previous = signature;
    if (
      stable >= 3
      && diagnostics.frames.length
      && diagnostics.frames.every(frame => frame.scrollWidth !== null)
      && diagnostics.frames.every(frame => frame.hasInternalScroll === false)
      && diagnostics.frames.every(frame => frame.sizeWarning === false)
      && diagnostics.frames.every(frame =>
        ['direct', 'report'].includes(frame.measurementSource))
    ) break;
  }
  document.documentElement.dataset.smoke =
    encodeURIComponent(JSON.stringify(diagnostics));
})();
</script>`;
  await writeFile(file, html.replace('</body>', `${probe}\n</body>`));
}

async function startServer(root) {
  const server = http.createServer(async (request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
      const requested = path.resolve(root, `.${pathname}`);
      if (requested !== root && !requested.startsWith(`${root}${path.sep}`)) {
        response.writeHead(403).end();
        return;
      }
      const content = await readFile(requested);
      const type = requested.endsWith('.html')
        ? 'text/html; charset=utf-8'
        : requested.endsWith('.js')
          ? 'text/javascript; charset=utf-8'
          : 'application/octet-stream';
      response.writeHead(200, { 'content-type': type });
      response.end(content);
    } catch {
      response.writeHead(404).end();
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return server;
}

async function dumpDom(chrome, profile, url) {
  const args = [
    '--headless=new',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    '--no-first-run',
    '--no-sandbox',
    `--user-data-dir=${profile}`,
    '--virtual-time-budget=7000',
    '--window-size=1600,1200',
    '--dump-dom',
    url,
  ];
  return new Promise((resolve, reject) => {
    const child = spawn(chrome, args);
    let stdout = '';
    let stderr = '';
    const timeout = setTimeout(() => {
      child.kill('SIGKILL');
      reject(new Error(`Chrome timed out for ${url}\n${stderr}`));
    }, 20000);
    child.stdout.setEncoding('utf8').on('data', chunk => { stdout += chunk; });
    child.stderr.setEncoding('utf8').on('data', chunk => { stderr += chunk; });
    child.once('error', reject);
    child.once('close', code => {
      clearTimeout(timeout);
      if (code === 0) resolve(stdout);
      else reject(new Error(`Chrome exited ${code} for ${url}\n${stderr}`));
    });
  });
}

function smokeData(dom) {
  const match = dom.match(/\bdata-smoke="([^"]+)"/);
  assert.ok(match, `browser probe did not finish\n${dom.slice(0, 1000)}`);
  return JSON.parse(decodeURIComponent(match[1]));
}

function assertNoInternalScroll(diagnostics, board) {
  assert.ok(diagnostics.frames.length > 0, `${board}: no frames rendered`);
  for (const frame of diagnostics.frames) {
    assert.equal(
      frame.hasInternalScroll,
      false,
      `${board}: internal scroll in ${frame.src} ${JSON.stringify(frame)}`,
    );
    assert.ok(
      frame.scrollWidth <= frame.width + 1 && frame.scrollHeight <= frame.height + 1,
      `${board}: clipped frame ${frame.src} ${JSON.stringify(frame)}`,
    );
    assert.equal(
      frame.sizeWarning,
      false,
      `${board}: unresolved frame size in ${frame.src} ${JSON.stringify(frame)}`,
    );
    assert.ok(
      ['direct', 'report'].includes(frame.measurementSource),
      `${board}: unmeasured frame ${frame.src} ${JSON.stringify(frame)}`,
    );
  }
  for (const [src, loads] of Object.entries(diagnostics.frameLoads)) {
    assert.equal(loads, 1, `${board}: iframe reloaded ${loads} times: ${src}`);
  }
}

function assertScreenGrid(diagnostics) {
  assert.equal(diagnostics.frames.length, 11, 'runtime variant inventory did not converge');
  assert.ok(
    diagnostics.frames.some(frame => frame.src.includes('#only=tablet-ready')),
    'new tablet variant is missing from the stale board runtime',
  );
  const inbox = diagnostics.variantFrames.filter(frame => frame.nodeId === 'inbox');
  assert.deepEqual(
    [...new Set(inbox.map(frame => frame.column))].sort(),
    ['desktop', 'mobile', 'tablet'],
  );
  assert.deepEqual(
    [...new Set(inbox.map(frame => frame.row))].sort(),
    ['loading', 'ready'],
  );
  for (const column of ['mobile', 'desktop']) {
    const positions = inbox.filter(frame => frame.column === column).map(frame => frame.left);
    assert.equal(new Set(positions).size, 1, `${column} variants are not column-aligned`);
  }
  for (const row of ['loading', 'ready']) {
    const positions = inbox.filter(frame => frame.row === row).map(frame => frame.top);
    assert.equal(new Set(positions).size, 1, `${row} variants are not row-aligned`);
  }
  const facetGrow = diagnostics.variantFrames.filter(frame => frame.nodeId === 'facet-grow');
  assert.deepEqual(
    [...new Set(facetGrow.map(frame => frame.facet))].sort(),
    ['theme=dark', 'theme=light'],
    'runtime facet growth did not create both groups',
  );
  const facetShrink = diagnostics.variantFrames
    .filter(frame => frame.nodeId === 'facet-shrink');
  assert.deepEqual(
    [...new Set(facetShrink.map(frame => frame.facet))],
    [''],
    'runtime facet shrink did not collapse to one group',
  );
}

async function main() {
  const temporary = await mkdtemp(path.join(os.tmpdir(), 'dcness-design-smoke-'));
  let server;
  try {
    const project = path.join(temporary, 'project');
    const design = path.join(project, 'docs', 'design-variants');
    const screens = path.join(design, 'screens');
    const uxPath = path.join(project, 'docs', 'epics', 'visual', 'ux-flow.md');
    await mkdir(path.dirname(uxPath), { recursive: true });
    await cp(TEMPLATE, design, { recursive: true });
    await mkdir(screens, { recursive: true });
    await writeFile(path.join(project, 'CLAUDE.md'), '# Project\n');
    await writeFile(path.join(project, 'docs', 'index.md'), '# Documentation\n');
    await writeFile(uxPath, uxFlow());
    await writeFile(path.join(screens, 'inbox.html'), screenHtml('inbox', [
      { id: 'mobile-loading', axes: 'breakpoint=mobile;state=loading' },
      { id: 'desktop-loading', axes: 'breakpoint=desktop;state=loading' },
      {
        id: 'mobile-ready',
        axes: 'breakpoint=mobile;state=ready',
        representative: true,
      },
      { id: 'desktop-ready', axes: 'breakpoint=desktop;state=ready' },
    ]));
    for (const id of ['review', 'done']) {
      await writeFile(
        path.join(screens, `${id}.html`),
        screenHtml(id, [{ id: 'default', axes: 'state=default' }]),
      );
    }
    await writeFile(path.join(screens, 'facet-grow.html'), screenHtml('facet-grow', [
      { id: 'mobile-ready', axes: 'breakpoint=mobile;state=ready' },
      { id: 'desktop-ready', axes: 'breakpoint=desktop;state=ready' },
    ]));
    await writeFile(path.join(screens, 'facet-shrink.html'), screenHtml('facet-shrink', [
      { id: 'mobile-ready', axes: 'breakpoint=mobile;state=ready;theme=light' },
      { id: 'desktop-ready', axes: 'breakpoint=desktop;state=ready;theme=dark' },
    ]));

    requireSuccess(
      runGenerator(project, uxPath, 'build-journey-boards.mjs'),
      'build-journey-boards',
    );
    requireSuccess(
      runGenerator(project, uxPath, 'build-screen-states.mjs'),
      'build-screen-states',
    );
    requireSuccess(
      runGenerator(project, uxPath, 'build-design-index.mjs'),
      'build-design-index',
    );

    const statesBoard = path.join(design, 'boards', 'screen-states.html');
    const journeyBoard = path.join(design, 'boards', 'journey-handle-notice.html');
    const statesBefore = await readFile(statesBoard, 'utf8');
    const inboxPath = path.join(screens, 'inbox.html');
    const inbox = await readFile(inboxPath, 'utf8');
    await writeFile(
      inboxPath,
      inbox.replace(
        '</body>',
        '<section data-variant="tablet-ready" '
          + 'data-variant-values="breakpoint=tablet;state=ready" '
          + 'data-node-id="inbox.tablet-ready">inbox · tablet-ready</section>\n</body>',
      ),
    );
    const facetGrowPath = path.join(screens, 'facet-grow.html');
    const facetGrow = await readFile(facetGrowPath, 'utf8');
    await writeFile(
      facetGrowPath,
      facetGrow
        .replace(
          'breakpoint=mobile;state=ready',
          'breakpoint=mobile;state=ready;theme=light',
        )
        .replace(
          'breakpoint=desktop;state=ready',
          'breakpoint=desktop;state=ready;theme=dark',
        ),
    );
    const facetShrinkPath = path.join(screens, 'facet-shrink.html');
    const facetShrink = await readFile(facetShrinkPath, 'utf8');
    await writeFile(
      facetShrinkPath,
      facetShrink
        .replace(';theme=light', '')
        .replace(';theme=dark', ''),
    );
    assert.equal(await readFile(statesBoard, 'utf8'), statesBefore);
    const stale = runGenerator(project, uxPath, 'build-screen-states.mjs', ['--check']);
    assert.notEqual(stale.status, 0, 'source drift was not detected');
    assert.match(stale.stderr, /DRIFT/);

    await injectProbe(statesBoard);
    await injectProbe(journeyBoard);
    const chrome = chromeExecutable();
    const profile = path.join(temporary, 'chrome-profile');
    server = await startServer(project);
    const address = server.address();
    const base = `http://127.0.0.1:${address.port}`;

    const states = smokeData(await dumpDom(
      chrome,
      profile,
      `${base}/docs/design-variants/boards/screen-states.html`,
    ));
    assertNoInternalScroll(states, 'screen-states');
    assertScreenGrid(states);

    const journey = smokeData(await dumpDom(
      chrome,
      profile,
      `${base}/docs/design-variants/boards/journey-handle-notice.html`,
    ));
    assertNoInternalScroll(journey, 'journey');
    assert.equal(journey.arrows.length, 2);
    assert.deepEqual(journey.geometry, {
      arrowCount: 2,
      arrowNodeHits: 0,
      labelNodeHits: 0,
      labelPairHits: 0,
    });

    const invalid = await dumpDom(
      chrome,
      profile,
      `${base}/docs/design-variants/screens/inbox.html#only=missing`,
    );
    assert.match(invalid, /id="dcness-variant-warning"/);
    process.stdout.write(`${JSON.stringify({
      status: 'PASS',
      screenFrames: states.frames.length,
      journeyFrames: journey.frames.length,
      arrows: journey.geometry.arrowCount,
    })}\n`);
  } finally {
    if (server) await new Promise(resolve => server.close(resolve));
    await rm(temporary, { recursive: true, force: true });
  }
}

main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
