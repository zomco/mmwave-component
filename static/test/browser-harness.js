import { execFile, execFileSync, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { platform } from 'node:os';

const live = new Set();

export function findBrowser(env = process.env) {
  const configured = env.MWCP_CHROME || env.CHROME_PATH || env.CHROMIUM_PATH;
  if (configured) return configured;
  const candidates = platform() === 'win32'
    ? [
        env.PROGRAMFILES && `${env.PROGRAMFILES}\\Google\\Chrome\\Application\\chrome.exe`,
        env['PROGRAMFILES(X86)'] && `${env['PROGRAMFILES(X86)']}\\Google\\Chrome\\Application\\chrome.exe`,
        env.LOCALAPPDATA && `${env.LOCALAPPDATA}\\Google\\Chrome\\Application\\chrome.exe`,
        env.PROGRAMFILES && `${env.PROGRAMFILES}\\Microsoft\\Edge\\Application\\msedge.exe`,
        env.LOCALAPPDATA && `${env.LOCALAPPDATA}\\Microsoft\\Edge\\Application\\msedge.exe`,
      ]
    : [
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/snap/bin/chromium',
      ];
  const found = candidates.find((item) => item && existsSync(item));
  if (found) return found;
  for (const name of platform() === 'win32' ? ['chrome.exe', 'msedge.exe'] : ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) {
    const located = which(name);
    if (located) return located;
  }
  return null;
}

export function launchBrowser({ executable, args = ['--version'], timeoutMs = 2000 } = {}) {
  const command = executable || findBrowser();
  if (!command) return Promise.reject(new Error('browser not found'));
  return new Promise((resolve, reject) => {
    let settled = false;
    const child = spawn(command, args, {
      windowsHide: true,
      stdio: 'ignore',
      detached: platform() !== 'win32',
    });
    live.add(child);
    const timer = setTimeout(() => finish(new Error('browser start timeout')), timeoutMs);
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) {
        killProcessTree(child).finally(() => reject(error));
        return;
      }
      resolve({
        child,
        async close() {
          await killProcessTree(child);
        },
      });
    };
    child.once('error', (error) => finish(error));
    child.once('exit', (code, signal) => {
      if (!settled) finish(new Error(`browser exited ${code ?? signal}`));
    });
    setTimeout(() => {
      if (!settled && child.exitCode == null && child.signalCode == null && !child.killed) finish(null);
    }, 30);
  });
}

export async function killProcessTree(child) {
  live.delete(child);
  if (!child?.pid) return;
  if (child.exitCode != null || child.signalCode != null) {
    child.unref?.();
    return;
  }
  try {
    if (platform() === 'win32') {
      await execBounded('taskkill', ['/PID', String(child.pid), '/T', '/F'], 3000);
    } else {
      try {
        process.kill(-child.pid, 'SIGKILL');
      } catch {
        child.kill('SIGKILL');
      }
    }
  } catch {
    try { child.kill('SIGKILL'); } catch { /* already gone */ }
  }
  await waitExit(child, 2000);
  child.unref?.();
}

launchBrowser.active = () => live.size;

function which(name) {
  try {
    const cmd = platform() === 'win32' ? 'where.exe' : 'which';
    const out = execFileSync(cmd, [name], { encoding: 'utf8', timeout: 2000, windowsHide: true });
    return out.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || null;
  } catch {
    return null;
  }
}

function execBounded(command, args, timeoutMs) {
  return new Promise((resolve, reject) => {
    const child = execFile(command, args, { windowsHide: true, timeout: timeoutMs }, (error) => {
      if (error) reject(error);
      else resolve();
    });
    child.once('error', reject);
  });
}

function waitExit(child, timeoutMs) {
  if (child.exitCode != null || child.signalCode != null) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(), timeoutMs);
    child.once('exit', () => {
      clearTimeout(timer);
      resolve();
    });
  });
}
