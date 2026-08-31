import { createHash } from "node:crypto";
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { buildThemePublication } from "../scripts/build-theme-publication.mjs";

const workspaces: string[] = [];
const pagesBaseUrl = "https://example.invalid/panel-de-control";

function workspace(): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-theme-publication-"));
  workspaces.push(path);
  return path;
}

function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function build(outputDirectory: string, baseUrl = pagesBaseUrl) {
  return buildThemePublication({
    sourceDirectory: resolve(process.cwd(), "themes/gallery"),
    outputDirectory,
    pagesBaseUrl: baseUrl,
    minimumVersions: {
      panel: "0.31.4",
      cssLoader: "2.1.2",
      cssLoaderBackend: 9,
    },
    notes: {
      es: "Actualización pública de Gallery.",
      en: "Public Gallery update.",
      it: "Aggiornamento pubblico di Gallery.",
    },
  });
}

describe("theme publication builder", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("builds a deterministic immutable version without publishing latest", async () => {
    const first = workspace();
    const second = workspace();

    const firstDescriptor = await build(first);
    const secondDescriptor = await build(second);
    const versionRoot = resolve(first, "themes/v1/hooandee-gallery/0.7.9");
    const archive = resolve(versionRoot, "gallery.zip");
    const descriptorPath = resolve(versionRoot, "gallery.json");

    expect(firstDescriptor).toEqual({
      schemaVersion: 1,
      catalogId: "hooandee-gallery",
      cssLoaderName: "Hooandee Gallery",
      version: "0.7.9",
      artifact: {
        url: `${pagesBaseUrl}/themes/v1/hooandee-gallery/0.7.9/gallery.zip`,
        size: readFileSync(archive).byteLength,
        sha256: sha256(archive),
      },
      minimumVersions: {
        panel: "0.31.4",
        cssLoader: "2.1.2",
        cssLoaderBackend: 9,
      },
      notes: {
        es: "Actualización pública de Gallery.",
        en: "Public Gallery update.",
        it: "Aggiornamento pubblico di Gallery.",
      },
    });
    expect(secondDescriptor).toEqual(firstDescriptor);
    expect(sha256(descriptorPath)).toBe(sha256(resolve(
      second,
      "themes/v1/hooandee-gallery/0.7.9/gallery.json",
    )));
    expect(sha256(archive)).toBe(sha256(resolve(
      second,
      "themes/v1/hooandee-gallery/0.7.9/gallery.zip",
    )));
    expect(existsSync(resolve(first, "themes/v1/hooandee-gallery/latest.json"))).toBe(false);
  });

  it("treats an identical rebuild as an idempotent no-op", async () => {
    const output = workspace();

    await build(output);
    const before = sha256(resolve(
      output,
      "themes/v1/hooandee-gallery/0.7.9/gallery.json",
    ));
    await build(output);

    expect(sha256(resolve(
      output,
      "themes/v1/hooandee-gallery/0.7.9/gallery.json",
    ))).toBe(before);
  });

  it("refuses different descriptor bytes under an existing version", async () => {
    const output = workspace();
    await build(output);

    await expect(build(output, "https://other.invalid/panel-de-control"))
      .rejects.toThrow("immutable theme version already exists with different bytes");
  });
});
