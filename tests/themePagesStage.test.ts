import {
  copyFileSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  truncateSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { buildThemePublication } from "../scripts/build-theme-publication.mjs";
import { stageImmutableCandidate } from "../scripts/stage-theme-pages.mjs";

const workspaces: string[] = [];
const pagesBaseUrl = "https://example.invalid/panel-de-control";

function workspace(): string {
  const path = mkdtempSync(resolve(tmpdir(), "pdc-theme-pages-stage-"));
  workspaces.push(path);
  return path;
}

async function candidate(root: string): Promise<string> {
  await buildThemePublication({
    sourceDirectory: resolve(process.cwd(), "themes/gallery"),
    outputDirectory: root,
    pagesBaseUrl,
    minimumVersions: {
      panel: "0.31.4",
      cssLoader: "2.1.2",
      cssLoaderBackend: 9,
    },
  });
  return resolve(root, "themes/v1/hooandee-gallery/0.7.9");
}

describe("Pages immutable theme staging", () => {
  afterEach(() => {
    workspaces.splice(0).forEach((path) => rmSync(path, { recursive: true, force: true }));
  });

  it("appends one verified version without changing the live descriptor", async () => {
    const source = await candidate(workspace());
    const pages = workspace();
    const latest = resolve(pages, "themes/v1/hooandee-gallery/latest.json");
    mkdirSync(resolve(latest, ".."), { recursive: true });
    writeFileSync(latest, "existing-live-descriptor\n");

    const result = await stageImmutableCandidate({
      candidateVersionDirectory: source,
      pagesDirectory: pages,
      pagesBaseUrl,
    });

    expect(result).toEqual({
      status: "staged",
      catalogId: "hooandee-gallery",
      version: "0.7.9",
    });
    const staged = resolve(pages, "themes/v1/hooandee-gallery/0.7.9");
    expect(readFileSync(resolve(staged, "gallery.json")))
      .toEqual(readFileSync(resolve(source, "gallery.json")));
    expect(readFileSync(resolve(staged, "gallery.zip")))
      .toEqual(readFileSync(resolve(source, "gallery.zip")));
    expect(readFileSync(latest, "utf8")).toBe("existing-live-descriptor\n");
  });

  it("treats identical bytes as an idempotent restage", async () => {
    const source = await candidate(workspace());
    const pages = workspace();
    const request = {
      candidateVersionDirectory: source,
      pagesDirectory: pages,
      pagesBaseUrl,
    };

    await stageImmutableCandidate(request);

    await expect(stageImmutableCandidate(request)).resolves.toEqual({
      status: "unchanged",
      catalogId: "hooandee-gallery",
      version: "0.7.9",
    });
  });

  it("rejects different bytes under an existing immutable version", async () => {
    const source = await candidate(workspace());
    const pages = workspace();
    await stageImmutableCandidate({
      candidateVersionDirectory: source,
      pagesDirectory: pages,
      pagesBaseUrl,
    });
    const stagedArchive = resolve(
      pages,
      "themes/v1/hooandee-gallery/0.7.9/gallery.zip",
    );
    copyFileSync(resolve(source, "gallery.json"), stagedArchive);

    await expect(stageImmutableCandidate({
      candidateVersionDirectory: source,
      pagesDirectory: pages,
      pagesBaseUrl,
    })).rejects.toThrow("immutable version already exists with different bytes");
  });

  it("rejects candidate files outside the two-file publication contract", async () => {
    const source = await candidate(workspace());
    writeFileSync(resolve(source, "unexpected.txt"), "not public\n");

    await expect(stageImmutableCandidate({
      candidateVersionDirectory: source,
      pagesDirectory: workspace(),
      pagesBaseUrl,
    })).rejects.toThrow("candidate version contains unexpected files");
  });

  it("keeps the complete durable Pages tree below 900 MiB", async () => {
    const source = await candidate(workspace());
    const pages = workspace();
    const existing = resolve(pages, "existing.bin");
    writeFileSync(existing, "");
    truncateSync(existing, 900 * 1024 * 1024);

    await expect(stageImmutableCandidate({
      candidateVersionDirectory: source,
      pagesDirectory: pages,
      pagesBaseUrl,
    })).rejects.toThrow("Pages tree must remain below 900 MiB");
  });
});
