import {
  cpSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { buildThemePublication } from "../scripts/build-theme-publication.mjs";
import { promoteStagedCandidate } from "../scripts/promote-theme-pages.mjs";
import { stageImmutableCandidate } from "../scripts/stage-theme-pages.mjs";

const workspaces: string[] = [];
const pagesBaseUrl = "https://example.invalid/panel-de-control";

function workspace(): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-theme-pages-promote-"));
  workspaces.push(path);
  return path;
}

function sourceVersion(
  version: string,
  mutate?: (manifest: Record<string, unknown>) => void,
): string {
  const source = resolve(workspace(), "gallery");
  cpSync(resolve(process.cwd(), "themes/gallery"), source, { recursive: true });
  const manifestPath = resolve(source, "theme.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as Record<string, unknown>;
  manifest.version = version;
  mutate?.(manifest);
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
  return source;
}

async function stageSource(pages: string, sourceDirectory: string): Promise<void> {
  const candidateRoot = workspace();
  const descriptor = await buildThemePublication({
    sourceDirectory,
    outputDirectory: candidateRoot,
    pagesBaseUrl,
    minimumVersions: {
      panel: "0.31.4",
      cssLoader: "2.1.2",
      cssLoaderBackend: 9,
    },
  });
  await stageImmutableCandidate({
    candidateVersionDirectory: resolve(
      candidateRoot,
      `themes/v1/${descriptor.catalogId}/${descriptor.version}`,
    ),
    pagesDirectory: pages,
    pagesBaseUrl,
  });
}

function patches(manifest: Record<string, unknown>): Record<string, {
  type: string;
  values: Record<string, unknown>;
}> {
  return manifest.patches as Record<string, {
    type: string;
    values: Record<string, unknown>;
  }>;
}

describe("Pages theme promotion", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("copies the exact staged descriptor to latest without rebuilding the artifact", async () => {
    const pages = workspace();
    await stageSource(pages, sourceVersion("0.7.8"));
    const immutableDescriptor = resolve(
      pages,
      "themes/v1/hooandee-gallery/0.7.8/gallery.json",
    );

    const result = await promoteStagedCandidate({
      pagesDirectory: pages,
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.8",
    });

    expect(result).toEqual({
      status: "promoted",
      catalogId: "hooandee-gallery",
      version: "0.7.8",
      previousVersion: null,
    });
    expect(readFileSync(resolve(pages, "themes/v1/hooandee-gallery/latest.json")))
      .toEqual(readFileSync(immutableDescriptor));
  });

  it("treats retrying the exact live descriptor as an idempotent no-op", async () => {
    const pages = workspace();
    await stageSource(pages, sourceVersion("0.7.8"));
    const request = {
      pagesDirectory: pages,
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.8",
    };
    await promoteStagedCandidate(request);

    await expect(promoteStagedCandidate(request)).resolves.toEqual({
      status: "unchanged",
      catalogId: "hooandee-gallery",
      version: "0.7.8",
      previousVersion: "0.7.8",
    });
  });

  it("rejects a version that is absent from the immutable Pages tree", async () => {
    await expect(promoteStagedCandidate({
      pagesDirectory: workspace(),
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
    })).rejects.toThrow("staged theme version is unavailable");
  });

  it("rejects a rollback after a newer descriptor is live", async () => {
    const pages = workspace();
    await stageSource(pages, sourceVersion("0.7.8"));
    await stageSource(pages, sourceVersion("0.7.9"));
    await promoteStagedCandidate({
      pagesDirectory: pages,
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
    });

    await expect(promoteStagedCandidate({
      pagesDirectory: pages,
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.8",
    })).rejects.toThrow("promotion version must be newer than latest");
  });

  it.each([
    ["removed patch", (manifest: Record<string, unknown>) => {
      delete patches(manifest)[Object.keys(patches(manifest))[0]];
    }],
    ["changed patch type", (manifest: Record<string, unknown>) => {
      patches(manifest)[Object.keys(patches(manifest))[0]].type = "checkbox";
    }],
    ["removed patch value", (manifest: Record<string, unknown>) => {
      const patch = patches(manifest)[Object.keys(patches(manifest))[0]];
      delete patch.values[Object.keys(patch.values)[0]];
    }],
  ])("rejects a candidate with a %s", async (_label, mutate) => {
    const pages = workspace();
    await stageSource(pages, sourceVersion("0.7.8"));
    await promoteStagedCandidate({
      pagesDirectory: pages,
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.8",
    });
    await stageSource(pages, sourceVersion("0.7.9", mutate));

    await expect(promoteStagedCandidate({
      pagesDirectory: pages,
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
    })).rejects.toThrow("published patch contract is not backward compatible");
  });
});
