import { describe, expect, it } from "vitest";

import { themeCoverFor } from "./themePresentation";
import type { PublishedThemeRelease } from "./remotePublication";

function release(catalogId: string, cssLoaderName: string): PublishedThemeRelease {
  return { catalogId, cssLoaderName } as PublishedThemeRelease;
}

describe("themeCoverFor", () => {
  it("gives each Hooandee theme its own cover", () => {
    const gallery = themeCoverFor(release("hooandee-gallery", "Hooandee Gallery"));
    const atlas = themeCoverFor(release("hooandee-luminous-atlas", "Hooandee Luminous Atlas"));

    expect(gallery).toBeTruthy();
    expect(atlas).toBeTruthy();
    expect(atlas).not.toBe(gallery);
  });

  it("gives no cover to an unknown theme or one whose identity does not match", () => {
    expect(themeCoverFor(release("someone-else", "Hooandee Luminous Atlas"))).toBeUndefined();
    expect(themeCoverFor(release("hooandee-luminous-atlas", "Other Name"))).toBeUndefined();
  });
});
