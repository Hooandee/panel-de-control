// @vitest-environment happy-dom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  checkUpdate: vi.fn(async () => ({
    current: "0.34.0",
    latest: "0.35.0",
    has_update: true,
    notes: "",
    download_url: "https://example.invalid/update.zip",
    error: "",
  })),
  installUpdate: vi.fn(),
  restartLoader: vi.fn(),
  toast: vi.fn(),
}));

vi.mock("@decky/api", () => ({
  toaster: { toast: mocks.toast },
}));

vi.mock("../api", () => ({
  checkUpdate: mocks.checkUpdate,
  installUpdate: mocks.installUpdate,
  restartLoader: mocks.restartLoader,
}));

let useUpdate: typeof import("./useUpdate").useUpdate;
beforeEach(async () => {
  vi.resetModules();
  vi.clearAllMocks();
  ({ useUpdate } = await import("./useUpdate"));
});
afterEach(cleanup);

describe("useUpdate Italian notification", () => {
  it("shows the update toast in Italian", async () => {
    renderHook(() => useUpdate("it"));

    await waitFor(() => {
      expect(mocks.toast).toHaveBeenCalledWith({
        title: "Aggiornamento disponibile",
        body: "v0.35.0",
      });
    });
  });
});

describe("shared update session", () => {
  it("publishes one pending check to mounted consumers and later remounts", async () => {
    let resolve!: (info: Awaited<ReturnType<typeof mocks.checkUpdate>>) => void;
    mocks.checkUpdate.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const first = renderHook(() => useUpdate("es"));
    const second = renderHook(() => useUpdate("es"));
    expect(first.result.current.status).toBe("checking");
    expect(second.result.current.status).toBe("checking");
    await act(async () => resolve({ current: "1", latest: "2", has_update: true, notes: "notes", download_url: "", error: "" }));
    expect(first.result.current.info?.latest).toBe("2");
    expect(second.result.current.info?.latest).toBe("2");
    expect(second.result.current.hasUpdate).toBe(true);
    first.unmount();
    const reopened = renderHook(() => useUpdate("es"));
    expect(reopened.result.current.info?.latest).toBe("2");
    expect(mocks.checkUpdate).toHaveBeenCalledExactlyOnceWith(false);
    expect(mocks.toast).toHaveBeenCalledOnce();
  });

  it("shares installing and done across consumers and remounts", async () => {
    const shell = renderHook(() => useUpdate("es"));
    await waitFor(() => expect(shell.result.current.status).toBe("idle"));
    const modal = renderHook(() => useUpdate("es"));
    let finish!: (result: { ok: boolean; needs_restart: boolean; message: string }) => void;
    mocks.installUpdate.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    let pending: ReturnType<typeof modal.result.current.install>;
    act(() => { pending = modal.result.current.install(); });
    expect(shell.result.current.status).toBe("installing");
    await act(async () => { finish({ ok: true, needs_restart: true, message: "" }); await pending; });
    expect(shell.result.current.status).toBe("done");
    modal.unmount();
    expect(renderHook(() => useUpdate("es")).result.current.status).toBe("done");
  });

  it("does not let a late check overwrite installation state", async () => {
    const shell = renderHook(() => useUpdate("es"));
    await waitFor(() => expect(shell.result.current.status).toBe("idle"));
    let resolve!: (info: Awaited<ReturnType<typeof mocks.checkUpdate>>) => void;
    mocks.checkUpdate.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    let checking: ReturnType<typeof shell.result.current.check>;
    act(() => { checking = shell.result.current.check(); });
    mocks.installUpdate.mockResolvedValueOnce({ ok: true, needs_restart: true, message: "" });
    await act(async () => { await shell.result.current.install(); });
    await act(async () => { resolve({ current: "1", latest: "2", has_update: true, notes: "", download_url: "", error: "" }); await checking; });
    expect(shell.result.current.status).toBe("done");
  });

  it("publishes installation failures so consumers can recover", async () => {
    const shell = renderHook(() => useUpdate("es"));
    await waitFor(() => expect(shell.result.current.status).toBe("idle"));
    const modal = renderHook(() => useUpdate("es"));
    mocks.installUpdate.mockRejectedValueOnce(new Error("offline"));
    await act(async () => { await modal.result.current.install(); });
    expect(shell.result.current.status).toBe("error");
    expect(shell.result.current.hasUpdate).toBe(true);
  });
});
