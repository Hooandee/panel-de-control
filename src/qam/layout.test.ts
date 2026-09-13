import { describe, expect, it } from "vitest";

import {
  coerceQamLayout,
  createDefaultQamLayout,
  resolveQamTokens,
  type QamLayout,
} from "./layout";

describe("QAM layout", () => {
  it("mixes pinned Panel views with visible native entries and keeps Decky last", () => {
    const layout: QamLayout = {
      order: ["pdc:section:hud", "native:friends", "native:help"],
      hiddenNative: ["native:help"],
      pinnedViews: ["pdc:section:hud"],
      ownedIds: {},
    };

    expect(resolveQamTokens(
      ["native:friends", "native:help", "pdc:section:hud", "decky"],
      layout,
      "decky",
    )).toEqual(["pdc:section:hud", "native:friends", "decky"]);
  });

  it("shows unseen native entries without pinning unseen Panel views", () => {
    const layout: QamLayout = {
      order: ["native:friends", "pdc:section:hud"],
      hiddenNative: [],
      pinnedViews: ["pdc:section:hud"],
      ownedIds: {},
    };

    expect(resolveQamTokens(
      ["native:friends", "native:help", "pdc:section:hud", "pdc:section:power", "decky"],
      layout,
      "decky",
    )).toEqual(["native:friends", "pdc:section:hud", "native:help", "decky"]);
  });

  it("drops unavailable and duplicate runtime tokens without losing protected Decky", () => {
    const layout: QamLayout = {
      order: ["native:missing", "native:friends", "native:friends", "decky"],
      hiddenNative: [],
      pinnedViews: [],
      ownedIds: {},
    };

    expect(resolveQamTokens(
      ["native:friends", "native:friends", "decky", "decky"],
      layout,
      "decky",
    )).toEqual(["native:friends", "decky"]);
  });

  it("coerces corrupt persisted values to unique supported tokens and stable IDs", () => {
    expect(coerceQamLayout({
      order: ["native:friends", 7, "native:friends", "bogus"],
      hiddenNative: ["pdc:home", "native:help", "native:help"],
      pinnedViews: ["native:friends", "pdc:home", "pdc:view:v1", "pdc:home"],
      ownedIds: {
        "pdc:home": 5_046_339,
        "pdc:view:v1": 5_046_340,
        "native:friends": 55,
        "pdc:view:bad": -1,
        "pdc:view:fraction": 12.5,
      },
    })).toEqual({
      order: ["native:friends"],
      hiddenNative: ["native:help"],
      pinnedViews: ["pdc:home", "pdc:view:v1"],
      ownedIds: {
        "pdc:home": 5_046_339,
        "pdc:view:v1": 5_046_340,
      },
    });
  });

  it("returns a fresh default for non-object persisted values", () => {
    expect(coerceQamLayout(null)).toEqual(createDefaultQamLayout());
    expect(coerceQamLayout([])).toEqual(createDefaultQamLayout());
  });
});
