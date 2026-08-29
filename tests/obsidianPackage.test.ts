import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { LOCAL_THEME_CATALOG } from "../src/themes/catalog";

const root = resolve(process.cwd(), "themes/obsidian-bloom");

function json(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(resolve(root, path), "utf8")) as Record<string, unknown>;
}

function referencedCss(value: unknown, files = new Set<string>()): Set<string> {
  if (!value || typeof value !== "object") return files;
  for (const [key, child] of Object.entries(value)) {
    if (key.endsWith(".css")) files.add(key);
    referencedCss(child, files);
  }
  return files;
}

describe("Obsidian Bloom package", () => {
  it("is a complete CSS Loader v9 theme whose referenced CSS exists", () => {
    const manifest = json("theme.json");

    expect(manifest).toMatchObject({
      name: "Hooandee Obsidian Bloom",
      display_name: "Obsidian Bloom",
      author: "Hooandee",
      version: "v0.3.2",
      manifest_version: 9,
      target: "System-Wide",
    });
    const references = referencedCss({ inject: manifest.inject, patches: manifest.patches });
    expect(references.size).toBeGreaterThan(8);
    expect([...references].filter((file) => !existsSync(resolve(root, file)))).toEqual([]);
    expect(LOCAL_THEME_CATALOG.themes.find((theme) => theme.id === "hooandee-obsidian-bloom")?.version)
      .toBe(String(manifest.version).replace(/^v/, ""));
  });

  it("ships its display font and license inside the on-demand theme package", () => {
    const fontPath = resolve(root, "assets/fonts/Oxanium-SemiBold.ttf");
    const licensePath = resolve(root, "assets/fonts/OFL.txt");
    const missing = [fontPath, licensePath].filter((path) => !existsSync(path));
    expect(missing).toEqual([]);
    if (missing.length) return;
    const font = readFileSync(fontPath);
    const license = readFileSync(licensePath, "utf8");

    expect([...font.subarray(0, 4)]).toEqual([0, 1, 0, 0]);
    expect(font.byteLength).toBeGreaterThan(10_000);
    expect(license).toContain("SIL OPEN FONT LICENSE Version 1.1");
  });

  it("exposes every advanced engine scene as a real CSS Loader patch with a CSS-only fallback", () => {
    const manifest = json("theme.json");
    const patches = manifest.patches as Record<string, unknown>;
    expect(Object.keys(patches)).toEqual(expect.arrayContaining([
      "Escena de biblioteca",
      "Escena de parrilla",
      "Transición al detalle",
      "Estilo de ajustes",
    ]));

    const advancedReferences = referencedCss({
      library: patches["Escena de biblioteca"],
      grid: patches["Escena de parrilla"],
      details: patches["Transición al detalle"],
      settings: patches["Estilo de ajustes"],
    });
    expect(advancedReferences).toEqual(new Set([
      "options/library-essential.css",
      "options/library-immersive.css",
      "options/grid-direct.css",
      "options/grid-orbit.css",
      "options/grid-constellation.css",
      "options/grid-abyss-fallback.css",
      "options/details-none.css",
      "options/details-fade.css",
      "options/details-portal-fallback.css",
      "options/settings-steam.css",
      "options/settings-glass.css",
      "options/settings-comet.css",
    ]));
  });

  it("declares a known Panel runtime without shipping executable code", () => {
    expect(json("panel-theme.json")).toMatchObject({
      schemaVersion: 1,
      catalogId: "hooandee-obsidian-bloom",
      runtime: {
        moduleId: "obsidian-bloom",
        surfaces: ["library", "library-grid", "game-details", "settings"],
      },
    });
    expect(readdirSync(root, { recursive: true })
      .map(String)
      .filter((file) => /\.(?:js|mjs|cjs|ts|tsx)$/i.test(file))).toEqual([]);
  });

  it("preserves a visible native focus fallback in every performance mode", () => {
    const tokens = readFileSync(resolve(root, "tokens.css"), "utf8");
    const performance = readFileSync(resolve(root, "options/performance-mode.css"), "utf8");

    expect(tokens).not.toMatch(/\.gpfocus\s*\{[^}]*outline[^}]*transparent/is);
    expect(performance).not.toMatch(/html:root\s+\*[^}]*box-shadow\s*:\s*none/is);
    expect(performance).not.toMatch(/html:root\s+\*(?:::[a-z-]+)?\s*\{/i);
    expect(performance).toContain('[class*="quickaccessmenu_"]');
    expect(performance).toContain("#Main");
  });

  it("connects every user-facing density and backdrop option to an observable style", () => {
    const library = readFileSync(resolve(root, "library.css"), "utf8");
    const home = readFileSync(resolve(root, "home.css"), "utf8");

    expect(library).toContain("var(--hob-grid-card-width)");
    expect(home).toContain("var(--hob-backdrop-opacity)");
  });

  it("limits reduced motion to theme-owned transitions instead of all of Steam", () => {
    const calm = readFileSync(resolve(root, "options/motion-calm.css"), "utf8");
    const details = readFileSync(resolve(root, "details.css"), "utf8");

    expect(calm).not.toMatch(/html:root\s+\*/);
    expect(details).toContain("hob-details-arrive var(--hob-details-duration)");
  });

  it("hands card transforms to Panel while keeping the CSS-only abyss fallback", () => {
    const abyss = readFileSync(resolve(root, "options/grid-abyss-fallback.css"), "utf8");

    expect(abyss).toContain(':not([data-pdc-orbit-active="true"])');
    expect(abyss).toContain('html:root[data-pdc-orbit-active="true"]');
    expect(abyss).toContain('[data-pdc-orbit-card="true"] > div,');
    expect(abyss).toMatch(/data-pdc-orbit-active="true"[^}]+\{[^}]*transform:\s*none\s*!important/is);
  });
});
