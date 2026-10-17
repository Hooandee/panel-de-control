// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PowerDraw, TdpState } from "../api";

const captured = vi.hoisted(() => ({
  arc: null as Record<string, unknown> | null,
  slider: null as Record<string, unknown> | null,
  presets: null as Record<string, unknown> | null,
}));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick, role, "aria-label": label, "aria-selected": selected }: any) => (
    <div role={role} aria-label={label} aria-selected={selected} onClick={onClick}>{children}</div>
  ),
  PanelSectionRow: ({ children }: any) => <div>{children}</div>,
  SliderField: (props: Record<string, unknown>) => {
    captured.slider = props;
    return <div />;
  },
  ToggleField: () => <div />,
}));

vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./PowerArc", () => ({
  PowerArc: (props: Record<string, unknown>) => {
    captured.arc = props;
    return <div />;
  },
}));
vi.mock("./Presets", () => ({
  Presets: (props: Record<string, unknown>) => {
    captured.presets = props;
    return <div />;
  },
}));
vi.mock("./TdpMonitorNotice", () => ({ TdpMonitorNotice: () => <div /> }));
vi.mock("./PowerPresetsModal", () => ({ openPowerPresetsModal: vi.fn() }));
vi.mock("./FirmwareModes", () => ({ FirmwareModes: () => <div /> }));
vi.mock("./AdvancedBoost", () => ({ AdvancedBoost: () => <div /> }));
vi.mock("./TdpSuggestionCard", () => ({ TdpSuggestionCard: () => <div /> }));
vi.mock("./TdpOwnershipStatus", () => ({ TdpOwnershipStatus: () => <div /> }));

import { TdpSection } from "./TdpSection";

const armState = (gpu: number | null, watts = 3) => ({
  supported: true,
  backend: "arm-frequency-levels",
  unit: "level",
  limits: { min: 1, default: 6, max: 10, max_ac: 10 },
  request_min: 1,
  on_ac: false,
  appid: null,
  has_game_profile: false,
  follows_global: true,
  watts,
  global_watts: watts,
  gpu_level_supported: true,
  gpu_level: gpu,
  global_gpu_level: gpu,
  applied_w: watts,
  supports_advanced: false,
  supports_auto_tdp: true,
  level_limits: {},
  levels: { pl1: watts, pl2: watts, pl3: watts },
  global_levels: { pl1: watts, pl2: watts, pl3: watts },
  boost_mode: "estable",
  global_boost_mode: "estable",
  presets: { quiet: 1, balanced: 6, turbo: 10, turbo_ac: 10 },
  level_frequencies: {
    "3": { cpu_khz: [1_248_000], gpu_mhz: 348 },
    "10": { cpu_khz: [3_187_200], gpu_mhz: 680 },
  },
  learned: { enough: false },
  global_auto_config: { enabled: false, target_fps: 40, initial_tdp: 6, min_tdp: null, max_tdp: null },
  auto_limits: { min: 1, default: 6, max: 10, max_ac: 10 },
  firmware_modes: [],
  ownership: {
    conflict_persistent: false,
    status: "in_sync",
    reason: "",
    requested: {},
    target: {},
    applied: {},
    surfaces: {},
    failures: 0,
  },
  ppt: null,
}) as unknown as TdpState;

function renderArm(tdp: TdpState, power: PowerDraw | null = null) {
  const onWatts = vi.fn();
  const onGpuLevel = vi.fn();
  render(
    <TdpSection
      tdp={tdp}
      scope="global"
      power={power}
      onWatts={onWatts}
      onGpuLevel={onGpuLevel}
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
  return { onWatts, onGpuLevel };
}

const tab = (name: string) => screen.getAllByRole("tab").find((node) => node.textContent?.includes(name))!;

describe("ARM single power dial with a CPU/GPU selector", () => {
  afterEach(() => {
    captured.arc = null;
    captured.slider = null;
    captured.presets = null;
    cleanup();
  });

  it("keeps one dial: linked, both parts move together and no inner ring shows", () => {
    const { onWatts, onGpuLevel } = renderArm(armState(null));
    expect(screen.getByRole("switch").getAttribute("aria-label")).toBe("tdp.target.unlink");
    expect(captured.arc?.ghost).toBeNull();

    fireEvent.click(tab("tdp.target.gpu"));
    (captured.slider?.onChange as (v: number) => void)(5);
    expect(onWatts).toHaveBeenCalledWith(5);
    expect(onGpuLevel).not.toHaveBeenCalled();
  });

  it("unlinking copies the CPU level into the GPU", () => {
    const { onGpuLevel } = renderArm(armState(null, 4));
    fireEvent.click(screen.getByRole("switch"));
    expect(onGpuLevel).toHaveBeenCalledWith(4);
  });

  it("split: the CPU tab drives the CPU and shows the GPU on the inner ring", () => {
    const { onWatts, onGpuLevel } = renderArm(armState(10));
    expect(captured.arc?.watts).toBe(3);
    expect(captured.arc?.ghost).toEqual({ value: 10, label: "tdp.target.gpu" });
    (captured.slider?.onChange as (v: number) => void)(2);
    expect(onWatts).toHaveBeenCalledWith(2);
    expect(onGpuLevel).not.toHaveBeenCalled();
    expect(screen.getByText("CPU 1.2 GHz · GPU 680 MHz", { normalizer: (text) => text.replace(/\s+/g, " ") })).toBeTruthy();
  });

  it("split: the GPU tab moves only the GPU, presets included", () => {
    const { onWatts, onGpuLevel } = renderArm(armState(10));
    fireEvent.click(tab("tdp.target.gpu"));
    expect(captured.arc?.watts).toBe(10);
    expect(captured.arc?.heroLabel).toBe("tdp.target.gpu");
    expect(captured.arc?.ghost).toEqual({ value: 3, label: "tdp.target.cpu" });

    (captured.slider?.onChange as (v: number) => void)(8);
    (captured.presets?.onPick as (item: { watts: number }) => void)({ watts: 1 });
    expect(onGpuLevel).toHaveBeenNthCalledWith(1, 8);
    expect(onGpuLevel).toHaveBeenNthCalledWith(2, 1);
    expect(onWatts).not.toHaveBeenCalled();
  });

  it("linking again hands the GPU back to the CPU level", () => {
    const { onGpuLevel } = renderArm(armState(10));
    fireEvent.click(screen.getByRole("switch"));
    expect(onGpuLevel).toHaveBeenCalledWith(null);
  });

  it("under Auto the inner ring keeps the distance the player set", () => {
    const power = { auto_tdp: true, setpoint: 5, applied: 5, watts: null } as unknown as PowerDraw;
    renderArm(armState(7, 3), power);
    expect(captured.arc?.ghost).toEqual({ value: 9, label: "tdp.target.gpu" });
  });

  it("PC never shows the selector", () => {
    renderArm({ ...armState(null), unit: "W", gpu_level_supported: false } as unknown as TdpState);
    expect(screen.queryByRole("switch")).toBeNull();
    expect(captured.arc?.heroLabel).toBeNull();
  });
});
