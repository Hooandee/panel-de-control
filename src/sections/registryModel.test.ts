import { describe, expect, it } from "vitest";

import { buildSections } from "./registryModel";

describe("buildSections", () => {
  it("keeps metadata order and rejects an unrenderable tab", () => {
    const First = () => null;
    const Settings = () => null;
    const tabs = [
      {
        id: "themes",
        labelKey: "nav.themes",
        descriptionKey: "nav.themes.desc",
        accent: "#925783",
        icon: () => null,
      },
      {
        id: "settings",
        labelKey: "nav.settings",
        descriptionKey: "nav.settings.desc",
        accent: "#626b73",
        icon: () => null,
      },
    ];

    expect(buildSections(tabs, { themes: First, settings: Settings }))
      .toMatchObject(tabs);
    expect(() => buildSections(tabs, { settings: Settings })).toThrow(
      "Missing component for section: themes",
    );
  });
});
