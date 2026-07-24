import { describe, it, expect } from "vitest";

import { pendingSave } from "./editorSave";

describe("pendingSave", () => {
  it("nothing to save until a real reading loaded", () => {
    expect(pendingSave({ loaded: false, malformed: false, dirty: true, preview: "mangohud %command%" })).toBeNull();
  });

  it("a malformed baseline is never written", () => {
    expect(pendingSave({ loaded: true, malformed: true, dirty: true, preview: "x" })).toBeNull();
  });

  it("an edit that matches the saved baseline leaves nothing pending", () => {
    expect(pendingSave({ loaded: true, malformed: false, dirty: false, preview: "" })).toBeNull();
  });

  it("a genuine unsaved change is the value to persist", () => {
    expect(pendingSave({ loaded: true, malformed: false, dirty: true, preview: "mangohud %command%" })).toBe("mangohud %command%");
  });

  it("clearing everything is a genuine change worth persisting", () => {
    expect(pendingSave({ loaded: true, malformed: false, dirty: true, preview: "" })).toBe("");
  });
});
