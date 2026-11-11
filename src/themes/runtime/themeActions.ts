/**
 * Buttons a theme declares under `actions` in its panel-theme.json, shown in its settings in Panel.
 * The listener runs with the action's id each time the user confirms one of this theme's actions; a
 * theme only ever hears its own. Absent on a Panel that does not offer actions (and on Windows).
 */
export interface ThemeActionsAccess {
  subscribe(listener: (id: string) => void): () => void;
}

/** What the host scopes per mounted theme; every call names the theme's catalog id. */
export interface ThemeActionsProvider {
  subscribe(catalogId: string, listener: (id: string) => void): () => void;
}

export class ThemeActionsChannel implements ThemeActionsProvider {
  private readonly listeners = new Map<string, Set<(id: string) => void>>();
  private readonly watchers = new Set<() => void>();

  constructor(private readonly log: (code: "action_listener_failed") => void = (code) => console.warn(`[themes:${code}]`)) {}

  subscribe(catalogId: string, listener: (id: string) => void): () => void {
    if (typeof listener !== "function") return () => {};
    let set = this.listeners.get(catalogId);
    if (!set) {
      set = new Set();
      this.listeners.set(catalogId, set);
    }
    const entry = (id: string) => listener(id);
    set.add(entry);
    this.notify();
    let active = true;
    return () => {
      if (!active) return;
      active = false;
      const current = this.listeners.get(catalogId);
      current?.delete(entry);
      if (current?.size === 0) this.listeners.delete(catalogId);
      this.notify();
    };
  }

  listening(catalogId: string): boolean {
    return (this.listeners.get(catalogId)?.size ?? 0) > 0;
  }

  /** Lets Panel's settings follow whether a theme's runtime is there to receive its actions. */
  watch(listener: () => void): () => void {
    this.watchers.add(listener);
    return () => { this.watchers.delete(listener); };
  }

  /** How many of the theme's listeners took the action without throwing. */
  dispatch(catalogId: string, id: string): number {
    let delivered = 0;
    for (const listener of [...(this.listeners.get(catalogId) ?? [])]) {
      try {
        listener(id);
        delivered += 1;
      } catch {
        this.log("action_listener_failed");
      }
    }
    return delivered;
  }

  private notify(): void {
    for (const watcher of [...this.watchers]) {
      try {
        watcher();
      } catch {}
    }
  }
}

export const themeActionsChannel = new ThemeActionsChannel();
