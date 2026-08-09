import { setUiActive } from "../api";

export interface UiActivityCoordinator {
  acquire(): () => void;
  shutdown(): void;
}

export function createUiActivityCoordinator(
  write: (active: boolean) => Promise<unknown>,
): UiActivityCoordinator {
  let owners = 0;
  let desired = false;
  let applied = false;
  let running: Promise<void> | null = null;

  const pump = (): void => {
    if (running || desired === applied) return;
    running = (async () => {
      while (desired !== applied) {
        const next = desired;
        try {
          await write(next);
        } catch {}
        applied = next;
      }
    })().finally(() => {
      running = null;
      pump();
    });
  };

  const setDesired = (next: boolean): void => {
    desired = next;
    pump();
  };

  return {
    acquire() {
      owners += 1;
      setDesired(true);
      let released = false;
      return () => {
        if (released) return;
        released = true;
        owners = Math.max(0, owners - 1);
        if (owners !== 0) return;
        queueMicrotask(() => {
          if (owners === 0) setDesired(false);
        });
      };
    },
    shutdown() {
      owners = 0;
      setDesired(false);
    },
  };
}

const uiActivity = createUiActivityCoordinator((active) => setUiActive(active));

export function acquireUiActivity(): () => void {
  return uiActivity.acquire();
}

export function shutdownUiActivity(): void {
  uiActivity.shutdown();
}
