// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LOCAL_THEME_CATALOG } from "../themes/catalog";
import { deriveThemeCards } from "../themes/state";
import type { ThemesController } from "../themes/useThemes";

const mocks = vi.hoisted(() => ({
  controller: null as ThemesController | null,
  external: vi.fn(),
}));

vi.mock("@decky/ui", () => ({
  ModalRoot: ({ children, onCancel }: { children?: ReactNode; onCancel?: () => void }) => (
    <div>{children}<button aria-label="modal-cancel" onClick={onCancel}>cancel</button></div>
  ),
  Focusable: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ButtonItem: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
  Navigation: { NavigateToExternalWeb: mocks.external },
  showModal: vi.fn(),
}));
vi.mock("../themes/useThemes", () => ({ useThemes: () => mocks.controller }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./ThemePatchControl", () => ({
  ThemePatchControl: ({ patch, onChange }: { patch: { name: string }; onChange: (value: string) => void }) => (
    <button onClick={() => onChange("No")}>{patch.name}</button>
  ),
}));
vi.mock("./ConfirmDialog", () => ({ ConfirmDialog: () => null }));
vi.mock("./FocusRoot", () => ({
  FocusRoot: ({ children }: { children?: ReactNode }) => <div data-testid="focus-root">{children}</div>,
}));

import { ThemeDetailsModal } from "./ThemeDetailsModal";

function readyController(installed: boolean): ThemesController {
  const snapshot = {
    status: "ready" as const,
    backendVersion: 9,
    themes: installed ? [{
      id: "Hooandee Obsidian Bloom",
      name: "Hooandee Obsidian Bloom",
      displayName: "Obsidian Bloom",
      version: "0.1.0",
      author: "Hooandee",
      enabled: false,
      patches: [
        { name: "Cover grid columns", defaultValue: "4", value: "4", options: ["4", "5"], type: "dropdown" as const, rawType: "dropdown" },
        { name: "Animated transitions", defaultValue: "Yes", value: "Yes", options: ["No", "Yes"], type: "checkbox" as const, rawType: "checkbox" },
      ],
    }] : [],
  };
  return {
    loading: false,
    snapshot,
    cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
    operation: null,
    error: null,
    refresh: vi.fn(async () => {}),
    install: vi.fn(async () => true),
    activate: vi.fn(async () => true),
    setPatch: vi.fn(async () => true),
  };
}

describe("ThemeDetailsModal", () => {
  afterEach(() => {
    cleanup();
    mocks.controller = null;
    vi.clearAllMocks();
  });

  it("connects the fullscreen modal cancel action to Decky's injected close callback", () => {
    const closeModal = vi.fn();
    mocks.controller = readyController(false);
    render(<ThemeDetailsModal themeId="hooandee-gallery" closeModal={closeModal} />);

    fireEvent.click(screen.getByRole("button", { name: "modal-cancel" }));
    expect(closeModal).toHaveBeenCalledOnce();
  });

  it("does not present an install state before CSS Loader detection settles", () => {
    mocks.controller = { ...readyController(false), loading: true };
    render(<ThemeDetailsModal themeId="hooandee-gallery" />);

    expect(screen.getByText("themes.loading")).toBeTruthy();
    expect(screen.queryByText("themes.install.unavailable")).toBeNull();
  });

  it("renders live CSS Loader patches in groups and delegates verified mutations", () => {
    mocks.controller = readyController(true);
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    expect(screen.getByText("Obsidian Bloom")).toBeTruthy();
    expect(screen.getByTestId("focus-root")).toBeTruthy();
    expect(screen.getByText("themes.group.grid")).toBeTruthy();
    expect(screen.getByText("themes.group.animations")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "themes.action.activate" }));
    expect(mocks.controller?.activate).toHaveBeenCalledWith("hooandee-obsidian-bloom");
    fireEvent.click(screen.getByRole("button", { name: "Animated transitions" }));
    expect(mocks.controller?.setPatch).toHaveBeenCalledWith(
      "hooandee-obsidian-bloom",
      "Animated transitions",
      "No",
    );
  });

  it("does not pretend an unverified install source exists", () => {
    mocks.controller = readyController(false);
    render(<ThemeDetailsModal themeId="hooandee-gallery" />);

    expect(screen.getByText("themes.install.unavailable")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "themes.action.activate" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "themes.action.project" }));
    expect(mocks.external).toHaveBeenCalledWith("https://github.com/Hooandee/hooandee-themes");
  });
});
