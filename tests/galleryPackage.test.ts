import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { LOCAL_THEME_CATALOG } from "../src/themes/catalog";

const root = resolve(process.cwd(), "themes/gallery");

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

describe("Hooandee Gallery package", () => {
  it("is a complete CSS Loader v9 theme with an independently pinned bundled version", () => {
    const manifest = json("theme.json");
    const bundledDescriptor = JSON.parse(readFileSync(resolve(
      process.cwd(),
      "themes/bundled/hooandee-gallery/0.7.8/gallery.json",
    ), "utf8")) as { version: string };

    expect(manifest).toMatchObject({
      name: "Hooandee Gallery",
      display_name: "Hooandee Gallery",
      author: "Hooandee",
      version: "0.7.9",
      manifest_version: 9,
      target: "System-Wide",
    });
    const references = referencedCss({ inject: manifest.inject, patches: manifest.patches });
    expect(references.size).toBe(50);
    expect([...references].filter((file) => !existsSync(resolve(root, file)))).toEqual([]);
    expect(LOCAL_THEME_CATALOG.themes.find((theme) => (
      theme.id === "hooandee-gallery"
    ))?.includedVersion).toBe(bundledDescriptor.version);
    expect(manifest.version).not.toBe(bundledDescriptor.version);
  });

  it("declares the stable Panel identity for its native runtime", () => {
    expect(json("panel-theme.json")).toEqual({
      schemaVersion: 1,
      catalogId: "hooandee-gallery",
      runtime: {
        moduleId: "gallery",
        surfaces: ["library", "library-grid", "game-details", "settings"],
      },
    });
  });

  it("keeps normal and performance profiles mutually exclusive and complete", () => {
    const manifest = json("theme.json");
    const patches = manifest.patches as Record<string, {
      values: Record<string, Record<string, readonly string[]>>;
    }>;
    const performance = patches["Modo de rendimiento"];

    expect(Object.keys(performance.values.No)).toEqual(["library.css", "details.css"]);
    expect(Object.keys(performance.values.Yes)).toEqual([
      "options/performance-library-core.css",
      "options/performance-details-core.css",
      "options/performance-mode.css",
    ]);
    for (const path of [...Object.keys(performance.values.No), ...Object.keys(performance.values.Yes)]) {
      expect(existsSync(resolve(root, path))).toBe(true);
    }
  });

  it("owns the full achievements route outside both game-details paint profiles", () => {
    const manifest = json("theme.json");
    const inject = manifest.inject as Record<string, readonly string[]>;
    const details = readFileSync(resolve(root, "details.css"), "utf8");
    const performanceDetails = readFileSync(
      resolve(root, "options/performance-details-core.css"),
      "utf8",
    );

    expect(inject["achievements.css"]).toEqual(["bigpicture"]);

    const achievements = readFileSync(resolve(root, "achievements.css"), "utf8");
    expect(achievements.startsWith("/* pdc-gallery-static: achievements */")).toBe(true);
    expect(achievements.startsWith("/* pdc-gallery-surface:")).toBe(false);
    expect(achievements.startsWith("/* pdc-gallery-feature:")).toBe(false);
    expect(achievements).toContain("--hdg-achievements-route: active");
    expect(achievements).toContain('@scope (#Main)');
    expect(details).not.toContain('id$="achievements_Content"');
    expect(performanceDetails).not.toContain('id$="achievements_Content"');

    const achievementRow = achievements.match(
      /\.Panel\.Focusable\[style\*="position: absolute"\][^{]+\{([\s\S]*?)\n\}/,
    )?.[1];
    const focusedRow = achievements.match(
      /\.Panel\.Focusable\.gpfocus\[style\*="position: absolute"\][^{]+\{([\s\S]*?)\n\}/,
    )?.[1];
    const focusHalo = achievements.match(
      /\.Panel\.Focusable\.gpfocus\[style\*="position: absolute"\][^{]+::after\s*\{([\s\S]*?)\n\}/,
    )?.[1];

    expect(achievementRow).toContain("margin-block: 6px !important");
    expect(achievementRow).toContain("overflow: visible !important");
    expect(focusedRow).toContain("z-index: 1");
    expect(focusHalo).toContain("inset: -5px !important");
  });

  it("ships only declarative CSS Loader content", () => {
    const entries = readdirSync(root, { recursive: true }).map(String);
    expect(entries.filter((file) => /\.(?:js|mjs|cjs|ts|tsx|py)$/i.test(file))).toEqual([]);
    expect(entries.filter((file) => /\.[^.\/]+$/i.test(file)).every((file) => (
      file.endsWith(".css") || file === "theme.json" || file === "panel-theme.json"
    ))).toBe(true);

    const manifest = json("theme.json");
    const declared = [...referencedCss({ inject: manifest.inject, patches: manifest.patches })]
      .sort();
    const packaged = entries.filter((file) => file.endsWith(".css")).sort();
    expect(packaged).toEqual(declared);
    for (const file of packaged) {
      const css = readFileSync(resolve(root, file), "utf8");
      expect(css).not.toMatch(/@import\b|url\s*\(/i);
    }
  });

  it("styles the active Panel tab from semantic state without an external glow", () => {
    const qam = readFileSync(resolve(root, "qam.css"), "utf8");
    const light = readFileSync(resolve(root, "options/light-mode.css"), "utf8");
    const activeRule = qam.match(
      /#QuickAccess-Menu \.pdc-tabstrip\s+\[role="button"\]\[aria-current="page"\]\s*\{([\s\S]*?)\n\}/,
    )?.[1];

    expect(activeRule).toBeDefined();
    expect(activeRule).toContain("background: var(--hdg-accent-fill) !important");
    expect(activeRule).toContain("color: var(--hdg-accent-on-fill) !important");
    expect(activeRule).not.toContain("var(--hdg-accent-glow)");
    expect(qam).toContain('[aria-current="page"] :is(div, span, svg)');
    const semanticState =
      '.pdc-root [role="button"]:is(.gpfocus, .gpfocuswithin, [aria-selected="true"], [aria-current="page"])';
    const semanticRuleStart = light.indexOf(semanticState);
    const semanticRuleEnd = light.indexOf("\n}", semanticRuleStart);

    expect(semanticRuleStart).toBeGreaterThanOrEqual(0);
    expect(light.slice(semanticRuleStart, semanticRuleEnd)).toContain(
      "color: var(--hdg-accent-on-fill) !important",
    );
  });

  it("marks each runtime-managed surface with an exact ownership comment", () => {
    const marker = (surface: string) => `/* pdc-gallery-surface: ${surface} */`;

    expect(readFileSync(resolve(root, "home.css"), "utf8").startsWith(marker("library"))).toBe(true);
    expect(readFileSync(resolve(root, "library.css"), "utf8").startsWith(marker("library-grid"))).toBe(true);
    expect(readFileSync(resolve(root, "options/performance-library-core.css"), "utf8")
      .startsWith(marker("library-grid"))).toBe(true);
    expect(readFileSync(resolve(root, "details.css"), "utf8").startsWith(marker("game-details"))).toBe(true);
    expect(readFileSync(resolve(root, "options/performance-details-core.css"), "utf8")
      .startsWith(marker("game-details"))).toBe(true);
    expect(readFileSync(resolve(root, "settings.css"), "utf8").startsWith(marker("settings"))).toBe(true);
  });

  it("marks expensive optional feature sheets for runtime isolation", () => {
    const marker = (feature: string) => `/* pdc-gallery-feature: ${feature}:v1 */`;

    expect(readFileSync(resolve(root, "downloads.css"), "utf8")
      .startsWith(marker("downloads"))).toBe(true);
    expect(readFileSync(resolve(root, "media.css"), "utf8")
      .startsWith(marker("media"))).toBe(true);
  });

  it("bounds relational selector work on game-details focus changes", () => {
    const details = readFileSync(resolve(root, "details.css"), "utf8");

    expect(details.split(":has(").length - 1).toBeLessThanOrEqual(160);
  });

  it("keeps the enlarged details artwork centered without flex shrink", () => {
    const details = readFileSync(resolve(root, "details.css"), "utf8");
    const artworkRule = details.match(
      /:scope\s+:is\(\s*img\[src\*="\/library_hero\.jpg"\],[\s\S]*?\)\s*\{([\s\S]*?)\n\}/,
    )?.[1];

    expect(artworkRule).toBeDefined();
    expect(artworkRule).toContain("flex-shrink: 0 !important");
    expect(artworkRule).toContain(
      "inset-block: calc(-1 * (var(--hdg-details-background-blur) + 24px)) !important",
    );
    expect(artworkRule).toContain("inset-inline: auto !important");
  });

  it("retires redundant native grid effects and lowers the focused backdrop during virtualized bursts", () => {
    const normal = readFileSync(resolve(root, "library.css"), "utf8");
    const performance = readFileSync(resolve(root, "options/performance-library-core.css"), "utf8");

    for (const profile of [normal, performance]) {
      expect(profile).toContain('[role="link"]:not(.gpfocus) ~ div:has(> img[role="presentation"])');
      expect(profile).toContain('div:has(> svg:first-child):has(> svg:nth-child(2))');
      expect(profile).toContain("backdrop-filter: none !important");
    }
    expect(normal).toContain('html:root[data-pdc-gallery-grid-motion="busy"]');
    expect(normal).toContain("filter: saturate(1.04) brightness(0.52) !important");
  });

  it("contains offscreen activity date groups in both details paint profiles", () => {
    const profiles = [
      readFileSync(resolve(root, "details.css"), "utf8"),
      readFileSync(resolve(root, "options/performance-details-core.css"), "utf8"),
    ];

    for (const profile of profiles) {
      expect(profile).toContain('[role="tabpanel"][id$="WhatsNew_Content"]');
      expect(profile).toContain('[role="region"] [role="region"]');
      expect(profile).toContain("content-visibility: auto");
      expect(profile).toContain("contain-intrinsic-block-size: auto 450px");
    }
  });

  it("contains offscreen community rows in both details paint profiles", () => {
    const profiles = [
      readFileSync(resolve(root, "details.css"), "utf8"),
      readFileSync(resolve(root, "options/performance-details-core.css"), "utf8"),
    ];

    for (const profile of profiles) {
      expect(profile).toContain('[role="tabpanel"][id$="Community_Content"]');
      expect(profile).toContain('[role="grid"] > [role="row"]');
      expect(profile).toContain("content-visibility: auto");
      expect(profile).toContain("contain-intrinsic-block-size: auto 520px");
    }
  });
});
