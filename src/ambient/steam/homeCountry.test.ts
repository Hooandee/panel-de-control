import { afterEach, describe, expect, it } from "vitest";

import { homeCountry } from "./homeCountry";

function steam(value: unknown) {
  (globalThis as { SteamClient?: unknown }).SteamClient = { User: { GetIPCountry: async () => value } };
}

describe("homeCountry", () => {
  afterEach(() => {
    delete (globalThis as { SteamClient?: unknown }).SteamClient;
  });

  it("prefers Steam's IP country over the language region", async () => {
    steam("es");
    expect(await homeCountry("en-US")).toBe("ES");
  });

  it("falls back to the language region when Steam has nothing", async () => {
    steam("");
    expect(await homeCountry("it-IT")).toBe("IT");
    delete (globalThis as { SteamClient?: unknown }).SteamClient;
    expect(await homeCountry("de-DE")).toBe("DE");
  });

  it("returns null instead of guessing", async () => {
    expect(await homeCountry("es")).toBeNull();
  });
});
