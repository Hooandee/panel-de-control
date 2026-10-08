// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ThemeHealthView } from "../themes/useThemeHealth";

const mocks = vi.hoisted(() => ({
  health: null as ThemeHealthView | null,
  modal: null as ReactElement | null,
  report: vi.fn(),
  controller: {
    snapshot: { status: "ready", themes: [] },
    operation: null,
    errorCode: null,
    refresh: vi.fn(async () => {}),
  },
}));

vi.mock("@decky/ui", () => ({
  ButtonItem: ({ children, onClick, disabled, description }: { children?: ReactNode; onClick?: () => void; disabled?: boolean; description?: ReactNode }) => (
    <button onClick={onClick} disabled={disabled} title={typeof description === "string" ? description : undefined}>{children}</button>
  ),
  DialogButton: ({ children, onClick, disabled }: { children?: ReactNode; onClick?: () => void; disabled?: boolean }) => <button onClick={onClick} disabled={disabled}>{children}</button>,
  Focusable: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ModalRoot: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  showModal: (element: ReactElement) => { mocks.modal = element; },
}));
vi.mock("./FocusRoot", () => ({ FocusRoot: ({ children }: { children?: ReactNode }) => <div>{children}</div> }));
vi.mock("./ReportModal", () => ({ openReportModal: mocks.report }));
vi.mock("../themes/useThemes", () => ({ useThemes: () => mocks.controller }));
vi.mock("../themes/useThemeHealth", () => ({ useThemeHealth: () => mocks.health }));
vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => params ? `${key} ${JSON.stringify(params)}` : key }),
}));

import { openThemeHealthModal, ThemeHealthCard } from "./ThemeHealth";
import type { ThemesController } from "../themes/useThemes";

function health(overrides: Partial<ThemeHealthView> = {}): ThemeHealthView {
  return {
    checking: false,
    unavailable: false,
    findings: [],
    plan: { keep: ["Eclipse"], disable: [], setAside: 0, ghostStyles: false },
    needsCleanup: false,
    undo: { available: false, moved: 0, disabled: 0 },
    display: null,
    recheck: vi.fn(async () => {}),
    cleanUp: vi.fn(async () => true),
    undoCleanup: vi.fn(async () => true),
    ...overrides,
  };
}

function openModal() {
  openThemeHealthModal();
  render(mocks.modal as ReactElement);
}

describe("ThemeHealth", () => {
  afterEach(() => { cleanup(); mocks.modal = null; vi.clearAllMocks(); });

  it("summarises a clean machine on the Themes card", () => {
    mocks.health = health();
    render(<ThemeHealthCard controller={mocks.controller as unknown as ThemesController} />);

    expect(screen.getByText("themes.health.summary.clean {\"count\":0}")).toBeTruthy();
    expect(screen.getByRole("button", { name: "themes.health.open" })).toBeTruthy();
  });

  it("asks before cleaning and reports the result", async () => {
    mocks.health = health({
      findings: [
        { id: "other_active", severity: "problem", names: ["Other"] },
        { id: "steam_scale", severity: "setting", scale: 1.25, autoScale: 1 },
      ],
      plan: { keep: ["Eclipse"], disable: ["Other"], setAside: 2, ghostStyles: false },
      needsCleanup: true,
    });
    openModal();

    expect(screen.getByText("Other")).toBeTruthy();
    expect(screen.getByText("themes.health.steam_scale.detail {\"scale\":\"125 %\",\"auto\":\"100 %\"}")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "themes.health.clean" }));
    expect(mocks.health.cleanUp).not.toHaveBeenCalled();
    expect(screen.getByText("themes.health.confirm.disable {\"count\":1}")).toBeTruthy();
    expect(screen.getByText("themes.health.confirm.setAside {\"count\":2}")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "themes.health.clean.ok" }));

    await waitFor(() => expect(screen.getByText("themes.health.result.cleaned")).toBeTruthy());
    expect(mocks.health.cleanUp).toHaveBeenCalledTimes(1);
  });

  it("offers undo with what it will bring back, and opens a theme report", () => {
    mocks.health = health({ undo: { available: true, moved: 2, disabled: 1 } });
    openModal();

    fireEvent.click(screen.getByRole("button", { name: "themes.health.undo" }));
    expect(mocks.health.undoCleanup).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "themes.health.report" }));
    expect(mocks.report).toHaveBeenCalledWith(["themes"]);
  });
});
