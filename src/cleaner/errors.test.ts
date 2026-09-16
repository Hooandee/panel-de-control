import { describe, expect, it } from "vitest";
import { cleanerErrorCode, cleanerReasonKey } from "./errors";

describe("cleaner errors", () => {
  it("extracts a known reason from Decky's Python exception shape", () => {
    const failure = new Error("") as Error & { pythonTraceback: string };
    failure.name = "Python Exception";
    failure.pythonTraceback = "Exception: path_changed";

    expect(cleanerErrorCode(failure)).toBe("path_changed");
  });

  it("keeps unknown failures behind the generic explanation", () => {
    expect(cleanerErrorCode({ pythonTraceback: "Exception: unexpected" })).toBe("internal_error");
    expect(cleanerReasonKey("unsupported")).toBe("cleaner.reason.unknown");
  });
});
