// @vitest-environment happy-dom
import { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const decky = vi.hoisted(() => ({ shownModal: null as ReactNode | null, showCount: 0 }));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, onClick, noFocusRing: _noFocusRing, ...props }: { children?: ReactNode; onActivate?: () => void; noFocusRing?: boolean } & HTMLAttributes<HTMLDivElement>) => (
    <div data-focusable={onActivate ? "true" : undefined} onClick={onClick ?? onActivate} {...props}>{children}</div>
  ),
  ModalRoot: ({ children, bAllowFullSize }: { children?: ReactNode; bAllowFullSize?: boolean }) => (
    <div data-testid="modal-root" data-full-size={bAllowFullSize ? "true" : undefined}>{children}</div>
  ),
  DialogButton: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button disabled={disabled} onClick={onClick}>{children}</button>
  ),
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  showModal: (node: ReactNode) => {
    decky.shownModal = node;
    decky.showCount += 1;
  },
  SliderField: ({ value, min, max, onChange }: { value: number; min?: number; max?: number; onChange?: (value: number) => void }) => (
    <input role="slider" type="range" value={value} min={min} max={max} onChange={(event) => onChange?.(Number(event.currentTarget.value))} />
  ),
}));

vi.mock("../api", () => ({
  getFanCurveState: vi.fn(() => new Promise(() => {})),
  setDesktopFanCurve: vi.fn(() => Promise.resolve()),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string, vars?: Record<string, string | number>) => {
    if (key === "desktop.fan.summary") {
      return [vars?.rpm, vars?.max, vars?.sensor].filter(Boolean).join(" · ");
    }
    return ({
      "desktop.fan.system": "Ventilador del sistema",
      "desktop.fan.auto.note": "Automático devuelve este ventilador a su propietario anterior o al firmware.",
    })[key] ?? key;
  } }),
}));

vi.mock("./FanCurveGraph", () => ({
  FanCurveGraph: ({ onChange }: { onChange: (points: [number, number][]) => void }) => (
    <button aria-label="change-inline-curve" onClick={() => onChange([[40, 10], [60, 100], [80, 190], [95, 255]])} />
  ),
}));

import { getFanCurveState, setDesktopFanCurve, type FanCurveState } from "../api";
import { DesktopFanCurves } from "./DesktopFanCurves";

const state = {
  device_key: "steam_machine",
  independent: true,
  presets: [],
  channels: [{
    key: "system",
    preset: "auto",
    points: null,
    sensor: "CPU / GPU / VRAM",
    rpm: 537,
    max_rpm: 1800,
    controllable: true,
  }, {
    key: "gpu",
    preset: "auto",
    points: null,
    sensor: "GPU junction",
    rpm: 822,
    max_rpm: 4900,
    controllable: false,
  }],
} as unknown as FanCurveState;

const customState = {
  ...state,
  channels: state.channels?.map((channel) => channel.key === "system"
    ? { ...channel, preset: "custom", points: [[40, 0], [60, 90], [80, 180], [95, 255]] }
    : channel),
} as FanCurveState;

describe("DesktopFanCurves", () => {
  afterEach(() => {
    decky.shownModal = null;
    decky.showCount = 0;
    vi.mocked(setDesktopFanCurve).mockClear();
    vi.mocked(getFanCurveState).mockReset();
    vi.mocked(getFanCurveState).mockImplementation(() => new Promise(() => {}));
    cleanup();
  });

  it("stacks the fan title above its explanatory metrics", () => {
    render(<DesktopFanCurves initial={state} />);

    const header = screen.getByTestId("desktop-fan-header-system");
    expect(header.style.flexDirection).toBe("column");
    expect(screen.getByText("Ventilador del sistema")).toBeTruthy();
    expect(header.textContent).toContain("537 RPM · CPU / GPU / VRAM");
    expect(header.textContent).not.toContain("1800");
  });

  it("shows scroll anchors only for controllable fan channels", () => {
    render(<DesktopFanCurves initial={state} />);

    const systemNote = screen.getByTestId("desktop-fan-note-system");
    expect(screen.getAllByRole("note")).toHaveLength(1);
    expect(systemNote.dataset.focusable).toBe("true");
    expect(systemNote.textContent).toBe("Automático devuelve este ventilador a su propietario anterior o al firmware.");
    expect(screen.queryByTestId("desktop-fan-header-gpu")).toBeNull();
  });

  it("keeps GPU channels visible on other desktop machines", () => {
    render(<DesktopFanCurves initial={{ ...state, device_key: "generic" } as FanCurveState} />);

    expect(screen.getByTestId("desktop-fan-header-system")).toBeTruthy();
    expect(screen.getByTestId("desktop-fan-header-gpu")).toBeTruthy();
  });

  it("offers the full-screen manual editor for a controllable custom channel", () => {
    render(<DesktopFanCurves initial={customState} />);

    const expand = screen.getByRole("button", { name: "fans.curve.expand" });
    expect(expand.dataset.focusable).toBe("true");
  });

  it("opens a full-size manual editor with controller sliders", () => {
    render(<DesktopFanCurves initial={customState} />);

    fireEvent.click(screen.getByRole("button", { name: "fans.curve.expand" }));
    expect(decky.shownModal).not.toBeNull();
    render(decky.shownModal as ReactNode);

    expect(screen.getByTestId("modal-root").dataset.fullSize).toBe("true");
    expect(screen.getAllByRole("slider")).toHaveLength(2);
  });

  it("opens one modal when Decky dispatches activation twice in the same tick", () => {
    render(<DesktopFanCurves initial={customState} />);

    const expand = screen.getByRole("button", { name: "fans.curve.expand" });
    fireEvent.click(expand);
    fireEvent.click(expand);

    expect(decky.showCount).toBe(1);
  });

  it("keeps plateau PWM values inside the visible percentage range", () => {
    const plateauState = {
      ...customState,
      channels: customState.channels?.map((channel) => channel.key === "system"
        ? { ...channel, points: [[40, 90], [60, 90], [80, 180], [95, 180]] }
        : channel),
    } as FanCurveState;
    render(<DesktopFanCurves initial={plateauState} />);
    fireEvent.click(screen.getByRole("button", { name: "fans.curve.expand" }));
    render(decky.shownModal as ReactNode);
    fireEvent.click(screen.getAllByRole("button", { name: "desktop.fan.manual.point" })[1]);

    const speed = screen.getAllByRole("slider")[1];
    expect(speed.getAttribute("min")).toBe("35");
    expect(speed.getAttribute("max")).toBe("71");
  });

  it("keeps the latest inline draft when the modal validates the channel", async () => {
    vi.mocked(getFanCurveState).mockResolvedValueOnce({
      ...customState,
      channels: customState.channels?.map((channel) => channel.key === "system"
        ? { ...channel, points: [[40, 0], [60, 60], [80, 150], [95, 255]] }
        : channel),
    } as FanCurveState);
    render(<DesktopFanCurves initial={customState} />);
    fireEvent.click(screen.getByRole("button", { name: "fans.curve.expand" }));
    render(decky.shownModal as ReactNode);
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByText("60° · 35%")).toBeTruthy();
  });

  it("flushes an inline draft before opening the modal", async () => {
    const draftState = {
      ...customState,
      apply_ok: true,
      channels: customState.channels?.map((channel) => channel.key === "system"
        ? { ...channel, points: [[40, 10], [60, 100], [80, 190], [95, 255]] }
        : channel),
    } as FanCurveState;
    vi.mocked(setDesktopFanCurve).mockResolvedValueOnce(draftState);
    render(<DesktopFanCurves initial={customState} />);

    fireEvent.click(screen.getByRole("button", { name: "change-inline-curve" }));
    fireEvent.click(screen.getByRole("button", { name: "fans.curve.expand" }));

    await waitFor(() => expect(setDesktopFanCurve).toHaveBeenCalledWith(
      "system",
      "custom",
      [[40, 10], [60, 100], [80, 190], [95, 255]],
      "global",
      null,
    ));
    await waitFor(() => expect(decky.shownModal).not.toBeNull());
  });

  it("blocks a second modal activation while an inline flush is pending", async () => {
    let resolveFlush: ((state: FanCurveState) => void) | undefined;
    vi.mocked(setDesktopFanCurve).mockImplementationOnce(() => new Promise((resolve) => {
      resolveFlush = resolve;
    }));
    render(<DesktopFanCurves initial={customState} />);
    fireEvent.click(screen.getByRole("button", { name: "change-inline-curve" }));
    const expand = screen.getByRole("button", { name: "fans.curve.expand" });
    fireEvent.click(expand);
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });
    fireEvent.click(screen.getByRole("button", { name: "fans.curve.expand" }));

    expect(setDesktopFanCurve).toHaveBeenCalledTimes(1);
    resolveFlush?.({ ...customState, apply_ok: true });
    await act(async () => { await Promise.resolve(); });
  });

  it("saves controller edits to the captured desktop fan channel", async () => {
    vi.mocked(setDesktopFanCurve).mockResolvedValueOnce({ ...customState, apply_ok: true });
    render(<DesktopFanCurves initial={customState} />);
    fireEvent.click(screen.getByRole("button", { name: "fans.curve.expand" }));
    render(decky.shownModal as ReactNode);

    fireEvent.click(screen.getAllByRole("button", { name: "desktop.fan.manual.point" })[1]);
    fireEvent.change(screen.getAllByRole("slider")[1], { target: { value: "50" } });
    const save = screen.getByRole("button", { name: "desktop.fan.manual.save" });
    expect(save.dataset.focusable).toBe("true");
    fireEvent.click(save);

    await waitFor(() => expect(setDesktopFanCurve).toHaveBeenCalledWith(
      "system",
      "custom",
      [[40, 0], [60, 128], [80, 180], [95, 255]],
      "global",
      null,
    ));
  });

  it("does not report success when the desktop channel rejects the manual curve", async () => {
    vi.mocked(setDesktopFanCurve).mockResolvedValueOnce({ ...customState, apply_ok: false });
    render(<DesktopFanCurves initial={customState} />);
    fireEvent.click(screen.getByRole("button", { name: "fans.curve.expand" }));
    render(decky.shownModal as ReactNode);

    fireEvent.click(screen.getByRole("button", { name: "desktop.fan.manual.save" }));

    expect(await screen.findByText("desktop.fan.manual.saveError")).toBeTruthy();
  });
});
