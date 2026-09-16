import { QAM_DECKY_TOKEN, type QamEntryToken } from "./layout";

const DECKY_PLUGIN_TAB_ID = 999;

export interface QamRenderedEntry {
  decky?: boolean;
  key: unknown;
  panel?: unknown;
  initialVisibility?: boolean;
  qAMVisibilitySetter?: (visible: boolean) => void;
}

export interface QamInventoryEntry {
  token: QamEntryToken;
  key: unknown;
  entry: QamRenderedEntry;
  kind: "native";
}

export type QamComposeFailureReason =
  | "decky_missing"
  | "rendered_key_invalid"
  | "rendered_key_duplicate"
  | "desired_token_duplicate"
  | "desired_token_missing"
  | "owned_entry_invalid"
  | "owned_key_collision";

export type QamComposeResult =
  | {
    ok: true;
    entries: QamRenderedEntry[];
    inventory: QamInventoryEntry[];
  }
  | {
    ok: false;
    reason: QamComposeFailureReason;
  };

function renderedKey(entry: QamRenderedEntry): string | null {
  return entry.key === null || entry.key === undefined ? null : String(entry.key);
}

export function composeQamEntries(
  original: readonly QamRenderedEntry[],
  desiredTokens: readonly QamEntryToken[],
  ownedEntries: ReadonlyMap<QamEntryToken, QamRenderedEntry>,
): QamComposeResult {
  const originalKeys = new Map<string, QamRenderedEntry>();
  for (const entry of original) {
    const key = renderedKey(entry);
    if (key === null) return { ok: false, reason: "rendered_key_invalid" };
    if (originalKeys.has(key)) return { ok: false, reason: "rendered_key_duplicate" };
    originalKeys.set(key, entry);
  }

  const ownedByKey = new Map<string, QamRenderedEntry>();
  for (const entry of ownedEntries.values()) {
    const key = renderedKey(entry);
    if (entry.decky !== true || entry.panel == null || key === null) {
      return { ok: false, reason: "owned_entry_invalid" };
    }
    const originalEntry = originalKeys.get(key);
    if ((originalEntry && originalEntry !== entry) || ownedByKey.has(key)) {
      return { ok: false, reason: "owned_key_collision" };
    }
    ownedByKey.set(key, entry);
  }

  const protectedDecky = original.filter((entry) => {
    const key = renderedKey(entry)!;
    return entry.decky === true && !ownedByKey.has(key);
  });
  if (!protectedDecky.some((entry) => String(entry.key) === String(DECKY_PLUGIN_TAB_ID))) {
    return { ok: false, reason: "decky_missing" };
  }

  const inventory: QamInventoryEntry[] = original
    .filter((entry) => entry.decky !== true)
    .map((entry) => ({
      token: `native:${String(entry.key)}`,
      key: entry.key,
      entry,
      kind: "native" as const,
    }));
  const available = new Map<QamEntryToken, QamRenderedEntry[]>();
  inventory.forEach(({ token, entry }) => available.set(token, [entry]));
  ownedEntries.forEach((entry, token) => available.set(token, [entry]));
  available.set(QAM_DECKY_TOKEN, protectedDecky);

  const seen = new Set<QamEntryToken>();
  const entries: QamRenderedEntry[] = [];
  for (const token of desiredTokens) {
    if (seen.has(token)) return { ok: false, reason: "desired_token_duplicate" };
    seen.add(token);
    const resolved = available.get(token);
    if (!resolved) return { ok: false, reason: "desired_token_missing" };
    entries.push(...resolved);
  }
  if (!seen.has(QAM_DECKY_TOKEN)) return { ok: false, reason: "desired_token_missing" };

  return { ok: true, entries, inventory };
}
