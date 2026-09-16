// @vitest-environment happy-dom
import { ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const qamState = vi.hoisted(() => ({
  snapshot: {
    initialized: true,
    applied: true,
    restartRequired: false,
    reason: "ready",
    activeTokens: ["pdc:home"],
    inventory: [],
  },
}));

const restartLoader = vi.hoisted(() => vi.fn(async () => {}));
const closeSideMenus = vi.hoisted(() => vi.fn());
const openQamCustomize = vi.hoisted(() => vi.fn());

vi.mock("@decky/ui", () => ({
  Navigation: { CloseSideMenus: closeSideMenus },
  ButtonItem: ({ children, description, onClick }: {
    children: ReactNode;
    description: ReactNode;
    onClick(): void;
  }) => <button onClick={onClick}>{children}<span>{description}</span></button>,
}));

vi.mock("../api", () => ({ restartLoader }));

vi.mock("../qam/runtime", () => ({
  getQamRuntimeSnapshot: () => qamState.snapshot,
  subscribeQamRuntime: () => () => {},
}));
vi.mock("./QamCustomizeModal", () => ({ openQamCustomizeModal: openQamCustomize }));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "settings.qamShortcut": "Configurar el QAM",
      "settings.qamShortcut.desc": "Elige qué entradas de Steam mostrar y qué vistas de Panel anclar.",
      "customize.qam.restart": "Recarga Decky para aplicar los cambios guardados.",
      "customize.qam.restartButton": "Recargar Decky",
      "customize.qam.unavailable": "No se pudo modificar el QAM. Panel sigue disponible dentro de Decky.",
    })[key] ?? key,
  }),
}));

import { QamShortcutSetting } from "./QamShortcutSetting";

describe("QamShortcutSetting", () => {
  beforeEach(() => {
    Object.assign(qamState.snapshot, {
      initialized: true,
      applied: true,
      restartRequired: false,
      reason: "ready",
    });
    openQamCustomize.mockClear();
    restartLoader.mockClear();
    closeSideMenus.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("opens the dedicated QAM editor instead of exposing a legacy toggle", () => {
    render(<QamShortcutSetting />);

    fireEvent.click(screen.getByText("Configurar el QAM"));

    expect(openQamCustomize).toHaveBeenCalledOnce();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("offers an explicit Decky restart while the applied state differs", () => {
    vi.useFakeTimers();
    Object.assign(qamState.snapshot, { applied: false, restartRequired: true });
    render(<QamShortcutSetting />);

    fireEvent.click(screen.getByText("Recargar Decky"));

    expect(closeSideMenus).toHaveBeenCalledOnce();
    expect(restartLoader).not.toHaveBeenCalled();
    vi.advanceTimersByTime(500);
    expect(restartLoader).toHaveBeenCalledOnce();
  });

  it("reports the standard Decky fallback when the private route is unavailable", () => {
    qamState.snapshot.applied = false;
    render(<QamShortcutSetting />);

    expect(screen.getByText(
      "No se pudo modificar el QAM. Panel sigue disponible dentro de Decky.",
    )).toBeTruthy();
  });
});
