import { describe, expect, it, vi } from "vitest";

import { createThemeLibraryAccess } from "./libraryAccess";

function dependencies(overrides: Record<string, unknown> = {}) {
  return {
    getOverview: vi.fn(() => ({ appid: 812140, gameid: "812140" })),
    runGame: vi.fn(),
    openSettings: vi.fn(),
    openController: vi.fn(),
    ...overrides,
  };
}

describe("theme library access", () => {
  it("launches the exact selected game through Steam's native game id", () => {
    const native = dependencies();
    const access = createThemeLibraryAccess(native);

    expect(access.launch(812140)).toBe("started");
    expect(native.getOverview).toHaveBeenCalledWith(812140);
    expect(native.runGame).toHaveBeenCalledWith("812140");
  });

  it("opens native settings and controller screens for the exact selected app", () => {
    const native = dependencies();
    const access = createThemeLibraryAccess(native);

    expect(access.openSettings(812140)).toBe(true);
    expect(access.openController(812140)).toBe(true);
    expect(native.openSettings).toHaveBeenCalledWith(812140);
    expect(native.openController).toHaveBeenCalledWith(812140);
  });

  it.each([0, -1, 1.5, Number.NaN])("fails closed for invalid app id %s", (appid) => {
    const native = dependencies();
    const access = createThemeLibraryAccess(native);

    expect(access.launch(appid)).toBe("unavailable");
    expect(access.openSettings(appid)).toBe(false);
    expect(access.openController(appid)).toBe(false);
    expect(native.getOverview).not.toHaveBeenCalled();
  });

  it("does not launch when Steam cannot resolve a matching game id", () => {
    const native = dependencies({
      getOverview: vi.fn(() => ({ appid: 42, gameid: "42" })),
    });
    const access = createThemeLibraryAccess(native);

    expect(access.launch(812140)).toBe("unavailable");
    expect(native.runGame).not.toHaveBeenCalled();
  });

  it("reports native failures without throwing into the theme runtime", () => {
    const native = dependencies({
      runGame: vi.fn(() => { throw new Error("Steam unavailable"); }),
      openSettings: vi.fn(() => { throw new Error("navigation unavailable"); }),
      openController: vi.fn(() => { throw new Error("controller unavailable"); }),
    });
    const access = createThemeLibraryAccess(native);

    expect(access.launch(812140)).toBe("failed");
    expect(access.openSettings(812140)).toBe(false);
    expect(access.openController(812140)).toBe(false);
  });

  it("resolves the local vertical capsule Steam uses for the rest of the library", () => {
    const access = createThemeLibraryAccess(dependencies({
      getOverview: vi.fn(() => ({
        appid: 2246340,
        library_capsule_filename: "e3fc16c6/library_600x900.jpg",
        local_cache_version: 711320584,
      })),
    }));

    expect(access.verticalCapsule(2246340)).toBe("/assets/2246340/e3fc16c6/library_600x900.jpg?c=711320584");
  });

  it("prefers the user's own vertical artwork when Steam reports one", () => {
    const access = createThemeLibraryAccess(dependencies({
      getOverview: vi.fn(() => ({ appid: 413150, library_capsule_filename: "library_600x900.jpg" })),
      customVerticalCapsules: vi.fn(() => ["/customimages/413150p.png?v=3"]),
    }));

    expect(access.verticalCapsule(413150)).toBe("/customimages/413150p.png?v=3");
  });

  it.each([
    [{ appid: 3570110851, library_capsule_filename: null }],
    [{ appid: 42, library_capsule_filename: "library_600x900.jpg" }],
    [{ appid: 812140, library_capsule_filename: "../../escape.jpg" }],
  ])("returns no capsule when Steam has none for the exact app (%o)", (overview) => {
    const access = createThemeLibraryAccess(dependencies({
      getOverview: vi.fn(() => overview),
      customVerticalCapsules: vi.fn(() => ["javascript:alert(1)", "//evil.example/x.png"]),
    }));

    expect(access.verticalCapsule(overview.appid === 42 ? 812140 : overview.appid)).toBeNull();
  });
});
