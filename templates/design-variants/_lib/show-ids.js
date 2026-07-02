/* docs/design-variants/_lib/show-ids.js
 * dcness plug-in 시드 — Show IDs 토글 + URL hash highlight.
 * 각 docs/design-variants/<screen-id>.html 가 <script defer src="_lib/show-ids.js"> 로 import.
 * draft HTML(docs/design-variants/drafts/) 은 ../_lib/show-ids.js 로 import 하고,
 * canvas-design 승격 단계에서 _lib/show-ids.js 로 정규화한다.
 *
 * 사용:
 *   1) 우상단 "Show IDs" 토글 → 모든 [data-node-id] 에 floating label overlay
 *   2) URL hash 입력 (예: payment-confirm-v1.html#payment-confirm.actions.receipt-btn)
 *      → 해당 노드 outline + scroll into view
 *   3) postMessage('show-ids:on'|'show-ids:off') 수신 — canvas.html 이 iframe 일괄 토글 시 사용
 */
(function () {
  'use strict';

  const STYLE_ID = 'dcness-show-ids-style';
  const TOGGLE_ID = 'dcness-show-ids-toggle';
  const ON_CLASS = 'dcness-show-ids';

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = `
      #${TOGGLE_ID} { position: fixed; top: 8px; right: 8px; z-index: 99999;
        font: 12px/1 system-ui, sans-serif; padding: 4px 8px; background: #1c1b1f; color: #fff;
        border: 0; border-radius: 4px; cursor: pointer; opacity: 0.6; }
      #${TOGGLE_ID}:hover { opacity: 1; }
      .${ON_CLASS} [data-node-id] { outline: 1px dashed rgba(103,80,164,0.5); position: relative; }
      .${ON_CLASS} [data-node-id]::after {
        content: attr(data-node-id);
        position: absolute; top: 0; left: 0; z-index: 99998;
        font: 10px/1.4 ui-monospace, monospace;
        background: rgba(28,27,31,0.85); color: #fff; padding: 2px 4px;
        pointer-events: none; white-space: nowrap;
      }
      [data-node-id].dcness-hash-highlight {
        outline: 2px solid #6750A4 !important; outline-offset: 2px;
      }
    `;
    document.head.appendChild(s);
  }

  function injectToggle() {
    if (document.getElementById(TOGGLE_ID)) return;
    const btn = document.createElement('button');
    btn.id = TOGGLE_ID;
    btn.type = 'button';
    btn.textContent = 'Show IDs';
    btn.addEventListener('click', () => toggle(!isOn()));
    document.body.appendChild(btn);
  }

  function isOn() { return document.documentElement.classList.contains(ON_CLASS); }

  function toggle(on) {
    document.documentElement.classList.toggle(ON_CLASS, on);
    const btn = document.getElementById(TOGGLE_ID);
    if (btn) btn.textContent = on ? 'Hide IDs' : 'Show IDs';
  }

  function applyHashHighlight() {
    document.querySelectorAll('.dcness-hash-highlight').forEach(n => n.classList.remove('dcness-hash-highlight'));
    const id = decodeURIComponent((location.hash || '').replace(/^#/, ''));
    if (!id) return;
    const target = document.querySelector(`[data-node-id="${CSS.escape(id)}"]`);
    if (!target) return;
    target.classList.add('dcness-hash-highlight');
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  window.addEventListener('hashchange', applyHashHighlight);
  window.addEventListener('message', (e) => {
    if (e.data === 'show-ids:on') toggle(true);
    else if (e.data === 'show-ids:off') toggle(false);
  });

  function init() {
    injectStyle();
    injectToggle();
    applyHashHighlight();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
