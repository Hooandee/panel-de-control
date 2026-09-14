export type QamEntryToken = string;

export interface QamLayout {
  order: QamEntryToken[];
  hiddenNative: QamEntryToken[];
  pinnedViews: QamEntryToken[];
  ownedIds: Record<QamEntryToken, number>;
}

export const QAM_DECKY_TOKEN = "decky";
export const QAM_HOME_TOKEN = "pdc:home";

export function isNativeQamToken(token: string): boolean {
  return token.startsWith("native:") && token.length > "native:".length;
}

export function isPanelQamToken(token: string): boolean {
  if (token === QAM_HOME_TOKEN) return true;
  return (token.startsWith("pdc:section:") && token.length > "pdc:section:".length)
    || (token.startsWith("pdc:view:") && token.length > "pdc:view:".length);
}

export function completeQamOrder(
  preferred: readonly QamEntryToken[],
  available: readonly QamEntryToken[],
): QamEntryToken[] {
  const allowed = new Set(available);
  return uniqueStrings([...preferred, ...available], (token) => allowed.has(token));
}

function uniqueStrings(value: unknown, keep: (token: string) => boolean): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const result: string[] = [];
  for (const candidate of value) {
    if (typeof candidate !== "string" || seen.has(candidate) || !keep(candidate)) continue;
    seen.add(candidate);
    result.push(candidate);
  }
  return result;
}

export function createDefaultQamLayout(): QamLayout {
  return {
    order: [],
    hiddenNative: [],
    pinnedViews: [],
    ownedIds: {},
  };
}

export function coerceQamLayout(value: unknown): QamLayout {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return createDefaultQamLayout();
  }
  const input = value as Partial<Record<keyof QamLayout, unknown>>;
  const ownedIds: Record<string, number> = {};
  if (input.ownedIds && typeof input.ownedIds === "object" && !Array.isArray(input.ownedIds)) {
    for (const [token, id] of Object.entries(input.ownedIds)) {
      if (isPanelQamToken(token) && Number.isSafeInteger(id) && (id as number) > 0) {
        ownedIds[token] = id as number;
      }
    }
  }
  return {
    order: uniqueStrings(input.order, (token) => isNativeQamToken(token) || isPanelQamToken(token)),
    hiddenNative: uniqueStrings(input.hiddenNative, isNativeQamToken),
    pinnedViews: uniqueStrings(input.pinnedViews, isPanelQamToken),
    ownedIds,
  };
}

export function resolveQamTokens(
  defaults: QamEntryToken[],
  layout: QamLayout,
  protectedToken: QamEntryToken,
): QamEntryToken[] {
  const hiddenNative = new Set(layout.hiddenNative);
  const pinnedViews = new Set(layout.pinnedViews);
  const visible = (token: string) => {
    if (token === protectedToken) return true;
    if (isNativeQamToken(token)) return !hiddenNative.has(token);
    if (isPanelQamToken(token)) return pinnedViews.has(token);
    return false;
  };
  const ordered = completeQamOrder(layout.order, defaults);
  const result = ordered.filter((token) => token !== protectedToken && visible(token));
  if (ordered.includes(protectedToken)) result.push(protectedToken);
  return result;
}
