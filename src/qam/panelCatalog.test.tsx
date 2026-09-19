import { describe, expect, it } from "vitest";

import { createDefaultLayout } from "../customize/layout";
import { buildPanelQamCatalog } from "./panelCatalog";

const options = {
  device: { key: "steam_deck_lcd" },
  desktopMode: false,
  disabled: new Set<string>(),
  layout: createDefaultLayout(),
  present: () => null,
};

describe("Panel QAM catalog", () => {
  it("does not offer sections unavailable on the current device", () => {
    const tokens = buildPanelQamCatalog([], options).map((entry) => entry.token);

    expect(tokens).not.toContain("pdc:section:mandos");
    expect(tokens).toContain("pdc:section:hud");
    expect(tokens).toContain("pdc:section:cleaner");
  });

  it("does not offer a disabled section or one with no visible content", () => {
    const disabledTokens = buildPanelQamCatalog([], {
      ...options,
      disabled: new Set(["fans"]),
    }).map((entry) => entry.token);
    const emptyTokens = buildPanelQamCatalog([], {
      ...options,
      layout: {
        ...options.layout,
        blocks: {
          system: {
            order: [],
            hidden: ["eco", "battery", "cpu", "gpu", "brightness", "volume", "colores"],
          },
        },
      },
    }).map((entry) => entry.token);

    expect(disabledTokens).not.toContain("pdc:section:fans");
    expect(emptyTokens).not.toContain("pdc:section:system");
  });

  it("changes presentation identity when the language changes", () => {
    const spanish = buildPanelQamCatalog([], {
      ...options,
      presentationKeySuffix: "es",
    });
    const english = buildPanelQamCatalog([], {
      ...options,
      presentationKeySuffix: "en",
    });

    expect(spanish.map((entry) => entry.presentationKey))
      .not.toEqual(english.map((entry) => entry.presentationKey));
  });
});
