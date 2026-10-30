export interface RotationState {
  order: "sequential" | "shuffle";
  queue: string[];
  current: string | null;
}

export type Random = () => number;

function shuffled(ids: string[], random: Random): string[] {
  const out = ids.slice();
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export function createRotation(order: RotationState["order"]): RotationState {
  return { order, queue: [], current: null };
}

/** Advances to the next item. Shuffle never repeats until every item has been shown. */
export function advance(state: RotationState, ids: readonly string[], random: Random = Math.random): RotationState {
  const available = Array.from(new Set(ids));
  if (available.length === 0) return { ...state, queue: [], current: null };
  if (state.order === "sequential") {
    const index = state.current === null ? -1 : available.indexOf(state.current);
    return { ...state, queue: [], current: available[(index + 1) % available.length] };
  }
  let queue = state.queue.filter((id) => available.includes(id));
  if (queue.length === 0) {
    queue = shuffled(available, random);
    if (queue.length > 1 && queue[0] === state.current) queue.push(queue.shift() as string);
  }
  const [current, ...rest] = queue;
  return { ...state, queue: rest, current };
}

export function shouldAdvance(elapsedMs: number, intervalSec: number, returnedHome: boolean, onReturnHome: boolean): boolean {
  if (onReturnHome) return returnedHome;
  return elapsedMs >= intervalSec * 1000;
}
