import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import ConsoleView from './src/console/ConsoleView.jsx';
import { ConsoleSession } from './src/console/session.js';
import { createClock } from './src/protocol/clock.js';
import { ProtocolClient } from './src/protocol/client.js';
import { SimulatedDevice, observation } from './src/protocol/simulator.js';

const clock = createClock(5000);
const device = new SimulatedDevice({ profile: 'r60', clock });
const advance = clock.advance.bind(clock);
clock.advance = (ms) => {
  advance(ms);
  device.poll(clock.now());
};
const transport = {
  write(bytes) { device.ingest(bytes); },
  onData() {},
  close() { device.expire(); },
  start() {},
};
const session = new ConsoleSession({ clock, helloTimeout: 8000, rpcTimeout: 1000 });
session.clientFactory = (next, extras) => {
  const client = new ProtocolClient(next, extras);
  device.onWire((bytes) => client.ingest(bytes));
  return client;
};

function Page() {
  const [snap, setSnap] = useState(() => session.snapshot());
  session.onChange = setSnap;
  return <ConsoleView
    language="zh"
    session={session}
    snapshot={snap}
    support={{ ok: true }}
    busy={false}
    selectedModel="r60abd1"
    onConnect={() => session.attach(transport, { mode: 'simulation' })}
    onDisconnect={() => session.stop()}
  />;
}

createRoot(document.getElementById('root')).render(<Page />);
window.__mwcp = {
  session,
  clock,
  device,
  observation,
  simulation: true,
};
