/** Groups shared by every theme: a hand-picked list, or the games that match a set of rules. */

export const RULE_TYPES = [
  "installed", "collection", "group", "name", "kind", "deckCompat", "steamosCompat", "tags", "features",
  "playtime", "lastPlayed", "released", "purchased", "size", "review", "achievements", "friends",
  "familyShared", "demo", "comingSoon", "streamable", "sdCard", "installFolder", "all",
] as const;
export type RuleType = (typeof RULE_TYPES)[number];

export interface Rule {
  type: RuleType;
  /** Matches the games the rule would leave out. */
  inverted: boolean;
  params: Record<string, unknown>;
}

export interface RuleSet {
  mode: "all" | "any";
  rules: Rule[];
}

export interface GroupDefinition {
  id: string;
  name: string;
  kind: "manual" | "rules";
  /** The picked games of a manual group. */
  appIds: number[];
  rules?: RuleSet;
  /** Games kept in a rule group even when they do not match. */
  added: number[];
  /** Games kept out of a rule group even when they match. */
  hidden: number[];
  /** Where an imported group came from, e.g. `tabmaster:<tab id>`; re-importing skips it. */
  importedFrom?: string;
  /** Id the group had in a theme before it moved to Panel, so pinned places still find it. */
  legacyId?: string;
}

export type AppKind = "game" | "shortcut" | "software" | "music" | "tool" | "video" | "other";

/** What the rules read about one app. Dates are Unix seconds; 0 means unknown. */
export interface AppFacts {
  appId: number;
  name: string;
  kind: AppKind;
  installed: boolean;
  collections: string[];
  tags: number[];
  features: number[];
  playtimeMinutes: number;
  lastPlayed: number;
  released: number;
  purchased: number;
  sizeBytes: number;
  /** Steam Deck / SteamOS compatibility: 0 unknown, 1 unsupported, 2 playable, 3 verified. */
  deckCompat: number;
  steamosCompat: number;
  metacritic: number;
  reviewPercent: number;
  achievementsPercent: number;
  achievementsDone: number;
  /** 0 when the app has no achievements. */
  achievementsTotal: number;
  familyShared: boolean;
  demo: boolean;
  comingSoon: boolean;
  streamable: boolean;
  installFolder: string | null;
  sdCard: string | null;
}

export interface EvaluationContext {
  facts(appId: number): AppFacts | undefined;
  /** The apps rules run over: games, shortcuts and family-shared games. */
  universe: readonly number[];
  /** Apps outside the default universe a `kind` rule may still reach (software, music, tools). */
  extended?: readonly number[];
  /** Steam ids of the friends who own the app, or null while not known yet. */
  friendOwners(appId: number): readonly string[] | null;
  definition(groupId: string): GroupDefinition | undefined;
  now: number;
}

export const GROUP_LIMITS = {
  groups: 100,
  manualGames: 200,
  rulesPerLevel: 32,
  depth: 3,
  name: 40,
} as const;
