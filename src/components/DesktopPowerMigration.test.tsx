// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { type HTMLAttributes, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ retry: vi.fn() }));

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick, ...props }: { children?: ReactNode; onClick?: () => void } & HTMLAttributes<HTMLButtonElement>) => (
    <button type="button" onClick={onClick} {...props}>{children}</button>
  ),
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SliderField: () => <div role="slider" />,
}));

vi.mock("../desktop/useDesktop", () => ({
  useDesktopState: () => ({
    state: {
      enabled: false,
      automatic: true,
      manual_enabled: false,
      migration_pending: true,
      migration_failure: "surface unavailable",
      power: { supported: false },
      telemetry: null,
      cpu: null,
    },
    error: false,
    retryMigration: mocks.retry,
    applyMode: vi.fn(),
    applyLimits: vi.fn(),
  }),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "desktop.migration.title": "Recuperando el control anterior",
      "desktop.migration.desc": "No cambiaremos la potencia hasta terminar.",
      "desktop.recovery.retry": "Reintentar ahora",
    } as Record<string, string>)[key] ?? key,
  }),
}));

import { DesktopPowerCard } from "./DesktopPowerCard";

describe("DesktopPowerCard migration recovery", () => {
  afterEach(cleanup);

  it("replaces power controls with an explicit retry while migration is pending", () => {
    render(<DesktopPowerCard />);

    expect(screen.getByText("Recuperando el control anterior")).toBeTruthy();
    expect(screen.queryByTitle("desktop.mode.free")).toBeNull();
    fireEvent.click(screen.getByText("Reintentar ahora"));
    expect(mocks.retry).toHaveBeenCalledOnce();
  });
});
