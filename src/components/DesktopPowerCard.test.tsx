// @vitest-environment happy-dom
import { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onActivate, noFocusRing: _noFocusRing, ...props }: { children?: ReactNode; onActivate?: () => void; noFocusRing?: boolean } & HTMLAttributes<HTMLDivElement>) => (
    <div data-focusable={onActivate ? "true" : undefined} {...props}>{children}</div>
  ),
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SliderField: () => <div role="slider" />,
}));

vi.mock("../desktop/useDesktop", () => ({
  useDesktopState: () => ({
    state: {
      enabled: true,
      automatic: true,
      manual_enabled: false,
      power: {
        supported: true,
        cpu_supported: false,
        cpu_policy_supported: true,
        cpu_policy: "balanced",
        gpu_supported: true,
        mode: "free",
        cpu_w: null,
        gpu_w: 110,
        cpu_min_w: 0,
        cpu_max_w: 0,
        gpu_min_w: 55,
        gpu_max_w: 110,
        presets: {},
      },
      telemetry: {
        cpu_watts: null,
        gpu_watts: 18,
        gpu_busy: 12,
        gpu_clock_mhz: 809,
        gpu_clock_max_mhz: 2500,
        vram_used_mb: 1536,
        vram_total_mb: 8192,
      },
      cpu: null,
    },
    applyMode: vi.fn(),
    applyLimits: vi.fn(),
  }),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, number>) => ({
      "desktop.cpu.policy.balanced": "Equilibrada",
      "desktop.cpu.short": "CPU",
      "desktop.gpu.limit": "Límite gráfico",
      "desktop.power.available": "Límite gráfico",
      "desktop.power.range": `Rango confirmado: ${values?.min}–${values?.max} W`,
      "desktop.metric.unavailable": "No disponible",
    })[key] ?? key,
  }),
}));

import { DesktopPowerCard } from "./DesktopPowerCard";

describe("DesktopPowerCard desktop hierarchy", () => {
  afterEach(cleanup);

  it("keeps CPU policy outside the narrow hero and after the power slider", () => {
    render(<DesktopPowerCard />);

    const hero = screen.getByTestId("desktop-power-hero");
    const slider = screen.getByTestId("desktop-slider-viewport");
    const policy = screen.getByTestId("desktop-cpu-policy");

    expect(hero.contains(policy)).toBe(false);
    expect(policy.textContent).toBe("CPU · Equilibrada");
    expect(slider.compareDocumentPosition(policy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps desktop mode pills compact within their declared height", () => {
    render(<DesktopPowerCard />);

    const free = screen.getByTitle("desktop.mode.free");
    expect(free.style.boxSizing).toBe("border-box");
    expect(free.style.height).toBe("32px");
    expect(free.style.minHeight).toBe("0px");
    expect(free.style.padding).toBe("4px 5px");
  });

  it("uses the short graphics-limit label throughout the narrow card", () => {
    render(<DesktopPowerCard />);

    expect(screen.getAllByText("Límite gráfico")).toHaveLength(2);
    expect(document.body.textContent).not.toContain("Límite de potencia de la gráfica");
  });

  it("uses one compact focus anchor for all telemetry below the power slider", () => {
    render(<DesktopPowerCard />);

    const slider = screen.getByTestId("desktop-slider-viewport");
    const metrics = screen.getByTestId("desktop-power-metrics");
    const gpuDraw = screen.getByTestId("desktop-metric-gpu-draw");

    expect(metrics.dataset.focusable).toBe("true");
    expect(metrics.getAttribute("role")).toBe("group");
    expect(slider.compareDocumentPosition(metrics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(gpuDraw.style.justifyContent).toBe("flex-start");
    expect(gpuDraw.style.gap).toBe("2px");
    expect(gpuDraw.style.boxSizing).toBe("border-box");
  });
});
