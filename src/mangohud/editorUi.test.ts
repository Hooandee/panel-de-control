import { describe, expect, it } from "vitest";

import { formatHudValue, hasLocalEditor } from "./editorUi";

describe("hasLocalEditor", () => {
  it("keeps actual editors expandable", () => {
    expect(hasLocalEditor({ kind: "text", id: "t", text: "", index: 0 })).toBe(true);
    expect(hasLocalEditor({ kind: "spacer", id: "s", size: "small", index: 0 })).toBe(true);
    expect(hasLocalEditor({ kind: "metric", id: "fps", index: 0 })).toBe(true);
    expect(hasLocalEditor({ kind: "metric", id: "pdc_model", index: 0 })).toBe(true);
  });

  it("makes separators and global-only metrics leaf rows", () => {
    expect(hasLocalEditor({ kind: "separator", id: "s", index: 0 })).toBe(false);
    expect(hasLocalEditor({ kind: "metric", id: "ram", index: 0 })).toBe(false);
    expect(hasLocalEditor({ kind: "metric", id: "resolution", index: 0 })).toBe(false);
  });
});

describe("formatHudValue", () => {
  it("formats QAM units without exposing storage scales", () => {
    expect(formatHudValue(24, "px")).toBe("24 px");
    expect(formatHudValue(65, "percent")).toBe("65%");
    expect(formatHudValue(125, "multiplier")).toBe("1.25×");
    expect(formatHudValue(-8.5, "signed-decimal")).toBe("−0.09");
    expect(formatHudValue(15, "decimal")).toBe("1.5 px");
  });
});
