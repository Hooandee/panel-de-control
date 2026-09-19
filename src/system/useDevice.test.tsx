// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getDevice = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({ getDevice }));

import { useDeviceState } from "./useDevice";

const device = { key: "steam_deck_lcd" };

function Probe() {
  const state = useDeviceState();
  return <div>{state.device?.key ?? (state.failed ? "failed" : "loading")}</div>;
}

describe("shared device store", () => {
  afterEach(cleanup);

  it("retries a transient RPC failure when the UI is closed and reopened", async () => {
    getDevice.mockRejectedValueOnce(new Error("not ready")).mockResolvedValue(device);
    const first = render(<Probe />);
    await screen.findByText("failed");
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(getDevice).toHaveBeenCalledOnce();

    first.unmount();
    render(<Probe />);

    await waitFor(() => expect(screen.getByText("steam_deck_lcd")).toBeTruthy());
    expect(getDevice).toHaveBeenCalledTimes(2);
  });
});
