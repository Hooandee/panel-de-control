// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const profileState = vi.hoisted(() => ({ owner: undefined as any, hasGameProfile: false, manual: false, boost: false }));
vi.mock("@decky/ui", () => ({
  Focusable: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ToggleField: () => <div>gpu-toggle</div>,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./Collapsible", () => ({ Collapsible: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock("./ContainedSlider", () => ({ ContainedSlider: () => null }));
vi.mock("../gpu/useGpuClock", () => ({ useGpuClock: () => ({
  state: { supported: true, range_min: 200, range_max: 1600, min: 200, max: 1600, manual: profileState.manual, cpu_boost_overrides: profileState.boost,
    has_game_profile: profileState.hasGameProfile, game_power_owner: profileState.owner },
  scope: "game", game: { appid: "42", name: "Dante" }, onScope: vi.fn(), setManual: vi.fn(), setWindow: vi.fn(),
}) }));
import { GpuClockCard } from "./GpuClockCard";

describe("GPU profile source hint", () => {
  afterEach(() => { cleanup(); profileState.owner = undefined; profileState.hasGameProfile = false; profileState.manual = false; profileState.boost = false; });
  it.each([
    [true, "steam", "steam.performance.profile.game"],
    [false, "steam", "tdp.inherit"],
    [true, "pdc", "tdp.inherit"],
    [undefined, undefined, "tdp.inherit"],
  ])("shows the actual profile source for supported=%s owner=%s", (supported, owner, hint) => {
    profileState.owner = owner ? { supported, owner } : undefined;
    render(<GpuClockCard />);
    expect(screen.getByText(hint)).toBeTruthy();
    expect(screen.queryByText(hint === "tdp.inherit" ? "steam.performance.profile.game" : "tdp.inherit")).toBeNull();
  });
  it("does not invent a saved PDC profile to hide the inheritance hint", () => {
    profileState.hasGameProfile = true;
    profileState.owner = { supported: true, owner: "steam" };
    render(<GpuClockCard />);
    expect(screen.queryByText("steam.performance.profile.game")).toBeNull();
    expect(screen.queryByText("tdp.inherit")).toBeNull();
  });
});

describe("GPU limit under a CPU boost", () => {
  afterEach(() => { cleanup(); profileState.manual = false; profileState.boost = false; });
  it("warns that the PS5 can exceed a manual limit while boost is on", () => {
    profileState.manual = true;
    profileState.boost = true;
    render(<GpuClockCard />);
    expect(screen.getByText("gpu.clock.boostOverrides")).toBeTruthy();
  });
  it("stays quiet without a manual limit", () => {
    profileState.boost = true;
    render(<GpuClockCard />);
    expect(screen.queryByText("gpu.clock.boostOverrides")).toBeNull();
  });
});
