import React from 'react';
import { createRoot } from 'react-dom/client';
import 'esp-web-tools/dist/web/install-button.js';
import App from './src/App.jsx';
import './src/index.css';
import { SimulatedDevice, observation } from './src/protocol/simulator.js';

let virtualMs = 1000;
const clock = {
  now() {
    virtualMs += 120;
    return virtualMs;
  },
};
const device = new SimulatedDevice({ profile: 'r60', clock });
let readerController = null;
const port = {
  readable: null,
  writable: null,
  openCalls: 0,
  closeCalls: 0,
  failClose: false,
  closeDelay: 0,
  addEventListener() {},
  removeEventListener() {},
  async open() {
    if (this.readable || this.writable) {
      const error = new Error('port already open');
      error.name = 'InvalidStateError';
      throw error;
    }
    this.openCalls += 1;
    this.readable = new ReadableStream({
      start(controller) { readerController = controller; },
      cancel() { readerController = null; },
    });
    this.writable = new WritableStream({
      write(chunk) { device.ingest(chunk); },
    });
  },
  async close() {
    this.closeCalls += 1;
    if (this.failClose) {
      const error = new Error('close failed');
      error.name = 'NetworkError';
      throw error;
    }
    if (this.closeDelay) await new Promise((resolve) => setTimeout(resolve, this.closeDelay));
    try { readerController?.close(); } catch { /* already closed */ }
    readerController = null;
    this.readable = null;
    this.writable = null;
  },
};
device.onWire((bytes) => {
  try { readerController?.enqueue(bytes); } catch { /* reader already closed */ }
});
const serial = {
  mode: 'ok',
  requestCount: 0,
  async requestPort() {
    this.requestCount += 1;
    if (this.beforeGrant) await this.beforeGrant();
    if (this.mode === 'cancel') {
      const error = new Error('cancelled');
      error.name = 'NotFoundError';
      throw error;
    }
    return port;
  },
};
Object.defineProperty(navigator, 'serial', { configurable: true, value: serial });
window.__mwcp = { device, port, serial, observation, simulation: true };
createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
