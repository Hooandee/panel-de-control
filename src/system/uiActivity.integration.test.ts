// @vitest-environment happy-dom
import { waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const rpc = vi.hoisted(() => ({
  invoke: vi.fn(async (_method: string, _args: unknown[]) => true),
}));

vi.mock("@decky/api", () => ({
  callable: (method: string) => (...args: unknown[]) => rpc.invoke(method, args),
}));
vi.mock("@decky/ui", () => ({ getGamepadNavigationTrees: () => [] }));
vi.mock("../qamDocument", () => ({ onQamDocument: () => () => {} }));

import { acquireUiActivity, shutdownUiActivity } from "./uiActivity";

afterEach(() => {
  shutdownUiActivity();
  rpc.invoke.mockClear();
});

it("sends menu ownership through the production Decky RPC binding", async () => {
  const release = acquireUiActivity();

  await waitFor(() => {
    expect(rpc.invoke).toHaveBeenCalledWith("set_ui_active", [true]);
  });

  release();
  await waitFor(() => {
    expect(rpc.invoke).toHaveBeenLastCalledWith("set_ui_active", [false]);
  });
});
