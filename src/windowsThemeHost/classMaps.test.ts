import { describe, expect, it } from "vitest";

import { HOST_CLASS_MAPS_KEY, installHostClassMaps, isClassMap } from "./classMaps";

function steamScope(modules: Record<string, unknown>) {
  const require = Object.assign((id: string) => {
    if (id === "throws") throw new Error("not loadable");
    return modules[id];
  }, { m: Object.fromEntries(Object.keys(modules).map((id) => [id, {}])) });
  return { webpackChunksteamui: { push: (chunk: unknown[]) => (chunk[2] as (found: unknown) => void)(require) } } as unknown as typeof globalThis;
}

describe("host class maps", () => {
  it("publishes Steam's CSS module maps the way Decky's classMap does", () => {
    const details = { AppDetailsRoot: "_3fp5y6tdU77MdrCQZt_aS9", Header: "_x" };
    const scope = steamScope({ a: details, b: { __esModule: true, X: "y" }, c: { F5: () => {} }, d: { n: 1 }, throws: null });
    const dispose = installHostClassMaps(scope);

    expect((scope as unknown as Record<string, unknown>)[HOST_CLASS_MAPS_KEY]).toEqual([details]);
    dispose();
    expect(HOST_CLASS_MAPS_KEY in scope).toBe(false);
  });

  it("recognises only plain objects of strings", () => {
    expect(isClassMap({ A: "b" })).toBe(true);
    expect(isClassMap({})).toBe(false);
    expect(isClassMap(["a"])).toBe(false);
    expect(isClassMap({ A: "b", c: 2 })).toBe(false);
  });
});
