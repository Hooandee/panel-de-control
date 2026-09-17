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
registerBlock("steamPerformance", {
  sectionId: "power",
  providerSectionId: null,
  Component: SteamPerformance,
});

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
  });

  it("hides persisted desktop blocks in handheld mode", () => {
    render(<CustomView viewId="mixed" />);

    expect(screen.getByText("handheld-auto-tdp")).toBeTruthy();
    expect(screen.queryByText("desktop-power")).toBeNull();
    expect(screen.getByTestId("power-provider")).toBeTruthy();
  });

  it("does not tie Steam's independent block to the TDP monitor fallback", () => {
    context.blocks = ["steamPerformance"];
    context.monitorOnly = true;

    render(<CustomView viewId="mixed" />);

    expect(screen.getByText("steam-performance")).toBeTruthy();
    expect(screen.queryByText("tdp-monitor-fallback")).toBeNull();
    expect(screen.queryByTestId("power-provider")).toBeNull();
  });
});
