// @vitest-environment happy-dom
import { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

const fanFixture = vi.hoisted(() => ({ desktop: true }));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, ...props }: { children?: ReactNode } & HTMLAttributes<HTMLDivElement>) => (
    <div {...props}>{children}</div>
  ),
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));

vi.mock("../api", () => ({}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "desktop.fan.channel.system": "Sistema",
      "desktop.fan.channel.gpu": "Gráfica",
      "desktop.fan.editable": "Curva editable",
      "desktop.fan.max": "Máx.",
    })[key] ?? key,
  }),
}));

vi.mock("../fans/useFanState", () => ({
  useFanState: () => ({
    state: fanFixture.desktop ? {
      supported: true,
      desktop: true,
      device_key: "steam_machine",
      fans: [
        { label: "System Fan", rpm: 537, percent: null, max_rpm: 1800, channel: "system" },
        { label: "GPU Fan", rpm: 822, percent: 30, max_rpm: 4900, channel: "gpu" },
      ],
      temps: [],
    } : {
      supported: true,
      fans: [{ label: "Handheld Fan", rpm: 2400, percent: 35, max_rpm: 5000 }],
      temps: [],
    },
    fanHistory: { "System Fan": [537], "GPU Fan": [822] },
  }),
}));

vi.mock("../components/FanChip", () => ({
  FanChip: ({ label, rpm, maxRpm, layout }: { label: string; rpm: number | null; maxRpm?: number | null; layout?: string }) => (
    <div data-testid={`fan-${label}`} data-layout={layout} data-max-rpm={maxRpm}>{rpm}</div>
  ),
}));

import { getBlockDef } from "../customize/blocks";
import { registerFanBlocks } from "./fanBlocks";

describe("desktop fan monitor", () => {
  afterEach(() => {
    fanFixture.desktop = true;
    cleanup();
  });

  it("keeps driver-only GPU telemetry out of the main RPM grid", () => {
    registerFanBlocks();
    const FanRpmBlock = getBlockDef("fanRpm")!.Component;

    render(<FanRpmBlock />);

    const systemFan = screen.getByTestId("fan-Sistema");
    expect(systemFan.textContent).toBe("537");
    expect(systemFan.dataset.layout).toBe("wide");
    expect(systemFan.dataset.maxRpm).toBe("1800");
    expect(screen.queryByTestId("fan-Gráfica")).toBeNull();
    expect(screen.queryByText("Máx.")).toBeNull();
    expect(screen.queryByText("Curva editable")).toBeNull();
    expect(systemFan.parentElement?.parentElement?.style.gridTemplateColumns).toBe("minmax(0, 1fr)");
  });

  it("keeps the established handheld RPM scale independent of desktop limits", () => {
    fanFixture.desktop = false;
    registerFanBlocks();
    const FanRpmBlock = getBlockDef("fanRpm")!.Component;

    render(<FanRpmBlock />);

    expect(screen.getByTestId("fan-fans.fan").dataset.maxRpm).toBeUndefined();
  });
});
