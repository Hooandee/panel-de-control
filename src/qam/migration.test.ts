import { describe, expect, it } from "vitest";

import { createDefaultQamLayout } from "./layout";
import { migrateLegacyQamShortcut } from "./migration";

describe("legacy QAM shortcut migration", () => {
  it("pins Inicio when the legacy shortcut was enabled", () => {
    expect(migrateLegacyQamShortcut(createDefaultQamLayout(), true)).toEqual({
      order: ["pdc:home"],
      hiddenNative: [],
      pinnedViews: ["pdc:home"],
      ownedIds: {},
    });
  });

  it("preserves the empty layout when the legacy shortcut was disabled", () => {
    expect(migrateLegacyQamShortcut(createDefaultQamLayout(), false))
      .toEqual(createDefaultQamLayout());
  });

  it("does not duplicate an already migrated Inicio", () => {
    const migrated = migrateLegacyQamShortcut(createDefaultQamLayout(), true);

    expect(migrateLegacyQamShortcut(migrated, true)).toEqual(migrated);
  });
});
