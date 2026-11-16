// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, onClick, ...rest }: {
    children?: React.ReactNode; onActivate?: () => void; onClick?: () => void; [key: string]: unknown;
  }) => (
    <div role="button" aria-label={rest["aria-label"] as string} aria-disabled={rest["aria-disabled"] as boolean}
      onClick={onClick ?? onActivate}>{children}</div>
  ),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./FanCurveGraph", () => ({
  FanCurveGraph: ({ points, editable }: { points: unknown[]; editable: boolean }) => (
    <div data-testid="graph" data-editable={String(editable)} data-points={JSON.stringify(points)} />
  ),
}));
vi.mock("../api", () => ({}));
vi.mock("./SuggestionCard", () => ({ AdaptiveCard: () => <div data-testid="adaptive" /> }));

import { FanCurveEditor } from "./FanCurveEditor";
import type { FanCurveControl } from "../fans/useFanCurve";

const base = {
  supported: true, preset: "balanced", points: [[40, 0], [95, 255]], custom_points: null, bias: 0,
  has_game_profile: false, presets: [], channels: [],
};
const makeControl = (state: Record<string, unknown>) => ({
  state: { ...base, ...state },
  saved: false,
  scope: "global",
  game: null,
  onScope: vi.fn(),
  onPreset: vi.fn(),
  onCustomMode: vi.fn(),
  onCurve: vi.fn(),
  onSplit: vi.fn(),
  onChannelCurve: vi.fn(),
  onAdaptiveBias: vi.fn(),
}) as unknown as FanCurveControl;

describe("FanCurveEditor Juntos / Por separado", () => {
  afterEach(cleanup);

  it.each([undefined, false])("offers no switch without split_available (%s)", (available) => {
    render(<FanCurveEditor control={makeControl({ split_available: available })} liveTemp={40} suggestion={null} />);
    expect(screen.queryByLabelText("fans.split.joined")).toBeNull();
    expect(screen.queryByLabelText("fans.split.separate")).toBeNull();
    expect(screen.getAllByTestId("graph")).toHaveLength(1);
  });

  it("offers the switch with split_available and switches on activation", () => {
    const control = makeControl({ split_available: true, split: false });
    render(<FanCurveEditor control={control} liveTemp={40} suggestion={null} />);
    fireEvent.click(screen.getByLabelText("fans.split.separate"));
    expect(control.onSplit).toHaveBeenCalledWith(true);
    fireEvent.click(screen.getByLabelText("fans.split.joined"));
    expect(control.onSplit).toHaveBeenCalledTimes(1); // already joined
  });

  it("shows one graph per fan and disables Adaptive when split", () => {
    const control = makeControl({
      split_available: true, split: true, preset: "custom",
      channels: [
        { key: "cpu", preset: "custom", points: [[40, 100], [95, 255]] },
        { key: "gpu", preset: "custom", points: [[40, 0], [95, 255]] },
      ],
    });
    render(<FanCurveEditor control={control} liveTemp={40} suggestion={null} />);
    const graphs = screen.getAllByTestId("graph");
    expect(graphs).toHaveLength(2);
    expect(graphs[0].getAttribute("data-points")).toBe("[[40,100],[95,255]]");
    expect(graphs[1].getAttribute("data-points")).toBe("[[40,0],[95,255]]");
    expect(graphs.every((graph) => graph.getAttribute("data-editable") === "true")).toBe(true);
    expect(screen.getByLabelText("fans.preset.adaptive").getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(screen.getByLabelText("fans.preset.adaptive"));
    expect(control.onPreset).not.toHaveBeenCalled();
    expect(screen.getByText("fans.split.adaptiveOff")).toBeTruthy();
  });
});
