import { describe, expect, it } from "vitest";

import { declareSteamGlobals, STEAM_GLOBALS } from "./steamGlobals";

describe("declareSteamGlobals", () => {
  it("creates empty bindings so optional chaining on them stops throwing", () => {
    const scope: Record<string, unknown> = {};
    declareSteamGlobals(scope);
    for (const name of STEAM_GLOBALS) {
      expect(name in scope).toBe(true);
      expect(scope[name]).toBeUndefined();
    }
  });

  it("never replaces a real Steam global", () => {
    const client = { System: {} };
    const scope: Record<string, unknown> = { SteamClient: client };
    declareSteamGlobals(scope);
    expect(scope.SteamClient).toBe(client);
  });
});
