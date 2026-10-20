/* dcness-design-engine: 1.1.0
 * #only=<data-variant> 요청을 같은 확정본 안의 변형 하나로 좁힌다.
 */
(function () {
  'use strict';

  const WARNING_ID = 'dcness-variant-warning';
  const STYLE_ID = 'dcness-only-variant-style';
  const HIDDEN_ATTR = 'data-dcness-hidden';

  function requestedVariant() {
    return new URLSearchParams(location.hash.replace(/^#/, '')).get('only');
  }

  function warning(message) {
    let banner = document.getElementById(WARNING_ID);
    if (!banner) {
      banner = document.createElement('div');
      banner.id = WARNING_ID;
      Object.assign(banner.style, {
        position: 'fixed',
        inset: '0 auto auto 0',
        zIndex: '2147483647',
        padding: '12px 16px',
        background: '#b42318',
        color: '#fff',
        font: '600 14px/1.4 system-ui, sans-serif',
      });
      document.body.appendChild(banner);
    }
    banner.textContent = message;
  }

  // 목업의 author CSS(예: [data-variant] { display: flex })는 브라우저 기본
  // [hidden] { display: none } 보다 우선한다. 숨김 표시는 !important 규칙으로 덮는다.
  function ensureHiddenStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `[${HIDDEN_ATTR}] { display: none !important; }`;
    (document.head || document.documentElement).appendChild(style);
  }

  // 요청한 변형으로 가는 경로 밖에서 다른 변형을 담은 요소를 통째로 숨긴다.
  // 변형과 그 제목 줄을 함께 감싼 묶음은 제목 줄까지 함께 사라진다.
  function hideOtherVariantGroups(kept) {
    for (let node = kept; node && node !== document.body; node = node.parentElement) {
      const parentElement = node.parentElement;
      if (!parentElement) break;
      for (const sibling of parentElement.children) {
        if (sibling === node) continue;
        if (sibling.matches('[data-variant]') || sibling.querySelector('[data-variant]')) {
          sibling.setAttribute(HIDDEN_ATTR, '');
        }
      }
    }
  }

  function apply() {
    document.getElementById(WARNING_ID)?.remove();
    const requested = requestedVariant();
    const variants = [...document.querySelectorAll('[data-variant]')];
    variants.forEach(element => { element.hidden = false; });
    document.querySelectorAll(`[${HIDDEN_ATTR}]`).forEach(element => {
      element.removeAttribute(HIDDEN_ATTR);
    });
    delete document.documentElement.dataset.dcnessOnlyVariant;
    if (!requested) return;
    const matched = variants.filter(element => element.dataset.variant === requested);
    if (matched.length !== 1) {
      warning(
        `요청한 변형 "${requested}"을 찾지 못했습니다. 사용 가능: `
        + (variants.map(element => element.dataset.variant).join(', ') || '없음'),
      );
      return;
    }
    ensureHiddenStyle();
    variants.forEach(element => {
      element.hidden = element !== matched[0];
      if (element !== matched[0]) element.setAttribute(HIDDEN_ATTR, '');
    });
    hideOtherVariantGroups(matched[0]);
    document.documentElement.dataset.dcnessOnlyVariant = requested;
  }

  window.addEventListener('hashchange', apply);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
})();
