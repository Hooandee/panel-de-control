// @vitest-environment happy-dom
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

import * as useUpdateModule from "./useUpdate";

const { useUpdate } = useUpdateModule;
const getUpdateAvailableTitle = Reflect.get(useUpdateModule, "getUpdateAvailableTitle") as
  | ((lang: "it") => string)
  | undefined;

describe("useUpdate Italian notification", () => {
  it("exposes the Italian toast copy without em dashes", () => {
    expect(getUpdateAvailableTitle).toBeTypeOf("function");
    expect(getUpdateAvailableTitle?.("it")).toBe("Aggiornamento disponibile");
    expect(getUpdateAvailableTitle?.("it")).not.toContain("—");
  });

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
