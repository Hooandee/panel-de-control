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
  ButtonItem: ({ children, onClick }: { children?: ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
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
    snapshot,
    cards: deriveThemeCards(LOCAL_THEME_CATALOG, snapshot),
    operation: null,
    error: null,
    refresh: vi.fn(async () => {}),
    install: vi.fn(async () => true),
    activate: vi.fn(async () => true),
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
    fireEvent.click(screen.getByRole("button", { name: "themes.cssLoader.openStore" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/decky/store");
    fireEvent.click(screen.getByRole("button", { name: "themes.retry" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("lists the complete catalog and opens a card through its focusable surface", () => {
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
    fireEvent.click(screen.getByTestId("theme-card-hooandee-obsidian-bloom"));
    expect(mocks.openDetails).toHaveBeenCalledWith("hooandee-obsidian-bloom", expect.any(Function));
    mocks.openDetails.mock.calls[0][1]();
    expect(mocks.controller?.refresh).toHaveBeenCalledOnce();
    expect(screen.getByText("themes.state.active")).toBeTruthy();
  });
});
