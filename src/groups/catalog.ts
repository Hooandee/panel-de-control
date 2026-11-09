import { createFriendOwnership, type SteamGlobals } from "./steamFacts";
import type { GroupDefinition } from "./types";

/** Values a theme offers when the user builds a rule: names come from Steam where it has them. */
export interface RuleCatalog {
  collections: { id: string; name: string }[];
  tags: { id: number; name: string }[];
  features: { id: number; name: string }[];
  friends: { id: string; name: string }[];
  folders: { id: string; name: string }[];
  cards: { id: string; name: string }[];
  groups: { id: string; name: string }[];
}

// Steam store categories ("features") by id. Steam has no client-side names for them.
const FEATURES: [number, string, string][] = [
  [2, "Un jugador", "Single-player"], [1, "Multijugador", "Multi-player"], [49, "JcJ", "PvP"],
  [9, "Cooperativo", "Co-op"], [38, "Cooperativo en línea", "Online co-op"], [48, "Cooperativo local", "Local co-op"],
  [24, "Pantalla compartida", "Shared/split screen"], [27, "Multiplataforma", "Cross-platform multiplayer"],
  [22, "Logros de Steam", "Steam Achievements"], [23, "Steam Cloud", "Steam Cloud"],
  [28, "Compatibilidad total con mando", "Full controller support"], [18, "Compatibilidad parcial con mando", "Partial controller support"],
  [29, "Cromos de Steam", "Steam Trading Cards"], [30, "Steam Workshop", "Steam Workshop"],
  [35, "Compras dentro de la aplicación", "In-app purchases"], [41, "Remote Play en teléfono", "Remote Play on phone"],
  [42, "Remote Play en tableta", "Remote Play on tablet"], [43, "Remote Play en TV", "Remote Play on TV"],
  [44, "Remote Play Together", "Remote Play Together"], [8, "Valve Anti-Cheat", "Valve Anti-Cheat"],
  [62, "Biblioteca familiar", "Family Sharing"],
];

export function buildCatalog(
  globals: SteamGlobals,
  friends: ReturnType<typeof createFriendOwnership>,
  groups: readonly GroupDefinition[],
  language: string,
  libraryTags: Iterable<number>,
): RuleCatalog {
  const es = language.startsWith("es");
  const store = globals.collectionStore;
  let user: readonly { id?: string; displayName?: string }[] = [];
  try { user = store?.userCollections ?? []; } catch { user = []; }
  const collections = [store?.GetCollection?.("favorite"), ...user]
    .flatMap((c) => (c?.id ? [{ id: c.id, name: c.displayName || c.id }] : []));
  const tagNames = globals.appStore?.m_mapStoreTagLocalization;
  const tags = [...new Set(libraryTags)].map((id) => ({ id, name: tagNames?.get(id) ?? "" }))
    .filter((tag) => tag.name).sort((a, b) => a.name.localeCompare(b.name));
  const folders = (globals.installFolderStore?.AllInstallFolders ?? []).map((folder) => {
    const id = folder.strDriveName || folder.strUserLabel || String(folder.nFolderIndex ?? "");
    return { id, name: folder.strUserLabel || id };
  }).filter((folder) => folder.id);
  const cards = (globals.MicroSDeck?.CardsAndGames ?? []).flatMap(([card]) => (card?.uid ? [{ id: card.uid, name: card.name || card.uid }] : []));
  return {
    collections,
    tags,
    features: FEATURES.map(([id, nameEs, nameEn]) => ({ id, name: es ? nameEs : nameEn })),
    friends: friends.list(),
    folders,
    cards,
    groups: groups.map((group) => ({ id: group.id, name: group.name })),
  };
}
