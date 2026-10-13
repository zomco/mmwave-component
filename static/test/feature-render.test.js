import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { copy } from '../src/content.js';

test('feature component renders accessible SVGs and respects reduced motion on first render', async (t) => {
  const server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true },
    logLevel: 'error',
  });
  const oldWindow = globalThis.window;
  const oldDocument = globalThis.document;
  t.after(async () => {
    if (oldWindow === undefined) delete globalThis.window;
    else globalThis.window = oldWindow;
    if (oldDocument === undefined) delete globalThis.document;
    else globalThis.document = oldDocument;
    await server.close();
  });
  const { default: FeatureShowcase } = await server.ssrLoadModule('/src/FeatureShowcase.jsx');
  for (const reduced of [true, false]) {
    globalThis.window = { matchMedia: () => ({ matches: reduced }) };
    globalThis.document = { hidden: false };
    for (const language of ['zh', 'en']) {
      const text = copy[language].features;
      const html = renderToStaticMarkup(React.createElement(FeatureShowcase, { t: text, onGuide() {} }));
      assert.equal((html.match(/role="img"/g) || []).length, 3);
      assert.equal((html.match(/<desc /g) || []).length, 3);
      assert.equal(html.includes('<table'), false);
      assert.ok(html.includes(reduced ? text.play : text.pause));
      assert.ok(html.includes(reduced ? 'value="620"' : 'value="0"'));
      assert.ok(html.includes(text.cardLink));
      assert.ok(html.includes(text.note));
    }
  }
});
