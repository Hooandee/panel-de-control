// @vitest-environment happy-dom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TdpState } from "../api";

const captured = vi.hoisted(() => ({ arc: null as Record<string, unknown> | null }));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children }: any) => <div>{children}</div>,
  PanelSectionRow: ({ children }: any) => <div>{children}</div>,
  SliderField: () => <div />,
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
  on_ac: true,
  appid: null,
  has_game_profile: false,
  follows_global: false,
  watts: 15,
  global_watts: 15,
  applied_w: 15,
  supports_advanced: true,
  level_limits: {},
  levels: { pl1: 15, pl2: 22, pl3: 28 },
  boost_mode: "custom",
  global_levels: { pl1: 15, pl2: 22, pl3: 28 },
  global_boost_mode: "custom",
  firmware_modes: [],
  firmware_mode: "custom",
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

describe("TdpSection Steam Deck PPT arc", () => {
  afterEach(() => {
    captured.arc = null;
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
});
