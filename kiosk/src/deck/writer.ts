/**
 * Latest-wins writer: at most one write in flight and at least `gapMs` between writes.
 * Values pushed meanwhile collapse into the newest one, so a fast drag never queues work.
 */
export interface CoalescedWriter<T> {
  push: (value: T) => void;
  /** Resolves once everything pushed so far has been written (or failed). */
  flush: () => Promise<void>;
}

export function createCoalescedWriter<T>(
  send: (value: T) => Promise<unknown>,
  gapMs: number,
  onError: (error: unknown) => void = () => {},
  now: () => number = () => Date.now(),
  wait: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
): CoalescedWriter<T> {
  let pending: { value: T } | null = null;
  let running: Promise<void> | null = null;
  let lastAt = -Infinity;

  const drain = async () => {
    while (pending) {
      const delay = lastAt + gapMs - now();
      if (delay > 0) await wait(delay);
      const { value } = pending;
      pending = null;
      lastAt = now();
      try {
        await send(value);
      } catch (error) {
        onError(error);
      }
    }
    running = null;
  };

  return {
    push(value) {
      pending = { value };
      if (!running) running = drain();
    },
    flush: () => running ?? Promise.resolve(),
  };
}
