export function createClock(start = 0) {
  let now = start;
  let nextId = 1;
  const timers = [];
  return {
    kind: 'manual',
    now: () => now,
    setTimeout(fn, ms) {
      const id = nextId++;
      timers.push({ id, at: now + ms, fn, done: false });
      return id;
    },
    clearTimeout(id) {
      const timer = timers.find((item) => item.id === id);
      if (timer) timer.done = true;
    },
    jump(ms) {
      now += ms;
    },
    advance(ms) {
      const target = now + ms;
      for (;;) {
        const pending = timers.filter((item) => !item.done && item.at <= target).sort((a, b) => a.at - b.at || a.id - b.id);
        if (!pending.length) break;
        const timer = pending[0];
        now = timer.at;
        timer.done = true;
        timer.fn();
      }
      now = target;
    },
  };
}

export function createRealClock() {
  const origin = performance.now();
  return {
    kind: 'real',
    now: () => performance.now() - origin,
    setTimeout(fn, ms) {
      return setTimeout(fn, ms);
    },
    clearTimeout(id) {
      clearTimeout(id);
    },
  };
}
