import { describe, expect, it, vi } from "vitest";

import {
  createThemeDataBridge,
  listThemeData,
  parseThemeDataEntries,
  parseThemeDataRecord,
  resetThemeData,
  type ThemeDataRpcHost,
} from "./themeDataClient";

function host(overrides: Partial<ThemeDataRpcHost> = {}): ThemeDataRpcHost {
  return {
    get: vi.fn(async () => ({ summary: "3 páginas", value: { v: 1 }, updatedAt: 5, bytes: 40 })),
    save: vi.fn(async () => ({ ok: true, record: {} })),
    list: vi.fn(async () => [{ catalogId: "hooandee-bubble", summary: "s", updatedAt: 5, bytes: 40 }]),
    reset: vi.fn(async () => ({ ok: true, deleted: true })),
    ...overrides,
  };
}

describe("theme data access", () => {
  it("reads and writes only the bound theme", async () => {
    const rpc = host();
    const data = createThemeDataBridge(rpc).forTheme("hooandee-bubble");

    expect(await data.read()).toEqual({ summary: "3 páginas", value: { v: 1 }, updatedAt: 5, bytes: 40 });
    expect(await data.write({ summary: "4 páginas", value: { v: 2 } })).toBe("saved");
    expect(rpc.get).toHaveBeenCalledWith("hooandee-bubble");
    expect(rpc.save).toHaveBeenCalledWith("hooandee-bubble", "4 páginas", { v: 2 });
  });

  it("refuses unsafe identities when binding", () => {
    expect(() => createThemeDataBridge(host()).forTheme("../x")).toThrow();
  });

  it("maps backend refusals and failures", async () => {
    const refused = createThemeDataBridge(host({ save: vi.fn(async () => ({ ok: false, code: "too_large" })) })).forTheme("hooandee-bubble");
    const broken = createThemeDataBridge(host({ save: vi.fn(async () => { throw new Error("rpc"); }) })).forTheme("hooandee-bubble");

    expect(await refused.write({ summary: "", value: {} })).toBe("rejected");
    expect(await broken.write({ summary: "", value: {} })).toBe("failed");
    expect(await refused.write({ summary: "x".repeat(200), value: {} })).toBe("rejected");
  });

  it("tells the mounted theme when its data is reset", async () => {
    const rpc = host();
    const data = createThemeDataBridge(rpc).forTheme("hooandee-bubble");
    const heard: unknown[] = [];
    const stop = data.subscribe((record) => heard.push(record));

    expect(await resetThemeData("hooandee-bubble", rpc)).toBe(true);
    stop();
    await resetThemeData("hooandee-bubble", rpc);

    expect(heard).toEqual([null]);
  });

  it("does not notify when the reset fails", async () => {
    const rpc = host({ reset: vi.fn(async () => ({ ok: false, code: "reset_failed" })) });
    const heard: unknown[] = [];
    createThemeDataBridge(rpc).forTheme("hooandee-bubble").subscribe((record) => heard.push(record));

    expect(await resetThemeData("hooandee-bubble", rpc)).toBe(false);
    expect(heard).toEqual([]);
  });

  it("lists entries and drops malformed ones", async () => {
    expect(await listThemeData(host())).toEqual([{ catalogId: "hooandee-bubble", summary: "s", updatedAt: 5, bytes: 40 }]);
    expect(parseThemeDataEntries([{ catalogId: "Bad Id", summary: "", updatedAt: 1, bytes: 1 }, null, 3])).toEqual([]);
    expect(parseThemeDataRecord({ summary: "", updatedAt: 1, bytes: 1 })).toBeNull();
  });
});
