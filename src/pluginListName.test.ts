// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  getUiPrefs: vi.fn(async () => ({})),
  setUiPrefs: vi.fn(async () => true),
}));

import { translate } from "./i18n";
import { nextRowText } from "./pluginListName";

const IDENTITY = "Panel de Control";

describe("nextRowText", () => {
  afterEach(() => window.localStorage.clear());

  it("localizes the identity row when the target differs (English)", () => {
    expect(nextRowText(IDENTITY, IDENTITY, "Control Panel")).toBe("Control Panel");
  });

  it("localizes the identity row from a persisted Italian selection", () => {
    window.localStorage.setItem("panel-de-control-lang", "it");

    expect(nextRowText(IDENTITY, IDENTITY, translate("app.title"))).toBe(
      "Pannello di controllo",
    );
  });

  it("leaves the row untouched when the target equals the identity (Spanish)", () => {
    expect(nextRowText(IDENTITY, IDENTITY, IDENTITY)).toBeNull();
  });

  it("ignores a row that is already localized (avoids a rewrite loop)", () => {
    expect(nextRowText("Control Panel", IDENTITY, "Control Panel")).toBeNull();
  });

  it("ignores other plugins' rows", () => {
    expect(nextRowText("Some Other Plugin", IDENTITY, "Control Panel")).toBeNull();
  });

  it("ignores empty text nodes", () => {
    expect(nextRowText("", IDENTITY, "Control Panel")).toBeNull();
  });

  it("does not match on partial/whitespace differences", () => {
    expect(nextRowText(" Panel de Control ", IDENTITY, "Control Panel")).toBeNull();
  });
});
