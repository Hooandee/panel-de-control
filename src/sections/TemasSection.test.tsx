// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { HTMLAttributes, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LOCAL_THEME_CATALOG } from "../themes/catalog";
import { deriveThemeCards } from "../themes/state";
import type { ThemesController } from "../themes/useThemes";

const mocks = vi.hoisted(() => ({
  controller: null as ThemesController | null,
  openDetails: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Focusable: ({ children, onActivate, style: _style, ...props }: {
    children?: ReactNode;
    onActivate?: () => void;
  } & HTMLAttributes<HTMLDivElement>) => <div onClick={onActivate} {...props}>{children}</div>,
  ButtonItem: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
  Navigation: { Navigate: mocks.navigate },
}));

vi.mock("../themes/useThemes", () => ({ useThemes: () => mocks.controller }));
vi.mock("../components/ThemeDetailsModal", () => ({ openThemeDetailsModal: mocks.openDetails }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));

import { TemasSection } from "./TemasSection";

function controller(overrides: Partial<ThemesController> = {}): ThemesController {
  const snapshot = { status: "missing" as const, themes: [] };
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
    ...overrides,
  };
}

describe("TemasSection", () => {
  afterEach(() => {
    cleanup();
    mocks.controller = null;
    vi.clearAllMocks();
  });

  it("does not flash a false missing state while detection is pending", () => {
    mocks.controller = controller({ loading: true });

    render(<TemasSection />);

    expect(screen.getByText("themes.loading")).toBeTruthy();
    expect(screen.queryByText("themes.cssLoader.missing")).toBeNull();
  });

  it("offers a useful CSS Loader requirement state", () => {
    const refresh = vi.fn(async () => {});
    mocks.controller = controller({ refresh });

    render(<TemasSection />);

    expect(screen.getByText("themes.cssLoader.missing")).toBeTruthy();
    expect(screen.queryAllByTestId(/^theme-card-/)).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "themes.cssLoader.openStore" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/decky/store");
    fireEvent.click(screen.getByRole("button", { name: "themes.retry" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("offers a manual official update check without replacing local cards", () => {
    const snapshot = { status: "ready" as const, pluginVersion: "2.1.2", backendVersion: 9, themes: [] };
    const refreshPublication = vi.fn(async () => {});
    mocks.controller = controller({
      snapshot,
      cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
      publication: { status: "published", checkedAt: 100, themes: [] },
      refreshPublication,
    });

    render(<TemasSection />);

    expect(screen.getAllByTestId(/^theme-card-/)).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "themes.remote.retry" }));
    expect(refreshPublication).toHaveBeenCalledOnce();
  });

  it("shows durable recovery as busy instead of accepting an inert retry", () => {
    mocks.controller = controller({ operation: { kind: "recovering" } });

    render(<TemasSection />);

    expect((screen.getByRole("button", { name: "themes.loading" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("announces durable recovery while the previous ready snapshot remains visible", () => {
    const snapshot = { status: "ready" as const, backendVersion: 9, themes: [] };
    mocks.controller = controller({
      snapshot,
      cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
      operation: { kind: "recovering" },
    });

    render(<TemasSection />);

    expect(screen.getByRole("status").textContent).toBe("themes.recovering");
  });

  it("keeps local cards visible while a blocked recovery requires a retry", () => {
    const snapshot = { status: "ready" as const, backendVersion: 9, themes: [] };
    const refresh = vi.fn(async () => {});
    mocks.controller = controller({
      snapshot,
      cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
      recoveryBlocked: true,
      error: "Panel theme recovery is blocked",
      refresh,
    });

    render(<TemasSection />);

    expect(screen.getAllByTestId(/^theme-card-/)).toHaveLength(3);
    expect(screen.getByText("themes.recovery.blocked")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.retry" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("lists the complete catalog but opens only the available theme", () => {
    const snapshot = {
      status: "ready" as const,
      backendVersion: 9,
      themes: [{
        id: "Hooandee Obsidian Bloom",
        name: "Hooandee Obsidian Bloom",
        displayName: "Obsidian Bloom",
        version: "0.1.0",
        author: "Hooandee",
        enabled: true,
        patches: [],
      }],
    };
    mocks.controller = controller({
      snapshot,
      cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
    });

    render(<TemasSection />);

    expect(screen.getAllByTestId(/^theme-card-/)).toHaveLength(3);
    fireEvent.click(screen.getByTestId("theme-card-hooandee-gallery"));
    expect(mocks.openDetails).toHaveBeenCalledWith("hooandee-gallery", expect.any(Function));
    fireEvent.click(screen.getByTestId("theme-card-hooandee-obsidian-bloom"));
    expect(mocks.openDetails).toHaveBeenCalledTimes(1);
    mocks.openDetails.mock.calls[0][1]();
    expect(mocks.controller?.refresh).toHaveBeenCalledOnce();
    expect(screen.getAllByText("themes.state.comingSoon")).toHaveLength(2);
  });

  it("shows a localized recoverable failure even when reconciliation remains ready", () => {
    const snapshot = { status: "ready" as const, backendVersion: 9, themes: [] };
    const refresh = vi.fn(async () => {});
    mocks.controller = controller({
      snapshot,
      cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
      error: "CSS Loader reset timed out",
      refresh,
    });

    render(<TemasSection />);

    expect(screen.getByText("themes.operation.failed")).toBeTruthy();
    expect(screen.queryByText("CSS Loader reset timed out")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "themes.retry" }));
    expect(refresh).toHaveBeenCalledOnce();
  });
});
