// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ThemesController } from "../themes/useThemes";

const mocks = vi.hoisted(() => ({ controller: null as ThemesController | null, navigate: vi.fn(), open: vi.fn() }));
vi.mock("@decky/ui", () => ({
  PanelSectionRow: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Focusable: ({ children, onClick, role, "aria-selected": selected, "aria-label": label }: { children?: ReactNode; onClick?: () => void; role?: string; "aria-selected"?: boolean; "aria-label"?: string }) => (
    <div role={role} aria-selected={selected} aria-label={label} onClick={onClick}>{children}</div>
  ),
  ButtonItem: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => <button onClick={onClick} disabled={disabled}>{children}</button>,
  Navigation: { Navigate: mocks.navigate },
  ToggleField: ({ label, description, checked, disabled, onChange }: { label: string; description: string; checked: boolean; disabled?: boolean; onChange(on: boolean): void }) => (
    <div><label>{label}<input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} /></label><span>{description}</span></div>
  ),
}));
vi.mock("../themes/useThemes", () => ({ useThemes: () => mocks.controller }));
vi.mock("../components/ThemeCard", () => ({ ThemeCard: ({ card, onOpen }: { card: { id: string }; onOpen(): void }) => <button onClick={onOpen}>{card.id}</button> }));
vi.mock("../components/ThemeDetailsModal", () => ({ openThemeDetailsModal: mocks.open }));
vi.mock("../assets/keyboards-preview.jpg", () => ({ default: "keyboards-preview.jpg" }));
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
    recoveryKeptCurrent: false,
    error: null,
    errorCode: null,
    sectionHandoff: null,
    publication: { status: "published", checkedAt: 10, themes: [release] },
    refresh: vi.fn(async () => {}), refreshPublication: vi.fn(async () => {}),
    install: vi.fn(async () => true), uninstall: vi.fn(async () => true), activate: vi.fn(async () => true),
    deactivate: vi.fn(async () => true), setPatch: vi.fn(async () => true),
    performanceMode: false, setPerformanceMode: vi.fn(async () => true),
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

  it("offers the performance mode switch once CSS Loader is ready", () => {
    const setPerformanceMode = vi.fn(async () => true);
    mocks.controller = controller({ snapshot: { status: "ready", themes: [] }, setPerformanceMode });
    render(<TemasSection />);

    fireEvent.click(screen.getByLabelText("themes.performance.title"));
    expect(setPerformanceMode).toHaveBeenCalledWith(true);
    expect(screen.getByText("themes.performance.description")).toBeTruthy();
  });

  it("says when the active theme has no performance mode yet", () => {
    const base = controller();
    const active = { id: "Example Theme", name: "Example Theme", displayName: "Example Theme", version: "1.2.3", author: "A", enabled: true, patches: [] };
    mocks.controller = controller({
      snapshot: { status: "ready", themes: [active] },
      cards: [{ ...base.cards[0], installed: true, active: true, cssLoaderTheme: active }],
    });
    render(<TemasSection />);
    expect(screen.getByText("themes.performance.unsupported")).toBeTruthy();
  });

  it("hides the switch while CSS Loader is unavailable", () => {
    mocks.controller = controller();
    render(<TemasSection />);
    expect(screen.queryByText("themes.performance.title")).toBeNull();
  });

  it("does not flash a false missing state while CSS Loader inspection is pending", () => {
    mocks.controller = controller({ loading: true, publication: { status: "checking" }, cards: [] });
    render(<TemasSection />);
    expect(screen.getByText("themes.loading")).toBeTruthy();
    expect(screen.queryByText("themes.cssLoader.missing")).toBeNull();
  });

  it("renders a deliberate empty state for a valid empty publication", () => {
    mocks.controller = controller({
      snapshot: { status: "ready", themes: [] },
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

  it("shows a non-blocking notice when the previous theme state was kept as current", () => {
    mocks.controller = controller({ recoveryKeptCurrent: true });
    render(<TemasSection />);
    expect(screen.getByText("themes.recovery.keptCurrent").getAttribute("role")).toBe("status");
    expect(screen.queryByText("themes.recovery.blocked")).toBeNull();
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

  it("opens on the system themes and teases keyboards behind their own tab", () => {
    mocks.controller = controller();
    render(<TemasSection />);

    expect(screen.getByRole("tab", { name: "themes.tab.system" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("button", { name: "example-theme" })).toBeTruthy();
    expect(screen.queryByText("comingSoon.badge")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "themes.tab.keyboards" }));

    expect(screen.queryByRole("button", { name: "example-theme" })).toBeNull();
    expect(screen.getByText("themes.keyboards.title")).toBeTruthy();
    expect(screen.getByText("comingSoon.badge")).toBeTruthy();
    expect(screen.getByRole("img", { name: "themes.keyboards.imageAlt" }).getAttribute("src")).toBe("keyboards-preview.jpg");
  });
});
