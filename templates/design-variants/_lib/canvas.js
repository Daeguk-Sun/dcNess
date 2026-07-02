/* docs/design-variants/_lib/canvas.js
 * dcness plug-in 시드 — canvas.html 의 pan/zoom + iframe auto-layout + 직선 화살표.
 * canvas.html 가 <script defer src="_lib/canvas.js"> 로 import.
 *
 * canvas-design 승격 단계 책임:
 *   <iframe data-frame-id="..." src="<screen-id>.html"></iframe>  (좌표 X — auto-layout)
 *   <iframe data-frame-id="..." data-pos="<col>,<row>" src="..."></iframe>  (override 시만)
 *   <svg class="flow-arrows">
 *     <path data-from="A" data-to="B" data-label="..."/>
 *   </svg>  (화살표는 optional)
 *
 * 그리드: 화면 가로 = 390 (모바일) + 110 간격, 한 row 4 col, viewport=desktop 시 1280.
 */
(function () {
  'use strict';

  const VIEWPORT_W = { mobile: 390, tablet: 768, desktop: 1280 };
  const FRAME_H = 720;
  const GAP = 110;
  const COLS = 4;

  let zoom = 1, panX = 0, panY = 0;

  function setupStage() {
    const stage = document.querySelector('.canvas');
    if (!stage) return null;
    Object.assign(stage.style, {
      transformOrigin: '0 0', position: 'relative',
      width: '100vw', height: '100vh', overflow: 'hidden', background: '#f5f5f7'
    });
    const inner = document.createElement('div');
    inner.className = 'canvas-inner';
    Object.assign(inner.style, { position: 'absolute', top: '0', left: '0', transformOrigin: '0 0' });
    while (stage.firstChild) inner.appendChild(stage.firstChild);
    stage.appendChild(inner);
    return inner;
  }

  function layoutFrames(inner) {
    const frames = inner.querySelectorAll('iframe[data-frame-id]');
    let nextCol = 0, nextRow = 0;
    frames.forEach(f => {
      const vp = f.dataset.viewport || 'mobile';
      const w = VIEWPORT_W[vp] || VIEWPORT_W.mobile;
      let col, row;
      if (f.dataset.pos) {
        [col, row] = f.dataset.pos.split(',').map(n => parseInt(n.trim(), 10));
      } else {
        col = nextCol; row = nextRow;
        nextCol++;
        if (nextCol >= COLS) { nextCol = 0; nextRow++; }
      }
      Object.assign(f.style, {
        position: 'absolute',
        left: (col * (w + GAP)) + 'px',
        top: (row * (FRAME_H + GAP)) + 'px',
        width: w + 'px', height: FRAME_H + 'px',
        border: '1px solid #d0d0d5', background: '#fff'
      });
    });
  }

  function applyTransform(inner) {
    inner.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
  }

  function setupPanZoom(stage, inner) {
    let dragging = false, lastX = 0, lastY = 0;
    stage.addEventListener('mousedown', (e) => {
      if (e.target.closest('iframe')) return;
      dragging = true; lastX = e.clientX; lastY = e.clientY;
      stage.style.cursor = 'grabbing';
    });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      panX += e.clientX - lastX; panY += e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      applyTransform(inner);
    });
    window.addEventListener('mouseup', () => { dragging = false; stage.style.cursor = ''; });
    stage.addEventListener('wheel', (e) => {
      e.preventDefault();
      const delta = -e.deltaY * 0.001;
      const next = Math.max(0.2, Math.min(2, zoom + delta));
      const rect = stage.getBoundingClientRect();
      const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
      panX = cx - (cx - panX) * (next / zoom);
      panY = cy - (cy - panY) * (next / zoom);
      zoom = next;
      applyTransform(inner);
    }, { passive: false });
  }

  function drawArrows(inner) {
    const svg = inner.querySelector('svg.flow-arrows');
    if (!svg) return;
    Object.assign(svg.style, { position: 'absolute', top: '0', left: '0', overflow: 'visible', pointerEvents: 'none' });
    svg.setAttribute('width', '100%'); svg.setAttribute('height', '100%');
    if (!svg.querySelector('defs')) {
      svg.insertAdjacentHTML('afterbegin',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 Z" fill="#6750A4"/></marker></defs>');
    }
    svg.querySelectorAll('path[data-from][data-to]').forEach(p => {
      const from = inner.querySelector(`iframe[data-frame-id="${CSS.escape(p.dataset.from)}"]`);
      const to = inner.querySelector(`iframe[data-frame-id="${CSS.escape(p.dataset.to)}"]`);
      if (!from || !to) return;
      const fx = from.offsetLeft + from.offsetWidth, fy = from.offsetTop + from.offsetHeight / 2;
      const tx = to.offsetLeft, ty = to.offsetTop + to.offsetHeight / 2;
      p.setAttribute('d', `M${fx},${fy} L${tx},${ty}`);
      p.setAttribute('stroke', '#6750A4'); p.setAttribute('stroke-width', '2');
      p.setAttribute('fill', 'none'); p.setAttribute('marker-end', 'url(#arrow)');
    });
  }

  function setupShowIdsBroadcast(inner) {
    const observer = new MutationObserver(() => {
      const on = document.documentElement.classList.contains('dcness-show-ids');
      inner.querySelectorAll('iframe').forEach(f => {
        try { f.contentWindow.postMessage(on ? 'show-ids:on' : 'show-ids:off', '*'); } catch (_) {}
      });
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  }

  function init() {
    const inner = setupStage();
    if (!inner) return;
    layoutFrames(inner);
    drawArrows(inner);
    setupPanZoom(document.querySelector('.canvas'), inner);
    setupShowIdsBroadcast(inner);
    applyTransform(inner);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
