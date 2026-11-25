// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PerformanceSettingControl } from "../steam/performanceSettings";

const captured = vi.hoisted(() => ({ rows: {} as Record<string, any> }));
vi.mock("@decky/ui", () => ({
  ToggleField: (props: any) => {
    captured.rows[props.label] = props;
    return <button role="switch" aria-checked={props.checked} disabled={props.disabled} onClick={() => props.onChange(!props.checked)}>{props.label}</button>;
  },
  DropdownItem: (props: any) => {
    captured.rows[props.label] = props;
    return <select aria-label={props.label} value={props.selectedOption} disabled={props.disabled} onChange={(event) => props.onChange({ data: Number(event.target.value) })}>{props.rgOptions.map((option: any) => <option key={option.data} value={option.data}>{option.label}</option>)}</select>;
  },
  SliderField: (props: any) => {
    captured.rows[props.label] = props;
    return <input aria-label={props.label} type="range" min={props.min} max={props.max} step={props.step} value={props.value} disabled={props.disabled} onChange={(event) => props.onChange(Number(event.target.value))} />;
  },
  DialogButton: (props: any) => {
    captured.rows[props.children] = props;
    return <button disabled={props.disabled} onClick={props.onClick}>{props.children}</button>;
  },
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
import { SteamPerformanceControls } from "./SteamPerformanceControls";

const controls: PerformanceSettingControl[] = [
  { id: "reset", kind: "action" },
  { id: "sharpness", kind: "slider", value: 2, min: 0, max: 5, step: 1 },
  { id: "splitScalingFilter", kind: "options", value: 1, options: [{ value: 1, label: "linear" }, { value: 2, label: "nearest" }, { value: 3, label: "sharp" }] },
  { id: "scalingMode", kind: "options", value: 1, options: ["auto", "integer", "fit", "fill", "stretch"].map((label, i) => ({ value: i + 1, label })) },
  { id: "vrr", kind: "toggle", value: true },
  { id: "refreshRate", kind: "options", value: 60, options: [{ value: 60, label: "60" }] },
];
const label = (id: string) => `steam.performance.control.${id}`;
afterEach(() => { cleanup(); captured.rows = {}; });

describe("SteamPerformanceControls", () => {
  it("orders groups and labels enum choices instead of exposing numeric IDs", () => {
    render(<SteamPerformanceControls controls={controls} disabled={false} onChange={vi.fn()} />);
    expect(screen.getAllByRole("group").map((group) => group.getAttribute("aria-label"))).toEqual(["steam.performance.group.display", "steam.performance.group.fluidity", "steam.performance.group.scaling"]);
    expect(captured.rows[label("splitScalingFilter")].rgOptions.map((option: any) => option.label)).toEqual(["linear", "nearest", "sharp"].map((key) => `steam.performance.option.${key}`));
    expect(captured.rows[label("scalingMode")].rgOptions.map((option: any) => option.label)).toEqual(["auto", "integer", "fit", "fill", "stretch"].map((key) => `steam.performance.option.${key}`));
    expect(screen.getByRole("option", { name: "60 Hz" })).toBeTruthy();
    expect(screen.getByRole("button", { name: label("reset") })).toBeTruthy();
  });

  it("forwards Decky controller callbacks and explicit reset actions", () => {
    const onChange = vi.fn();
    render(<SteamPerformanceControls controls={controls} disabled={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole("switch"));
    captured.rows[label("splitScalingFilter")].onChange({ data: 3 });
    captured.rows[label("sharpness")].onChange(4);
    fireEvent.click(screen.getByRole("button", { name: label("reset") }));
    expect(onChange.mock.calls).toEqual([["vrr", false], ["splitScalingFilter", 3], ["sharpness", 4], ["reset", undefined]]);
    expect(captured.rows[label("sharpness")]).toMatchObject({ min: 0, max: 5, step: 1, showValue: true });
  });

  it("uses an FPS slider with only Steam-supported values, including unlimited", () => {
    const onChange = vi.fn();
    render(<SteamPerformanceControls controls={[{
      id: "legacyFrameRate", kind: "options", value: 30,
      options: [15, 30, 60, 0].map((value) => ({ value, label: String(value) })),
    }]} disabled={false} onChange={onChange} />);
    const name = `${label("legacyFrameRate")}: 30 FPS`;
    expect(screen.getByRole("slider", { name })).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    const slider = captured.rows[name];
    expect(slider).toMatchObject({ value: 1, min: 0, max: 3, step: 1, showValue: false });
    slider.onChange(2);
    slider.onChange(3);
    slider.onChange(1.5);
    slider.onChange(9);
    expect(onChange.mock.calls).toEqual([["legacyFrameRate", 60], ["legacyFrameRate", 0]]);
  });

  it("disables every Decky control and guards queued controller callbacks", () => {
    const onChange = vi.fn();
    render(<SteamPerformanceControls controls={controls} disabled onChange={onChange} />);
    expect(Object.values(captured.rows).every((row) => row.disabled)).toBe(true);
    captured.rows[label("vrr")].onChange(false);
    captured.rows[label("splitScalingFilter")].onChange({ data: 3 });
    captured.rows[label("sharpness")].onChange(4);
    captured.rows[label("reset")].onClick();
    expect(onChange).not.toHaveBeenCalled();
  });
});
