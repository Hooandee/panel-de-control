// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LOCAL_THEME_CATALOG } from "../themes/catalog";
import { deriveThemeCards } from "../themes/state";
import type { ThemesController } from "../themes/useThemes";

const mocks = vi.hoisted(() => ({
  controller: null as ThemesController | null,
  external: vi.fn(),
  showModal: vi.fn(),
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
  showModal: mocks.showModal,
}));
vi.mock("../themes/useThemes", () => ({ useThemes: () => mocks.controller }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./ThemePatchControl", () => ({
  ThemePatchControl: ({ patch, disabled, onChange }: { patch: { name: string }; disabled?: boolean; onChange: (value: string) => void }) => (
    <button disabled={disabled} onClick={() => onChange("No")}>{patch.name}</button>
  ),
}));
vi.mock("./ConfirmDialog", () => ({ ConfirmDialog: () => null }));
vi.mock("./FocusRoot", () => ({
  FocusRoot: ({ children }: { children?: ReactNode }) => <div data-testid="focus-root">{children}</div>,
}));

import { ThemeDetailsModal } from "./ThemeDetailsModal";

function readyController(installed: boolean, enabled = false): ThemesController {
  const snapshot = {
    status: "ready" as const,
    backendVersion: 9,
    themes: installed ? [{
      id: "Hooandee Obsidian Bloom",
      name: "Hooandee Obsidian Bloom",
      displayName: "Obsidian Bloom",
      version: "0.1.0",
      author: "Hooandee",
      enabled,
      patches: [
        { name: "Cover grid columns", defaultValue: "4", value: "4", options: ["4", "5"], type: "dropdown" as const, rawType: "dropdown" },
        { name: "Animated transitions", defaultValue: "Yes", value: "Yes", options: ["No", "Yes"], type: "checkbox" as const, rawType: "checkbox" },
      ],
    }] : [],
  };
  return {
    loading: false,
    refreshing: false,
    snapshot,
    cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
    operation: null,
    recoveryBlocked: false,
    error: null,
    publication: { status: "disabled" },
    refresh: vi.fn(async () => {}),
    refreshPublication: vi.fn(async () => {}),
    install: vi.fn(async () => true),
    activate: vi.fn(async () => true),
    deactivate: vi.fn(async () => true),
    setPatch: vi.fn(async () => true),
  };
}

function galleryController(
  version: string,
  publication: ThemesController["publication"] = { status: "disabled" },
): ThemesController {
  const base = readyController(false);
  const snapshot = {
    status: "ready" as const,
    backendVersion: 9,
    themes: [{
      id: "Hooandee Gallery",
      name: "Hooandee Gallery",
      displayName: "Hooandee Gallery",
      version,
      author: "Hooandee",
      enabled: false,
      patches: [],
    }],
  };
  return {
    ...base,
    snapshot,
    publication,
    cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot, publication),
  };
}

function shatteredController(version: string): ThemesController {
  const base = readyController(false);
  const snapshot = {
    status: "ready" as const,
    backendVersion: 9,
    themes: [{
      id: "Hooandee Shattered Realms",
      name: "Hooandee Shattered Realms",
      displayName: "Hooandee Shattered Realms",
      version,
      author: "Hooandee",
      enabled: true,
      patches: [],
    }],
  };
  return {
    ...base,
    snapshot,
    cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
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

  it("shows durable recovery as busy in a non-ready CSS Loader state", () => {
    mocks.controller = {
      ...readyController(false),
      snapshot: { status: "missing", themes: [] },
      cards: [],
      operation: { kind: "recovering" },
    };
    render(<ThemeDetailsModal themeId="hooandee-gallery" />);

    expect((screen.getByRole("button", { name: "themes.loading" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("announces durable recovery while showing the previous ready theme", () => {
    mocks.controller = {
      ...readyController(true),
      operation: { kind: "recovering" },
    };
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    expect(screen.getByRole("status").textContent).toBe("themes.recovering");
    expect((screen.getByRole("button", { name: "Animated transitions" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("blocks theme changes but keeps recovery retry available for an invalid journal", () => {
    const refresh = vi.fn(async () => {});
    mocks.controller = {
      ...readyController(true),
      recoveryBlocked: true,
      error: "Panel theme recovery is blocked",
      refresh,
    };
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    expect(screen.getByText("themes.recovery.blocked")).toBeTruthy();
    expect((screen.getByRole("button", { name: "themes.action.activate" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Animated transitions" }) as HTMLButtonElement).disabled).toBe(true);
    const retry = screen.getByRole("button", { name: "themes.retry" });
    expect((retry as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(retry);
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("renders live CSS Loader patches in groups and delegates verified mutations", () => {
    mocks.controller = readyController(true);
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    expect(screen.getByText("themes.obsidian.name")).toBeTruthy();
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

  it("presents every patch category as a labelled region with ordered rows", () => {
    mocks.controller = readyController(true);
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    const grid = screen.getByRole("region", { name: "themes.group.grid" });
    const animations = screen.getByRole("region", { name: "themes.group.animations" });

    expect(within(grid).getAllByRole("listitem")).toHaveLength(1);
    expect(within(grid).getByRole("button", { name: "Cover grid columns" })).toBeTruthy();
    expect(within(animations).getAllByRole("listitem")).toHaveLength(1);
    expect(within(animations).getByRole("button", { name: "Animated transitions" })).toBeTruthy();
  });

  it("uses the modal glass as its canvas and keeps groups lighter than patch surfaces", () => {
    mocks.controller = readyController(true);
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    const content = screen.getByTestId("theme-settings-content");
    const header = screen.getByTestId("theme-settings-header");
    const action = screen.getByTestId("theme-settings-action");
    const grid = screen.getByRole("region", { name: "themes.group.grid" });
    const row = within(grid).getByRole("listitem");

    expect(content.style.maxWidth).toBe("760px");
    expect(content.style.background).toBe("");
    expect(header.style.display).toBe("grid");
    expect(action.getAttribute("data-pdc-theme-action")).toBe("true");
    expect(grid.style.background).toBe("");
    expect(row.style.padding).toBe("");
    expect(content.querySelector("style")?.textContent).toContain(
      "[data-pdc-theme-patch-control] > .Panel",
    );
    expect(content.querySelector("style")?.textContent).toContain(
      "[data-pdc-theme-action] > div",
    );
    expect(content.querySelector("style")?.textContent).toContain("--hdg-text-primary");
    expect(content.querySelector("style")?.textContent).toContain("--hdg-text-secondary");
    expect(content.querySelector("style")?.textContent).toContain("--hdg-settings-row-surface");
    expect(content.querySelector("style")?.textContent).toContain(
      "[data-pdc-theme-patch-control] > .Panel:not(.gpfocus)",
    );
    expect(content.querySelector("style")?.textContent).toContain("[data-pdc-theme-slider]");
    expect(content.querySelector("style")?.textContent).toContain(":has(.SliderHandle)");
    expect(content.querySelector("style")?.textContent).toContain(".gpfocuswithin");
    expect(content.querySelector("style")?.textContent).toContain(".SliderHandleFocusPop");
    expect(content.querySelector("style")?.textContent).toContain("#GamepadUI_Full_Root");
  });

  it("keeps auxiliary states on the same adaptive surface as theme settings", () => {
    mocks.controller = {
      ...readyController(true),
      operation: { kind: "recovering" },
      error: "recoverable",
    };
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    const surfaces = document.querySelectorAll("[data-pdc-theme-status-surface]");
    expect(surfaces).toHaveLength(2);
    const css = screen.getByTestId("theme-settings-content").querySelector("style")?.textContent;
    expect(css).toContain("[data-pdc-theme-status-surface]");
    expect(css).toContain("background: var(--hdg-settings-row-surface");
    expect(css).toContain("box-shadow: inset 0 0 0 1px var(--hdg-glass-stroke-soft");
    expect(css).toContain("color: var(--hdg-warning-ink, var(--hdg-critical");
    expect(screen.getByRole("alert").querySelector("[data-pdc-theme-warning]")).toBeTruthy();
  });

  it("offers verified deactivation for the active catalog theme", () => {
    mocks.controller = readyController(true, true);
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.deactivate" }));

    expect(mocks.controller?.deactivate).toHaveBeenCalledWith("hooandee-obsidian-bloom");
  });

  it("offers an explicit individual update when Gallery's installed version is older", () => {
    mocks.controller = galleryController("0.5.0");
    render(<ThemeDetailsModal themeId="hooandee-gallery" />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.update" }));

    expect(screen.getByText("themes.update.confirm.title")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.update.confirm.ok" }));
    expect(mocks.controller?.install).toHaveBeenCalledWith("hooandee-gallery", {
      version: "0.7.8",
      source: "bundled",
    });
    expect(mocks.showModal).not.toHaveBeenCalled();
  });

  it("uses Back or Escape to cancel confirmation before closing theme details", () => {
    const closeModal = vi.fn();
    mocks.controller = galleryController("0.5.0");
    render(<ThemeDetailsModal themeId="hooandee-gallery" closeModal={closeModal} />);

    fireEvent.click(screen.getByRole("button", { name: "themes.action.update" }));
    expect(screen.getByText("themes.update.confirm.title")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "modal-cancel" }));

    expect(closeModal).not.toHaveBeenCalled();
    expect(screen.queryByText("themes.update.confirm.title")).toBeNull();
    expect(screen.getByTestId("theme-settings-content")).toBeTruthy();
  });

  it("shows installed and official versions as separate truths", () => {
    mocks.controller = galleryController("0.7.8", {
      status: "published",
      checkedAt: 100,
      themes: [{
        catalogId: "hooandee-gallery",
        cssLoaderName: "Hooandee Gallery",
        publishedVersion: "0.7.9",
        compatibility: "compatible",
        notes: { es: "Novedades" },
      }],
    });

    render(<ThemeDetailsModal themeId="hooandee-gallery" />);

    expect(screen.getByText("themes.version.installed")).toBeTruthy();
    expect(screen.getByText("themes.version.published")).toBeTruthy();
    expect(screen.getByText("themes.remote.notes")).toBeTruthy();
  });

  it("keeps local controls available when remote discovery is temporarily unavailable", () => {
    const refreshPublication = vi.fn(async () => {});
    mocks.controller = {
      ...galleryController("0.7.8"),
      publication: {
        status: "temporarily-unavailable",
        code: "offline",
        retryable: true,
      },
      refreshPublication,
    };

    render(<ThemeDetailsModal themeId="hooandee-gallery" />);

    expect(screen.getByText("themes.remote.unavailable")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.remote.retry" }));
    expect(refreshPublication).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "themes.action.activate" })).toBeTruthy();
  });

  it("does not infer a published update for a theme without a verified source", () => {
    mocks.controller = shatteredController("0.3.0");
    render(<ThemeDetailsModal themeId="hooandee-shattered-realms" />);

    expect(screen.queryByText("themes.update.ready")).toBeNull();
    expect(screen.getByText("themes.patches.empty")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "themes.action.update" })).toBeNull();
  });

  it("does not label a patch save as theme deactivation", () => {
    mocks.controller = {
      ...readyController(true, true),
      operation: {
        kind: "saving",
        themeId: "hooandee-obsidian-bloom",
        patchName: "Animated transitions",
      },
    };
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    expect(screen.getByRole("button", { name: "themes.action.deactivate" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "themes.action.deactivating" })).toBeNull();
  });

  it("disables every theme action while the shared client is mutating another theme", () => {
    mocks.controller = {
      ...readyController(true),
      operation: { kind: "activating", themeId: "hooandee-gallery" },
    };
    render(<ThemeDetailsModal themeId="hooandee-obsidian-bloom" />);

    expect((screen.getByRole("button", { name: "themes.action.activate" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Animated transitions" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not pretend an unverified install source exists", () => {
    mocks.controller = readyController(false);
    render(<ThemeDetailsModal themeId="hooandee-shattered-realms" />);

    expect(screen.getByText("themes.install.unavailable")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "themes.action.activate" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "themes.action.project" }));
    expect(mocks.external).toHaveBeenCalledWith("https://github.com/Hooandee/hooandee-themes");
  });
});
