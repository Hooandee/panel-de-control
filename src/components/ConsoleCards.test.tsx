// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConsoleState } from "../api";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => <div onClick={onClick}>{children}</div>,
  ToggleField: ({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) => (
    <button onClick={() => onChange(!checked)}>{label}</button>
  ),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./Collapsible", () => ({ Collapsible: ({ children, summary }: { children: ReactNode; summary: ReactNode }) => <div><span>{summary}</span>{children}</div> }));
vi.mock("./ContainedSlider", () => ({ ContainedSlider: () => null }));

import { ConsoleLightCard } from "./ConsoleLightCard";
import { ConsoleThermalCard } from "./ConsoleThermalCard";

const state = (overrides: Partial<ConsoleState> = {}): ConsoleState => ({
  supported: true,
  temps: { apu: 54, ssd: 40 },
  led: {
    supported: true,
    presets: [{ id: "off", animated: false }, { id: "blue_rich", animated: false }, { id: "pink_breathe", animated: true }],
    active: "blue_rich",
    last: null,
  },
  guard: { enabled: true, threshold: 95, effective_threshold: 95, blocked: null, alarm: false, alarm_supported: true, active: false, fan_held: false, fan_supported: true, last_beep: null },
  ...overrides,
});

describe("Console light card", () => {
  afterEach(cleanup);
  it("splits steady and animated effects and picks one", () => {
    const onPick = vi.fn();
    render(<ConsoleLightCard state={state()} onPick={onPick} />);
    expect(screen.getByText("console.light.fixed")).toBeTruthy();
    expect(screen.getByText("console.light.animated")).toBeTruthy();
    fireEvent.click(screen.getByText("console.light.off"));
    expect(onPick).toHaveBeenCalledWith("off");
  });
  it("says when the console refused the change", () => {
    render(<ConsoleLightCard state={state({ led: { ...state().led!, last: { ok: false, preset: "x", detail: "timeout" } } })} onPick={vi.fn()} />);
    expect(screen.getByText("console.light.failed")).toBeTruthy();
  });
});

describe("Thermal protection card", () => {
  afterEach(cleanup);
  it("toggles the guard and the beep separately", () => {
    const onChange = vi.fn();
    render(<ConsoleThermalCard state={state()} onChange={onChange} />);
    fireEvent.click(screen.getByText("console.guard.toggle"));
    fireEvent.click(screen.getByText("console.guard.alarm"));
    expect(onChange).toHaveBeenNthCalledWith(1, false, null, null);
    expect(onChange).toHaveBeenNthCalledWith(2, null, null, true);
  });
  it("shows when the protection is cooling the console", () => {
    render(<ConsoleThermalCard state={state({ guard: { ...state().guard!, active: true, fan_held: true } })} onChange={vi.fn()} />);
    expect(screen.getByText("console.guard.active")).toBeTruthy();
  });
  it("does not claim the fan is at maximum when the console has not accepted it", () => {
    render(<ConsoleThermalCard state={state({ guard: { ...state().guard!, active: true, fan_held: false } })} onChange={vi.fn()} />);
    expect(screen.getByText("console.guard.retrying")).toBeTruthy();
    expect(screen.queryByText("console.guard.active")).toBeNull();
  });
  it("hides the beep where the console has no buzzer", () => {
    render(<ConsoleThermalCard state={state({ guard: { ...state().guard!, alarm_supported: false } })} onChange={vi.fn()} />);
    expect(screen.queryByText("console.guard.alarm")).toBeNull();
  });
});

describe("Thermal protection notices", () => {
  afterEach(cleanup);
  it("asks to turn the fan module on when it is off", () => {
    render(<ConsoleThermalCard state={state({ guard: { ...state().guard!, blocked: "fan_module_off" } })} onChange={vi.fn()} />);
    expect(screen.getByText("console.guard.fanModuleOff")).toBeTruthy();
  });
  it("explains a limit raised above the fan target", () => {
    render(<ConsoleThermalCard state={state({ guard: { ...state().guard!, threshold: 80, effective_threshold: 90 } })} onChange={vi.fn()} />);
    expect(screen.getByText("console.guard.aboveTarget")).toBeTruthy();
  });
});

describe("Thermal protection summary", () => {
  afterEach(cleanup);
  it("is not shown as off while only the beep is armed", () => {
    render(<ConsoleThermalCard state={state({ guard: { ...state().guard!, enabled: false, alarm: true } })} onChange={vi.fn()} />);
    expect(screen.queryByText("system.off")).toBeNull();
    expect(screen.getByText("console.guard.at")).toBeTruthy();
  });
});
