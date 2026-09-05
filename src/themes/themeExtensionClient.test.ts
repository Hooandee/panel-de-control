import { describe, expect, it, vi } from "vitest";

import {
  createThemeExtensionClient,
  parseThemeExtensionDescriptors,
  parseThemeExtensionPayload,
} from "./themeExtensionClient";

const DESCRIPTOR = {
  catalogId: "example-theme",
  cssLoaderName: "Example Theme",
  version: "1.2.3",
  abiVersion: 1,
  sha256: "a".repeat(64),
};

describe("theme extension RPC parser", () => {
  it("accepts exact bounded descriptors and payloads", () => {
    expect(parseThemeExtensionDescriptors([DESCRIPTOR])).toEqual([DESCRIPTOR]);
    expect(parseThemeExtensionPayload({ ...DESCRIPTOR, source: "module.exports = {};" }))
      .toEqual({ ...DESCRIPTOR, source: "module.exports = {};" });
  });

  it.each([
    { ...DESCRIPTOR, path: "/private/theme.js" },
    { ...DESCRIPTOR, url: "https://attacker.invalid/theme.js" },
    { ...DESCRIPTOR, version: "v1.2.3" },
    { ...DESCRIPTOR, abiVersion: 2 },
    { ...DESCRIPTOR, sha256: "A".repeat(64) },
    { ...DESCRIPTOR, cssLoaderName: "Example/Theme" },
    { ...DESCRIPTOR, cssLoaderName: "Example\\Theme" },
  ])("rejects unknown, unsafe or unsupported descriptor fields", (descriptor) => {
    expect(() => parseThemeExtensionDescriptors([descriptor])).toThrow();
  });

  it("rejects duplicate and oversized descriptor collections", () => {
    expect(() => parseThemeExtensionDescriptors([DESCRIPTOR, DESCRIPTOR])).toThrow();
    expect(() => parseThemeExtensionDescriptors(Array.from({ length: 33 }, (_, index) => ({
      ...DESCRIPTOR, catalogId: `example-${index}`, cssLoaderName: `Example ${index}`,
    })))).toThrow();
  });

  it("bounds payload source by UTF-8 bytes and rejects missing source", () => {
    expect(() => parseThemeExtensionPayload({ ...DESCRIPTOR, source: "" })).toThrow();
    expect(() => parseThemeExtensionPayload({
      ...DESCRIPTOR,
      source: "é".repeat(1_048_577),
    })).toThrow();
  });

  it("exposes only parsed list/load results from the configured RPC host", async () => {
    const list = vi.fn(async () => [DESCRIPTOR]);
    const load = vi.fn(async () => ({ ...DESCRIPTOR, source: "module.exports = {};" }));
    const client = createThemeExtensionClient({ list, load });

    await expect(client.list()).resolves.toEqual([DESCRIPTOR]);
    await expect(client.load("example-theme", "1.2.3")).resolves.toMatchObject(DESCRIPTOR);
    expect(load).toHaveBeenCalledWith("example-theme", "1.2.3");
  });
});
