import { LOCAL_THEME_CATALOG } from "../catalog";
import type { ThemeCatalog } from "../types";
import { createGalleryRuntime } from "./gallery";
import { createObsidianBloomRuntime } from "./obsidianBloom";
import type { ThemeRuntimeModule } from "./runtimeManager";

export type ThemeRuntimeFactory = (doc: Document) => ThemeRuntimeModule;

export const THEME_RUNTIME_FACTORIES: ReadonlyMap<string, ThemeRuntimeFactory> = new Map([
  ["gallery", createGalleryRuntime],
  ["obsidian-bloom", createObsidianBloomRuntime],
]);

export function createRegisteredRuntimeModules(
  doc: Document,
  catalog: ThemeCatalog = LOCAL_THEME_CATALOG,
  factories: ReadonlyMap<string, ThemeRuntimeFactory> = THEME_RUNTIME_FACTORIES,
): ThemeRuntimeModule[] {
  const created = new Set<string>();
  const modules: ThemeRuntimeModule[] = [];
  for (const entry of catalog.themes) {
    const moduleId = entry.runtime?.moduleId;
    if (!moduleId || created.has(moduleId)) continue;
    const factory = factories.get(moduleId);
    if (!factory) continue;
    try {
      const module = factory(doc);
      if (module.id !== moduleId || typeof module.mount !== "function") continue;
      created.add(moduleId);
      modules.push(module);
    } catch {}
  }
  return modules;
}
