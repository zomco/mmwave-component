import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { copy } from '../src/content.js';
import { radars } from '../src/catalog.js';

test('R60ABD1 specifications use documented reporting interval, not protocol units as resolution', () => {
  const radar = radars.find((item) => item.id === 'r60abd1');
  assert.equal(radar.range, null);
  for (const key of ['horizontalAngle', 'verticalAngle', 'rangeResolution', 'angleResolution']) {
    assert.equal(radar.detectionSpecs[key], null);
  }
  assert.deepEqual(radar.detectionSpecs.positionInterval, { zh: '2 s', en: '2 s' });
  assert.match(radar.specificationSource.label.zh, /V3\.4.*6.*DP5/);
});

test('radar details show all fields, localize unknowns and retain documented values', async (t) => {
  const server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true },
    logLevel: 'error',
  });
  t.after(() => server.close());
  const { default: RadarDetails } = await server.ssrLoadModule('/src/RadarDetails.jsx');
  const render = (radar, language) => renderToStaticMarkup(React.createElement(RadarDetails, { radar, language, t: copy[language] }));
  for (const language of ['zh', 'en']) {
    const html = render(radars[0], language);
    assert.equal((html.match(/<dt /g) || []).length, 6);
    assert.equal(html.split(`>${copy[language].specs.unknown}</dd>`).length - 1, 5);
    assert.ok(html.includes('>2 s</dd>'));
    assert.ok(html.includes(radars[0].specificationSource.url));
    assert.ok(html.includes(copy[language].docs));
    const missing = render({ ...radars[0], range: undefined, detectionSpecs: { horizontalAngle: { zh: ' ', en: '' } } }, language);
    assert.equal(missing.split(`>${copy[language].specs.unknown}</dd>`).length - 1, 6);
    const known = render({ ...radars[0], range: { en: '6 m' }, detectionSpecs: { horizontalAngle: { zh: '±60°', en: '±60°' }, rangeResolution: { en: '0.72 m' } } }, language);
    for (const value of ['6 m', '±60°', '0.72 m']) assert.ok(known.includes(`>${value}</dd>`));
  }
});
