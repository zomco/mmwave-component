import { ProtocolClient } from '../protocol/client.js';
import { createDiagController } from './diag.js';

export function bindDiagPage(document, serial, hello, options = {}) {
  const state = document.querySelector('#state');
  const log = document.querySelector('#log');
  const exported = document.querySelector('#export-out');
  const diag = createDiagController({
    hello,
    clock: options.clock,
    maxSamples: options.maxSamples,
    captureIntervalMs: options.captureIntervalMs,
    writeWaitMs: options.writeWaitMs,
    createClient(transport) { return new ProtocolClient(transport, options.clientOptions); },
    onState() { paint(); },
  });
  function paint() {
    if (state) state.textContent = diag.state();
    if (log) log.textContent = diag.records().map((item) => `${item.kind} ${item.detail}`).join('\n');
  }
  document.querySelector('#connect').addEventListener('click', async () => {
    try {
      await diag.connect(serial);
    } catch (error) {
      if (state) state.textContent = diag.state();
      if (log) log.textContent = `${diag.state()} ${error}`;
    }
  });
  document.querySelector('#close').addEventListener('click', async () => {
    try {
      await diag.disconnect();
    } catch (error) {
      if (state) state.textContent = diag.state();
      if (log) log.textContent = `${diag.state()} ${error}`;
    }
  });
  document.querySelector('#capture').addEventListener('click', async () => {
    try {
      diag.startCapture();
      await diag.sampleOnce();
    } catch (error) {
      if (log) log.textContent = `${diag.state()} ${error}`;
    }
    paint();
  });
  document.querySelector('#stop').addEventListener('click', async () => {
    await diag.stopCapture();
    paint();
  });
  document.querySelector('#export').addEventListener('click', () => {
    if (exported) exported.textContent = diag.exportEvidence();
  });
  paint();
  return diag;
}
