// @vitest-environment happy-dom
import { ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const qamState = vi.hoisted(() => ({
  snapshot: {
    enabled: true,
    initialized: true,
    appliedEnabled: true,
    registered: true,
    restartRequired: false,
  },
  setEnabled: vi.fn(),
}));

const restartLoader = vi.hoisted(() => vi.fn(async () => {}));
const closeSideMenus = vi.hoisted(() => vi.fn());

vi.mock("@decky/ui", () => ({
  Navigation: { CloseSideMenus: closeSideMenus },
  ToggleField: ({
    label,
    description,
    checked,
    onChange,
  }: {
    label: ReactNode;
    description: ReactNode;
    checked: boolean;
    onChange(next: boolean): void;
  }) => (
    <label>
      {label}
      <span>{description}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.currentTarget.checked)}
      />
    </label>
  ),
  ButtonItem: ({ children, description, onClick }: {
    children: ReactNode;
    description: ReactNode;
    onClick(): void;
  }) => <button onClick={onClick}>{children}<span>{description}</span></button>,
}));

vi.mock("../api", () => ({ restartLoader }));

vi.mock("../system/qamShortcut", () => ({
  getQamShortcutSnapshot: () => qamState.snapshot,
  setQamShortcutEnabled: qamState.setEnabled,
  subscribeQamShortcut: () => () => {},
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "settings.qamShortcut": "Acceso directo en el QAM",
      "settings.qamShortcut.desc": "Añade un icono opcional junto a Decky. Panel de Control siempre sigue disponible dentro de Decky.",
      "settings.qamShortcut.restart": "Reinicia Decky para aplicar el cambio.",
      "settings.qamShortcut.restartButton": "Reiniciar Decky",
      "settings.qamShortcut.fallback": "No se ha podido añadir el icono directo. Panel de Control sigue disponible dentro de Decky.",
    })[key] ?? key,
  }),
}));

import { QamShortcutSetting } from "./QamShortcutSetting";

describe("QamShortcutSetting", () => {
  beforeEach(() => {
    Object.assign(qamState.snapshot, {
      enabled: true,
      initialized: true,
      appliedEnabled: true,
      registered: true,
      restartRequired: false,
    });
    qamState.setEnabled.mockClear();
    restartLoader.mockClear();
    closeSideMenus.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("shows the enabled-by-default shortcut state", () => {
    render(<QamShortcutSetting />);

    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByText("Reiniciar Decky")).toBeNull();
  });

  it("persists the user's new preference", () => {
    render(<QamShortcutSetting />);

    fireEvent.click(screen.getByRole("checkbox"));

    expect(qamState.setEnabled).toHaveBeenCalledWith(false);
  });

  it("offers an explicit Decky restart while the applied state differs", () => {
    vi.useFakeTimers();
    qamState.snapshot.restartRequired = true;
    render(<QamShortcutSetting />);

    fireEvent.click(screen.getByText("Reiniciar Decky"));

    expect(closeSideMenus).toHaveBeenCalledOnce();
    expect(restartLoader).not.toHaveBeenCalled();
    vi.advanceTimersByTime(500);
    expect(restartLoader).toHaveBeenCalledOnce();
  });

  it("reports the standard Decky fallback when the private route is unavailable", () => {
    qamState.snapshot.registered = false;
    render(<QamShortcutSetting />);

    expect(screen.getByText(
      "No se ha podido añadir el icono directo. Panel de Control sigue disponible dentro de Decky.",
    )).toBeTruthy();
  });
});
