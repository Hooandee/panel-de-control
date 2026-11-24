// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, noFocusRing, onActivate }: { children?: React.ReactNode; noFocusRing?: boolean; onActivate?: () => void }) => (
    <div data-focusable data-activatable={onActivate ? "1" : "0"} data-no-focus-ring={noFocusRing ? "1" : "0"}>{children}</div>
  ),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./FanCurveGraph", () => ({ FanCurveGraph: () => null }));
vi.mock("../api", () => ({}));
vi.mock("./SuggestionCard", () => ({ AdaptiveCard: () => null }));

import { FanCurveEditor } from "./FanCurveEditor";
import type { FanCurveControl } from "../fans/useFanCurve";

const control = {
  state: { supported: true, preset: "auto", points: null, custom_points: null, bias: 0, has_game_profile: false, presets: [] },
  saved: false,
  scope: "global",
  game: { appid: "1", name: "Game" },
  onScope: vi.fn(),
  onPreset: vi.fn(),
  onCustomMode: vi.fn(),
  onCurve: vi.fn(),
  onAdaptiveBias: vi.fn(),
} as unknown as FanCurveControl;

describe("FanCurveEditor focus ring", () => {
  afterEach(cleanup);

  // Steam's own focus ring pulses 20 times on a focused control inside a full-size modal and
  // repaints the whole modal each frame; Panel draws its own ring.
  it("keeps Steam's pulsing ring off every selectable chip", () => {
    const { container } = render(<FanCurveEditor control={control} liveTemp={40} suggestion={null} expanded />);
    const chips = [...container.querySelectorAll('[data-focusable][data-activatable="1"]')];
    expect(chips.length).toBeGreaterThanOrEqual(8);
    expect(chips.filter((chip) => chip.getAttribute("data-no-focus-ring") !== "1")).toHaveLength(0);
  });
});
