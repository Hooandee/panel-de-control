import { describe, expect, it } from "vitest";

import { parsePublicationDescriptor } from "../scripts/theme-publication-contract.mjs";

const pagesBaseUrl = "https://example.invalid/panel-de-control";
const validDescriptor = {
  schemaVersion: 1,
  catalogId: "hooandee-gallery",
  cssLoaderName: "Hooandee Gallery",
  version: "0.7.9",
  artifact: {
    url: `${pagesBaseUrl}/themes/v1/hooandee-gallery/0.7.9/gallery.zip`,
    size: 107_697,
    sha256: "3af309363a453511d6b00a0b82ac3617bd2791026758f958aba909b877f6bbeb",
  },
  minimumVersions: {
    panel: "0.31.4",
    cssLoader: "2.1.2",
    cssLoaderBackend: 9,
  },
  notes: {
    es: "Actualización de prueba",
    en: "Test update",
    it: "Aggiornamento di prova",
  },
};

function descriptorWith(patch: Record<string, unknown>): unknown {
  return { ...structuredClone(validDescriptor), ...patch };
}

describe("public theme release contract", () => {
  it("accepts the exact stable v1 descriptor for the configured Pages base", () => {
    expect(parsePublicationDescriptor(validDescriptor, pagesBaseUrl)).toEqual(validDescriptor);
  });

  it.each([
    ["unknown schema", descriptorWith({ schemaVersion: 2 })],
    ["unknown top-level field", descriptorWith({ unexpected: true })],
    ["unstable catalog id", descriptorWith({ catalogId: "../gallery" })],
    ["prerelease", descriptorWith({ version: "0.7.9-beta.1" })],
    ["v-prefixed version", descriptorWith({ version: "v0.7.9" })],
    ["cross-origin artifact", descriptorWith({
      artifact: { ...validDescriptor.artifact, url: "https://attacker.invalid/gallery.zip" },
    })],
    ["wrong artifact version path", descriptorWith({
      artifact: {
        ...validDescriptor.artifact,
        url: `${pagesBaseUrl}/themes/v1/hooandee-gallery/0.8.0/gallery.zip`,
      },
    })],
    ["protocol-relative artifact", descriptorWith({
      artifact: { ...validDescriptor.artifact, url: "//example.invalid/gallery.zip" },
    })],
    ["unsafe artifact size", descriptorWith({
      artifact: { ...validDescriptor.artifact, size: 64 * 1024 * 1024 + 1 },
    })],
    ["invalid digest", descriptorWith({
      artifact: { ...validDescriptor.artifact, sha256: "ABC123" },
    })],
    ["unknown minimum", descriptorWith({
      minimumVersions: { ...validDescriptor.minimumVersions, other: "1.0.0" },
    })],
    ["unsupported note locale", descriptorWith({
      notes: { ...validDescriptor.notes, de: "Nicht erlaubt" },
    })],
    ["oversized note", descriptorWith({ notes: { es: "x".repeat(1_001) } })],
  ])("rejects %s", (_label, descriptor) => {
    expect(() => parsePublicationDescriptor(descriptor, pagesBaseUrl)).toThrow();
  });
});
