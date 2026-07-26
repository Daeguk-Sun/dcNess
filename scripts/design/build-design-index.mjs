#!/usr/bin/env node
/** Generate the agent README and human landing page from one derived model. */
import {
  existsSync,
  readFileSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import {
  escapeHtml,
  parseCli,
  readModels,
  regenerationCommand,
  resolveProjectJourneys,
  scanScreens,
  screenMetadata,
  sha12,
  warnEngineDrift,
} from './ux-flow.mjs';

function projectName(projectRoot) {
  const result = spawnSync(
    'git',
    ['rev-parse', '--path-format=absolute', '--git-common-dir'],
    { cwd: projectRoot, encoding: 'utf8' },
  );
  if (result.status === 0) {
    const common = result.stdout.trim();
    return basename(common.endsWith('/.git') ? dirname(common) : common);
  }
  return basename(projectRoot);
}

function confirmedEdges(models, screens) {
  return models.flatMap(model => model.flow.edges.filter(edge => {
    const fromId = model.inventory.get(model.flow.aliasToInventoryId.get(edge.fromAlias))?.screenId;
    const toId = model.inventory.get(model.flow.aliasToInventoryId.get(edge.toAlias))?.screenId;
    return fromId && toId && fromId !== toId && screens.has(fromId) && screens.has(toId);
  }));
}

function boardState(projectRoot, journeys) {
  const boardsDir = join(projectRoot, 'docs', 'design-variants', 'boards');
  const missing = [];
  if (!existsSync(join(boardsDir, 'screen-states.html'))) missing.push('screen-states.html');
  for (const journey of journeys.filter(item => item.wanted)) {
    if (!existsSync(join(boardsDir, journey.file))) missing.push(journey.file);
  }
  return { boardsDir, missing };
}

const ENTRY_MARKER = '<!-- dcness-design-variants-entry -->';

function entryPoint(path, link) {
  if (!existsSync(path)) {
    throw new Error(`디자인 인덱스 포인터를 둘 문서가 없습니다: ${path}`);
  }
  const current = readFileSync(path, 'utf8');
  const line = `- [디자인 산출물](${link}) ${ENTRY_MARKER}`;
  const newline = current.includes('\r\n') ? '\r\n' : '\n';
  const lines = current.split(/\r?\n/);
  const markerAt = lines.findIndex(item => item.includes(ENTRY_MARKER));
  const insertAt = markerAt >= 0
    ? lines.slice(0, markerAt).filter(item => !item.includes(ENTRY_MARKER)).length
    : Math.max(0, lines.length - (current.endsWith('\n') ? 1 : 0));
  const withoutMarkers = lines.filter(item => !item.includes(ENTRY_MARKER));
  if (markerAt >= 0) withoutMarkers.splice(insertAt, 0, line);
  else withoutMarkers.splice(insertAt, 0, '', line);
  return withoutMarkers.join(newline);
}

function sourcePaths(models) {
  return [...new Set(models.flatMap(model =>
    [model.uxFlowRelative, model.nameSource.relativePath]))];
}

function renderReadme({ models, screens, journeys, transitionCount, command, sourceHash }) {
  const built = journeys.filter(journey => journey.wanted);
  const omitted = journeys.filter(journey => !journey.wanted);
  const totalVariants = [...screens.values()]
    .reduce((count, screen) => count + screen.variants.length, 0);
  const journeyRows = built.length
    ? built.map(journey =>
      `| [${journey.file}](boards/${journey.file}) | ${journey.name} | ${journey.nodes.join(' → ')} | ${journey.arrows.length} |`).join('\n')
    : '| — | 선언된 여정 없음 | — | 0 |';
  const omittedRows = omitted.length
    ? omitted.map(journey => `| ${journey.name} | ${journey.reason} | ${journey.skipped.join('<br>') || '—'} |`).join('\n')
    : '| — | 없음 | — |';
  const screenRows = [...screens.values()].map(screen => {
    const meta = screenMetadata(models, screen);
    const axes = screen.axes.length ? screen.axes.join(' × ') : '단일 변형';
    return `| [${screen.id}](screens/${screen.file}) | ${meta.title} | ${screen.variants.map(variant => variant.id).join(', ')} | ${axes} | ${screen.nodePrefix} |`;
  }).join('\n');
  return `<!--
생성물 — 손으로 고치지 않는다.
재생성: ${command}
진본: ${sourcePaths(models).join('; ')}; docs/design-variants/screens/*.html
진본 해시: ${sourceHash}
-->
# 디자인 산출물

## 한눈에 보기

- 프레임 규격: 화면 진본의 자연 크기를 런타임에 보고하며 선언 크기는 두지 않는다.
- 화면 ${screens.size}개 · 변형 ${totalVariants}개 · 확정본 사이 전이 ${transitionCount}개
- 여정 선언 ${journeys.length}개 · 보드 생성 ${built.length}개 · 미생성 ${omitted.length}개
- 변형 전수 보드: [screen-states.html](boards/screen-states.html)

## 여정 보드 — 화면 사이

| 보드 | 여정 | 경로 | 전이 |
|---|---|---|---:|
${journeyRows}

## 보드를 만들지 않은 여정

| 여정 | 사유 | 제외 상세 |
|---|---|---|
${omittedRows}

## 변형 전수 보드 — 화면 안

화면별 변형을 같은 진본 파일의 \`#only=<variant>\` 링크로 열며, 여러 축은 열·행·facet으로 파생한다.

## 화면 확정본

| node-id | 화면 | 변형 | 변형 축 | node-id prefix |
|---|---|---|---|---|
${screenRows}

## 진본과 파생 규칙

- 화면 그림의 진본은 \`screens/*.html\`, 화면·전이·여정 선언의 진본은 프로젝트의 모든 \`docs/epics/**/ux-flow.md\`이다.
- 현재 ux-flow: ${models.map(model => `\`${model.uxFlowRelative}\``).join(', ')}
- \`boards/*.html\`, 이 README, \`index.html\`은 생성물이다. 진본을 고친 뒤 위 재생성 명령을 실행한다.
- 보드는 확정본을 링크할 뿐 화면 사본을 소유하지 않는다. 크기·배치·곡률·간격은 런타임에서 파생한다.
- \`_lib/\`는 플러그인 엔진 사본이며 프로젝트에서 수정하지 않는다.
- \`drafts/\`는 사용자 PICK 전 후보다. 승격은 \`screens/\`로 순수 이동하고 같은 화면의 탈락 후보를 제거한다.
`;
}

function renderIndex({ project, models, screens, journeys, transitionCount, command, sourceHash }) {
  const built = journeys.filter(journey => journey.wanted);
  const omitted = journeys.filter(journey => !journey.wanted);
  const totalVariants = [...screens.values()]
    .reduce((count, screen) => count + screen.variants.length, 0);
  const journeySection = built.length
    ? `<section>
    <h2>여정 <small>화면 사이</small></h2>
    <div class="cards">
${built.map(journey => `      <a class="card journey-card" href="boards/${escapeHtml(journey.file)}">
        <span>${escapeHtml(journey.unit)} · ${escapeHtml(journey.id)}</span>
        <strong>${escapeHtml(journey.name)}</strong>
        <p>${escapeHtml(journey.nodes.join(' → '))}</p>
        <small>화면 ${journey.nodes.length} · 전이 ${journey.arrows.length}</small>
      </a>`).join('\n')}
    </div>
${omitted.length ? `    <p class="note">보드를 만들지 않은 여정 — ${omitted.map(journey => `${escapeHtml(journey.name)} (${escapeHtml(journey.reason)})`).join(' · ')}</p>` : ''}
  </section>`
    : '';
  const screenLinks = [...screens.values()].map(screen => {
    const meta = screenMetadata(models, screen);
    return `<li><a href="screens/${escapeHtml(screen.file)}">${escapeHtml(meta.title)}</a><small>변형 ${screen.variants.length}</small></li>`;
  }).join('\n      ');
  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>${escapeHtml(project)} · 디자인 산출물</title>
  <!--
    생성물 — 손으로 고치지 않는다.
    재생성: ${command}
    진본: ${sourcePaths(models).join('; ')}; docs/design-variants/screens/*.html
    진본 해시: ${sourceHash}
  -->
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 3rem 1.25rem; background: #f4f1ec; color: #24211d; font-family: system-ui, sans-serif; }
    header, section, footer { max-width: 64rem; margin: 0 auto 2.5rem; }
    h1 { margin-bottom: .4rem; } h2 { border-bottom: 1px solid #cfc7bc; padding-bottom: .6rem; }
    h2 small { color: #6c655d; font-weight: 400; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: 1rem; }
    .card { display: flex; flex-direction: column; gap: .45rem; padding: 1.2rem; border: 1px solid #d8d0c6; border-radius: .8rem; background: #fff; color: inherit; text-decoration: none; }
    .card span, .card small, .note { color: #6c655d; } .card p { margin: 0; }
    ul { display: flex; flex-wrap: wrap; gap: .7rem; padding: 0; list-style: none; }
    li { display: flex; gap: .5rem; padding: .7rem 1rem; border-radius: 999px; background: #fff; }
    a { color: inherit; }
  </style>
</head>
<body>
  <header>
    <h1>${escapeHtml(project)} · 디자인 산출물</h1>
    <p>화면 ${screens.size} · 변형 ${totalVariants} · 전이 ${transitionCount} · 여정 보드 ${built.length}</p>
  </header>
  ${journeySection}
  <section>
    <h2>화면 <small>화면 안</small></h2>
    <div class="cards">
      <a class="card" href="boards/screen-states.html">
        <span>변형 전수</span><strong>화면 변형 갤러리</strong>
        <small>화면 ${screens.size} · 변형 ${totalVariants}</small>
      </a>
    </div>
    <ul>
      ${screenLinks}
    </ul>
  </section>
  <footer>에이전트용 진입점은 <a href="README.md">README.md</a>입니다.</footer>
</body>
</html>
`;
}

let options;
try {
  options = parseCli();
} catch (error) {
  console.error(`[design-index] ${error.message}`);
  process.exit(1);
}

try {
  const models = readModels(options.projectRoot, options.uxFlow);
  const scan = scanScreens(options.projectRoot, { validateDrafts: false });
  if (scan.problems.length) throw new Error(scan.problems.join('\n'));
  warnEngineDrift(options.projectRoot);
  const journeys = resolveProjectJourneys(models, scan.screens);
  const boards = boardState(options.projectRoot, journeys);
  if (boards.missing.length) {
    throw new Error(
      `먼저 보드를 생성하십시오. 누락: ${boards.missing.join(', ')}`,
    );
  }
  const transitionCount = confirmedEdges(models, scan.screens).length;
  const command = regenerationCommand('build-design-index.mjs', models);
  const sourceHash = sha12(
    `${models.map(model => `${model.uxFlowHash}:${model.nameSource.hash}`).join(':')}:`
    + [...scan.screens.values()].map(screen => screen.hash).join(':'),
  );
  const input = {
    project: projectName(options.projectRoot),
    models,
    screens: scan.screens,
    journeys,
    transitionCount,
    command,
    sourceHash,
  };
  const designDir = join(options.projectRoot, 'docs', 'design-variants');
  const outputs = [
    { path: join(designDir, 'README.md'), content: renderReadme(input) },
    { path: join(designDir, 'index.html'), content: renderIndex(input) },
    {
      path: join(options.projectRoot, 'CLAUDE.md'),
      content: entryPoint(
        join(options.projectRoot, 'CLAUDE.md'),
        'docs/design-variants/README.md',
      ),
    },
    {
      path: join(options.projectRoot, 'docs', 'index.md'),
      content: entryPoint(
        join(options.projectRoot, 'docs', 'index.md'),
        'design-variants/README.md',
      ),
    },
  ];

  if (options.check) {
    const drift = outputs.filter(output =>
      !existsSync(output.path) || readFileSync(output.path, 'utf8') !== output.content);
    if (drift.length) {
      console.error(`[design-index] DRIFT — 재생성: ${command}`);
      process.exit(1);
    }
    console.log('[design-index] OK — 진입점과 프로젝트 포인터 일치');
    process.exit(0);
  }

  for (const output of outputs) writeFileSync(output.path, output.content);
  console.log('[design-index] README.md · index.html · 프로젝트 포인터 생성');
} catch (error) {
  console.error(`[design-index] ${error.message}`);
  process.exit(1);
}
