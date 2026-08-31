import { describe, expect, it, vi } from "vitest";

import { createRemotePublicationClient } from "./remotePublicationClient";

describe("remote publication client", () => {
  it("discovers publications without depending on a CSS Loader snapshot", async () => {
    const check = vi.fn(async () => ({ status: "published", checkedAt: 1, themes: [] }));

    await expect(createRemotePublicationClient(check).check(true)).resolves.toEqual({
      status: "published", checkedAt: 1, themes: [],
    });
    expect(check).toHaveBeenCalledWith(true);
  });

  it("fails closed when the backend response is not a sanitized publication", async () => {
    const result = await createRemotePublicationClient(async () => ({
      status: "published", checkedAt: 1, themes: [], transportUrl: "https://attacker.invalid",
    })).check(false);

    expect(result).toEqual({
      status: "recoverable-failure",
      code: "invalid_descriptor",
      retryable: true,
    });
  });
});
