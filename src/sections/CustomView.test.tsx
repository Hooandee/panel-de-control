// @vitest-environment happy-dom
import { FC } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const context = vi.hoisted(() => ({
  desktop: false,
  blocks: ["autoTdp", "desktopPower"],
  monitorOnly: false,
}));

vi.mock("@decky/api", () => ({ callable: () => () => Promise.resolve() }));
vi.mock("../theme", () => ({ theme: { space: { card: 6 } } }));
vi.mock("../customize/viewStore", () => ({
  useViews: () => [{
    id: "mixed",
    name: "Mixed",
    icon: "star",
    blocks: context.blocks,
  }],
}));
vi.mock("../customize/modules", () => ({ useModules: () => new Set<string>() }));
vi.mock("../desktop/useDesktop", () => ({
  useDesktopState: () => ({ state: { enabled: context.desktop } }),
}));
vi.mock("../tdp/potenciaContext", () => ({
  usePotencia: () => ({
    monitorOnly: context.monitorOnly,
    tdp: { supported: true },
    onReactivate: () => {},
  }),
}));
vi.mock("../components/TdpMonitorNotice", () => ({
  TdpMonitorNotice: () => <div>tdp-monitor-fallback</div>,
}));
vi.mock("./providerMounts", () => ({
  PotenciaProviderMount: ({
    children,
    showProfileSelector,
  }: {
    children: React.ReactNode;
    showProfileSelector?: boolean;
  }) => (
    <div data-testid="power-provider">
      {showProfileSelector && <div>profile-selector</div>}
      {children}
    </div>
  ),
  SECTION_PROVIDERS: {
    power: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="power-provider">{children}</div>
    ),
  },
}));

import { registerBlock } from "../customize/blocks";
import { CustomView } from "./CustomView";

const AutoTdp: FC = () => <div>handheld-auto-tdp</div>;
const DesktopPower: FC = () => <div>desktop-power</div>;
const SteamPerformance: FC = () => <div>steam-performance</div>;
registerBlock("autoTdp", { sectionId: "power", Component: AutoTdp });
registerBlock("desktopPower", { sectionId: "power", Component: DesktopPower });
registerBlock("steamPerformance", { sectionId: "power", Component: SteamPerformance });

describe("CustomView machine-specific blocks", () => {
  afterEach(() => {
    context.desktop = false;
    context.blocks = ["autoTdp", "desktopPower"];
    context.monitorOnly = false;
    cleanup();
  });

  it("hides persisted handheld blocks in desktop mode", () => {
    context.desktop = true;
    render(<CustomView viewId="mixed" />);

    expect(screen.getByText("desktop-power")).toBeTruthy();
    expect(screen.queryByText("handheld-auto-tdp")).toBeNull();
    expect(screen.queryByText("profile-selector")).toBeNull();
  });

  it("hides persisted desktop blocks in handheld mode", () => {
    render(<CustomView viewId="mixed" />);

    expect(screen.getByText("handheld-auto-tdp")).toBeTruthy();
    expect(screen.queryByText("desktop-power")).toBeNull();
    expect(screen.getByTestId("power-provider")).toBeTruthy();
  });

  it("mounts the power provider for Steam's shared global and game scope", () => {
    context.blocks = ["steamPerformance"];

    render(<CustomView viewId="mixed" />);

    expect(screen.getByText("steam-performance")).toBeTruthy();
    expect(screen.getByTestId("power-provider")).toBeTruthy();
    expect(screen.getByText("profile-selector")).toBeTruthy();
  });

  it("does not ask to reactivate TDP for a Steam-only view", () => {
    context.blocks = ["steamPerformance"];
    context.monitorOnly = true;

    render(<CustomView viewId="mixed" />);

    expect(screen.queryByText("tdp-monitor-fallback")).toBeNull();
    expect(screen.getByText("steam-performance")).toBeTruthy();
  });

  it("keeps the reactivation notice for an Auto-TDP-only view", () => {
    context.blocks = ["autoTdp"];
    context.monitorOnly = true;

    render(<CustomView viewId="mixed" />);

    expect(screen.getByText("tdp-monitor-fallback")).toBeTruthy();
    expect(screen.getByText("handheld-auto-tdp")).toBeTruthy();
  });
});
