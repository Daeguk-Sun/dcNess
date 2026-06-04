<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{screen-id} - v{N}</title>
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
    <section data-node-id="{screen-id}.section">
      <h1 data-node-id="{screen-id}.title">화면 제목</h1>
    </section>
  </main>
  <script defer src="_lib/show-ids.js"></script>
</body>
</html>
