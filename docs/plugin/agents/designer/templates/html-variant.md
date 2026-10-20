<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{screen-id}</title>
  <style>
    :root {
      --color-surface: #ffffff;
      --color-text: #111827;
      --space-md: 16px;
      --radius-md: 8px;
    }
    body { margin: 0; font-family: system-ui, sans-serif; background: var(--color-surface); color: var(--color-text); }
  </style>
</head>
<body>
  <main data-screen-id="{screen-id}">
    <!-- 변형 제목 줄은 data-variant 요소 안에 둔다. #only 는 다른 변형과 그 묶음만 숨긴다. -->
    <section data-variant="default" data-variant-values="state=default"
             data-journey-representative="true"
             data-node-id="{screen-id}.section">
      <h1 data-node-id="{screen-id}.title">화면 제목</h1>
    </section>
  </main>
  <script defer src="../_lib/only-variant.js"></script>
  <script defer src="../_lib/report-size.js"></script>
  <script defer src="../_lib/show-ids.js"></script>
</body>
</html>
