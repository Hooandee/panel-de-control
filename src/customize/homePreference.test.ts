import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Layout } from "./layout";
import { resetHomeMode, updateShowHome } from "./homePreference";

const mocks = vi.hoisted(() => ({
  saveLayout: vi.fn(),
  setShellMode: vi.fn(),
}));

vi.mock("./store", () => ({ saveLayout: mocks.saveLayout }));
vi.mock("../sections/shellMode", () => ({ setShellMode: mocks.setShellMode }));

const layout: Layout = {
  showHome: true,
  showDeviceHeader: true,
  tabs: { order: ["power", "settings"], hidden: [] },
  blocks: {},
  subitems: {},
};

describe("Home preference", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hides Home and switches immediately to classic tabs", () => {
    updateShowHome(layout, false);

    expect(mocks.saveLayout).toHaveBeenCalledTimes(1);
    expect(mocks.saveLayout).toHaveBeenNthCalledWith(1, { ...layout, showHome: false });
    expect(mocks.setShellMode).toHaveBeenCalledTimes(1);
    expect(mocks.setShellMode).toHaveBeenNthCalledWith(1, "tabs");
  });

  it("shows Home and opens it immediately", () => {
    updateShowHome(layout, true);

    expect(mocks.saveLayout).toHaveBeenCalledTimes(1);
    expect(mocks.saveLayout).toHaveBeenNthCalledWith(1, { ...layout, showHome: true });
    expect(mocks.setShellMode).toHaveBeenCalledTimes(1);
    expect(mocks.setShellMode).toHaveBeenNthCalledWith(1, "home");
  });

  it("returns navigation to Home after reset", () => {
    resetHomeMode();

    expect(mocks.saveLayout).not.toHaveBeenCalled();
    expect(mocks.setShellMode).toHaveBeenCalledTimes(1);
    expect(mocks.setShellMode).toHaveBeenNthCalledWith(1, "home");
  });
});
