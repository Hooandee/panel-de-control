// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
vi.mock("../components/ContainedSlider", () => ({ ContainedSlider: ({ label, value, min, max, step, disabled, onChange, notchLabels }: any) => <div><span data-testid="notches">{notchLabels?.map((n: any) => n.label).join("|")}</span><input type="range" aria-label={label} value={value} min={min} max={max} step={step} disabled={disabled} onChange={e => onChange(Number(e.target.value))} /></div> }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
import { FlowScale, clampFlowScale } from "./FlowScale";

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

const slider = () => screen.getByRole("slider", { name: "up.lsfg.flowScale" }) as HTMLInputElement;

it("shows the saved value and spans lsfg-vk's 0.25 to 1.0 range", () => {
  render(<FlowScale appid="1" value={0.75} disabled={false} onCommit={vi.fn()} />);
  expect(slider().value).toBe("75");
  expect([slider().min, slider().max, slider().step]).toEqual(["25", "100", "5"]);
});

it("commits the chosen value as a fraction once the slider rests", () => {
  const commit = vi.fn();
  render(<FlowScale appid="1" value={0.75} disabled={false} onCommit={commit} />);
  fireEvent.change(slider(), { target: { value: "60" } });
  fireEvent.change(slider(), { target: { value: "85" } });
  expect(commit).not.toHaveBeenCalled();
  act(() => { vi.advanceTimersByTime(400); });
  expect(commit).toHaveBeenCalledExactlyOnceWith(0.85);
});

it("never commits outside the range, at either end", () => {
  const commit = vi.fn();
  render(<FlowScale appid="1" value={0.75} disabled={false} onCommit={commit} />);
  fireEvent.change(slider(), { target: { value: "5" } });
  act(() => { vi.advanceTimersByTime(400); });
  fireEvent.change(slider(), { target: { value: "400" } });
  act(() => { vi.advanceTimersByTime(400); });
  expect(commit.mock.calls).toEqual([[0.25], [1]]);
  expect([clampFlowScale(24), clampFlowScale(101), clampFlowScale(62)]).toEqual([25, 100, 60]);
});

it("ignores the slider while the controls are blocked", () => {
  const commit = vi.fn();
  render(<FlowScale appid="1" value={0.5} disabled onCommit={commit} />);
  fireEvent.change(slider(), { target: { value: "90" } });
  act(() => { vi.advanceTimersByTime(400); });
  expect(commit).not.toHaveBeenCalled();
});

it("labels both ends so the number is not needed", () => {
  render(<FlowScale appid="1" value={0.75} disabled={false} onCommit={vi.fn()} />);
  expect(screen.getByTestId("notches").textContent).toBe("up.lsfg.flowScale.performance|up.lsfg.flowScale.quality");
});
