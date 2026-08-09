// @vitest-environment happy-dom
import { FC } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const context = vi.hoisted(() => ({ desktop: false }));

vi.mock("@decky/api", () => ({ callable: () => () => Promise.resolve() }));
vi.mock("../theme", () => ({ theme: { space: { card: 6 } } }));
vi.mock("../customize/viewStore", () => ({
  useViews: () => [{
    id: "mixed",
    name: "Mixed",
    icon: "star",
    blocks: ["autoTdp", "desktopPower"],
  }],
}));
vi.mock("../customize/modules", () => ({ useModules: () => new Set<string>() }));
vi.mock("../desktop/useDesktop", () => ({
  useDesktopState: () => ({ state: { enabled: context.desktop } }),
}));
vi.mock("../tdp/potenciaContext", () => ({
  usePotencia: () => ({ monitorOnly: false, tdp: null, onReactivate: () => {} }),
}));
vi.mock("../components/TdpMonitorNotice", () => ({ TdpMonitorNotice: () => null }));
vi.mock("./providerMounts", () => ({ SECTION_PROVIDERS: {} }));

import { registerBlock } from "../customize/blocks";
import { CustomView } from "./CustomView";

const AutoTdp: FC = () => <div>handheld-auto-tdp</div>;
const DesktopPower: FC = () => <div>desktop-power</div>;
registerBlock("autoTdp", { sectionId: "power", Component: AutoTdp });
registerBlock("desktopPower", { sectionId: "power", Component: DesktopPower });

describe("CustomView machine-specific blocks", () => {
  afterEach(() => {
    context.desktop = false;
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
  });
});
