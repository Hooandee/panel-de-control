import {
  cpSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";


const workspaces: string[] = [];

function workspace(): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-theme-package-"));
  workspaces.push(path);
  return path;
}

function packageTheme(source: string, output: string) {
  return spawnSync(process.execPath, [
    resolve(process.cwd(), "scripts/package-theme.mjs"),
    source,
    output,
  ], { encoding: "utf8" });
}

function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

describe("theme package builder", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("builds Gallery as a deterministic single-root zip plus verified descriptor", () => {
    const first = workspace();
    const second = workspace();
    const source = resolve(process.cwd(), "themes/gallery");

    expect(packageTheme(source, first)).toMatchObject({ status: 0 });
    expect(packageTheme(source, second)).toMatchObject({ status: 0 });

    const descriptor = JSON.parse(readFileSync(resolve(first, "gallery.json"), "utf8")) as {
      schemaVersion: number;
      id: string;
      cssLoaderName: string;
      version: string;
      artifact: { file: string; sha256: string; size: number };
    };
    const archive = resolve(first, descriptor.artifact.file);
    expect(descriptor).toEqual({
      schemaVersion: 1,
      id: "hooandee-gallery",
      cssLoaderName: "Hooandee Gallery",
      version: "0.7.9",
      artifact: {
        file: "gallery.zip",
        sha256: sha256(archive),
        size: readFileSync(archive).byteLength,
      },
    });
    expect(sha256(archive)).toBe(sha256(resolve(second, "gallery.zip")));

    const listing = spawnSync("unzip", ["-Z1", archive], { encoding: "utf8" });
    expect(listing.status).toBe(0);
    expect(listing.stdout.trim().split("\n").every((path) => (
      path.startsWith("Hooandee Gallery/") && !path.includes("..")
    ))).toBe(true);
    expect(listing.stdout).toContain("Hooandee Gallery/theme.json");
    expect(listing.stdout).toContain("Hooandee Gallery/panel-theme.json");
  });

  it("rejects links instead of following files outside the theme package", () => {
    const fixture = workspace();
    const source = resolve(fixture, "unsafe-theme");
    cpSync(resolve(process.cwd(), "themes/gallery"), source, { recursive: true });
    symlinkSync("/etc/passwd", resolve(source, "outside.txt"));

    const result = packageTheme(source, resolve(fixture, "out"));

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("links are not permitted");
  });

  it("rejects executable content from declarative CSS Loader packages", () => {
    const fixture = workspace();
    const source = resolve(fixture, "unsafe-theme");
    cpSync(resolve(process.cwd(), "themes/gallery"), source, { recursive: true });
    writeFileSync(resolve(source, "payload.js"), "alert('no')\n", { mode: 0o755 });

    const result = packageTheme(source, resolve(fixture, "out"));

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain(`unsupported theme file: ${basename(source)}/payload.js`);
  });

  it("rejects CSS Loader names that would become unsafe ZIP paths", () => {
    const fixture = workspace();
    const source = resolve(fixture, "unsafe-theme");
    cpSync(resolve(process.cwd(), "themes/gallery"), source, { recursive: true });
    const manifestPath = resolve(source, "theme.json");
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Record<string, unknown>;
    manifest.name = "Hooandee\\Gallery";
    writeFileSync(manifestPath, `${JSON.stringify(manifest)}\n`);

    const result = packageTheme(source, resolve(fixture, "out"));

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("invalid CSS Loader theme name");
  });

  it("keeps CSS Loader's persisted activation and patch state out of release packages", () => {
    const fixture = workspace();
    const source = resolve(fixture, "unsafe-theme");
    cpSync(resolve(process.cwd(), "themes/gallery"), source, { recursive: true });
    writeFileSync(resolve(source, "config_ROOT.json"), '{"active":true}\n');

    const result = packageTheme(source, resolve(fixture, "out"));

    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("CSS Loader state cannot be packaged");
  });
});
