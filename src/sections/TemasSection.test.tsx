// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ThemesController } from "../themes/useThemes";

const mocks = vi.hoisted(() => ({ controller: null as ThemesController | null, navigate: vi.fn(), open: vi.fn() }));
vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ButtonItem: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => <button onClick={onClick} disabled={disabled}>{children}</button>,
  Navigation: { Navigate: mocks.navigate },
}));
vi.mock("../themes/useThemes", () => ({ useThemes: () => mocks.controller }));
vi.mock("../components/ThemeCard", () => ({ ThemeCard: ({ card, onOpen }: { card: { id: string }; onOpen(): void }) => <button onClick={onOpen}>{card.id}</button> }));
vi.mock("../components/ThemeDetailsModal", () => ({ openThemeDetailsModal: mocks.open }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));

import { TemasSection } from "./TemasSection";

function controller(overrides: Partial<ThemesController> = {}): ThemesController {
  const release = {
    catalogId: "example-theme", cssLoaderName: "Example Theme", publishedVersion: "1.2.3",
    displayName: { es: "Tema", en: "Example Theme", it: "Tema" },
    description: { es: "Descripcion", en: "Description", it: "Descrizione" },
    author: "Example Author", tags: [], notes: {}, compatibility: "compatible" as const,
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
    refresh: vi.fn(async () => {}), refreshPublication: vi.fn(async () => {}),
    install: vi.fn(async () => true), activate: vi.fn(async () => true),
    deactivate: vi.fn(async () => true), setPatch: vi.fn(async () => true),
    ...overrides,
  };
}

describe("TemasSection", () => {
  afterEach(() => { cleanup(); mocks.controller = null; vi.clearAllMocks(); });

  it("shows catalog cards and Store guidance without CSS Loader", () => {
    mocks.controller = controller();
    render(<TemasSection />);

    expect(screen.getByRole("button", { name: "example-theme" })).toBeTruthy();
    expect(screen.getByText("themes.cssLoader.missing")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.cssLoader.openStore" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/decky/store");
  });

  it("does not flash a false missing state while CSS Loader inspection is pending", () => {
    mocks.controller = controller({ loading: true, publication: { status: "checking" }, cards: [] });
    render(<TemasSection />);
    expect(screen.getByText("themes.loading")).toBeTruthy();
    expect(screen.queryByText("themes.cssLoader.missing")).toBeNull();
  });

  it("renders a deliberate empty state for a valid empty publication", () => {
    mocks.controller = controller({
      snapshot: { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [] },
      publication: { status: "published", checkedAt: 10, themes: [] },
      cards: [],
    });
    render(<TemasSection />);
    expect(screen.getByText("themes.catalog.empty")).toBeTruthy();
  });

  it("shows retry when publication is unavailable without cache", () => {
    const refreshPublication = vi.fn(async () => {});
    mocks.controller = controller({
      publication: { status: "temporarily-unavailable", code: "offline", retryable: true },
      cards: [], refreshPublication,
    });
    render(<TemasSection />);
    expect(screen.getByText("themes.catalog.unavailable")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.remote.retry" }));
    expect(refreshPublication).toHaveBeenCalledOnce();
  });

  it("keeps cached cards visible with an offline banner", () => {
    const base = controller();
    mocks.controller = controller({
      publication: { status: "cached", checkedAt: 10, themes: [base.cards[0].release], code: "offline", retryable: true },
    });
    render(<TemasSection />);
    expect(screen.getByText("themes.remote.cached")).toBeTruthy();
    expect(screen.getByRole("button", { name: "example-theme" })).toBeTruthy();
  });
});
