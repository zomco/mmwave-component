export function connectCdp(url, options = {}) {
  const openTimeoutMs = options.openTimeoutMs ?? 3000;
  const commandTimeoutMs = options.commandTimeoutMs ?? 2000;
  const ws = options.socket || new WebSocket(url);
  let nextId = 0;
  let opened = false;
  let openSettled = false;
  const pending = new Map();
  let rejectOpen = () => {};
  const failAll = (error) => {
    for (const waiter of pending.values()) {
      clearTimeout(waiter.timer);
      waiter.reject(error);
    }
    pending.clear();
  };
  const openedPromise = new Promise((resolve, reject) => {
    rejectOpen = reject;
    const timer = setTimeout(() => {
      if (openSettled) return;
      openSettled = true;
      try { ws.close(); } catch { /* already closed */ }
      const error = new Error('cdp timeout');
      failAll(error);
      reject(error);
    }, openTimeoutMs);
    ws.addEventListener('open', () => {
      if (openSettled) return;
      openSettled = true;
      opened = true;
      clearTimeout(timer);
      resolve();
    });
    const fail = () => {
      clearTimeout(timer);
      const error = new Error('cdp closed');
      failAll(error);
      if (!openSettled) {
        openSettled = true;
        reject(error);
      }
    };
    ws.addEventListener('error', fail);
    ws.addEventListener('close', fail);
  });
  openedPromise.catch(() => {});
  ws.addEventListener('message', (event) => {
    let message;
    try {
      message = JSON.parse(typeof event.data === 'string' ? event.data : '');
    } catch {
      return;
    }
    if (!message?.id || !pending.has(message.id)) return;
    const waiter = pending.get(message.id);
    pending.delete(message.id);
    clearTimeout(waiter.timer);
    if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
    else waiter.resolve(message.result);
  });
  return {
    async send(method, params = {}, timeoutMs = commandTimeoutMs) {
      await openedPromise;
      if (!opened) throw new Error('cdp closed');
      const id = ++nextId;
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          if (!pending.has(id)) return;
          pending.delete(id);
          reject(new Error('cdp command timeout'));
        }, timeoutMs);
        pending.set(id, { resolve, reject, timer });
        try {
          ws.send(JSON.stringify({ id, method, params }));
        } catch (error) {
          clearTimeout(timer);
          pending.delete(id);
          reject(error);
        }
      });
    },
    close() {
      if (!openSettled) {
        openSettled = true;
        rejectOpen(new Error('cdp closed'));
      }
      failAll(new Error('cdp closed'));
      try { ws.close(); } catch { /* already closed */ }
    },
    pendingCount() {
      return pending.size;
    },
  };
}

export async function waitForText(cdp, { timeoutMs = 5000, commandTimeoutMs = 500, match = '"ok"' } = {}) {
  const deadline = Date.now() + timeoutMs;
  let last = '';
  while (Date.now() < deadline) {
    const budget = Math.max(1, Math.min(commandTimeoutMs, deadline - Date.now()));
    try {
      const result = await cdp.send('Runtime.evaluate', {
        expression: 'document.body ? document.body.textContent : ""',
        returnByValue: true,
      }, budget);
      last = result?.result?.value || '';
      if (String(last).includes(match)) return last;
    } catch (error) {
      if (Date.now() >= deadline) throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  throw new Error(`browser result missing: ${last}`);
}
