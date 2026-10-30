import type { RepeatMode } from "./types";

export type { RepeatMode };

export interface QueueEntry<T> {
  key: string;
  item: T;
}

/** Entries are kept in play order; with shuffle on, `original` remembers the order to go back to. */
export interface QueueState<T> {
  entries: QueueEntry<T>[];
  position: number;
  repeat: RepeatMode;
  shuffle: boolean;
  original: string[] | null;
}

export type Random = () => number;

let counter = 0;
export function queueKey(): string {
  counter = (counter + 1) % Number.MAX_SAFE_INTEGER;
  return `q${Date.now().toString(36)}${counter.toString(36)}`;
}

export function emptyQueue<T>(repeat: RepeatMode = "all", shuffle = false): QueueState<T> {
  return { entries: [], position: 0, repeat, shuffle, original: null };
}

function shuffled<T>(items: readonly T[], random: Random): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function withUpcomingShuffled<T>(state: QueueState<T>, random: Random): QueueState<T> {
  const kept = state.entries.slice(0, state.position + 1);
  return { ...state, entries: [...kept, ...shuffled(state.entries.slice(state.position + 1), random)] };
}

export function current<T>(state: QueueState<T>): QueueEntry<T> | null {
  return state.entries[state.position] ?? null;
}

/** Replaces the queue; with shuffle on, the chosen item plays first and the rest is mixed. */
export function fromItems<T>(state: QueueState<T>, items: readonly T[], start = 0, random: Random = Math.random): QueueState<T> {
  const entries = items.map((item) => ({ key: queueKey(), item }));
  const position = entries.length ? Math.max(0, Math.min(start, entries.length - 1)) : 0;
  const next: QueueState<T> = { ...state, entries, position, original: state.shuffle ? entries.map((e) => e.key) : null };
  if (!state.shuffle || entries.length < 2) return next;
  const first = entries[position];
  return withUpcomingShuffled({ ...next, entries: [first, ...entries.filter((e) => e !== first)], position: 0 }, random);
}

/** Adds items at the end, or right after the one playing. */
export function enqueue<T>(state: QueueState<T>, items: readonly T[], where: "end" | "next" = "end"): QueueState<T> {
  const added = items.map((item) => ({ key: queueKey(), item }));
  if (!added.length) return state;
  const at = where === "next" && state.entries.length ? state.position + 1 : state.entries.length;
  const entries = [...state.entries.slice(0, at), ...added, ...state.entries.slice(at)];
  const original = state.original ? [...state.original, ...added.map((e) => e.key)] : null;
  return { ...state, entries, original };
}

/** Next entry index, or null when the queue ends. `ended` honours repeat-one; a user skip always moves on. */
export function nextPosition<T>(state: QueueState<T>, reason: "ended" | "skip"): number | null {
  const count = state.entries.length;
  if (!count) return null;
  if (reason === "ended" && state.repeat === "one") return state.position;
  if (state.position + 1 < count) return state.position + 1;
  return state.repeat === "off" && reason === "ended" ? null : 0;
}

export function previousPosition<T>(state: QueueState<T>): number | null {
  const count = state.entries.length;
  if (!count) return null;
  if (state.position > 0) return state.position - 1;
  return state.repeat === "all" ? count - 1 : 0;
}

/** Moves to `position`; wrapping to the start of a shuffled queue mixes it again. */
export function goTo<T>(state: QueueState<T>, position: number, random: Random = Math.random): QueueState<T> {
  if (position === 0 && state.position === state.entries.length - 1 && state.shuffle && state.entries.length > 2) {
    return { ...state, entries: shuffled(state.entries, random), position: 0 };
  }
  return { ...state, position };
}

export function indexOfKey<T>(state: QueueState<T>, key: string): number {
  return state.entries.findIndex((e) => e.key === key);
}

/** Removes one entry; when it was playing, what follows it takes its place (or the one before, at the end). */
export function remove<T>(state: QueueState<T>, key: string): { state: QueueState<T>; currentChanged: boolean } {
  const index = indexOfKey(state, key);
  if (index < 0) return { state, currentChanged: false };
  const entries = state.entries.filter((e) => e.key !== key);
  const original = state.original?.filter((k) => k !== key) ?? null;
  const position = index < state.position ? state.position - 1 : Math.min(state.position, Math.max(0, entries.length - 1));
  return { state: { ...state, entries, original, position }, currentChanged: index === state.position };
}

/** Moves an entry to another place in the play order; the one playing keeps playing. */
export function move<T>(state: QueueState<T>, key: string, to: number): QueueState<T> {
  const from = indexOfKey(state, key);
  if (from < 0) return state;
  const target = Math.max(0, Math.min(to, state.entries.length - 1));
  if (from === target) return state;
  const playing = current(state)?.key;
  const entries = [...state.entries];
  const [entry] = entries.splice(from, 1);
  entries.splice(target, 0, entry);
  const original = state.shuffle ? state.original : null;
  return { ...state, entries, original, position: Math.max(0, entries.findIndex((e) => e.key === playing)) };
}

export function setRepeat<T>(state: QueueState<T>, repeat: RepeatMode): QueueState<T> {
  return { ...state, repeat };
}

/** Shuffle mixes only what has not played yet; turning it off restores the order the items came in. */
export function setShuffle<T>(state: QueueState<T>, on: boolean, random: Random = Math.random): QueueState<T> {
  if (on === state.shuffle) return state;
  if (on) return withUpcomingShuffled({ ...state, shuffle: true, original: state.entries.map((e) => e.key) }, random);
  const playing = current(state)?.key;
  const rank = new Map((state.original ?? []).map((key, i) => [key, i]));
  const entries = [...state.entries].sort((a, b) => (rank.get(a.key) ?? Number.MAX_SAFE_INTEGER) - (rank.get(b.key) ?? Number.MAX_SAFE_INTEGER));
  return { ...state, entries, shuffle: false, original: null, position: Math.max(0, entries.findIndex((e) => e.key === playing)) };
}

export function clear<T>(state: QueueState<T>): QueueState<T> {
  return { ...state, entries: [], position: 0, original: state.shuffle ? [] : null };
}
