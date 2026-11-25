// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FanTargetState } from "../api";

vi.mock("@decky/api", () => ({ callable: () => async () => ({}) }));
vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogButton: ({ children }: { children: ReactNode }) => <button>{children}</button>,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./ContainedSlider", () => ({ ContainedSlider: () => null }));
vi.mock("./SegmentedTabs", () => ({ SegmentedTabs: () => null }));

import { FanTargetCard } from "./FanTargetCard";

const state: FanTargetState = {
  supported: true, celsius: 50, target: 70, min: 50, max: 90, default: 80, guard_active: true,
  presets: [{ id: "quiet", celsius: 85 }, { id: "balanced", celsius: 80 }, { id: "cool", celsius: 70 }, { id: "max", celsius: 50 }],
};

describe("FanTargetCard under the thermal guard", () => {
  afterEach(cleanup);
  it("shows the user's own target and says it applies once the console cools", () => {
    render(<FanTargetCard state={state} onChange={() => undefined} />);
    expect(screen.getByText("70 °C")).toBeTruthy();
    expect(screen.getByText("fans.target.deferred")).toBeTruthy();
  });
  it("falls back to the factory value when no target was chosen", () => {
    render(<FanTargetCard state={{ ...state, target: null }} onChange={() => undefined} />);
    expect(screen.getByText("80 °C")).toBeTruthy();
  });
  it("shows the live value again once the guard releases", () => {
    render(<FanTargetCard state={{ ...state, celsius: 70, guard_active: false }} onChange={() => undefined} />);
    expect(screen.getByText("fans.target.note")).toBeTruthy();
  });
});
