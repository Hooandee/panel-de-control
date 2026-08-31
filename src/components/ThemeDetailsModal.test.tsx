// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ThemesController } from "../themes/useThemes";

const mocks = vi.hoisted(() => ({ controller: null as ThemesController | null, navigate: vi.fn(), showModal: vi.fn() }));
vi.mock("@decky/ui", () => ({
  ModalRoot: ({ children, onCancel }: { children?: ReactNode; onCancel?: () => void }) => (
    <div>{children}<button aria-label="modal-cancel" onClick={onCancel}>cancel</button></div>
  ),
  Focusable: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ButtonItem: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
  Navigation: { Navigate: mocks.navigate },
  showModal: mocks.showModal,
}));
vi.mock("../themes/useThemes", () => ({ useThemes: () => mocks.controller }));
vi.mock("../i18n", () => ({ useI18n: () => ({ lang: "en", t: (key: string) => key }) }));
vi.mock("./ThemePatchControl", () => ({
  ThemePatchControl: ({ patch, disabled, onChange }: { patch: { name: string }; disabled?: boolean; onChange(value: string): void }) => (
    <button disabled={disabled} onClick={() => onChange("No")}>{patch.name}</button>
  ),
}));
vi.mock("./FocusRoot", () => ({ FocusRoot: ({ children }: { children?: ReactNode }) => <div>{children}</div> }));

import { ThemeDetailsModal } from "./ThemeDetailsModal";

function controller(overrides: Partial<ThemesController> = {}): ThemesController {
  const release = {
    catalogId: "example-theme", cssLoaderName: "Example Theme", publishedVersion: "1.2.3",
    displayName: { es: "Tema", en: "Example Theme", it: "Tema" },
    description: { es: "Descripcion", en: "Description", it: "Descrizione" },
    author: "Example Author", tags: ["dark", "compact"], notes: {}, compatibility: "compatible" as const,
  };
  return {
    loading: false,
    refreshing: false,
    snapshot: { status: "missing", themes: [] },
    cards: [{
      id: "example-theme", release, installed: false, active: false,
      targetVersion: "1.2.3", installable: true, versionRelation: "not-installed", updateAvailable: false,
    }],
    operation: null,
    recoveryBlocked: false,
    error: null,
    publication: { status: "published", checkedAt: 10, themes: [release] },
    refresh: vi.fn(async () => {}),
    refreshPublication: vi.fn(async () => {}),
    install: vi.fn(async () => true),
    activate: vi.fn(async () => true),
    deactivate: vi.fn(async () => true),
    setPatch: vi.fn(async () => true),
    ...overrides,
  };
}

describe("ThemeDetailsModal", () => {
  afterEach(() => { cleanup(); mocks.controller = null; vi.clearAllMocks(); });

  it("keeps published details visible and offers Decky Store when CSS Loader is missing", () => {
    mocks.controller = controller();
    render(<ThemeDetailsModal themeId="example-theme" />);

    expect(screen.getByText("Example Theme")).toBeTruthy();
    expect(screen.getByText("Description")).toBeTruthy();
    expect(screen.getByText("themes.cssLoader.missing")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.cssLoader.openStore" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/decky/store");
  });

  it("shows metadata and omits notes when the published notes object is empty", () => {
    mocks.controller = controller();
    render(<ThemeDetailsModal themeId="example-theme" />);

    expect(screen.getByText("Example Author")).toBeTruthy();
    expect(screen.getByText("#dark")).toBeTruthy();
    expect(screen.getByText("#compact")).toBeTruthy();
    expect(screen.queryByText("themes.remote.notes")).toBeNull();
  });

  it("labels cached metadata as offline and retries publication", () => {
    const refreshPublication = vi.fn(async () => {});
    const base = controller();
    mocks.controller = controller({
      publication: { status: "cached", checkedAt: 10, themes: [base.cards[0].release], code: "offline", retryable: true },
      refreshPublication,
    });
    render(<ThemeDetailsModal themeId="example-theme" />);

    expect(screen.getByText("themes.remote.cached")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.remote.retry" }));
    expect(refreshPublication).toHaveBeenCalledOnce();
  });

  it("confirms a remote install using only the exact version", () => {
    const install = vi.fn(async () => true);
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
      install,
    });
    render(<ThemeDetailsModal themeId="example-theme" />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.install" }));
    fireEvent.click(screen.getByRole("button", { name: "themes.install.confirm.ok" }));
    expect(install).toHaveBeenCalledWith("example-theme", { version: "1.2.3" });
  });

  it("renders installed patches and delegates activation/readback mutations", () => {
    const activate = vi.fn(async () => true);
    const setPatch = vi.fn(async () => true);
    const base = controller();
    const installedTheme = {
      id: "Example Theme", name: "Example Theme", displayName: "Example Theme", version: "1.2.3",
      author: "Example Author", enabled: false, patches: [{
        name: "Motion", defaultValue: "Yes", value: "Yes", options: ["No", "Yes"],
        type: "checkbox" as const, rawType: "checkbox",
      }],
    };
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [installedTheme] },
      cards: [{ ...base.cards[0], installed: true, installedVersion: "1.2.3", cssLoaderTheme: installedTheme, versionRelation: "current" }],
      activate,
      setPatch,
    });
    render(<ThemeDetailsModal themeId="example-theme" />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.activate" }));
    fireEvent.click(screen.getByRole("button", { name: "Motion" }));
    expect(activate).toHaveBeenCalledWith("example-theme");
    expect(setPatch).toHaveBeenCalledWith("example-theme", "Motion", "No");
  });

  it("uses Panel tokens instead of theme-owned chrome variables", () => {
    mocks.controller = controller();
    render(<ThemeDetailsModal themeId="example-theme" />);
    const css = screen.getByTestId("theme-settings-content").querySelector("style")?.textContent ?? "";
    expect(css).not.toContain("--hdg-");
    expect(css).toContain("[data-pdc-theme-settings]");
  });
});
