import { describe, it, expect } from "vitest";
import { sortGames, SortMode } from "./sort";

const g = (name: string, lastPlayed: number, playtime: number) => ({ name, lastPlayed, playtime });

const GAMES = [
  g("Bravo", 0, 100), // never played
  g("Alpha", 1000, 5),
  g("Charlie", 3000, 50),
  g("Delta", 3000, 999), // same lastPlayed as Charlie
];

const names = (mode: SortMode) => sortGames(GAMES, mode).map((x) => x.name);

describe("sortGames", () => {
  it("recent: most-recently-played first, never-played last, ties by name", () => {
    expect(names("recent")).toEqual(["Charlie", "Delta", "Alpha", "Bravo"]);
  });

  it("alpha: A→Z by name", () => {
    expect(names("alpha")).toEqual(["Alpha", "Bravo", "Charlie", "Delta"]);
  });

  it("played: most minutes first, ties by name", () => {
    expect(names("played")).toEqual(["Delta", "Bravo", "Charlie", "Alpha"]);
  });

  it("does not mutate the input array", () => {
    const before = GAMES.map((x) => x.name);
    sortGames(GAMES, "recent");
    expect(GAMES.map((x) => x.name)).toEqual(before);
  });
});
