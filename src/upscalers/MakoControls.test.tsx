// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MakoProfile } from "../api";
import { MakoControls } from "./MakoControls";

vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../components/ContainedSlider", () => ({ ContainedSlider: ({ label, value, min, max, step, disabled, onChange }: any) => <input type="range" aria-label={label} value={value} min={min} max={max} step={step} disabled={disabled} onChange={e => onChange(Number(e.target.value))} /> }));
vi.mock("./parts", () => ({
  Note: ({ children }: any) => <div>{children}</div>,
  ListCard: ({ children }: any) => <section>{children}</section>,
  ListRow: ({ label, disabled, onPress }: any) => <button disabled={disabled} onClick={onPress}>{label}</button>,
  PickerButton: ({ label, value, options, disabled, onChange }: any) => <select aria-label={label} value={value} disabled={disabled} onChange={event => onChange(event.target.value)}>{options.map((option: any) => <option key={option.value} value={option.value}>{option.label}</option>)}</select>,
}));
afterEach(() => { cleanup(); vi.useRealTimers(); });
const profile: MakoProfile = { mode: "fixed", multiplier: 2, target_fps: 90, max_multiplier: 3, flow: "balanced", performance: false };

describe("MAKO controls", () => {
  it("shows fixed multiplier and keeps the other choices when changing it", () => {
    const onChange = vi.fn();
    render(<MakoControls appid="123" duo={false} disabled={false} profile={profile} onChange={onChange} />);
    expect(screen.queryByRole("combobox", { name: "up.mako.target" })).toBeNull();
    fireEvent.change(screen.getByRole("combobox", { name: "up.lsfg.multiplier" }), { target: { value: "4" } });
    expect(onChange).toHaveBeenCalledWith({ ...profile, multiplier: 4 });
  });
  it("slides to any target and saves only the final drag value", async () => {
    vi.useFakeTimers();
    const onChange = vi.fn();
    render(<MakoControls appid="123" duo disabled={false} profile={{ ...profile, mode: "adaptive", target_fps: 87 }} onChange={onChange} />);
    expect(screen.queryByRole("combobox", { name: "up.lsfg.multiplier" })).toBeNull();
    expect((screen.getByRole("slider", { name: "up.mako.target" }) as HTMLInputElement).value).toBe("87");
    fireEvent.change(screen.getByRole("slider", { name: "up.mako.target" }), { target: { value: "120" } });
    fireEvent.change(screen.getByRole("slider", { name: "up.mako.target" }), { target: { value: "121" } });
    expect(onChange).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(350); });
    expect(onChange).toHaveBeenCalledExactlyOnceWith({ ...profile, mode: "adaptive", target_fps: 121 });
  });
  it("disables every control while saving", () => {
    const onChange = vi.fn();
    render(<MakoControls appid="123" duo={false} disabled profile={profile} onChange={onChange} />);
    expect(screen.getAllByRole("combobox").every(element => (element as HTMLSelectElement).disabled)).toBe(true);
    fireEvent.click(screen.getByRole("button"));
    expect(onChange).not.toHaveBeenCalled();
  });
});

it("cancels a pending target when leaving the game", async () => {
  vi.useFakeTimers();
  const onChange = vi.fn();
  const view = render(<MakoControls appid="123" duo disabled={false} profile={{ ...profile, mode: "adaptive" }} onChange={onChange} />);
  fireEvent.change(screen.getByRole("slider", { name: "up.mako.target" }), { target: { value: "144" } });
  view.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(350); });
  expect(onChange).not.toHaveBeenCalled();
});
