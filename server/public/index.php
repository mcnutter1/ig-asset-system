<?php
// Serve the SPA from /public/assets (no SSR).
// You can build/compile your frontend separately and drop files into /public/assets.
readfile(__DIR__ . '/assets/index.html');
