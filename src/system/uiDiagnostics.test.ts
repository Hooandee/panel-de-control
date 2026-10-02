import { afterEach, describe, expect, it, vi } from "vitest";

const recorded: unknown[][] = [];
vi.mock("../api", () => ({
  recordUiDiagnostic: (...args: unknown[]) => {
    recorded.push(args);
    return Promise.resolve(true);
  },
}));

import { describeError, startFrontendErrorReporting } from "./uiDiagnostics";

afterEach(() => {
  recorded.length = 0;
});

describe("frontend error reporting", () => {
  it("names the error, where it happened and Panel's first frame", () => {
    const error = new TypeError("cannot read 'pl1'");
    error.stack = [
      "TypeError: cannot read 'pl1'",
      "    at Object.render (http://127.0.0.1:1337/steam_resource/x.js:1:2)",
      "    at TdpCard (http://127.0.0.1:1337/plugins/Panel%20de%20Control/dist/index.js:812:33)",
    ].join("\n");
    expect(describeError("section:power", error)).toEqual({
      code: "type_error",
      detail: "section:power: cannot read 'pl1' TdpCard index.js:812:33",
    });
  });

  it("reports only rejections coming from Panel's own code", async () => {
    const target = new EventTarget() as unknown as Window;
    const stop = startFrontendErrorReporting(target);
    const ours = new Error("ours");
    ours.stack = "Error: ours\n    at f (http://127.0.0.1:1337/plugins/Panel%20de%20Control/dist/index.js:1:1)";
    const theirs = new Error("theirs");
    theirs.stack = "Error: theirs\n    at g (http://127.0.0.1:1337/plugins/CSS%20Loader/dist/index.js:1:1)";
    for (const reason of [ours, theirs]) {
      const event = new Event("unhandledrejection") as Event & { reason: unknown };
      event.reason = reason;
      target.dispatchEvent(event);
    }
    stop();
    expect(recorded.map((args) => args[0])).toEqual(["frontend"]);
    expect(String(recorded[0][2])).toContain("async: ours");
  });
});
