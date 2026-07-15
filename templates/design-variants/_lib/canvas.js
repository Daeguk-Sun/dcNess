/* docs/design-variants/_lib/canvas.js
 * dcness plug-in seed: pan/zoom design flow board.
 *
 *   <div class="screen-node" data-node-id="..." data-pos="<col>,<row>"
 *        data-title="..." data-desc="..." data-states="..." data-h="900">
 *     <iframe src="<screen-id>.html"></iframe>
 *   </div>
 *
 * Optional arrows:
 *   <svg class="flow-arrows">
 *     <path data-from="A" data-to="B" data-label="..." data-bend="0"/>
 *   </svg>
 *
 * Theme hooks:
 *   --dcness-canvas-arrow, --dcness-canvas-font, --dcness-canvas-bg
 */
(function () {
  'use strict';

  const GRID_COLS = 4;
  const FLOW_NODE_W = 390;
  const FLOW_FRAME_H = 900;
  const FLOW_GAP_X = 150;
  const FLOW_GAP_Y = 120;
  const BOARD_PAD = 80;
  const ZOOM_MIN = 0.2;
  const ZOOM_MAX = 2;

  let zoom = 1, panX = 0, panY = 0;
  let theme = {};

  function cssVar(name, fallback) {
    const styles = window.getComputedStyle(document.documentElement);
    const value = styles.getPropertyValue(name).trim();
    return value || fallback;
  }

  function readTheme() {
    theme = {
      arrow: cssVar('--dcness-canvas-arrow', '#6750A4'),
      font: cssVar('--dcness-canvas-font', 'system-ui, sans-serif'),
      bg: cssVar('--dcness-canvas-bg', '#f5f5f7'),
      captionBg: cssVar('--dcness-canvas-caption-bg', '#ffffff'),
      captionBorder: cssVar('--dcness-canvas-caption-border', '#d0d0d5'),
      text: cssVar('--dcness-canvas-text', '#1f1f24'),
      muted: cssVar('--dcness-canvas-muted', '#54545c'),
      chipBg: cssVar('--dcness-canvas-chip-bg', '#efe7ff'),
      chipText: cssVar('--dcness-canvas-chip-text', '#4f378b'),
      labelBg: cssVar('--dcness-canvas-label-bg', '#ffffff'),
      labelBorder: cssVar('--dcness-canvas-label-border', '#d7c9ff')
    };
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function parsePositiveInt(value, fallback) {
    const parsed = parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  }

  function parsePos(value, fallbackCol, fallbackRow) {
    if (!value) return { col: fallbackCol, row: fallbackRow };
    const parts = value.split(',').map(n => parseInt(n.trim(), 10));
    return {
      col: Number.isFinite(parts[0]) && parts[0] >= 0 ? parts[0] : fallbackCol,
      row: Number.isFinite(parts[1]) && parts[1] >= 0 ? parts[1] : fallbackRow
    };
  }

  function setupStage() {
    const stage = document.querySelector('.canvas');
    if (!stage) return null;
    Object.assign(stage.style, {
      position: 'fixed',
      inset: '0',
      width: '100vw',
      height: '100vh',
      overflow: 'hidden',
      background: theme.bg,
      cursor: 'grab',
      userSelect: 'none'
    });
    const inner = document.createElement('div');
    inner.className = 'canvas-inner';
    Object.assign(inner.style, {
      position: 'absolute',
      top: '0',
      left: '0',
      transformOrigin: '0 0'
    });
    while (stage.firstChild) inner.appendChild(stage.firstChild);
    stage.appendChild(inner);
    return { stage, inner };
  }

  function buildCaption(node) {
    const old = node.querySelector('.node-caption');
    if (old) old.remove();

    const cap = document.createElement('div');
    cap.className = 'node-caption';
    Object.assign(cap.style, {
      width: FLOW_NODE_W + 'px',
      boxSizing: 'border-box',
      marginTop: '10px',
      padding: '12px 14px',
      background: theme.captionBg,
      border: '1px solid ' + theme.captionBorder,
      borderRadius: '8px',
      fontFamily: theme.font,
      boxShadow: '0 1px 3px rgba(0,0,0,.06)'
    });

    const title = document.createElement('div');
    title.textContent = node.dataset.title || node.dataset.nodeId || 'screen';
    Object.assign(title.style, {
      fontSize: '15px',
      fontWeight: '700',
      color: theme.text,
      lineHeight: '1.35'
    });
    cap.appendChild(title);

    if (node.dataset.desc) {
      const desc = document.createElement('div');
      desc.textContent = node.dataset.desc;
      Object.assign(desc.style, {
        fontSize: '13px',
        color: theme.muted,
        marginTop: '4px',
        lineHeight: '1.4'
      });
      cap.appendChild(desc);
    }

    if (node.dataset.states) {
      const states = document.createElement('div');
      Object.assign(states.style, {
        marginTop: '8px',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '5px'
      });
      node.dataset.states.split('/').forEach(raw => {
        const state = raw.trim();
        if (!state) return;
        const chip = document.createElement('span');
        chip.textContent = state;
        Object.assign(chip.style, {
          fontSize: '11px',
          lineHeight: '1.4',
          color: theme.chipText,
          background: theme.chipBg,
          borderRadius: '999px',
          padding: '2px 8px'
        });
        states.appendChild(chip);
      });
      cap.appendChild(states);
    }

    return cap;
  }

  function layoutScreenNodes(inner) {
    const nodes = Array.from(inner.querySelectorAll('.screen-node'));
    const placements = [];
    let nextCol = 0, nextRow = 0;

    nodes.forEach(node => {
      const pos = parsePos(node.dataset.pos, nextCol, nextRow);
      const frameH = parsePositiveInt(node.dataset.h, FLOW_FRAME_H);
      const iframe = node.querySelector('iframe');
      if (iframe) {
        Object.assign(iframe.style, {
          width: FLOW_NODE_W + 'px',
          height: frameH + 'px',
          border: '1px solid #c8cdd6',
          borderRadius: '8px',
          background: '#fff',
          display: 'block',
          boxSizing: 'border-box',
          boxShadow: '0 6px 24px rgba(0,0,0,.12)'
        });
      }

      node.appendChild(buildCaption(node));
      Object.assign(node.style, {
        position: 'absolute',
        width: FLOW_NODE_W + 'px',
        boxSizing: 'border-box',
        left: '0',
        top: '0',
        zIndex: '10'
      });

      placements.push({ node, col: pos.col, row: pos.row });
      nextCol++;
      if (nextCol >= GRID_COLS) { nextCol = 0; nextRow++; }
    });

    const maxRow = placements.reduce((max, item) => Math.max(max, item.row), 0);
    const rowHeights = new Map();
    placements.forEach(item => {
      rowHeights.set(item.row, Math.max(rowHeights.get(item.row) || 0, item.node.offsetHeight));
    });

    const rowTops = new Map();
    let top = 0;
    for (let row = 0; row <= maxRow; row++) {
      rowTops.set(row, top);
      top += (rowHeights.get(row) || (FLOW_FRAME_H + 100)) + FLOW_GAP_Y;
    }

    placements.forEach(item => {
      Object.assign(item.node.style, {
        left: (item.col * (FLOW_NODE_W + FLOW_GAP_X)) + 'px',
        top: (rowTops.get(item.row) || 0) + 'px'
      });
      item.node.addEventListener('click', event => {
        event.stopPropagation();
        focusNode(inner, item.node.dataset.nodeId);
      });
    });
  }

  function readArrowSpecs(inner) {
    const svg = inner.querySelector('svg.flow-arrows');
    if (!svg) return [];
    return Array.from(svg.querySelectorAll('path[data-from][data-to]')).map(path => ({
      from: path.dataset.from,
      to: path.dataset.to,
      label: path.dataset.label || '',
      bend: parseInt(path.dataset.bend, 10) || 0
    }));
  }

  function nodeBox(inner, id) {
    const escaped = cssEscape(id);
    const node = inner.querySelector(`.screen-node[data-node-id="${escaped}"]`);
    if (!node) return null;
    return {
      el: node,
      x: node.offsetLeft,
      y: node.offsetTop,
      w: node.offsetWidth,
      h: node.offsetHeight
    };
  }

  function boardItems(inner) {
    return Array.from(inner.querySelectorAll('.screen-node'));
  }

  function boardBounds(inner) {
    const items = boardItems(inner);
    if (!items.length) return { minX: 0, minY: 0, maxX: 0, maxY: 0, w: BOARD_PAD, h: BOARD_PAD };

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    items.forEach(item => {
      minX = Math.min(minX, item.offsetLeft);
      minY = Math.min(minY, item.offsetTop);
      maxX = Math.max(maxX, item.offsetLeft + item.offsetWidth);
      maxY = Math.max(maxY, item.offsetTop + item.offsetHeight);
    });
    return {
      minX,
      minY,
      maxX,
      maxY,
      w: maxX - minX + BOARD_PAD * 2,
      h: maxY - minY + BOARD_PAD * 2
    };
  }

  function sizeInner(inner) {
    const bounds = boardBounds(inner);
    inner.style.width = (bounds.maxX + BOARD_PAD) + 'px';
    inner.style.height = (bounds.maxY + BOARD_PAD) + 'px';
  }

  function anchors(from, to) {
    const fromCenter = { x: from.x + from.w / 2, y: from.y + from.h / 2 };
    const toCenter = { x: to.x + to.w / 2, y: to.y + to.h / 2 };
    const dx = toCenter.x - fromCenter.x;
    const dy = toCenter.y - fromCenter.y;
    let start, end, dir;

    if (Math.abs(dx) >= Math.abs(dy)) {
      dir = 'h';
      if (dx >= 0) {
        start = { x: from.x + from.w, y: fromCenter.y };
        end = { x: to.x, y: toCenter.y };
      } else {
        start = { x: from.x, y: fromCenter.y };
        end = { x: to.x + to.w, y: toCenter.y };
      }
    } else {
      dir = 'v';
      if (dy >= 0) {
        start = { x: fromCenter.x, y: from.y + from.h };
        end = { x: toCenter.x, y: to.y };
      } else {
        start = { x: fromCenter.x, y: from.y };
        end = { x: toCenter.x, y: to.y + to.h };
      }
    }

    return { start, end, dir };
  }

  function arrowPathData(anchor, bend) {
    const k = 70;
    let c1, c2;
    if (anchor.dir === 'h') {
      const sign = anchor.end.x >= anchor.start.x ? 1 : -1;
      c1 = { x: anchor.start.x + sign * k, y: anchor.start.y + bend };
      c2 = { x: anchor.end.x - sign * k, y: anchor.end.y + bend };
    } else {
      const sign = anchor.end.y >= anchor.start.y ? 1 : -1;
      c1 = { x: anchor.start.x + bend, y: anchor.start.y + sign * k };
      c2 = { x: anchor.end.x + bend, y: anchor.end.y - sign * k };
    }
    return `M${anchor.start.x},${anchor.start.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${anchor.end.x},${anchor.end.y}`;
  }

  function drawArrowLabel(group, spec, anchor) {
    if (!spec.label) return;
    const ns = 'http://www.w3.org/2000/svg';
    const bendOffset = spec.bend * 0.6;
    const mx = (anchor.start.x + anchor.end.x) / 2 + (anchor.dir === 'v' ? bendOffset : 0);
    const my = (anchor.start.y + anchor.end.y) / 2 + (anchor.dir === 'h' ? bendOffset : 0);
    const width = Math.max(34, spec.label.length * 13 + 18);

    const rect = document.createElementNS(ns, 'rect');
    rect.classList.add('flow-arrow-label-bg');
    rect.setAttribute('x', mx - width / 2);
    rect.setAttribute('y', my - 12);
    rect.setAttribute('width', width);
    rect.setAttribute('height', 22);
    rect.setAttribute('rx', 11);
    rect.setAttribute('fill', theme.labelBg);
    rect.setAttribute('stroke', theme.labelBorder);

    const text = document.createElementNS(ns, 'text');
    text.classList.add('flow-arrow-label-text');
    text.textContent = spec.label;
    text.setAttribute('x', mx);
    text.setAttribute('y', my + 4);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-family', theme.font);
    text.setAttribute('font-size', 13);
    text.setAttribute('font-weight', 600);
    text.setAttribute('fill', theme.chipText);

    group.appendChild(rect);
    group.appendChild(text);
  }

  function drawArrows(inner, specs) {
    const svg = inner.querySelector('svg.flow-arrows');
    if (!svg) return;

    const bounds = boardBounds(inner);
    Object.assign(svg.style, {
      position: 'absolute',
      top: '0',
      left: '0',
      overflow: 'visible',
      pointerEvents: 'none',
      zIndex: '5'
    });
    svg.setAttribute('width', bounds.maxX + BOARD_PAD);
    svg.setAttribute('height', bounds.maxY + BOARD_PAD);
    svg.innerHTML =
      '<defs><marker id="dcness-flow-arrow-head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">' +
      '<path d="M0,0 L10,5 L0,10 Z" fill="' + theme.arrow + '"/></marker></defs>';

    const ns = 'http://www.w3.org/2000/svg';
    specs.forEach(spec => {
      const from = nodeBox(inner, spec.from);
      const to = nodeBox(inner, spec.to);
      if (!from || !to) return;

      const anchor = anchors(from, to);
      const group = document.createElementNS(ns, 'g');
      group.classList.add('flow-arrow');
      group.dataset.from = spec.from;
      group.dataset.to = spec.to;
      group.dataset.label = spec.label;
      group.style.pointerEvents = 'auto';
      group.style.cursor = 'pointer';

      const path = document.createElementNS(ns, 'path');
      path.setAttribute('d', arrowPathData(anchor, spec.bend));
      path.setAttribute('stroke', theme.arrow);
      path.setAttribute('stroke-width', '2.5');
      path.setAttribute('fill', 'none');
      path.setAttribute('marker-end', 'url(#dcness-flow-arrow-head)');
      path.dataset.from = spec.from;
      path.dataset.to = spec.to;
      path.dataset.label = spec.label;
      path.style.pointerEvents = 'stroke';

      group.appendChild(path);
      drawArrowLabel(group, spec, anchor);
      group.addEventListener('click', event => {
        event.stopPropagation();
        focusEdge(inner, spec.from, spec.to);
      });
      svg.appendChild(group);
    });
  }

  function selectableNodes(inner) {
    return Array.from(inner.querySelectorAll('.screen-node'));
  }

  function nodeId(node) {
    return node.dataset.nodeId;
  }

  function styleNodeFocus(node, on, dim) {
    node.style.opacity = dim ? '0.45' : '1';
    node.style.outline = on ? '3px solid ' + theme.arrow : 'none';
    node.style.outlineOffset = '4px';
    node.style.borderRadius = on ? '8px' : '';
  }

  function focusNode(inner, id) {
    if (!id) return;
    selectableNodes(inner).forEach(node => {
      const connected = nodeId(node) === id;
      styleNodeFocus(node, connected, !connected);
    });
    inner.querySelectorAll('g.flow-arrow').forEach(group => {
      const on = group.dataset.from === id || group.dataset.to === id;
      group.style.opacity = on ? '1' : '0.2';
      const path = group.querySelector('path');
      if (path) path.setAttribute('stroke-width', on ? '4' : '1.5');
    });
  }

  function focusEdge(inner, fromId, toId) {
    selectableNodes(inner).forEach(node => {
      const id = nodeId(node);
      const on = id === fromId || id === toId;
      styleNodeFocus(node, on, !on);
    });
    inner.querySelectorAll('g.flow-arrow').forEach(group => {
      const on = group.dataset.from === fromId && group.dataset.to === toId;
      group.style.opacity = on ? '1' : '0.18';
      const path = group.querySelector('path');
      if (path) path.setAttribute('stroke-width', on ? '4' : '1.5');
    });
  }

  function clearFocus(inner) {
    selectableNodes(inner).forEach(node => styleNodeFocus(node, false, false));
    inner.querySelectorAll('g.flow-arrow').forEach(group => {
      group.style.opacity = '1';
      const path = group.querySelector('path');
      if (path) path.setAttribute('stroke-width', '2.5');
    });
  }

  function applyTransform(inner) {
    inner.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
  }

  function setupPanZoom(stage, inner) {
    let dragging = false, moved = false, lastX = 0, lastY = 0;
    stage.addEventListener('mousedown', event => {
      if (event.target.closest('iframe')) return;
      dragging = true;
      moved = false;
      lastX = event.clientX;
      lastY = event.clientY;
      stage.style.cursor = 'grabbing';
    });
    window.addEventListener('mousemove', event => {
      if (!dragging) return;
      panX += event.clientX - lastX;
      panY += event.clientY - lastY;
      lastX = event.clientX;
      lastY = event.clientY;
      moved = true;
      applyTransform(inner);
    });
    window.addEventListener('mouseup', () => {
      dragging = false;
      stage.style.cursor = 'grab';
    });
    stage.addEventListener('click', event => {
      if (!moved && !event.target.closest('.screen-node') && !event.target.closest('g.flow-arrow')) {
        clearFocus(inner);
      }
    });
    stage.addEventListener('wheel', event => {
      event.preventDefault();
      const next = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoom - event.deltaY * 0.0012));
      const rect = stage.getBoundingClientRect();
      const cx = event.clientX - rect.left;
      const cy = event.clientY - rect.top;
      panX = cx - (cx - panX) * (next / zoom);
      panY = cy - (cy - panY) * (next / zoom);
      zoom = next;
      applyTransform(inner);
    }, { passive: false });
  }

  function zoomToFit(stage, inner) {
    const items = boardItems(inner);
    if (!items.length) return;
    const bounds = boardBounds(inner);
    const vw = stage.clientWidth;
    const vh = stage.clientHeight;
    zoom = Math.min(vw / bounds.w, vh / bounds.h, 1);
    panX = (vw - bounds.w * zoom) / 2 - (bounds.minX - BOARD_PAD) * zoom;
    panY = (vh - bounds.h * zoom) / 2 - (bounds.minY - BOARD_PAD) * zoom;
    applyTransform(inner);
  }

  function setupShowIdsBroadcast(inner) {
    const observer = new MutationObserver(() => {
      const on = document.documentElement.classList.contains('dcness-show-ids');
      inner.querySelectorAll('iframe').forEach(frame => {
        try { frame.contentWindow.postMessage(on ? 'show-ids:on' : 'show-ids:off', '*'); } catch (_) {}
      });
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  }

  function init() {
    readTheme();
    const context = setupStage();
    if (!context) return;

    const { stage, inner } = context;
    const specs = readArrowSpecs(inner);
    layoutScreenNodes(inner);

    sizeInner(inner);
    drawArrows(inner, specs);
    setupPanZoom(stage, inner);
    setupShowIdsBroadcast(inner);
    applyTransform(inner);

    setTimeout(() => {
      sizeInner(inner);
      drawArrows(inner, specs);
      zoomToFit(stage, inner);
    }, 350);
    window.addEventListener('load', () => {
      sizeInner(inner);
      drawArrows(inner, specs);
      zoomToFit(stage, inner);
    });
    window.addEventListener('resize', () => zoomToFit(stage, inner));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
