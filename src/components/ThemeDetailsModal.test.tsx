// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ThemesController } from "../themes/useThemes";

const mocks = vi.hoisted(() => ({ controller: null as ThemesController | null, navigate: vi.fn(), showModal: vi.fn() }));
vi.mock("@decky/ui", () => ({
  ModalRoot: ({ children, onCancel, onEscKeypress, bAllowFullSize }: { children?: ReactNode; onCancel?: () => void; onEscKeypress?: () => void; bAllowFullSize?: boolean }) => (
    <div data-testid="modal-root" data-allow-full-size={bAllowFullSize ? "true" : "false"}>
      {children}
      <button aria-label="modal-cancel" onClick={onCancel}>cancel</button>
      <button aria-label="modal-escape" onClick={onEscKeypress}>escape</button>
    </div>
  ),
  Focusable: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ButtonItem: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
  DialogButton: ({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
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

  it("keeps only version metadata in the simplified header", () => {
    mocks.controller = controller();
    render(<ThemeDetailsModal themeId="example-theme" />);

    expect(screen.getByText("themes.version.published")).toBeTruthy();
    expect(screen.queryByText("themes.details.eyebrow")).toBeNull();
    expect(screen.queryByText("Example Author")).toBeNull();
    expect(screen.queryByText("#dark")).toBeNull();
    expect(screen.queryByText("#compact")).toBeNull();
    expect(screen.queryByText("themes.remote.notes")).toBeNull();
  });

  it("uses the HOOANDEE cover behind the modal title with a readability gradient", () => {
    const base = controller();
    const release = {
      ...base.cards[0].release,
      catalogId: "hooandee-gallery",
      cssLoaderName: "Hooandee Gallery",
      displayName: { es: "HOOANDEE", en: "HOOANDEE", it: "HOOANDEE" },
    };
    mocks.controller = controller({
      cards: [{ ...base.cards[0], id: "hooandee-gallery", release }],
      publication: { status: "published", checkedAt: 10, themes: [release] },
    });

    render(<ThemeDetailsModal themeId="hooandee-gallery" />);

    expect(screen.getByRole("heading", { name: "HOOANDEE" })).toBeTruthy();
    expect(screen.getByTestId("theme-details-cover").getAttribute("alt")).toBe("");
    expect(screen.getByTestId("theme-details-cover").style.inset).toBe("-2px");
    expect(screen.getByTestId("theme-details-cover").style.width).toBe("calc(100% + 4px)");
    expect(screen.getByTestId("theme-details-cover-gradient")).toBeTruthy();
    expect(screen.getByTestId("theme-details-cover-copy").style.textShadow).not.toBe("");
  });

  it("keeps generic themes neutral and falls back if the HOOANDEE cover fails", () => {
    mocks.controller = controller();
    const view = render(<ThemeDetailsModal themeId="example-theme" />);

    expect(screen.queryByTestId("theme-details-cover")).toBeNull();

    const base = controller();
    const release = {
      ...base.cards[0].release,
      catalogId: "hooandee-gallery",
      cssLoaderName: "Hooandee Gallery",
    };
    mocks.controller = controller({
      cards: [{ ...base.cards[0], id: "hooandee-gallery", release }],
      publication: { status: "published", checkedAt: 10, themes: [release] },
    });
    view.rerender(<ThemeDetailsModal themeId="hooandee-gallery" />);
    fireEvent.error(screen.getByTestId("theme-details-cover"));

    expect(screen.queryByTestId("theme-details-cover")).toBeNull();
    expect(screen.queryByTestId("theme-details-cover-gradient")).toBeNull();
  });

  it("uses full-size layout only when installed settings need the space", () => {
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
    });
    const view = render(<ThemeDetailsModal themeId="example-theme" />);

    expect(screen.getByTestId("modal-root").getAttribute("data-allow-full-size")).toBe("false");

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
    });
    view.rerender(<ThemeDetailsModal themeId="example-theme" />);

    expect(screen.getByTestId("modal-root").getAttribute("data-allow-full-size")).toBe("true");
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

  it("replaces the ready offer with one compact, safely ordered confirmation", () => {
    const install = vi.fn(async () => true);
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
      install,
    });
    render(<ThemeDetailsModal themeId="example-theme" />);

    expect(screen.getByRole("group", { name: "themes.install.ready" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.action.install" }));
    expect(screen.queryByRole("group", { name: "themes.install.ready" })).toBeNull();

    const confirmation = screen.getByRole("group", { name: "themes.install.confirm.title" });
    expect(within(confirmation).getByText("themes.remote.card.version")).toBeTruthy();
    expect(within(confirmation).getAllByRole("button").map((button) => button.textContent)).toEqual([
      "themes.install.confirm.cancel",
      "themes.install.confirm.ok",
    ]);
    const primaryAction = within(confirmation).getByRole("button", { name: "themes.install.confirm.ok" });
    expect(primaryAction.querySelector('svg[aria-hidden="true"]')).toBeTruthy();

    fireEvent.click(primaryAction);
    expect(install).toHaveBeenCalledWith("example-theme", { version: "1.2.3" });
  });

  it("keeps local cancellation available if another theme operation starts", () => {
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
    });
    const view = render(<ThemeDetailsModal themeId="example-theme" />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.install" }));
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
      operation: { kind: "activating", themeId: "another-theme" },
    });
    view.rerender(<ThemeDetailsModal themeId="example-theme" />);

    const cancel = screen.getByRole("button", { name: "themes.install.confirm.cancel" });
    expect((cancel as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(cancel);
    expect(screen.getByRole("group", { name: "themes.install.ready" })).toBeTruthy();
  });

  it("uses Escape to restore the offer before closing the modal", () => {
    const closeModal = vi.fn();
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
    });
    render(<ThemeDetailsModal themeId="example-theme" closeModal={closeModal} />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.install" }));
    fireEvent.click(screen.getByRole("button", { name: "modal-escape" }));
    expect(screen.getByRole("group", { name: "themes.install.ready" })).toBeTruthy();
    expect(closeModal).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "modal-escape" }));
    expect(closeModal).toHaveBeenCalledOnce();
  });

  it("confirms an update with its exact published version", () => {
    const install = vi.fn(async () => true);
    const base = controller();
    const installedTheme = {
      id: "Example Theme", name: "Example Theme", displayName: "Example Theme", version: "1.2.2",
      author: "Example Author", enabled: true, patches: [],
    };
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [installedTheme] },
      cards: [{
        ...base.cards[0], installed: true, active: true, installedVersion: "1.2.2",
        targetVersion: "1.2.3", updateAvailable: true, versionRelation: "update-available",
        cssLoaderTheme: installedTheme,
      }],
      install,
    });
    render(<ThemeDetailsModal themeId="example-theme" />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.update" }));
    const confirmation = screen.getByRole("group", { name: "themes.update.confirm.title" });
    expect(within(confirmation).getByText("themes.remote.card.version")).toBeTruthy();
    fireEvent.click(within(confirmation).getByRole("button", { name: "themes.update.confirm.ok" }));

    expect(install).toHaveBeenCalledWith("example-theme", { version: "1.2.3" });
  });

  it("does not consume cancel after the confirmed version becomes stale", () => {
    const closeModal = vi.fn();
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
    });
    const view = render(<ThemeDetailsModal themeId="example-theme" closeModal={closeModal} />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.install" }));
    expect(screen.getByRole("group", { name: "themes.install.confirm.title" })).toBeTruthy();

    const next = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
    });
    mocks.controller = {
      ...next,
      cards: [{ ...next.cards[0], targetVersion: "1.2.4" }],
    };
    view.rerender(<ThemeDetailsModal themeId="example-theme" closeModal={closeModal} />);

    expect(screen.queryByRole("group", { name: "themes.install.confirm.title" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "modal-cancel" }));
    expect(closeModal).toHaveBeenCalledOnce();
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

    expect(screen.getByText("themes.version.installed")).toBeTruthy();
    expect(screen.getByText("themes.version.published")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.action.activate" }));
    fireEvent.click(screen.getByRole("button", { name: "Motion" }));
    expect(activate).toHaveBeenCalledWith("example-theme");
    expect(setPatch).toHaveBeenCalledWith("example-theme", "Motion", "No");
  });

  it("disables activation for an incompatible installed release", () => {
    const base = controller();
    const installedTheme = {
      id: "Example Theme", name: "Example Theme", displayName: "Example Theme", version: "1.2.3",
      author: "Example Author", enabled: false, patches: [],
    };
    const incompatibleRelease = {
      ...base.cards[0].release,
      compatibility: "incompatible-panel" as const,
    };
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [installedTheme] },
      cards: [{
        ...base.cards[0], release: incompatibleRelease, installed: true,
        installedVersion: "1.2.3", cssLoaderTheme: installedTheme, versionRelation: "unknown",
        installable: false, targetVersion: undefined,
      }],
      publication: { status: "published", checkedAt: 10, themes: [incompatibleRelease] },
    });
    render(<ThemeDetailsModal themeId="example-theme" />);

    expect((screen.getByRole("button", { name: "themes.action.activate" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("allows deactivation when an active catalog release becomes incompatible", () => {
    const deactivate = vi.fn(async () => true);
    const base = controller();
    const installedTheme = {
      id: "Example Theme", name: "Example Theme", displayName: "Example Theme", version: "1.2.3",
      author: "Example Author", enabled: true, patches: [],
    };
    const incompatibleRelease = {
      ...base.cards[0].release,
      compatibility: "incompatible-panel" as const,
    };
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [installedTheme] },
      cards: [{
        ...base.cards[0], release: incompatibleRelease, installed: true, active: true,
        installedVersion: "1.2.3", cssLoaderTheme: installedTheme, versionRelation: "unknown",
        installable: false, targetVersion: undefined,
      }],
      publication: { status: "published", checkedAt: 10, themes: [incompatibleRelease] },
      deactivate,
    });
    render(<ThemeDetailsModal themeId="example-theme" />);

    const button = screen.getByRole("button", { name: "themes.action.deactivate" });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    expect(deactivate).toHaveBeenCalledWith("example-theme");
  });

  it("uses Panel tokens instead of theme-owned chrome variables", () => {
    mocks.controller = controller();
    render(<ThemeDetailsModal themeId="example-theme" />);
    const css = screen.getByTestId("theme-settings-content").querySelector("style")?.textContent ?? "";
    expect(css).not.toContain("--hdg-");
    expect(css).toContain("[data-pdc-theme-settings]");
  });
});
