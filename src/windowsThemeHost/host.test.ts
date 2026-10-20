// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CssLoaderSnapshot } from "../themes/cssLoaderTypes";
import { createWindowsThemeHost, findBigPictureDocument, findQuickAccessDocument, type WindowsThemeHost } from "./host";

const SOURCE = `
module.exports = Object.freeze({
  abiVersion: 2,
  mount: (context) => {
    context.document.body.dataset.mounted = context.theme.patches[0].value;
    return () => { delete context.document.body.dataset.mounted; };
  },
});`;

const SHA = "a".repeat(64);

function scopeWith(trees: { m_ID: string; doc: Document }[]): typeof globalThis {
  return {
    FocusNavController: {
      m_ActiveContext: {
        m_rgGamepadNavigationTrees: trees.map(({ m_ID, doc }) => ({ m_ID, Root: { Element: { ownerDocument: doc } } })),
      },
    },
  } as unknown as typeof globalThis;
}

function snapshot(enabled: boolean, accent = "Venus"): CssLoaderSnapshot {
  return {
    status: "ready",
    themes: [{
      id: "Hooandee Eclipse",
      name: "Hooandee Eclipse",
      displayName: "Eclipse",
      version: "0.2.5",
      author: "Hooandee",
      enabled,
      patches: [{ name: "Acento", defaultValue: "Venus", value: accent, options: ["Venus", "Marte"], type: "dropdown", rawType: "dropdown" }],
    }],
  };
}

const extension = { catalogId: "hooandee-eclipse", cssLoaderName: "Hooandee Eclipse", version: "0.2.5", abiVersion: 2 as const, sha256: SHA, source: SOURCE };

let host: WindowsThemeHost | undefined;

afterEach(() => {
  host?.dispose();
  host = undefined;
  delete document.body.dataset.mounted;
  vi.useRealTimers();
});

async function settle() {
  for (let index = 0; index < 5; index += 1) await Promise.resolve();
}

describe("Windows theme host", () => {
  it("finds Big Picture and the QAM through Steam's navigation trees", () => {
    const qam = document.implementation.createHTMLDocument("qam");
    const scope = scopeWith([{ m_ID: "QuickAccess-NA", doc: qam }, { m_ID: "GamepadUI_Full_Root", doc: document }]);

    expect(findBigPictureDocument(scope)).toBe(document);
    expect(findQuickAccessDocument(scope)).toBe(qam);
    expect(findBigPictureDocument(scopeWith([]))).toBeNull();
  });

  it("mounts the enabled theme's runtime and reports it", async () => {
    host = createWindowsThemeHost(scopeWith([{ m_ID: "GamepadUI_Full_Root", doc: document }]));

    host.update({ revision: 1, snapshot: snapshot(true, "Marte"), extensions: [extension] });
    await settle();

    expect(document.body.dataset.mounted).toBe("Marte");
    expect(host.status()).toMatchObject({ revision: 1, steamDocument: true, mounted: ["hooandee-eclipse@0.2.5"], errors: [] });
  });

  it("unmounts when the theme is turned off and ignores stale revisions", async () => {
    host = createWindowsThemeHost(scopeWith([{ m_ID: "GamepadUI_Full_Root", doc: document }]));
    host.update({ revision: 2, snapshot: snapshot(true), extensions: [extension] });
    await settle();

    host.update({ revision: 1, snapshot: snapshot(false), extensions: [extension] });
    await settle();
    expect(document.body.dataset.mounted).toBe("Venus");

    host.update({ revision: 3, snapshot: snapshot(false), extensions: [extension] });
    await settle();
    expect(document.body.dataset.mounted).toBeUndefined();
    expect(host.status().mounted).toEqual([]);
  });

  it("waits for Big Picture to appear before mounting", async () => {
    vi.useFakeTimers();
    const trees: { m_ID: string; doc: Document }[] = [];
    const scope = {
      FocusNavController: {
        m_ActiveContext: {
          get m_rgGamepadNavigationTrees() {
            return trees.map(({ m_ID, doc }) => ({ m_ID, Root: { Element: { ownerDocument: doc } } }));
          },
        },
      },
    } as unknown as typeof globalThis;
    host = createWindowsThemeHost(scope);
    host.update({ revision: 1, snapshot: snapshot(true), extensions: [extension] });
    await settle();
    expect(document.body.dataset.mounted).toBeUndefined();

    trees.push({ m_ID: "GamepadUI_Full_Root", doc: document });
    await vi.advanceTimersByTimeAsync(2_100);
    await settle();

    expect(document.body.dataset.mounted).toBe("Venus");
  });

  it("rejects a payload whose identity is malformed", () => {
    host = createWindowsThemeHost(scopeWith([]));

    expect(() => host!.update({ revision: 1, snapshot: snapshot(true), extensions: [{ ...extension, sha256: "nope" }] })).toThrow();
  });
});
