// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TdpState } from "../api";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children }: any) => <div>{children}</div>,
  PanelSectionRow: ({ children }: any) => <div>{children}</div>,
  SliderField: () => <div />,
  ToggleField: () => <div />,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./PowerArc", () => ({ PowerArc: () => <div /> }));
vi.mock("./TdpMonitorNotice", () => ({ TdpMonitorNotice: () => <div /> }));
vi.mock("./PowerPresetsModal", () => ({ openPowerPresetsModal: vi.fn() }));
vi.mock("./Presets", () => ({ Presets: () => <div /> }));
vi.mock("./FirmwareModes", () => ({ FirmwareModes: () => <div /> }));
vi.mock("./AdvancedBoost", () => ({ AdvancedBoost: () => <div /> }));
vi.mock("./TdpSuggestionCard", () => ({ TdpSuggestionCard: () => <div /> }));
vi.mock("./TdpOwnershipStatus", () => ({ TdpOwnershipStatus: () => <div /> }));

import { TdpSection } from "./TdpSection";

const noop = () => undefined;
const levels = { pl1: 10, pl2: 10, pl3: 10 };
const unsupported = {
  supported: false, limits: { min: 4, default: 10, max: 30, max_ac: 30 }, level_limits: {},
  levels, requested_levels: levels, global_levels: levels, global_requested_levels: levels,
  watts: 10, global_watts: 10, unit: "W", presets: { quiet: 4, balanced: 10, turbo: 30, turbo_ac: 30 }, firmware_modes: [], boost_mode: "estable", global_boost_mode: "estable",
} as unknown as TdpState;
const render_ = (consoleManaged: boolean) => render(
  <TdpSection tdp={unsupported} scope="global" power={null}
    onWatts={noop} onGpuLevel={noop} onSetLevels={noop} onSetMode={noop} onApplySuggestion={noop}
    onFirmwareMode={noop} onLowBatteryHold={noop} monitorOnly={false} onReactivate={noop}
    presets={null} refreshPresets={noop} onApplyPreset={noop} consoleManaged={consoleManaged} />,
);

describe("TdpSection without a TDP route", () => {
  afterEach(cleanup);

  it("explains on the PS5 that the console manages its power and where to act", () => {
    render_(true);
    expect(screen.getByText("tdp.console.title")).toBeTruthy();
    expect(screen.getByText("tdp.console.body")).toBeTruthy();
    expect(screen.queryByText("tdp.unsupported")).toBeNull();
  });

  it("keeps the generic notice elsewhere", () => {
    render_(false);
    expect(screen.getByText("tdp.unsupported")).toBeTruthy();
  });
});
