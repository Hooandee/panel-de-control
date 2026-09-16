// @vitest-environment happy-dom
import type { ReactElement, ReactNode } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createDefaultLayout } from "../customize/layout";
import type { QamViewDescriptor } from "../qam/viewCatalog";

const state = vi.hoisted(() => ({ presentVersion: 0, emptyFans: false, notify: () => {} }));
vi.mock("@decky/ui", () => ({
  showModal: (element: ReactElement) => render(element),
  ModalRoot: ({ children }: { children: ReactNode }) => <div role="dialog">{children}</div>,
  Focusable: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  ButtonItem: ({ children }: { children: ReactNode }) => <button>{children}</button>,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../api", () => ({ getBatteryState: async () => ({ charge_limit: { supported: false } }) }));
vi.mock("../customize/store", () => ({ useLayout: () => layout, saveLayout: vi.fn(), resetLayout: vi.fn() }));
vi.mock("../customize/modules", () => ({ useModules: () => disabled, setModuleDisabled: vi.fn(), resetModules: vi.fn() }));
vi.mock("../customize/homePreference", () => ({ resetHomeMode: vi.fn(), updateShowHome: vi.fn() }));
vi.mock("../customize/present", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    usePresentVersion: () => useSyncExternalStore((notify) => {
      state.notify = notify;
      return () => {};
    }, () => state.presentVersion),
    getPresent: (id: string) => id === "fans" && state.emptyFans ? [] : null,
  };
});
vi.mock("../customize/viewStore", () => ({ useViews: () => views, createView: vi.fn() }));
vi.mock("../desktop/useDesktop", () => ({ useDesktopState: () => ({ state: { enabled: false } }) }));
vi.mock("../system/useDevice", () => ({ useDevice: () => device }));
vi.mock("../system/useAccent", () => ({ useAccent: () => ({ id: "blue" }), setAccent: vi.fn() }));
vi.mock("./FocusRoot", () => ({ FocusRoot: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock("./HomeVisibilitySetting", () => ({ HomeVisibilitySetting: () => <div>Internal navigation settings</div> }));
vi.mock("./ViewEditor", () => ({ openViewEditorModal: vi.fn() }));
vi.mock("./DisableModuleModal", () => ({ openDisableModuleModal: vi.fn() }));
vi.mock("./IconAction", () => ({ iconBtn: {}, IconAction: () => null }));
vi.mock("./QamLayoutEditor", () => ({
  QamLayoutEditor: ({ catalog }: { catalog: QamViewDescriptor[] }) => (
    <div data-testid="qam-editor">{catalog.map((entry) => <div key={entry.token}>{entry.token}</div>)}</div>
  ),
}));

const layout = createDefaultLayout();
const disabled = new Set<string>();
const device = { key: "steam_deck_lcd" };
const views: [] = [];

import { openCustomizeModal } from "./CustomizeModal";
import { openQamCustomizeModal } from "./QamCustomizeModal";

afterEach(() => { cleanup(); state.emptyFans = false; state.presentVersion = 0; });

describe("customization destinations", () => {
  it("keeps QAM entries separate from internal navigation and appearance", () => {
    openQamCustomizeModal();
    expect(screen.getByText("settings.qamShortcut")).toBeTruthy();
    expect(screen.getByTestId("qam-editor")).toBeTruthy();
    expect(screen.queryByText("Internal navigation settings")).toBeNull();
    expect(screen.queryByText("customize.appearance")).toBeNull();
    expect(screen.queryByText("customize.reset")).toBeNull();
    expect(screen.queryByText("pdc:section:mandos")).toBeNull();
  });

  it("keeps the interface editor focused on internal settings", () => {
    openCustomizeModal();
    expect(screen.getByText("Internal navigation settings")).toBeTruthy();
    expect(screen.getByText("customize.appearance")).toBeTruthy();
    expect(screen.getByText("customize.reset")).toBeTruthy();
    expect(screen.queryByTestId("qam-editor")).toBeNull();
  });

  it("refreshes QAM availability when the reported blocks change", () => {
    openQamCustomizeModal();
    expect(screen.getByText("pdc:section:fans")).toBeTruthy();
    act(() => {
      state.emptyFans = true;
      state.presentVersion++;
      state.notify();
    });
    expect(screen.queryByText("pdc:section:fans")).toBeNull();
  });
});
