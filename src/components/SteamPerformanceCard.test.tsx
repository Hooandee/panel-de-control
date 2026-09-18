// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const surface = vi.hoisted(() => ({
  useSurface: vi.fn(),
}));

const decky = vi.hoisted(() => ({
  modal: null as ReactNode | null,
}));

vi.mock("../steam/useSteamPerformanceSurface", () => ({
  useSteamPerformanceSurface: surface.useSurface,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("./Collapsible", () => ({
  Collapsible: ({ children, summary, title }: {
    children?: ReactNode;
    summary?: ReactNode;
    title?: ReactNode;
  }) => (
    <section>
      <h2>{title}</h2>
      <div>{summary}</div>
      {children}
    </section>
  ),
}));

vi.mock("./FocusRoot", () => ({
  FocusRoot: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, onClick, noFocusRing: _noFocusRing, ...props }: {
    children?: ReactNode;
    onActivate?: () => void;
    onClick?: () => void;
    noFocusRing?: boolean;
    [key: string]: unknown;
  }) => (
    <button {...props} onClick={onClick ?? onActivate}>{children}</button>
  ),
  ModalRoot: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  showModal: (modal: ReactNode) => {
    decky.modal = modal;
  },
}));

import { SteamPerformanceCard } from "./SteamPerformanceCard";
import { SteamPerformanceModal } from "./SteamPerformanceModal";
import type { SteamPerformanceSurfaceState } from "../steam/useSteamPerformanceSurface";

function openDetail(): void {
  render(<SteamPerformanceCard />);
  expect(screen.queryByTestId("native-row")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "steam.performance.open" }));
  const modal = decky.modal;
  expect(modal).not.toBeNull();
  cleanup();
  render(modal);
}

describe("SteamPerformanceCard", () => {
  beforeEach(() => {
    surface.useSurface.mockReset();
    decky.modal = null;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("keeps synchronization visible as a compact indicator without competing with the summary", () => {
    surface.useSurface.mockReturnValue({ status: "ready", rows: [] });

    render(<SteamPerformanceCard />);

    const card = screen.getByRole("button", { name: "steam.performance.open" });
    expect(within(card).getByText("steam.performance.cardSummary")).toBeTruthy();
    expect(within(card).queryByText("steam.performance.synced")).toBeNull();
    expect(within(card).getByLabelText("steam.performance.synced")).toBeTruthy();
  });

  it("keeps native controls out of the compact card and opens them in a dedicated view", () => {
    const Refresh = () => <div data-testid="native-row">refresh</div>;
    const Vrr = () => <div data-testid="native-row">vrr</div>;
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [
        { id: "refreshRate", Component: Refresh },
        { id: "vrr", Component: Vrr },
      ],
    });

    openDetail();

    expect(screen.getByRole("heading", { name: "steam.performance.detailTitle" })).toBeTruthy();
    expect(screen.getAllByTestId("native-row").map((row) => row.textContent)).toEqual([
      "refresh",
      "vrr",
    ]);
  });

  it("groups the dedicated controls into display, fluidity and scaling", () => {
    const row = (text: string) => () => <div data-testid="native-row">{text}</div>;
    surface.useSurface.mockReturnValue({
      status: "ready",
      rows: [
        { id: "profile", Component: row("profile") },
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

    openDetail();

    expect(within(screen.getByRole("group", { name: "steam.performance.group.display" }))
      .getAllByTestId("native-row").map((item) => item.textContent))
      .toEqual(["profile", "frame", "limit"]);
    expect(within(screen.getByRole("group", { name: "steam.performance.group.fluidity" }))
      .getAllByTestId("native-row").map((item) => item.textContent))
      .toEqual(["shading", "vrr", "tearing"]);
    expect(within(screen.getByRole("group", { name: "steam.performance.group.scaling" }))
      .getAllByTestId("native-row").map((item) => item.textContent))
      .toEqual(["mode", "filter", "sharpness"]);
    const rows = screen.getAllByTestId("native-row");
    expect(rows[rows.length - 1]?.textContent).toBe("reset");
  });

  it("shows the unavailable state without inventing summary values", () => {
    surface.useSurface.mockReturnValue({ status: "unavailable", rows: [] });

    openDetail();

    expect(screen.getByText("steam.performance.unavailable")).toBeTruthy();
    expect(screen.queryByTestId("native-row")).toBeNull();
  });

  it("keeps healthy modal controls mounted if one Steam control throws", () => {
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

    openDetail();

    expect(screen.getByTestId("native-row").textContent).toBe("tearing");
    expect(screen.getByText("steam.performance.partial")).toBeTruthy();
    expect(screen.queryByText("steam.performance.synced")).toBeNull();
  });

  it("recovers a failed modal control when Steam publishes a new generation", () => {
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

    render(<SteamPerformanceCard />);
    fireEvent.click(screen.getByRole("button", { name: "steam.performance.open" }));
    const modal = decky.modal;
    cleanup();
    const view = render(modal);
    expect(screen.getByText("steam.performance.partial")).toBeTruthy();

    current = {
      status: "ready",
      rows: [{ id: "refreshRate", Component: Recovered }],
    };
    view.rerender(<SteamPerformanceModal />);

    expect(screen.getByTestId("native-row").textContent).toBe("refresh-recovered");
    expect(screen.getByText("steam.performance.synced")).toBeTruthy();
  });

  it("retries one transient native render failure in the dedicated view", () => {
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

    openDetail();
    expect(screen.getByText("steam.performance.partial")).toBeTruthy();

    hydrated = true;
    act(() => { vi.advanceTimersByTime(2000); });

    expect(screen.getByTestId("native-row").textContent).toBe("recovered");
    expect(screen.getByText("steam.performance.synced")).toBeTruthy();
  });
});
