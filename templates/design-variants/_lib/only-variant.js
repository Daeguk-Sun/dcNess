/* dcness-design-engine: 1.0.0
 * #only=<data-variant> 요청을 같은 확정본 안의 변형 하나로 좁힌다.
 */
(function () {
  'use strict';

  const WARNING_ID = 'dcness-variant-warning';

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

  function apply() {
    document.getElementById(WARNING_ID)?.remove();
    const requested = requestedVariant();
    const variants = [...document.querySelectorAll('[data-variant]')];
    variants.forEach(element => { element.hidden = false; });
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
    variants.forEach(element => { element.hidden = element !== matched[0]; });
    document.documentElement.dataset.dcnessOnlyVariant = requested;
  }

  window.addEventListener('hashchange', apply);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
})();
