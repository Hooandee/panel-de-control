// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PowerDraw, TdpState } from "../api";

const captured = vi.hoisted(() => ({
  arc: null as Record<string, unknown> | null,
  slider: null as Record<string, unknown> | null,
}));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children }: any) => <div>{children}</div>,
  PanelSectionRow: ({ children }: any) => <div>{children}</div>,
  SliderField: (props: Record<string, unknown>) => {
    captured.slider = props;
    return <div />;
  },
  ToggleField: ({ label, description, checked, onChange }: any) => (
    <button onClick={() => onChange(!checked)}>
      {label} · {description}
    </button>
  ),
}));

vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./PowerArc", () => ({
  PowerArc: (props: Record<string, unknown>) => {
    captured.arc = props;
    return <div />;
  },
}));
vi.mock("./TdpMonitorNotice", () => ({ TdpMonitorNotice: () => <div /> }));
vi.mock("./PowerPresetsModal", () => ({ openPowerPresetsModal: vi.fn() }));
vi.mock("./ProfileSelector", () => ({ ProfileSelector: () => <div /> }));
vi.mock("./Presets", () => ({ Presets: () => <div /> }));
vi.mock("./FirmwareModes", () => ({ FirmwareModes: () => <div /> }));
vi.mock("./AdvancedBoost", () => ({ AdvancedBoost: () => <div /> }));
vi.mock("./TdpSuggestionCard", () => ({ TdpSuggestionCard: () => <div /> }));
vi.mock("./TdpOwnershipStatus", () => ({ TdpOwnershipStatus: () => <div /> }));

import { TdpSection } from "./TdpSection";

const deckState = {
  supported: true,
  backend: "steamdeck-hwmon",
  limits: { min: 3, default: 12, max: 15, max_ac: 15 },
  request_min: 3,
  on_ac: true,
  appid: null,
  has_game_profile: false,
  follows_global: false,
  watts: 15,
  global_watts: 15,
  applied_w: 15,
  supports_advanced: true,
  supports_auto_tdp: true,
  level_limits: {},
  levels: { pl1: 15, pl2: 22, pl3: 28 },
  requested_levels: { pl1: 15, pl2: 22, pl3: 28 },
  boost_mode: "custom",
  global_levels: { pl1: 15, pl2: 22, pl3: 28 },
  global_requested_levels: { pl1: 15, pl2: 22, pl3: 28 },
  global_boost_mode: "custom",
  firmware_modes: [],
  firmware_mode: "custom",
  low_battery_hold: {
    available: true,
    enabled: false,
    active: false,
    verified: false,
    status: "inactive" as const,
    applied_w: null,
    reason: "disabled",
  },
  presets: {},
  learned: { enough: false, reason: "disabled" },
  ownership: {
    status: "in_sync",
    reason: "",
    requested: {},
    target: {},
    applied: {},
    surfaces: {},
    conflict_persistent: false,
    failures: 0,
  },
  ppt: {
    supported: true,
    source: "sysfs",
    visual_max: 30,
    slow: { min: 3, max: 29 },
    fast: { min: 3, max: 30 },
    requested: { slow: 22, fast: 28 },
    applied: { slow: 18, fast: 27 },
  },
} as unknown as TdpState;

const elevatedFloorState = {
  ...deckState,
  limits: { min: 20, default: 25, max: 35, max_ac: 35 },
  request_min: 20,
  watts: 20,
  global_watts: 20,
  levels: { pl1: 20, pl2: 20, pl3: 20 },
  global_levels: { pl1: 20, pl2: 20, pl3: 20 },
  requested_levels: { pl1: 20, pl2: 20, pl3: 20 },
  global_requested_levels: { pl1: 20, pl2: 20, pl3: 20 },
  ppt: null,
} as unknown as TdpState;

function renderTdpSection(
  tdp: TdpState,
  { power = null, monitorOnly = false }: {
    power?: PowerDraw | null;
    monitorOnly?: boolean;
  } = {},
) {
  return render(
    <TdpSection
      tdp={tdp}
      scope="global"
      game={null}
      power={power}
      onScope={vi.fn()}
      onWatts={vi.fn()}
      onSetLevels={vi.fn()}
      onSetMode={vi.fn()}
      onApplySuggestion={vi.fn()}
      onFirmwareMode={vi.fn()}
      onLowBatteryHold={vi.fn()}
      monitorOnly={monitorOnly}
      presets={null}
      refreshPresets={vi.fn()}
      onApplyPreset={vi.fn()}
    />,
  );
}

describe("TdpSection Steam Deck PPT arc", () => {
  afterEach(() => {
    captured.arc = null;
    captured.slider = null;
    cleanup();
  });

  it("keeps the requested Slow rail separate from its confirmed readback", () => {
    render(
      <TdpSection
        tdp={deckState}
        scope="game"
        game={null}
        power={null}
        onScope={vi.fn()}
        onWatts={vi.fn()}
        onSetLevels={vi.fn()}
        onSetMode={vi.fn()}
        onApplySuggestion={vi.fn()}
        onFirmwareMode={vi.fn()}
        onLowBatteryHold={vi.fn()}
        monitorOnly
        presets={null}
        refreshPresets={vi.fn()}
        onApplyPreset={vi.fn()}
      />,
    );

    expect(captured.arc).toMatchObject({
      watts: 22,
      appliedWatts: 18,
      baseMarkerWatts: 15,
      slowMarkerWatts: 22,
      fastMarkerWatts: 28,
    });
  });

  it("offers three watts while keeping the physical minimum visible as information", () => {
    const state = {
      ...deckState,
      backend: "firmware-attr:lenovo-wmi-other",
      limits: { min: 5, default: 15, max: 33, max_ac: 40 },
      request_min: 3,
      watts: 3,
      global_watts: 3,
      levels: { pl1: 5, pl2: 15, pl3: 20 },
      global_levels: { pl1: 5, pl2: 15, pl3: 20 },
      requested_levels: { pl1: 3, pl2: 3, pl3: 3 },
      global_requested_levels: { pl1: 3, pl2: 3, pl3: 3 },
      ppt: null,
    };

    const { container } = render(
      <TdpSection
        tdp={state}
        scope="global"
        game={null}
        power={null}
        onScope={vi.fn()}
        onWatts={vi.fn()}
        onSetLevels={vi.fn()}
        onSetMode={vi.fn()}
        onApplySuggestion={vi.fn()}
        onFirmwareMode={vi.fn()}
        onLowBatteryHold={vi.fn()}
        presets={null}
        refreshPresets={vi.fn()}
        onApplyPreset={vi.fn()}
      />,
    );

    expect(captured.slider).toMatchObject({ min: 3, value: 3 });
    expect(screen.getByText("tdp.minimum.notice")).toBeTruthy();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(captured.arc).toMatchObject({
      watts: 3,
      limits: { min: 3, default: 15, max: 33, max_ac: 40 },
      appliedWatts: null,
    });
  });

  it("hides the minimum notice once the selected value reaches the physical floor", () => {
    const state = {
      ...deckState,
      limits: { min: 5, default: 15, max: 33, max_ac: 40 },
      request_min: 3,
      watts: 5,
      global_watts: 5,
      ppt: null,
    };

    render(
      <TdpSection
        tdp={state}
        scope="global"
        game={null}
        power={null}
        onScope={vi.fn()}
        onWatts={vi.fn()}
        onSetLevels={vi.fn()}
        onSetMode={vi.fn()}
        onApplySuggestion={vi.fn()}
        onFirmwareMode={vi.fn()}
        onLowBatteryHold={vi.fn()}
        presets={null}
        refreshPresets={vi.fn()}
        onApplyPreset={vi.fn()}
      />,
    );

    expect(screen.queryByText("tdp.minimum.notice")).toBeNull();
  });

  it("explains an elevated firmware floor while that minimum is selected", () => {
    renderTdpSection(elevatedFloorState);

    expect(captured.slider).toMatchObject({ min: 20, value: 20 });
    expect(screen.getByText("tdp.minimum.floor")).toBeTruthy();
  });

  const hiddenFirmwareFloorCases: Array<[
    string,
    TdpState,
    { power?: PowerDraw; monitorOnly?: boolean },
  ]> = [
    ["the selected value is above it", { ...elevatedFloorState, watts: 25, global_watts: 25 }, {}],
    ["the device uses the universal floor", { ...elevatedFloorState, limits: { min: 3, default: 12, max: 15, max_ac: 15 }, request_min: 3, watts: 3, global_watts: 3 }, {}],
    ["automatic TDP owns the control", elevatedFloorState, { power: { auto_tdp: true } as PowerDraw }],
    ["a firmware mode owns the control", { ...elevatedFloorState, firmware_modes: ["balanced"], firmware_mode: "balanced" }, {}],
    ["the section is monitor-only", elevatedFloorState, { monitorOnly: true }],
  ];

  it.each(hiddenFirmwareFloorCases)("hides the elevated firmware-floor explanation when %s", (_case, state, options) => {
    renderTdpSection(state, options);

    expect(screen.queryByText("tdp.minimum.floor")).toBeNull();
  });

  it("keeps the physical minimum on the automatic TDP scale", () => {
    const state = {
      ...deckState,
      limits: { min: 20, default: 25, max: 35, max_ac: 35 },
      request_min: 3,
      watts: 25,
      global_watts: 25,
      ppt: null,
    };

    render(
      <TdpSection
        tdp={state}
        scope="global"
        game={null}
        power={{ auto_tdp: true } as never}
        onScope={vi.fn()}
        onWatts={vi.fn()}
        onSetLevels={vi.fn()}
        onSetMode={vi.fn()}
        onApplySuggestion={vi.fn()}
        onFirmwareMode={vi.fn()}
        onLowBatteryHold={vi.fn()}
        presets={null}
        refreshPresets={vi.fn()}
        onApplyPreset={vi.fn()}
      />,
    );

    expect(captured.arc).toMatchObject({
      limits: { min: 20, default: 25, max: 35, max_ac: 35 },
    });
  });

  it("marks the low-battery switch as experimental and forwards the requested value", () => {
    const onLowBatteryHold = vi.fn();

    render(
      <TdpSection
        tdp={deckState}
        scope="global"
        game={null}
        power={null}
        onScope={vi.fn()}
        onWatts={vi.fn()}
        onSetLevels={vi.fn()}
        onSetMode={vi.fn()}
        onApplySuggestion={vi.fn()}
        onFirmwareMode={vi.fn()}
        onLowBatteryHold={onLowBatteryHold}
        presets={null}
        refreshPresets={vi.fn()}
        onApplyPreset={vi.fn()}
      />,
    );

    const toggle = screen.getByText(/tdp.lowBatteryHold.title/).closest("button")!;
    expect(toggle.textContent).toContain("tdp.lowBatteryHold.experimental");
    expect(toggle.textContent).toContain("tdp.lowBatteryHold.hint");
    fireEvent.click(toggle);
    expect(onLowBatteryHold).toHaveBeenCalledWith(true);
  });

  it("hides the switch when the active backend does not advertise support", () => {
    render(
      <TdpSection
        tdp={{
          ...deckState,
          low_battery_hold: {
            available: false,
            enabled: false,
            active: false,
            verified: false,
            status: "inactive",
            applied_w: null,
            reason: "unsupported",
          },
        }}
        scope="global"
        game={null}
        power={null}
        onScope={vi.fn()}
        onWatts={vi.fn()}
        onSetLevels={vi.fn()}
        onSetMode={vi.fn()}
        onApplySuggestion={vi.fn()}
        onFirmwareMode={vi.fn()}
        onLowBatteryHold={vi.fn()}
        presets={null}
        refreshPresets={vi.fn()}
        onApplyPreset={vi.fn()}
      />,
    );

    expect(screen.queryByText(/tdp.lowBatteryHold.title/)).toBeNull();
  });
});
