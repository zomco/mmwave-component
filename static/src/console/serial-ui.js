/** Button decisions shared by the production page and the port tests. */

export function serialControls(serialSnap, sessionSnap) {
  const owner = serialSnap && serialSnap.owner ? serialSnap.owner : 'none';
  const connecting = !!(serialSnap && serialSnap.connecting);
  const closing = !!(serialSnap && serialSnap.busy);
  const closeError = serialSnap && serialSnap.closeError ? serialSnap.closeError : null;
  const layers = sessionSnap && sessionSnap.layers ? sessionSnap.layers : {};
  const sessionHeld = layers.port === 'open'
    || layers.protocol === 'online'
    || layers.protocol === 'handshake'
    || layers.protocol === 'session_expired';
  const consoleHeld = owner === 'console' || sessionHeld;
  let phase = 'idle';
  if (closeError) phase = 'close_failed';
  else if (closing) phase = 'closing';
  else if (connecting) phase = 'connecting';
  else if (owner === 'installer') phase = 'installer';
  else if (serialSnap && serialSnap.installerUnconfirmed) phase = 'installer_unconfirmed';
  else if (consoleHeld) phase = 'console';
  return {
    phase,
    flashDisabled: phase === 'close_failed' || phase === 'closing' || phase === 'connecting' || phase === 'installer' || phase === 'console',
    connectDisabled: phase === 'closing' || phase === 'connecting' || phase === 'installer',
    showDisconnect: phase === 'close_failed' || phase === 'closing' || phase === 'console',
  };
}
