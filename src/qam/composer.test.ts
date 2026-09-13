import { describe, expect, it } from "vitest";

import { composeQamEntries, type QamRenderedEntry } from "./composer";

const native = (key: unknown): QamRenderedEntry => ({ key });
const decky = (key: unknown): QamRenderedEntry => ({ decky: true, key, panel: { key } });

describe("QAM entry composition", () => {
  it("mixes owned views and native entries without replacing opaque references", () => {
    const friends = native("friends");
    const help = native("help");
    const standardDecky = decky(999);
    const hud = decky(5_260_356);
    const original = [friends, help, standardDecky];

    const result = composeQamEntries(
      original,
      ["pdc:section:hud", "native:friends", "decky"],
      new Map([["pdc:section:hud", hud]]),
    );

    expect(result).toEqual({
      ok: true,
      entries: [hud, friends, standardDecky],
      inventory: [
        { token: "native:friends", key: "friends", entry: friends, kind: "native" },
        { token: "native:help", key: "help", entry: help, kind: "native" },
      ],
    });
    expect(original).toEqual([friends, help, standardDecky]);
    expect(result.ok && result.entries[1]).toBe(friends);
  });

  it("keeps unowned Decky tabs protected beside the standard Decky entry", () => {
    const friends = native(4);
    const standardDecky = decky(999);
    const otherOwnedPlugin = decky(42);

    const result = composeQamEntries(
      [friends, standardDecky, otherOwnedPlugin],
      ["native:4", "decky"],
      new Map(),
    );

    expect(result.ok && result.entries).toEqual([friends, standardDecky, otherOwnedPlugin]);
  });

  it("rejects a materialization without the protected Decky entry", () => {
    expect(composeQamEntries(
      [native("friends")],
      ["native:friends", "decky"],
      new Map(),
    )).toEqual({ ok: false, reason: "decky_missing" });
  });

  it("rejects duplicate rendered keys before changing order", () => {
    expect(composeQamEntries(
      [native("same"), native("same"), decky(999)],
      ["native:same", "decky"],
      new Map(),
    )).toEqual({ ok: false, reason: "rendered_key_duplicate" });
  });

  it("rejects duplicate or unavailable desired tokens", () => {
    const original = [native("friends"), decky(999)];

    expect(composeQamEntries(
      original,
      ["native:friends", "native:friends", "decky"],
      new Map(),
    )).toEqual({ ok: false, reason: "desired_token_duplicate" });
    expect(composeQamEntries(
      original,
      ["native:missing", "decky"],
      new Map(),
    )).toEqual({ ok: false, reason: "desired_token_missing" });
  });

  it("rejects owned entries without Decky panel semantics", () => {
    expect(composeQamEntries(
      [native("friends"), decky(999)],
      ["pdc:section:hud", "decky"],
      new Map([["pdc:section:hud", { key: 5_260_356 }]]),
    )).toEqual({ ok: false, reason: "owned_entry_invalid" });
  });
});
