/* dcness-design-engine: 1.0.0
 * Project-agnostic design board engine: natural-size frames, derived layout,
 * pan/zoom, and collision-aware journey arrows.
 *
 * 프로젝트는 이 파일을 수정하지 않는다. plugin 배포본에서 갱신한다.
 */
(function () {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const BORDER = 1;
  const BOARD_PAD = 64;
  const CURVE_SAMPLES = 32;
  const ZOOM = { min: 0.08, max: 3 };
  const arrowSpecCache = new WeakMap();
  const geometryDiagnostics = new WeakMap();
  const labelWidthCache = new Map();
  let labelMeasureContext;
  let scale = 1;
  let panX = 0;
  let panY = 0;
  let theme;

  function cssVar(name, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }

  function readTheme() {
    theme = {
      background: cssVar('--dcness-canvas-bg', '#f4f4f6'),
      surface: cssVar('--dcness-canvas-surface', '#fff'),
      border: cssVar('--dcness-canvas-border', '#c8c8d0'),
      text: cssVar('--dcness-canvas-text', '#202027'),
      muted: cssVar('--dcness-canvas-muted', '#60606b'),
      arrow: cssVar('--dcness-canvas-arrow', '#6750a4'),
      label: cssVar('--dcness-canvas-label', '#fff'),
      font: cssVar('--dcness-canvas-font', 'system-ui, sans-serif'),
    };
  }

  function setupStage() {
    const stage = document.querySelector('.canvas');
    if (!stage) return null;
    Object.assign(stage.style, {
      position: 'fixed',
      inset: '0',
      overflow: 'hidden',
      background: theme.background,
      cursor: 'grab',
      userSelect: 'none',
    });
    const inner = document.createElement('div');
    inner.className = 'canvas-inner';
    Object.assign(inner.style, {
      position: 'absolute',
      left: '0',
      top: '0',
      transformOrigin: '0 0',
    });
    while (stage.firstChild) inner.appendChild(stage.firstChild);
    stage.appendChild(inner);
    return { stage, inner };
  }

  function frameSize(frame) {
    return {
      width: Number(frame.dataset.measuredWidth) || frame.clientWidth || 1,
      height: Number(frame.dataset.measuredHeight) || frame.clientHeight || 1,
    };
  }

  function styleFrame(frame) {
    const size = frameSize(frame);
    Object.assign(frame.style, {
      width: `${size.width}px`,
      height: `${size.height}px`,
      border: `${BORDER}px solid ${theme.border}`,
      borderRadius: '.55rem',
      background: theme.surface,
      boxSizing: 'content-box',
    });
  }

  function uniqueInOrder(values) {
    return [...new Set(values.filter(Boolean))];
  }

  function layoutVariantGrid(grid) {
    const frames = [...grid.querySelectorAll(':scope > .variant-frame')];
    const columns = uniqueInOrder(frames.map(frame => frame.dataset.axisColumn));
    const rows = uniqueInOrder(frames.map(frame => frame.dataset.axisRow));
    Object.assign(grid.style, {
      display: 'grid',
      gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, max-content)`,
      gap: '1rem',
      alignItems: 'start',
    });
    for (const frame of frames) {
      const column = Math.max(columns.indexOf(frame.dataset.axisColumn), 0) + 1;
      const row = Math.max(rows.indexOf(frame.dataset.axisRow), 0) + 1;
      frame.style.gridColumn = String(column);
      frame.style.gridRow = String(row);
      frame.querySelectorAll('iframe').forEach(styleFrame);
    }
  }

  function variantSignature(variants) {
    return JSON.stringify(variants.map(variant => ({
      id: variant.id,
      axes: variant.axes || {},
    })));
  }

  function seedFrameSize(node, frame) {
    const measured = node.querySelector(
      'iframe[data-measured-width][data-measured-height]',
    );
    if (!measured) return;
    frame.dataset.measuredWidth = measured.dataset.measuredWidth;
    frame.dataset.measuredHeight = measured.dataset.measuredHeight;
  }

  function syncVariantFrames(node, variants) {
    if (!node.dataset.screenSrc || !Array.isArray(variants) || !variants.length) {
      return false;
    }
    const signature = variantSignature(variants);
    if (node.dataset.runtimeVariantSignature === signature) return false;
    node.dataset.runtimeVariantSignature = signature;

    const existing = new Map(
      [...node.querySelectorAll('.variant-frame')].map(frame => [
        frame.dataset.variantId,
        frame,
      ]),
    );
    node.querySelectorAll(':scope > .variant-grid, :scope > .variant-facet')
      .forEach(element => element.remove());

    const axes = [];
    for (const variant of variants) {
      for (const axis of Object.keys(variant.axes || {})) {
        if (!axes.includes(axis)) axes.push(axis);
      }
    }
    const columnAxis = axes[0] || 'variant';
    const rowAxis = axes[1] || '';
    const facetAxes = axes.slice(2);
    const groups = new Map();
    for (const variant of variants) {
      const facet = facetAxes
        .map(axis => `${axis}=${variant.axes?.[axis] || ''}`)
        .join(';');
      if (!groups.has(facet)) groups.set(facet, []);
      groups.get(facet).push(variant);
    }

    const caption = node.querySelector(':scope > .node-caption');
    for (const [facet, members] of groups) {
      if (facet) {
        const heading = document.createElement('h3');
        heading.className = 'variant-facet';
        heading.textContent = facet;
        node.insertBefore(heading, caption);
      }
      const grid = document.createElement('div');
      grid.className = 'variant-grid';
      grid.dataset.columnAxis = columnAxis;
      grid.dataset.rowAxis = rowAxis;
      for (const variant of members) {
        let frame = existing.get(variant.id);
        if (!frame) {
          frame = document.createElement('figure');
          frame.className = 'variant-frame';
          frame.dataset.variantId = variant.id;
          const label = document.createElement('figcaption');
          label.textContent = variant.id;
          const iframe = document.createElement('iframe');
          iframe.src = `${node.dataset.screenSrc}#only=${encodeURIComponent(variant.id)}`;
          iframe.title = `${node.dataset.nodeId} ${variant.id}`;
          seedFrameSize(node, iframe);
          frame.append(label, iframe);
        }
        frame.dataset.axisColumn = variant.axes?.[columnAxis] || variant.id;
        frame.dataset.axisRow = rowAxis ? variant.axes?.[rowAxis] || '' : '';
        grid.appendChild(frame);
      }
      node.insertBefore(grid, caption);
      layoutVariantGrid(grid);
    }
    node.dataset.variants = variants.map(variant => variant.id).join(' / ');
    return true;
  }

  function removeCaption(node) {
    node.querySelector(':scope > .node-caption')?.remove();
  }

  function buildCaption(node) {
    removeCaption(node);
    const caption = document.createElement('div');
    caption.className = 'node-caption';
    Object.assign(caption.style, {
      marginTop: '.7rem',
      padding: '.75rem .9rem',
      border: `1px solid ${theme.border}`,
      borderRadius: '.55rem',
      background: theme.surface,
      color: theme.text,
      fontFamily: theme.font,
      maxWidth: `${Math.max(node.scrollWidth, 1)}px`,
    });
    const title = document.createElement('strong');
    title.textContent = node.dataset.title || node.dataset.nodeId || 'screen';
    caption.appendChild(title);
    if (node.dataset.desc) {
      const description = document.createElement('p');
      description.textContent = node.dataset.desc;
      Object.assign(description.style, {
        margin: '.3rem 0 0',
        color: theme.muted,
        fontSize: '.82rem',
      });
      caption.appendChild(description);
    }
    if (node.dataset.variants) {
      const variants = document.createElement('p');
      variants.textContent = node.dataset.variants;
      Object.assign(variants.style, {
        margin: '.45rem 0 0',
        color: theme.arrow,
        fontSize: '.75rem',
      });
      caption.appendChild(variants);
    }
    node.appendChild(caption);
  }

  function prepareNodes(inner) {
    const nodes = [...inner.querySelectorAll('.screen-node')];
    for (const node of nodes) {
      node.querySelectorAll('.variant-grid').forEach(layoutVariantGrid);
      node.querySelectorAll('iframe').forEach(styleFrame);
      Object.assign(node.style, {
        position: 'absolute',
        left: '0',
        top: '0',
        zIndex: '2',
        width: 'max-content',
      });
      buildCaption(node);
    }
    return nodes;
  }

  function readArrowSpecs(svg) {
    if (!arrowSpecCache.has(svg)) {
      arrowSpecCache.set(svg, [...svg.querySelectorAll(':scope > path')].map(path => ({
        from: path.dataset.from,
        to: path.dataset.to,
        label: path.dataset.label || '',
        fullLabel: path.dataset.labelFull || path.dataset.label || '',
      })));
    }
    return arrowSpecCache.get(svg);
  }

  function arrowLabelGap(inner) {
    const svg = inner.querySelector('.flow-arrows');
    const labels = svg
      ? readArrowSpecs(svg).map(spec => spec.label)
      : [];
    if (!labels.length) return 96;
    return Math.ceil(Math.max(...labels.map(label => labelTextWidth(label, 13))) + 48);
  }

  function labelTextWidth(label, fontSize = 12) {
    const key = `${fontSize}:${label}`;
    if (labelWidthCache.has(key)) return labelWidthCache.get(key);
    labelMeasureContext ||= document.createElement('canvas').getContext('2d');
    let width;
    if (labelMeasureContext) {
      labelMeasureContext.font = `${fontSize}px ${theme.font}`;
      width = labelMeasureContext.measureText(label).width;
    } else {
      width = [...label].length * fontSize;
    }
    labelWidthCache.set(key, width);
    return width;
  }

  function layoutNodes(stage, inner, nodes) {
    const boardKind = stage.dataset.boardKind;
    const gap = arrowLabelGap(inner);
    const sizes = nodes.map(node => ({
      node,
      width: Math.max(node.scrollWidth, 1),
      height: Math.max(node.scrollHeight, 1),
    }));
    if (boardKind === 'screen-states') {
      let top = 0;
      for (const item of sizes) {
        item.node.style.left = '0px';
        item.node.style.top = `${top}px`;
        top += item.height + gap;
      }
      return;
    }

    const columns = Math.max(1, Math.ceil(Math.sqrt(sizes.length)));
    const columnWidths = Array(columns).fill(0);
    const rows = Math.ceil(sizes.length / columns);
    const rowHeights = Array(rows).fill(0);
    const placements = sizes.map((item, index) => {
      const row = Math.floor(index / columns);
      const offset = index % columns;
      const column = row % 2 === 0 ? offset : columns - 1 - offset;
      columnWidths[column] = Math.max(columnWidths[column], item.width);
      rowHeights[row] = Math.max(rowHeights[row], item.height);
      return { ...item, row, column };
    });
    const lefts = [];
    const tops = [];
    let left = 0;
    for (const width of columnWidths) {
      lefts.push(left);
      left += width + gap;
    }
    let top = 0;
    for (const height of rowHeights) {
      tops.push(top);
      top += height + gap;
    }
    for (const item of placements) {
      item.node.style.left = `${lefts[item.column]}px`;
      item.node.style.top = `${tops[item.row]}px`;
    }
  }

  function boardBounds(inner) {
    const nodes = [...inner.querySelectorAll('.screen-node')];
    const right = Math.max(0, ...nodes.map(node => node.offsetLeft + node.offsetWidth));
    const bottom = Math.max(0, ...nodes.map(node => node.offsetTop + node.offsetHeight));
    return { width: right + BOARD_PAD * 2, height: bottom + BOARD_PAD * 2 };
  }

  function sizeInner(inner) {
    const bounds = boardBounds(inner);
    inner.style.width = `${bounds.width}px`;
    inner.style.height = `${bounds.height}px`;
    const svg = inner.querySelector('.flow-arrows');
    if (svg) {
      Object.assign(svg.style, {
        position: 'absolute',
        inset: '0',
        width: `${bounds.width}px`,
        height: `${bounds.height}px`,
        overflow: 'visible',
        pointerEvents: 'none',
        zIndex: '1',
      });
      svg.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
    }
  }

  function nodeBox(inner, id) {
    const escaped = window.CSS?.escape ? CSS.escape(id) : id.replace(/["\\]/g, '\\$&');
    const node = inner.querySelector(`.screen-node[data-node-id="${escaped}"]`);
    if (!node) return null;
    return {
      id,
      x: node.offsetLeft,
      y: node.offsetTop,
      width: node.offsetWidth,
      height: node.offsetHeight,
    };
  }

  function anchors(from, to) {
    const fromCenter = { x: from.x + from.width / 2, y: from.y + from.height / 2 };
    const toCenter = { x: to.x + to.width / 2, y: to.y + to.height / 2 };
    const horizontal = Math.abs(toCenter.x - fromCenter.x) >= Math.abs(toCenter.y - fromCenter.y);
    if (horizontal) {
      const direction = toCenter.x >= fromCenter.x ? 1 : -1;
      return {
        direction: 'horizontal',
        start: { x: fromCenter.x + direction * from.width / 2, y: fromCenter.y },
        end: { x: toCenter.x - direction * to.width / 2, y: toCenter.y },
      };
    }
    const direction = toCenter.y >= fromCenter.y ? 1 : -1;
    return {
      direction: 'vertical',
      start: { x: fromCenter.x, y: fromCenter.y + direction * from.height / 2 },
      end: { x: toCenter.x, y: toCenter.y - direction * to.height / 2 },
    };
  }

  function curve(anchor, bend) {
    const reach = Math.max(
      60,
      Math.hypot(anchor.end.x - anchor.start.x, anchor.end.y - anchor.start.y) / 3,
    );
    if (anchor.direction === 'horizontal') {
      const direction = Math.sign(anchor.end.x - anchor.start.x) || 1;
      return {
        p0: anchor.start,
        c1: { x: anchor.start.x + direction * reach, y: anchor.start.y + bend },
        c2: { x: anchor.end.x - direction * reach, y: anchor.end.y + bend },
        p3: anchor.end,
      };
    }
    const direction = Math.sign(anchor.end.y - anchor.start.y) || 1;
    return {
      p0: anchor.start,
      c1: { x: anchor.start.x + bend, y: anchor.start.y + direction * reach },
      c2: { x: anchor.end.x + bend, y: anchor.end.y - direction * reach },
      p3: anchor.end,
    };
  }

  function pointAt(value, time) {
    const inverse = 1 - time;
    const a = inverse ** 3;
    const b = 3 * inverse ** 2 * time;
    const c = 3 * inverse * time ** 2;
    const d = time ** 3;
    return {
      x: a * value.p0.x + b * value.c1.x + c * value.c2.x + d * value.p3.x,
      y: a * value.p0.y + b * value.c1.y + c * value.c2.y + d * value.p3.y,
    };
  }

  function pathData(value) {
    return `M${value.p0.x},${value.p0.y} C${value.c1.x},${value.c1.y} ${value.c2.x},${value.c2.y} ${value.p3.x},${value.p3.y}`;
  }

  function overlaps(left, right) {
    return left.x < right.x + right.width
      && left.x + left.width > right.x
      && left.y < right.y + right.height
      && left.y + left.height > right.y;
  }

  function labelBox(spec, value) {
    if (!spec.label) return null;
    const point = pointAt(value, 0.5);
    const width = Math.max(44, labelTextWidth(spec.label) + 18);
    return { x: point.x - width / 2, y: point.y - 12, width, height: 24 };
  }

  function curveHitsBox(value, box) {
    for (let index = 1; index < CURVE_SAMPLES; index += 1) {
      const point = pointAt(value, index / CURVE_SAMPLES);
      if (
        point.x > box.x + 3
        && point.x < box.x + box.width - 3
        && point.y > box.y + 3
        && point.y < box.y + box.height - 3
      ) return true;
    }
    return false;
  }

  function chooseCurve(spec, anchor, nodeBoxes, labels) {
    const step = Math.max(80, arrowLabelGap(document));
    const candidates = [0];
    for (let index = 1; index <= 20; index += 1) candidates.push(index * step, -index * step);
    let best = null;
    for (const bend of candidates) {
      const value = curve(anchor, bend);
      const label = labelBox(spec, value);
      const nodeHits = nodeBoxes.filter(box =>
        box.id !== spec.from && box.id !== spec.to && curveHitsBox(value, box)).length;
      const labelHits = label
        ? nodeBoxes.filter(box => overlaps(label, box)).length
          + labels.filter(box => overlaps(label, box)).length
        : 0;
      const score = nodeHits * 10 + labelHits * 5;
      if (!score) return { value, label, bend };
      if (!best || score < best.score) best = { value, label, bend, score };
    }
    return best;
  }

  function drawLabel(group, spec, box) {
    if (!box) return;
    const rect = document.createElementNS(SVG_NS, 'rect');
    rect.setAttribute('x', String(box.x));
    rect.setAttribute('y', String(box.y));
    rect.setAttribute('width', String(box.width));
    rect.setAttribute('height', String(box.height));
    rect.setAttribute('rx', '12');
    rect.setAttribute('fill', theme.label);
    rect.setAttribute('stroke', theme.arrow);
    const text = document.createElementNS(SVG_NS, 'text');
    text.setAttribute('x', String(box.x + box.width / 2));
    text.setAttribute('y', String(box.y + 16));
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-family', theme.font);
    text.setAttribute('font-size', '12');
    text.setAttribute('fill', theme.text);
    text.textContent = spec.label;
    group.append(rect, text);
  }

  function drawArrows(inner) {
    const svg = inner.querySelector('.flow-arrows');
    if (!svg) {
      geometryDiagnostics.set(inner, {
        arrowCount: 0,
        arrowNodeHits: 0,
        labelNodeHits: 0,
        labelPairHits: 0,
      });
      return;
    }
    const specs = readArrowSpecs(svg);
    svg.replaceChildren();
    const defs = document.createElementNS(SVG_NS, 'defs');
    defs.innerHTML = `<marker id="dcness-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${theme.arrow}"/></marker>`;
    svg.appendChild(defs);
    const nodeBoxes = [...inner.querySelectorAll('.screen-node')].map(node => ({
      id: node.dataset.nodeId,
      x: node.offsetLeft,
      y: node.offsetTop,
      width: node.offsetWidth,
      height: node.offsetHeight,
    }));
    const labels = [];
    let arrowCount = 0;
    let arrowNodeHits = 0;
    let labelNodeHits = 0;
    for (const spec of specs) {
      const from = nodeBox(inner, spec.from);
      const to = nodeBox(inner, spec.to);
      if (!from || !to) continue;
      const selected = chooseCurve(spec, anchors(from, to), nodeBoxes, labels);
      arrowCount += 1;
      arrowNodeHits += nodeBoxes.filter(box =>
        box.id !== spec.from
        && box.id !== spec.to
        && curveHitsBox(selected.value, box)).length;
      labelNodeHits += selected.label
        ? nodeBoxes.filter(box => overlaps(selected.label, box)).length
        : 0;
      if (selected.label) labels.push(selected.label);
      const group = document.createElementNS(SVG_NS, 'g');
      group.classList.add('flow-arrow');
      group.dataset.from = spec.from;
      group.dataset.to = spec.to;
      group.dataset.bend = String(selected.bend);
      const title = document.createElementNS(SVG_NS, 'title');
      title.textContent = spec.fullLabel;
      const path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', pathData(selected.value));
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', theme.arrow);
      path.setAttribute('stroke-width', '2.5');
      path.setAttribute('marker-end', 'url(#dcness-arrow)');
      group.append(title, path);
      drawLabel(group, spec, selected.label);
      svg.appendChild(group);
    }
    let labelPairHits = 0;
    for (let left = 0; left < labels.length; left += 1) {
      for (let right = left + 1; right < labels.length; right += 1) {
        if (overlaps(labels[left], labels[right])) labelPairHits += 1;
      }
    }
    geometryDiagnostics.set(inner, {
      arrowCount,
      arrowNodeHits,
      labelNodeHits,
      labelPairHits,
    });
  }

  function applyTransform(inner) {
    inner.style.transform = `translate(${panX}px,${panY}px) scale(${scale})`;
  }

  function zoomToFit(stage, inner) {
    const bounds = boardBounds(inner);
    if (!bounds.width || !bounds.height) return;
    scale = Math.min(
      1,
      Math.max(
        ZOOM.min,
        Math.min((stage.clientWidth - 32) / bounds.width, (stage.clientHeight - 32) / bounds.height),
      ),
    );
    panX = (stage.clientWidth - bounds.width * scale) / 2;
    panY = (stage.clientHeight - bounds.height * scale) / 2;
    applyTransform(inner);
  }

  function setupPanZoom(stage, inner) {
    let drag = null;
    stage.addEventListener('pointerdown', event => {
      drag = { x: event.clientX, y: event.clientY, panX, panY };
      stage.setPointerCapture(event.pointerId);
      stage.style.cursor = 'grabbing';
    });
    stage.addEventListener('pointermove', event => {
      if (!drag) return;
      panX = drag.panX + event.clientX - drag.x;
      panY = drag.panY + event.clientY - drag.y;
      applyTransform(inner);
    });
    stage.addEventListener('pointerup', () => {
      drag = null;
      stage.style.cursor = 'grab';
    });
    stage.addEventListener('wheel', event => {
      event.preventDefault();
      const previous = scale;
      scale = Math.min(ZOOM.max, Math.max(ZOOM.min, scale * Math.exp(-event.deltaY * 0.001)));
      const rect = stage.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      panX = x - (x - panX) * (scale / previous);
      panY = y - (y - panY) * (scale / previous);
      applyTransform(inner);
    }, { passive: false });
  }

  function setupSizeReports(inner, relayout) {
    window.addEventListener('message', event => {
      const data = event.data;
      if (!data || data.type !== 'dcness-frame-size') return;
      const frame = [...inner.querySelectorAll('iframe')]
        .find(candidate => candidate.contentWindow === event.source);
      if (!frame) return;
      const width = Number(data.width);
      const height = Number(data.height);
      if (!width || !height) return;
      const sizeChanged = (
        frame.dataset.measuredWidth !== String(width)
        || frame.dataset.measuredHeight !== String(height)
      );
      if (sizeChanged) {
        frame.dataset.measuredWidth = String(width);
        frame.dataset.measuredHeight = String(height);
      }
      const node = frame.closest('.screen-node');
      const variantsChanged = node && syncVariantFrames(node, data.variants);
      if (sizeChanged || variantsChanged) {
        relayout();
      }
    });
    function requestSize(frame) {
      if (!frame.dataset.sizeRequestBound) {
        frame.dataset.sizeRequestBound = 'true';
        frame.addEventListener('load', () => requestSize(frame));
      }
      frame.contentWindow?.postMessage({ type: 'dcness-request-frame-size' }, '*');
    }
    const observer = new MutationObserver(records => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches('iframe')) requestSize(node);
          node.querySelectorAll?.('iframe').forEach(requestSize);
        }
      }
    });
    observer.observe(inner, { childList: true, subtree: true });
    inner.querySelectorAll('iframe').forEach(requestSize);
  }

  function diagnostics(inner) {
    return {
      frames: [...inner.querySelectorAll('iframe')].map(frame => {
        const root = frame.contentDocument?.documentElement;
        return {
          src: frame.getAttribute('src'),
          width: frame.clientWidth,
          height: frame.clientHeight,
          scrollWidth: root?.scrollWidth ?? null,
          scrollHeight: root?.scrollHeight ?? null,
          hasInternalScroll: root
            ? (
              root.scrollWidth > frame.clientWidth
              || root.scrollHeight > frame.clientHeight
            )
            : null,
        };
      }),
      variantFrames: [...inner.querySelectorAll('.variant-frame')].map(frame => ({
        nodeId: frame.closest('.screen-node')?.dataset.nodeId || '',
        id: frame.dataset.variantId || '',
        column: frame.dataset.axisColumn || '',
        row: frame.dataset.axisRow || '',
        left: frame.offsetLeft,
        top: frame.offsetTop,
        width: frame.offsetWidth,
        height: frame.offsetHeight,
      })),
      arrows: [...inner.querySelectorAll('.flow-arrow')].map(arrow => ({
        from: arrow.dataset.from,
        to: arrow.dataset.to,
        bend: Number(arrow.dataset.bend),
      })),
      geometry: geometryDiagnostics.get(inner) || {
        arrowCount: 0,
        arrowNodeHits: 0,
        labelNodeHits: 0,
        labelPairHits: 0,
      },
    };
  }

  function init() {
    readTheme();
    const context = setupStage();
    if (!context) return;
    const { stage, inner } = context;
    function relayout() {
      const nodes = prepareNodes(inner);
      layoutNodes(stage, inner, nodes);
      sizeInner(inner);
      drawArrows(inner);
      applyTransform(inner);
    }
    relayout();
    setupSizeReports(inner, relayout);
    setupPanZoom(stage, inner);
    window.dcnessCanvasDiagnostics = () => diagnostics(inner);
    setTimeout(() => {
      relayout();
      zoomToFit(stage, inner);
    }, 250);
    window.addEventListener('load', () => {
      relayout();
      zoomToFit(stage, inner);
    });
    window.addEventListener('resize', () => zoomToFit(stage, inner));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
