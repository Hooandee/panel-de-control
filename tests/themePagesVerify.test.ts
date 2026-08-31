import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";

import { verifyPublishedTheme } from "../scripts/verify-theme-pages.mjs";

const pagesBaseUrl = "https://example.invalid/panel-de-control";
const archive = Buffer.from("verified theme archive");
const descriptor = {
  schemaVersion: 1,
  catalogId: "hooandee-gallery",
  cssLoaderName: "Hooandee Gallery",
  version: "0.7.9",
  artifact: {
    url: `${pagesBaseUrl}/themes/v1/hooandee-gallery/0.7.9/gallery.zip`,
    size: archive.length,
    sha256: createHash("sha256").update(archive).digest("hex"),
  },
  minimumVersions: {
    panel: "0.31.4",
    cssLoader: "2.1.2",
    cssLoaderBackend: 9,
  },
};
const descriptorBytes = Buffer.from(`${JSON.stringify(descriptor, null, 2)}\n`);

function response(body: BodyInit, contentType: string): Response {
  return new Response(body, { status: 200, headers: { "content-type": contentType } });
}

function publicationFetch(overrides: Record<string, Response> = {}) {
  const responses: Record<string, Response> = {
    "/panel-de-control/themes/v1/hooandee-gallery/0.7.9/gallery.json": response(
      descriptorBytes,
      "application/json; charset=utf-8",
    ),
    "/panel-de-control/themes/v1/hooandee-gallery/0.7.9/gallery.zip": response(
      archive,
      "application/zip",
    ),
    "/panel-de-control/themes/v1/hooandee-gallery/latest.json": response(
      descriptorBytes,
      "application/json",
    ),
    ...overrides,
  };
  return async (input: string | URL | Request): Promise<Response> => {
    const url = new URL(input instanceof Request ? input.url : input.toString());
    const value = responses[url.pathname];
    if (!value) return new Response("missing", { status: 404 });
    return value.clone();
  };
}

describe("served Pages theme verification", () => {
  it("verifies the immutable descriptor, MIME types, bytes, and digest", async () => {
    await expect(verifyPublishedTheme({
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
      requireLatest: false,
      expectedDescriptorBytes: descriptorBytes,
      expectedArchiveBytes: archive,
      fetchImpl: publicationFetch(),
    })).resolves.toEqual({
      catalogId: "hooandee-gallery",
      version: "0.7.9",
      size: archive.length,
      sha256: descriptor.artifact.sha256,
      latest: false,
    });
  });

  it("requires latest.json to be the exact immutable descriptor after promotion", async () => {
    await expect(verifyPublishedTheme({
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
      requireLatest: true,
      expectedDescriptorBytes: descriptorBytes,
      expectedArchiveBytes: archive,
      fetchImpl: publicationFetch(),
    })).resolves.toMatchObject({ latest: true });

    await expect(verifyPublishedTheme({
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
      requireLatest: true,
      expectedDescriptorBytes: descriptorBytes,
      expectedArchiveBytes: archive,
      fetchImpl: publicationFetch({
        "/panel-de-control/themes/v1/hooandee-gallery/latest.json": response(
          Buffer.from(`${JSON.stringify({ ...descriptor, notes: { en: "changed" } })}\n`),
          "application/json",
        ),
      }),
    })).rejects.toThrow("latest descriptor does not match the immutable version");
  });

  it("rejects unexpected MIME types and archive bytes", async () => {
    await expect(verifyPublishedTheme({
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
      requireLatest: false,
      expectedDescriptorBytes: descriptorBytes,
      expectedArchiveBytes: archive,
      fetchImpl: publicationFetch({
        "/panel-de-control/themes/v1/hooandee-gallery/0.7.9/gallery.zip": response(
          Buffer.from("not the archive"),
          "text/plain",
        ),
      }),
    })).rejects.toThrow("served theme response has an unexpected content type");
  });

  it("rejects redirect targets outside the authoritative Pages prefix", async () => {
    const redirectingFetch = async (input: string | URL | Request): Promise<Response> => {
      const url = new URL(input instanceof Request ? input.url : input.toString());
      if (url.pathname.endsWith("gallery.json")) {
        return new Response(null, {
          status: 302,
          headers: { location: "https://attacker.invalid/gallery.json" },
        });
      }
      return new Response("missing", { status: 404 });
    };

    await expect(verifyPublishedTheme({
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
      requireLatest: false,
      expectedDescriptorBytes: descriptorBytes,
      expectedArchiveBytes: archive,
      fetchImpl: redirectingFetch,
    })).rejects.toThrow("served theme redirect escaped the Pages prefix");
  });

  it("requires the served publication to match the reviewed local candidate exactly", async () => {
    await expect(verifyPublishedTheme({
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
      requireLatest: false,
      expectedDescriptorBytes: Buffer.from(`${JSON.stringify({ ...descriptor, notes: "changed" })}\n`),
      expectedArchiveBytes: archive,
      fetchImpl: publicationFetch(),
    })).rejects.toThrow("served theme descriptor differs from the reviewed candidate");

    await expect(verifyPublishedTheme({
      pagesBaseUrl,
      catalogId: "hooandee-gallery",
      version: "0.7.9",
      requireLatest: false,
      expectedDescriptorBytes: descriptorBytes,
      expectedArchiveBytes: Buffer.from("different reviewed archive"),
      fetchImpl: publicationFetch(),
    })).rejects.toThrow("served theme archive differs from the reviewed candidate");
  });
});
