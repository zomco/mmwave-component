export function auditInstallerSources(connectSource, dialogSource) {
  const closedHandler = connectSource.slice(connectSource.indexOf('"closed"'));
  return {
    version: '10.4.0',
    closedCallsPortClose: /port!?.close\(/.test(closedHandler),
    closedAwaitsPortClose: /await\s+port!?.close\(/.test(closedHandler),
    dialogReopensAfterFinish: dialogSource.includes('this.port.open({ baudRate: 115200'),
    dialogInitializesImprovAfterFinish: dialogSource.includes('_initialize(true)'),
    manifestCanDisableImprovWait: dialogSource.includes('new_install_improv_wait_time === 0'),
  };
}

export function portIsClosed(port) {
  return !!port && port.readable == null && port.writable == null;
}

export async function claimReleasedPort(port, open) {
  if (!portIsClosed(port)) return { ok: false, reason: 'installer_still_owns_port' };
  try {
    await open(port);
  } catch (error) {
    return { ok: false, reason: 'open_failed', error: error.name || 'Error' };
  }
  if (port.readable == null || port.writable == null) return { ok: false, reason: 'open_did_not_acquire' };
  return { ok: true, owner: 'console' };
}
