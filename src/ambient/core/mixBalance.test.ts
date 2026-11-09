import { expect, it } from "vitest";
import { levelsForBalance, mixBalance } from "./mixBalance";

it("balances between game-only, equal levels and media-only", () => {
  expect(levelsForBalance(-100, 100, 100)).toEqual({game:100,media:0});
  expect(levelsForBalance(0, 100, 100)).toEqual({game:100,media:100});
  expect(levelsForBalance(100, 100, 100)).toEqual({game:0,media:100});
});
it("preserves existing independent levels when merely reading the balance", () => {
  for (const [game, media] of [[100,50],[25,100],[40,20],[20,40],[20,20],[0,0]]) {
    expect(levelsForBalance(mixBalance(game,media),game,media)).toEqual({game,media});
  }
});
it("does not increase the existing ceiling or unmute silent settings", () => {
  for (const value of [-100,-50,0,50,100]) {
    const result=levelsForBalance(value,20,10);
    expect(Math.max(result.game,result.media)).toBe(20);
    expect(levelsForBalance(value,0,0)).toEqual({game:0,media:0});
  }
});
it("bounds stale or invalid values", () => {
  expect(levelsForBalance(200,130,-2)).toEqual({game:0,media:100});
  expect(levelsForBalance(NaN,NaN,50)).toEqual({game:50,media:50});
});
