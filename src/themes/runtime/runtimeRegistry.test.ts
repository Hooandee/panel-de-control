import { describe, expect, it, vi } from "vitest";

import type { ThemeCatalog } from "../types";
import type { ThemeRuntimeModule } from "./runtimeManager";
import type { ThemeRuntimeFactory } from "./runtimeRegistry";

describe("theme runtime registry", () => {
  it("creates only catalog-declared runtimes whose factories are registered", async () => {
    const modulePath = "./runtimeRegistry";
    const loaded = await import(/* @vite-ignore */ modulePath).catch(() => null);

    expect(loaded).not.toBeNull();
    if (!loaded) return;
    const createRegisteredRuntimeModules = Reflect.get(
      loaded,
      "createRegisteredRuntimeModules",
    ) as unknown;
    expect(createRegisteredRuntimeModules).toBeTypeOf("function");
    if (typeof createRegisteredRuntimeModules !== "function") return;

    const catalog: ThemeCatalog = {
      schemaVersion: 1,
      themes: [
        {
          id: "known",
          cssLoaderName: "Known",
          nameKey: "known",
          descriptionKey: "known",
          availability: "available",
          author: "Hooandee",
          cssLoaderManifestVersion: 9,
          minimumCssLoaderBackendVersion: 9,
          tags: [],
          installSources: [],
          runtime: { moduleId: "known-runtime", surfaces: ["library"], capabilities: [] },
        },
        {
          id: "unknown",
          cssLoaderName: "Unknown",
          nameKey: "unknown",
          descriptionKey: "unknown",
          availability: "available",
          author: "Hooandee",
          cssLoaderManifestVersion: 9,
          minimumCssLoaderBackendVersion: 9,
          tags: [],
          installSources: [],
          runtime: { moduleId: "unknown-runtime", surfaces: ["library"], capabilities: [] },
        },
      ],
    };
    const known: ThemeRuntimeModule = { id: "known-runtime", mount: vi.fn(() => vi.fn()) };
    const factory = vi.fn(() => known);
    const modules = createRegisteredRuntimeModules(
      {} as Document,
      catalog,
      new Map([["known-runtime", factory]]),
    ) as ThemeRuntimeModule[];

    expect(modules).toEqual([known]);
    expect(factory).toHaveBeenCalledOnce();
  });

  it("fails closed for throwing, mismatched, and duplicate factories", async () => {
    const { createRegisteredRuntimeModules } = await import("./runtimeRegistry");
    const entry = (id: string, moduleId: string): ThemeCatalog["themes"][number] => ({
      id,
      cssLoaderName: id,
      nameKey: id,
      descriptionKey: id,
      availability: "available",
      author: "Hooandee",
      cssLoaderManifestVersion: 9,
      minimumCssLoaderBackendVersion: 9,
      tags: [],
      installSources: [],
      runtime: { moduleId, surfaces: ["library"], capabilities: [] },
    });
    const catalog: ThemeCatalog = {
      schemaVersion: 1,
      themes: [
        entry("throwing", "throwing-runtime"),
        entry("mismatched", "mismatched-runtime"),
        entry("known-first", "known-runtime"),
        entry("known-duplicate", "known-runtime"),
      ],
    };
    const known: ThemeRuntimeModule = { id: "known-runtime", mount: vi.fn(() => vi.fn()) };
    const knownFactory = vi.fn(() => known);
    const modules = createRegisteredRuntimeModules({} as Document, catalog, new Map<string, ThemeRuntimeFactory>([
      ["throwing-runtime", () => { throw new Error("broken factory"); }],
      ["mismatched-runtime", () => ({ id: "other-runtime", mount: () => vi.fn() })],
      ["known-runtime", knownFactory],
    ]));

    expect(modules).toEqual([known]);
    expect(knownFactory).toHaveBeenCalledOnce();
  });
});
