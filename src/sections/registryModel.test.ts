import { describe, expect, it } from "vitest";

import { buildSections } from "./registryModel";

describe("buildSections", () => {
  it("keeps metadata order and rejects an unrenderable tab", () => {
    const First = () => null;
    const Settings = () => null;
    const tabs = [
      { id: "themes", labelKey: "nav.themes", icon: null },
      { id: "settings", labelKey: "nav.settings", icon: null },
    ];

    expect(buildSections(tabs, { themes: First, settings: Settings }).map((section) => section.id))
      .toEqual(["themes", "settings"]);
    expect(() => buildSections(tabs, { settings: Settings })).toThrow(
      "Missing component for section: themes",
    );
  });
});
