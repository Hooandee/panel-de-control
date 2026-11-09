import { describe, expect, it } from "vitest";

import { upscalerErrorCode } from "./errorCode";

describe("upscaler error codes", () => {
  it("reads the code from the message when Decky passes it", () => {
    expect(upscalerErrorCode(new Error("running"))).toBe("running");
  });

  it("falls back to the traceback when the message is empty", () => {
    const error = { name: "Python Exception", message: "", pythonTraceback: "  File \"decky_loader/plugin/messages.py\", line 44, in wait_for_result\nException: running\n" };
    expect(upscalerErrorCode(error)).toBe("running");
  });

  it("calls anything unreadable generic", () => {
    expect(upscalerErrorCode({ message: "", stack: "TypeError: x is null" })).toBe("generic");
    expect(upscalerErrorCode(null)).toBe("generic");
  });
});
