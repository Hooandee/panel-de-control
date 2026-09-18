// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { CSSProperties, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const surface = vi.hoisted(() => ({
  useSurface: vi.fn(),
}));

vi.mock("../steam/useSteamPerformanceSurface", () => ({
  useSteamPerformanceSurface: surface.useSurface,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("../system/collapseState", () => ({
  isCollapsed: () => false,
  setCollapsed: vi.fn(),
}));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick, style }: {
    children?: ReactNode;
    onClick?: () => void;
    style?: CSSProperties;
  }) => <button type="button" onClick={onClick} style={style}>{children}</button>,
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));

import { SteamPerformanceCard } from "./SteamPerformanceCard";
import type { SteamPerformanceSurfaceState } from "../steam/useSteamPerformanceSurface";

describe("SteamPerformanceCard", () => {
  beforeEach(() => {
    surface.useSurface.mockReset();
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders the native controls inline in three always-open groups", () => {
    const row = (text: string) => () => <div data-testid="native-row">{text}</div>;
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [
        { id: "appFrameRate", Component: row("frame") },
        { id: "disableFrameLimit", Component: row("limit") },
        { id: "variableResolution", Component: row("shading") },
        { id: "vrr", Component: row("vrr") },
        { id: "allowTearing", Component: row("tearing") },
        { id: "scalingMode", Component: row("mode") },
        { id: "splitScalingFilter", Component: row("filter") },
        { id: "sharpness", Component: row("sharpness") },
        { id: "reset", Component: row("reset") },
      ],
    });

    render(<SteamPerformanceCard />);

    expect(screen.queryByRole("button", { name: /steam\.performance\.open/ })).toBeNull();
    expect(within(screen.getByRole("group", { name: "steam.performance.group.display" }))
      .getAllByTestId("native-row").map((item) => item.textContent))
      .toEqual(["frame", "limit"]);
    expect(within(screen.getByRole("group", { name: "steam.performance.group.fluidity" }))
      .getAllByTestId("native-row").map((item) => item.textContent))
      .toEqual(["shading", "vrr", "tearing"]);
    expect(within(screen.getByRole("group", { name: "steam.performance.group.scaling" }))
      .getAllByTestId("native-row").map((item) => item.textContent))
      .toEqual(["mode", "filter", "sharpness"]);
    const rows = screen.getAllByTestId("native-row");
    expect(rows[rows.length - 1]?.textContent).toBe("reset");
  });

  it("selects the running game's Steam profile through the shared power scope", () => {
    surface.useSurface.mockImplementation((scope, gameId) => ({
      status: scope === "game" && gameId === 42 ? "ready" : "unavailable",
      rows: [],
    }));

    render(<SteamPerformanceCard profileScope="game" runningGameId={42} />);

    expect(screen.getByRole("status").textContent).toContain("steam.performance.synced");
  });

  it("uses the same inline collapsible card pattern as the System section", () => {
    const Refresh = () => <div data-testid="native-row">refresh</div>;
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [{ id: "refreshRate", Component: Refresh }],
    });

    render(<SteamPerformanceCard />);

    const title = screen.getByText("steam.performance.title");
    const toggle = title.closest("button");
    expect(toggle).toBeTruthy();
    expect(screen.getByRole("group", { name: "steam.performance.group.display" })).toBeTruthy();

    fireEvent.click(toggle!);
    expect(screen.queryByRole("group", { name: "steam.performance.group.display" })).toBeNull();

    fireEvent.click(toggle!);
    expect(screen.getByRole("group", { name: "steam.performance.group.display" })).toBeTruthy();
  });

  it("shortens only Steam's automatic scaling notch to Auto", () => {
    const ScalingMode = () => (
      <div>
        <span>Automático</span>
        <span>Ajustar</span>
      </div>
    );
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [{ id: "scalingMode", Component: ScalingMode }],
    });

    render(<SteamPerformanceCard />);

    expect(screen.queryByText("Automático")).toBeNull();
    expect(screen.getByText("Auto")).toBeTruthy();
    expect(screen.getByText("Ajustar")).toBeTruthy();
  });

  it("fits native scaling sliders inside a narrower isolated viewport", () => {
    const sliderRow = (id: string, text: string) => () => (
      <div>
        <div id={`${id}-label`}>{text}</div>
        <div role="button" data-testid="native-slider-control">
          <div
            role="slider"
            aria-labelledby={`${id}-label`}
            data-testid="native-slider"
          />
        </div>
      </div>
    );
    const Tearing = () => <div>tearing</div>;
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [
        { id: "scalingMode", Component: sliderRow("mode", "mode") },
        { id: "splitScalingFilter", Component: sliderRow("filter", "filter") },
        { id: "sharpness", Component: sliderRow("sharpness", "sharpness") },
        { id: "allowTearing", Component: Tearing },
      ],
    });

    render(<SteamPerformanceCard />);

    const viewports = screen.getAllByTestId("steam-scaling-slider-viewport");
    const controls = screen.getAllByTestId("native-slider-control");
    const sliders = screen.getAllByTestId("native-slider");
    expect(viewports).toHaveLength(3);
    expect(controls).toHaveLength(3);
    expect(sliders).toHaveLength(3);
    expect(screen.queryByTestId("steam-scaling-slider-layout")).toBeNull();
    viewports.forEach((viewport) => {
      expect(viewport.style.width).toBe("calc(100% - 8px)");
      expect(viewport.style.marginInline).toBe("auto");
      expect(viewport.style.minWidth).toBe("0");
      expect(viewport.style.overflow).toBe("visible");
      expect(viewport.style.contain).toBe("layout");
    });
    controls.forEach((control) => {
      expect(control.style.width).toBe("");
      const scale = Number(control.style.transform.match(/scale\(([^)]+)\)/)?.[1]);
      expect(scale).toBeLessThanOrEqual(0.86);
      expect(control.style.transformOrigin).toBe("left top");
    });
    sliders.forEach((slider) => {
      expect(slider.style.width).toBe("");
      expect(slider.style.transform).toBe("");
    });
    expect(screen.getByText("tearing").closest('[data-testid="steam-scaling-slider-viewport"]')).toBeNull();
  });

  it("indents native scaling titles without changing unrelated controls", () => {
    const ScalingMode = () => (
      <div>
        <div id="scaling-mode-label">Modo de escalado</div>
        <div role="slider" aria-labelledby="scaling-mode-label">Auto</div>
      </div>
    );
    const Tearing = () => (
      <div>
        <div id="tearing-label">Permitir desgarro</div>
        <div role="slider" aria-labelledby="tearing-label">Off</div>
      </div>
    );
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [
        { id: "scalingMode", Component: ScalingMode },
        { id: "allowTearing", Component: Tearing },
      ],
    });

    render(<SteamPerformanceCard />);

    expect(screen.getByText("Modo de escalado").style.paddingInline).toBe("8px");
    expect(screen.getByText("Modo de escalado").style.boxSizing).toBe("border-box");
    expect(screen.getByText("Permitir desgarro").style.paddingInline).toBe("");
  });

  it("suppresses only Steam's separator below the reset row", () => {
    const Reset = () => (
      <div className="Panel Focusable" data-testid="native-reset-panel">
        <button type="button">Restablecer predeterminado</button>
      </div>
    );
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [{ id: "reset", Component: Reset }],
    });

    render(<SteamPerformanceCard />);

    const resetWrapper = screen.getByTestId("native-reset-panel")
      .closest("[data-pdc-steam-reset]");
    expect(resetWrapper).toBeTruthy();
    expect(resetWrapper?.querySelector("style")?.textContent)
      .toContain("[data-pdc-steam-reset] .Panel.Focusable::after");
  });

  it("shows synchronization as visible announced text", () => {
    surface.useSurface.mockReturnValue({ status: "ready", rows: [] });

    render(<SteamPerformanceCard />);

    expect(screen.getByText("steam.performance.title")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("steam.performance.synced");
  });

  it("shows an honest loading state before Steam discovery finishes", () => {
    surface.useSurface.mockReturnValue({ status: "loading", rows: [] });

    render(<SteamPerformanceCard />);

    expect(screen.getByRole("status").textContent).toContain("steam.performance.loading");
    expect(screen.queryByTestId("native-row")).toBeNull();
  });

  it("shows the unavailable state without inventing controls", () => {
    surface.useSurface.mockReturnValue({ status: "unavailable", rows: [] });

    render(<SteamPerformanceCard />);

    expect(screen.getByRole("status").textContent).toContain("steam.performance.unavailable");
    expect(screen.queryByTestId("native-row")).toBeNull();
  });

  it("keeps healthy inline controls mounted if one Steam control throws", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const Broken = () => {
      throw new Error("Steam component changed");
    };
    const Healthy = () => <div data-testid="native-row">tearing</div>;
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [
        { id: "vrr", Component: Broken },
        { id: "allowTearing", Component: Healthy },
      ],
    });

    render(<SteamPerformanceCard />);

    expect(screen.getByTestId("native-row").textContent).toBe("tearing");
    expect(screen.getByRole("status").textContent).toContain("steam.performance.partial");
  });

  it("recovers a failed inline control when Steam publishes a new generation", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const Broken = () => {
      throw new Error("Old Steam component");
    };
    const Recovered = () => <div data-testid="native-row">refresh-recovered</div>;
    let current: SteamPerformanceSurfaceState = {
      status: "ready",
      rows: [{ id: "refreshRate", Component: Broken }],
    };
    surface.useSurface.mockImplementation(() => current);
    const view = render(<SteamPerformanceCard />);
    expect(screen.getByRole("status").textContent).toContain("steam.performance.partial");

    current = {
      status: "ready",
      rows: [{ id: "refreshRate", Component: Recovered }],
    };
    view.rerender(<SteamPerformanceCard />);

    expect(screen.getByTestId("native-row").textContent).toBe("refresh-recovered");
    expect(screen.getByRole("status").textContent).toContain("steam.performance.synced");
  });

  it("retries one transient native render failure inline", () => {
    vi.useFakeTimers();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let hydrated = false;
    const Transient = () => {
      if (!hydrated) throw new Error("Steam is still hydrating");
      return <div data-testid="native-row">recovered</div>;
    };
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [{ id: "refreshRate", Component: Transient }],
    });

    render(<SteamPerformanceCard />);
    expect(screen.getByRole("status").textContent).toContain("steam.performance.partial");

    hydrated = true;
    act(() => { vi.advanceTimersByTime(2000); });

    expect(screen.getByTestId("native-row").textContent).toBe("recovered");
    expect(screen.getByRole("status").textContent).toContain("steam.performance.synced");
  });

  it("renews the retry budget after the same inline control recovers", () => {
    vi.useFakeTimers();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let failing = true;
    const Intermittent = () => {
      if (failing) throw new Error("Steam control is temporarily unavailable");
      return <div data-testid="native-row">stable</div>;
    };
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [{ id: "refreshRate", Component: Intermittent }],
    });
    const view = render(<SteamPerformanceCard />);

    failing = false;
    act(() => { vi.advanceTimersByTime(2000); });
    expect(screen.getByTestId("native-row").textContent).toBe("stable");

    failing = true;
    view.rerender(<SteamPerformanceCard />);
    expect(screen.getByRole("status").textContent).toContain("steam.performance.partial");

    failing = false;
    act(() => { vi.advanceTimersByTime(2000); });
    expect(screen.getByTestId("native-row").textContent).toBe("stable");
  });

  it("hides a group while its only native control is failed", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const Broken = () => {
      throw new Error("Steam display control changed");
    };
    const Healthy = () => <div data-testid="native-row">vrr</div>;
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [
        { id: "refreshRate", Component: Broken },
        { id: "vrr", Component: Healthy },
      ],
    });

    render(<SteamPerformanceCard />);

    expect(screen.queryByRole("group", { name: "steam.performance.group.display" })).toBeNull();
    expect(within(screen.getByRole("group", { name: "steam.performance.group.fluidity" }))
      .getByTestId("native-row").textContent).toBe("vrr");
  });
});
