import { useSyncExternalStore } from "react";
import { ConsoleState, getConsoleState, setConsoleLed, setThermalGuard } from "../api";

const POLL_MS = 2000;
export const HISTORY_SAMPLES = 60;

interface ConsoleSnapshot {
  state: ConsoleState | null;
  apu: number[];
  ssd: number[];
}

let snapshot: ConsoleSnapshot = { state: null, apu: [], ssd: [] };
let timer: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();

const push = (history: number[], value: number | null | undefined) =>
  value == null ? history : [...history, value].slice(-HISTORY_SAMPLES);

export function acceptConsoleState(state: ConsoleState): void {
  snapshot = {
    state,
    apu: push(snapshot.apu, state.temps?.apu),
    ssd: push(snapshot.ssd, state.temps?.ssd),
  };
  listeners.forEach((listener) => listener());
}

const refresh = () => getConsoleState().then(acceptConsoleState).catch(() => null);

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === null) {
    void refresh();
    timer = setInterval(refresh, POLL_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

export function useConsole() {
  const current = useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
  return {
    ...current,
    setLight: (preset: string) => setConsoleLed(preset).then(acceptConsoleState).catch(() => null),
    setGuard: (enabled: boolean | null, threshold: number | null, alarm: boolean | null) =>
      setThermalGuard(enabled, threshold, alarm).then(acceptConsoleState).catch(() => null),
  };
}
