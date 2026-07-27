import { describe, expect, it } from "vitest";
import { nextRowText } from "./pluginListName";

const IDENTITY = "Panel de Control";

describe("nextRowText", () => {
  it("localizes the identity row when the target differs (English)", () => {
    expect(nextRowText(IDENTITY, IDENTITY, "Control Panel")).toBe("Control Panel");
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
