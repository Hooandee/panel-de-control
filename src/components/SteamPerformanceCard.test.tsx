// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
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

vi.mock("./Collapsible", () => ({
  Collapsible: ({ title, summary, children }: {
    title: string;
    summary: ReactNode;
    children: ReactNode;
  }) => (
    <section>
      <h2>{title}</h2>
      <div>{summary}</div>
      {children}
    </section>
  ),
}));

import { SteamPerformanceCard } from "./SteamPerformanceCard";
import type { SteamPerformanceSurfaceState } from "../steam/useSteamPerformanceSurface";

describe("SteamPerformanceCard", () => {
  beforeEach(() => {
    surface.useSurface.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders Steam's native controls in the selected order", () => {
    const First = () => <div data-testid="native-row">refresh</div>;
    const Second = () => <div data-testid="native-row">vrr</div>;
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [
        { id: "refreshRate", Component: First },
        { id: "vrr", Component: Second },
      ],
    });

    render(<SteamPerformanceCard />);

    expect(screen.getByRole("heading", { name: "steam.performance.title" })).toBeTruthy();
    expect(screen.getAllByText("steam.performance.synced")).toHaveLength(2);
    expect(screen.getAllByTestId("native-row").map((row) => row.textContent)).toEqual([
      "refresh",
      "vrr",
    ]);
  });

  it("shows an honest unavailable state instead of empty controls", () => {
    surface.useSurface.mockReturnValue({ status: "unavailable", rows: [] });

    render(<SteamPerformanceCard />);

    expect(screen.getAllByText("steam.performance.unavailable")).toHaveLength(2);
    expect(screen.getByText("steam.performance.desc")).toBeTruthy();
    expect(screen.queryByTestId("native-row")).toBeNull();
  });

  it("keeps healthy native controls mounted if one Steam control throws", () => {
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
    expect(screen.getAllByText("steam.performance.partial")).toHaveLength(2);
    expect(screen.queryByText("steam.performance.synced")).toBeNull();
  });

  it("recovers a failed row when Steam publishes a new component generation", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const Broken = () => {
      throw new Error("Old Steam component");
    };
    const Recovered = () => <div data-testid="native-row">refresh-recovered</div>;
    let current: SteamPerformanceSurfaceState = {
      status: "ready" as const,
      rows: [{ id: "refreshRate" as const, Component: Broken }],
    };
    surface.useSurface.mockImplementation(() => current);

    const view = render(<SteamPerformanceCard />);
    expect(screen.getAllByText("steam.performance.partial")).toHaveLength(2);

    current = {
      status: "ready",
      rows: [{ id: "refreshRate", Component: Recovered }],
    };
    view.rerender(<SteamPerformanceCard />);

    expect(screen.getByTestId("native-row").textContent).toBe("refresh-recovered");
    expect(screen.getAllByText("steam.performance.synced")).toHaveLength(2);
  });

  it("retries one transient native render failure", () => {
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
    expect(screen.getAllByText("steam.performance.partial")).toHaveLength(2);

    hydrated = true;
    act(() => { vi.advanceTimersByTime(2000); });

    expect(screen.getByTestId("native-row").textContent).toBe("recovered");
    expect(screen.getAllByText("steam.performance.synced")).toHaveLength(2);
  });
});
