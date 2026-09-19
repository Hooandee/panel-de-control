import { PDC_QAM_TAB_ID } from "../deckyInternal";
import { isPanelQamToken, QAM_HOME_TOKEN, type QamEntryToken } from "./layout";

export function assignOwnedIds(
  tokens: QamEntryToken[],
  existing: Record<QamEntryToken, number>,
  occupied: ReadonlySet<number>,
): Record<QamEntryToken, number> {
  const assigned = { ...existing };
  const used = new Set<number>(occupied);
  const existingIds = new Set<number>();

  for (const [token, id] of Object.entries(existing)) {
    if (!isPanelQamToken(token) || !Number.isSafeInteger(id) || id <= 0) {
      throw new Error("owned_id_invalid");
    }
    if (existingIds.has(id)) throw new Error("owned_id_duplicate");
    if (occupied.has(id)) throw new Error("owned_id_occupied");
    existingIds.add(id);
    used.add(id);
  }

  if (tokens.includes(QAM_HOME_TOKEN)) {
    const current = assigned[QAM_HOME_TOKEN];
    if (current !== undefined && current !== PDC_QAM_TAB_ID) {
      throw new Error("home_id_mismatch");
    }
    if (current === undefined && occupied.has(PDC_QAM_TAB_ID)) {
      throw new Error("home_id_occupied");
    }
    assigned[QAM_HOME_TOKEN] = PDC_QAM_TAB_ID;
    used.add(PDC_QAM_TAB_ID);
  }

  let candidate = PDC_QAM_TAB_ID + 1;
  for (const token of tokens) {
    if (!isPanelQamToken(token)) throw new Error("owned_token_invalid");
    if (assigned[token] !== undefined) continue;
    while (used.has(candidate)) candidate += 1;
    assigned[token] = candidate;
    used.add(candidate);
    candidate += 1;
  }
  return assigned;
}
