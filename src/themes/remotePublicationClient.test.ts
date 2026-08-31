import { describe, expect, it, vi } from "vitest";

import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import { createRemotePublicationClient } from "./remotePublicationClient";

const READY: CssLoaderReadySnapshot = {
  status: "ready",
  pluginVersion: "2.1.2",
  backendVersion: 9,
  themes: [],
};

describe("remote publication client", () => {
  it.each(["latest", "v2.1.2", "2.1", "2.1.2-beta.1"])(
    "fails closed before RPC for a non-stable CSS Loader version: %s",
    async (pluginVersion) => {
      const check = vi.fn();
      const result = await createRemotePublicationClient(check).check(
        { ...READY, pluginVersion },
        false,
      );

      expect(result).toEqual({
        status: "recoverable-failure",
        code: "invalid_descriptor",
        retryable: false,
      });
      expect(check).not.toHaveBeenCalled();
    },
  );

  it("passes only verified runtime fields to the configured RPC", async () => {
    const check = vi.fn(async () => ({ status: "disabled" }));

    const result = await createRemotePublicationClient(check).check(READY, true);

    expect(result).toEqual({ status: "disabled" });
    expect(check).toHaveBeenCalledWith(true, "2.1.2", 9);
  });
});
