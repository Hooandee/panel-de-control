import { describe, expect, it } from "vitest";
import type { CleanerEntry } from "./types";
import { filterGames, formatBytes, groupEntries, toggleCaches, toggleEntry } from "./model";

const entry = (id: string, overrides: Partial<CleanerEntry> = {}): CleanerEntry => ({
  id, game_id: "game", appid: "10", name: "Game", kind: "shadercache",
  library_id: "library", library_label: "Library", bytes: 100,
  installation: "installed", blocked_reason: null, warnings: [], ...overrides,
});

describe("Steam Cleaner selection", () => {
  it("uses familiar decimal storage units without treating unknown sizes as zero", () => {
    expect(formatBytes(1_500_000_000, "en")).toBe("1.5 GB");
    expect(formatBytes(1_500_000, "es")).toBe("1,5 MB");
    expect(formatBytes(1000, "en")).toBe("1 KB");
    expect(formatBytes(0, "en")).toBe("0 B");
  });
  it("selects only eligible caches in a mixed game and keeps explicit prefixes", () => {
    const entries = [entry("cache"), entry("prefix", { kind: "compatdata" }), entry("busy", { blocked_reason: "game_running" })];
    expect([...toggleCaches(entries, new Set())]).toEqual(["cache"]);
    expect([...toggleCaches(entries, new Set(["prefix"]))]).toEqual(["prefix", "cache"]);
    expect([...toggleCaches(entries, new Set(["prefix", "cache"]))]).toEqual(["prefix"]);
  });

  it("requires an explicit category choice for prefixes and refuses protected entries", () => {
    expect([...toggleEntry(entry("prefix", { kind: "compatdata" }), new Set())]).toEqual(["prefix"]);
    expect([...toggleEntry(entry("blocked", { blocked_reason: "unknown_owner" }), new Set())]).toEqual([]);
  });

  it("does not infer ownership or eligibility from visual Steam metadata", () => {
    const groups = groupEntries([entry("x", { name: null, installation: "unknown", blocked_reason: "unknown_owner" })], new Map([["10", { name: "Known title", coverUrls: ["art"] }]]));
    expect(groups[0].name).toBe("Known title");
    expect(groups[0].entries[0].installation).toBe("unknown");
    expect([...toggleCaches(groups[0].entries, new Set())]).toEqual([]);
  });

  it("groups locations by backend identity and filters without changing selection", () => {
    const entries = [entry("a"), entry("b", { library_id: "second" }), entry("c", { game_id: "other", name: "Another", bytes: 999, installation: "not_installed" }), entry("d", { game_id: "blocked", name: "Blocked", blocked_reason: "game_running" })];
    const groups = groupEntries(entries, new Map());
    const selected = new Set(["b"]);
    expect(groups).toHaveLength(3);
    expect(filterGames(groups, "GAME", "all", "size", selected).map((g) => g.id)).toEqual(["game"]);
    expect(filterGames(groups, "", "cleanable", "size", selected).map((g) => g.id)).toEqual(["other", "game"]);
    expect(filterGames(groups, "", "not_installed", "size", selected).map((g) => g.id)).toEqual(["other"]);
    expect(filterGames(groups, "", "selected", "size", selected).map((g) => g.id)).toEqual(["game"]);
    expect([...selected]).toEqual(["b"]);
  });
});
