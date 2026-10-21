/* dcness-design-engine: 1.1.0
 * 확정본의 자연 크기를 부모 보드에 보고한다. 선언 크기는 사용하지 않는다.
 */
(function () {
  'use strict';

  let previous = '';

  // 보드 칸(iframe)은 보고한 자연 크기로 잡히므로 스크롤할 내용이 없다. 스크롤 막대가
  // 자리를 차지하는 환경에서는 크기를 맞추기 전에 생긴 세로 막대가 폭을 줄여 가로 막대를,
  // 가로 막대가 높이를 줄여 세로 막대를 서로 유지시킨다. 같은 크기는 다시 보고하지 않으므로
  // 이 상태가 풀리지 않는다. iframe 안에서만 스크롤 막대를 그리지 않아 자리를 없앤다.
  function hideFrameScrollbars() {
    if (window.parent === window || document.getElementById('dcness-frame-scrollbar-style')) return;
    const style = document.createElement('style');
    style.id = 'dcness-frame-scrollbar-style';
    style.textContent = 'html, body { scrollbar-width: none; }'
      + ' html::-webkit-scrollbar, body::-webkit-scrollbar { display: none; }';
    (document.head || document.documentElement).appendChild(style);
  }

  function px(value) {
    return Number.parseFloat(value) || 0;
  }

  // 화면에 보이는 문서 흐름 요소 중 가장 오른쪽 끝. 브라우저의 scrollable overflow 규칙과
  // 같은 범위만 센다.
  // - fixed·absolute 요소는 뷰포트(=iframe) 크기를 기준으로 놓일 수 있어, 넣으면 보고 폭이
  //   iframe 폭을 따라 계속 커진다 (예: Show IDs 버튼). 넘친 부분은 scrollWidth 가 포함한다.
  // - overflow 가 visible 이 아닌 요소(캐러셀·스크롤 영역)의 안쪽은 그 요소 경계에서 잘리므로
  //   요소 자신의 경계만 센다.
  function inFlowRight(element) {
    let right = 0;
    for (const child of element.children) {
      const style = getComputedStyle(child);
      if (style.position === 'fixed' || style.position === 'absolute') continue;
      const rect = child.getBoundingClientRect();
      if (rect.width || rect.height) right = Math.max(right, rect.right + window.scrollX);
      if (style.overflowX === 'visible') right = Math.max(right, inFlowRight(child));
    }
    return right;
  }

  // scrollWidth 는 넘친 내용의 오른쪽 padding 을 포함하지 않는다. 블록 묶음 요소의 폭은
  // 넘친 내용이 아니라 부모 폭을 따르므로, body 안 흐름 요소의 오른쪽 끝에 body·html 의
  // 오른쪽 margin/border/padding 을 더해 좌우 여백을 포함한 폭을 구한다.
  function contentWidth(root, body) {
    if (!body) return 0;
    const right = inFlowRight(body);
    if (!right) return 0;
    const bodyStyle = getComputedStyle(body);
    const rootStyle = getComputedStyle(root);
    return right
      + px(bodyStyle.paddingRight) + px(bodyStyle.borderRightWidth) + px(bodyStyle.marginRight)
      + px(rootStyle.paddingRight) + px(rootStyle.borderRightWidth);
  }

  function variants() {
    return [...document.querySelectorAll('[data-variant]')].map(element => ({
      id: element.dataset.variant,
      axes: Object.fromEntries(
        (element.dataset.variantValues || '').split(';').filter(Boolean).map(pair => {
          const [axis, ...rest] = pair.split('=');
          return [axis.trim(), rest.join('=').trim()];
        }),
      ),
    }));
  }

  function measure() {
    const root = document.documentElement;
    const body = document.body;
    const width = Math.ceil(Math.max(
      root.scrollWidth,
      root.offsetWidth,
      body?.scrollWidth || 0,
      body?.offsetWidth || 0,
      contentWidth(root, body),
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
      variants: variants(),
    }, '*');
  }

  function schedule() {
    requestAnimationFrame(() => requestAnimationFrame(measure));
  }

  hideFrameScrollbars();
  window.addEventListener('load', schedule);
  window.addEventListener('hashchange', schedule);
  window.addEventListener('message', event => {
    if (event.data?.type !== 'dcness-request-frame-size') return;
    previous = '';
    schedule();
  });
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
