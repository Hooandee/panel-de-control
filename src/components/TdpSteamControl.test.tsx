// @vitest-environment happy-dom
import { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { PowerDraw, TdpState } from "../api";

const captured = vi.hoisted(() => ({ slider: null as Record<string, unknown> | null }));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, onClick, noFocusRing: _n, ...props }: {
    children?: ReactNode; onActivate?: () => void; onClick?: () => void; noFocusRing?: boolean;
  } & HTMLAttributes<HTMLDivElement>) => (
    <div {...props} onClick={onClick ?? onActivate}>{children}</div>
  ),
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SliderField: (props: Record<string, unknown>) => {
    captured.slider = props;
    return <div />;
  },
  ToggleField: () => <div />,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./PowerArc", () => ({ PowerArc: () => <div data-testid="arc" /> }));
vi.mock("./PowerPresetsModal", () => ({ openPowerPresetsModal: vi.fn() }));
vi.mock("./Presets", () => ({ Presets: () => <div /> }));
vi.mock("./AdvancedBoost", () => ({ AdvancedBoost: () => <div /> }));
vi.mock("./TdpSuggestionCard", () => ({ TdpSuggestionCard: () => <div /> }));
vi.mock("./TdpOwnershipStatus", () => ({ TdpOwnershipStatus: () => <div /> }));

import { TdpSection } from "./TdpSection";
import { TdpWattsControl } from "./TdpWattsControl";

const tdp = {
  supported: true,
  backend: "steamdeck-hwmon",
  limits: { min: 3, default: 12, max: 15, max_ac: 15 },
  request_min: 3,
  on_ac: true,
  watts: 11,
  global_watts: 12,
  applied_w: 12,
  supports_advanced: false,
  supports_auto_tdp: true,
  level_limits: {},
  levels: { pl1: 12, pl2: 12, pl3: 12 },
  global_levels: { pl1: 12, pl2: 12, pl3: 12 },
  boost_mode: "estable",
  global_boost_mode: "estable",
  firmware_modes: [],
  firmware_mode: "custom",
  presets: {},
  learned: { enough: false },
  ownership: { status: "in_sync", reason: "", requested: {}, target: {}, applied: {}, surfaces: {}, conflict_persistent: false, failures: 0 },
} as unknown as TdpState;

function section(extra: Record<string, unknown> = {}) {
  return render(
    <TdpSection
      tdp={tdp}
      scope="global"
      power={null}
      onWatts={vi.fn()}
      onSetLevels={vi.fn()}
      onSetMode={vi.fn()}
      onApplySuggestion={vi.fn()}
      onFirmwareMode={vi.fn()}
      onLowBatteryHold={vi.fn()}
      presets={null}
      refreshPresets={vi.fn()}
      onApplyPreset={vi.fn()}
      {...extra}
    />,
  );
}

afterEach(() => { cleanup(); captured.slider = null; });

describe("handing the TDP back to Steam from inside the section", () => {
  it("stays reachable in the section after the card is closed", () => {
    const release = vi.fn();
    section({ onReleaseControl: release });
    fireEvent.click(screen.getByText("tdp.conflict.steamos.release"));
    expect(release).toHaveBeenCalledTimes(1);
  });

  it("is absent when no manager is detected", () => {
    section();
    expect(screen.queryByText("tdp.conflict.steamos.release")).toBeNull();
  });
});

describe("section without control", () => {
  it("shows the Steam line with a recover action and no write controls", async () => {
    const reactivate = vi.fn();
    section({ monitorOnly: true, steamControlled: true, onReactivate: reactivate });
    expect(screen.getByText("tdp.steamControl.line")).toBeTruthy();
    fireEvent.click(screen.getByText("tdp.steamControl.recover"));
    await waitFor(() => expect(reactivate).toHaveBeenCalledTimes(1));
    expect(captured.slider).toBeNull();
  });

  it("keeps the plain monitor wording when Steam is not the one driving", () => {
    section({ monitorOnly: true, steamControlled: false, onReactivate: vi.fn() });
    expect(screen.getByText("tdp.monitor.notice")).toBeTruthy();
  });

  it("reports a refused re-enable and allows a retry", async () => {
    const reactivate = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    section({ monitorOnly: true, onReactivate: reactivate });
    const button = screen.getByText("tdp.monitor.reactivate");
    fireEvent.click(button);
    expect((await screen.findByRole("alert")).textContent).toBe("tdp.monitor.reactivateFailed");
    expect(captured.slider).toBeNull();
    fireEvent.click(button);
    await waitFor(() => expect(reactivate).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("TDP block for custom views", () => {
  const props = {
    tdp,
    scope: "global" as const,
    power: null as PowerDraw | null,
    onWatts: vi.fn(),
    monitorOnly: false,
    steamControlled: false,
    onReactivate: vi.fn(),
  };

  it("exposes only the watts slider and writes through onWatts", () => {
    render(<TdpWattsControl {...props} />);
    expect(captured.slider).toMatchObject({ value: 12, min: 3, max: 15, disabled: false });
    (captured.slider!.onChange as (w: number) => void)(9);
    expect(props.onWatts).toHaveBeenCalledWith(9);
    expect(screen.queryByTestId("arc")).toBeNull();
  });

  it("is disabled with the Steam line and recover action without control", async () => {
    const onReactivate = vi.fn();
    render(<TdpWattsControl {...props} monitorOnly steamControlled onReactivate={onReactivate} />);
    expect(captured.slider).toMatchObject({ disabled: true });
    fireEvent.click(screen.getByText("tdp.steamControl.recover"));
    await waitFor(() => expect(onReactivate).toHaveBeenCalledTimes(1));
  });
});
