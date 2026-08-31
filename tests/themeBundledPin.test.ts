import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";

const bundledRoot = resolve(
  process.cwd(),
  "themes/bundled/hooandee-gallery/0.7.8",
);

function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

describe("bundled Gallery pin", () => {
  it("keeps the offline Gallery 0.7.8 package immutable and internally verified", () => {
    const descriptor = JSON.parse(
      readFileSync(resolve(bundledRoot, "gallery.json"), "utf8"),
    ) as {
      schemaVersion: number;
      id: string;
      cssLoaderName: string;
      version: string;
      artifact: { file: string; sha256: string; size: number };
    };
    const archive = resolve(bundledRoot, descriptor.artifact.file);

    expect(descriptor).toEqual({
      schemaVersion: 1,
      id: "hooandee-gallery",
      cssLoaderName: "Hooandee Gallery",
      version: "0.7.8",
      artifact: {
        file: "gallery.zip",
        sha256: sha256(archive),
        size: readFileSync(archive).byteLength,
      },
    });

    const manifestResult = spawnSync(
      "unzip",
      ["-p", archive, "Hooandee Gallery/theme.json"],
      { encoding: "utf8" },
    );

    expect(manifestResult.status).toBe(0);
    expect(JSON.parse(manifestResult.stdout)).toMatchObject({
      name: "Hooandee Gallery",
      version: "0.7.8",
      manifest_version: 9,
    });

    const listingResult = spawnSync("unzip", ["-Z1", archive], { encoding: "utf8" });
    const packagedPaths = listingResult.stdout.trim().split("\n");

    expect(listingResult.status).toBe(0);
    expect(packagedPaths).toContain("Hooandee Gallery/panel-theme.json");
    expect(packagedPaths.some((path) => /(?:^|\/)(?:\.pdc|\.codex|\.claude|\.notes)(?:\/|$)/.test(path)))
      .toBe(false);
  });
});
