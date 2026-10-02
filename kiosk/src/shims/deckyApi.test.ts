import { afterEach, describe, expect, it, vi } from "vitest";

import { callable, KIOSK_TOKEN_HEADER, KioskRpcError, kioskToken } from "./deckyApi";

afterEach(() => vi.unstubAllGlobals());

describe("kiosk callable", () => {
  it("reads the launch token from the page URL", () => {
    expect(kioskToken("?k=abc123")).toBe("abc123");
    expect(kioskToken("")).toBe("");
  });

  it("posts the method and positional args with the token", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ result: { unit: "level" } })));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("window", { location: { search: "?k=tok" } });
    const getState = callable<[scope: string], { unit: string }>("get_tdp_state");

    await expect(getState("global")).resolves.toEqual({ unit: "level" });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/rpc");
    expect((init.headers as Record<string, string>)[KIOSK_TOKEN_HEADER]).toBe("tok");
    expect(JSON.parse(init.body as string)).toEqual({ method: "get_tdp_state", args: ["global"] });
  });

  it("rejects like Decky does when the backend reports an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "RuntimeError" }), { status: 500 })));
    vi.stubGlobal("window", { location: { search: "?k=tok" } });
    await expect(callable("get_tdp_state")()).rejects.toBeInstanceOf(KioskRpcError);
  });
});
