// A MobX computed that threw while reading only plain fields tracks nothing, so it never runs again and keeps
// rethrowing. Steam's userCollections does that when read before its collections load from the cloud,
// and the library, a game's gear menu and its properties then crash until Steam restarts. Once the collections are
// in, marking such a computed stale makes its next read compute afresh.

interface MobxComputed {
  derivation?: unknown;
  value_?: { cause?: unknown };
  observing_?: readonly unknown[];
  dependenciesState_?: number;
  onBecomeStale_?: () => void;
}

const MOBX_STALE = 2;
const CHECK_MS = 3_000;
const GIVE_UP_MS = 10 * 60_000;

type CollectionStore = { m_mapCollectionsFromStorage?: { values?: unknown } } & object;

export function healPoisonedComputeds(store: object | undefined): number {
  try {
    if (!store) return 0;
    const admin = Object.getOwnPropertySymbols(store)
      .map((key) => (store as Record<symbol, unknown>)[key])
      .find((value): value is { values_: Map<string, MobxComputed> } =>
        value instanceof Object && (value as { values_?: unknown }).values_ instanceof Map);
    let healed = 0;
    for (const computed of admin?.values_.values() ?? []) {
      if (typeof computed?.derivation !== "function" || !(computed.value_?.cause instanceof Error) || computed.observing_?.length !== 0) continue;
      computed.dependenciesState_ = MOBX_STALE;
      computed.onBecomeStale_?.();
      healed += 1;
    }
    return healed;
  } catch {
    return 0;
  }
}

const collectionsLoaded = (store: CollectionStore | undefined) => {
  try {
    return typeof store?.m_mapCollectionsFromStorage?.values === "function";
  } catch {
    return false;
  }
};

/** Heals Steam's collection store once its collections have loaded; stops after that or after ten minutes. */
export function startCollectionsHeal(
  getStore: () => CollectionStore | undefined,
  onHealed: (count: number) => void,
): () => void {
  const started = Date.now();
  let timer: ReturnType<typeof setInterval> | null = null;
  const stop = () => {
    if (timer) clearInterval(timer);
    timer = null;
  };
  const check = () => {
    if (Date.now() - started > GIVE_UP_MS) return stop();
    const store = getStore();
    if (!collectionsLoaded(store)) return;
    stop();
    onHealed(healPoisonedComputeds(store));
  };
  timer = setInterval(check, CHECK_MS);
  check();
  return stop;
}
