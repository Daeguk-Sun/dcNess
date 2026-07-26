/* dcness-design-engine: 1.0.0
 * 확정본의 자연 크기를 부모 보드에 보고한다. 선언 크기는 사용하지 않는다.
 */
(function () {
  'use strict';

  let previous = '';

  function measure() {
    const root = document.documentElement;
    const body = document.body;
    const width = Math.ceil(Math.max(
      root.scrollWidth,
      root.offsetWidth,
      body?.scrollWidth || 0,
      body?.offsetWidth || 0,
    ));
    const height = Math.ceil(Math.max(
      root.scrollHeight,
      root.offsetHeight,
      body?.scrollHeight || 0,
      body?.offsetHeight || 0,
    ));
    const signature = `${width}x${height}`;
    if (signature === previous || !width || !height) return;
    previous = signature;
    parent.postMessage({
      type: 'dcness-frame-size',
      width,
      height,
      variant: document.documentElement.dataset.dcnessOnlyVariant || null,
    }, '*');
  }

  function schedule() {
    requestAnimationFrame(() => requestAnimationFrame(measure));
  }

  window.addEventListener('load', schedule);
  window.addEventListener('hashchange', schedule);
  if (typeof ResizeObserver === 'function') {
    const observer = new ResizeObserver(schedule);
    const start = () => observer.observe(document.documentElement);
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', start);
    } else {
      start();
    }
  }
  schedule();
})();
