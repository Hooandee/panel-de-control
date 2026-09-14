// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { QamRuntimeSnapshot } from "../qam/runtime";
import type { QamLayout } from "../qam/layout";
import type { QamViewDescriptor } from "../qam/viewCatalog";

const state = vi.hoisted(() => ({
  layout: null as QamLayout | null,
  runtime: null as QamRuntimeSnapshot | null,
  save: vi.fn(),
  reset: vi.fn(),
}));

vi.mock("@decky/ui", () => ({
  ButtonItem: ({ children, onClick }: { children: ReactNode; onClick(): void }) => (
    <button onClick={onClick}>{children}</button>
  ),
  Focusable: ({ children, onClick, ...props }: {
    children: ReactNode;
    onClick?: () => void;
    [key: string]: unknown;
  }) => <button onClick={onClick} {...props}>{children}</button>,
  Navigation: { CloseSideMenus: vi.fn() },
}));

vi.mock("../qam/store", () => ({
  useQamLayout: () => state.layout,
  saveQamLayout: (layout: QamLayout) => {
    state.layout = layout;
    state.save(layout);
  },
  resetQamLayout: state.reset,
}));

vi.mock("../qam/runtime", () => ({
  getQamRuntimeSnapshot: () => state.runtime,
  subscribeQamRuntime: () => () => {},
}));

vi.mock("../customize/viewStore", () => ({ useViews: () => [] }));
vi.mock("../api", () => ({ restartLoader: vi.fn() }));
vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "customize.qam.native.friends": "Amigos",
      "customize.qam.native.help": "Ayuda",
      "customize.qam.decky": "Decky",
      "customize.qam.pin": "Anclar",
      "customize.qam.unpin": "Desanclar",
      "customize.hide": "Ocultar",
      "customize.show": "Mostrar",
      "customize.moveUp": "Subir",
      "customize.moveDown": "Bajar",
      "customize.qam.reset": "Restaurar QAM",
      "customize.qam.applied": "Aplicado al instante",
      "customize.qam.restart": "Recarga Decky para aplicar los cambios guardados.",
      "customize.qam.restartButton": "Recargar Decky",
    })[key] ?? key,
  }),
}));

const icon = () => null;
const catalog: QamViewDescriptor[] = [
  {
    token: "pdc:home",
    labelKey: "home.title",
    label: "Inicio",
    descriptionKey: "home.subtitle",
    accent: "#000",
    icon,
    target: { kind: "home" },
  },
  {
    token: "pdc:section:hud",
    labelKey: "nav.hud",
    label: "HUD",
    descriptionKey: "nav.hud.desc",
    accent: "#000",
    icon,
    target: { kind: "section", id: "hud" },
  },
];

import { nativeQamLabelKey, QamLayoutEditor } from "./QamLayoutEditor";

describe("QamLayoutEditor", () => {
  it("maps the native IDs observed in Steam's QAM to localized labels", () => {
    expect([0, 3, 4, 5, 7, 6].map(nativeQamLabelKey)).toEqual([
      "customize.qam.native.notifications",
      "customize.qam.native.friends",
      "customize.qam.native.quickSettings",
      "customize.qam.native.performance",
      "customize.qam.native.soundtracks",
      "customize.qam.native.help",
    ]);
  });

  beforeEach(() => {
    state.layout = {
      order: ["native:friends", "native:help", "pdc:home"],
      hiddenNative: [],
      pinnedViews: ["pdc:home"],
      ownedIds: { "pdc:home": 1 },
    };
    state.runtime = {
      initialized: true,
      applied: true,
      restartRequired: false,
      reason: "ready",
      activeTokens: ["pdc:home"],
      inventory: [
        { token: "native:friends", key: "friends", entry: { key: "friends" }, kind: "native" },
        { token: "native:help", key: "help", entry: { key: "help" }, kind: "native" },
      ],
    };
    state.save.mockClear();
    state.reset.mockClear();
  });

  afterEach(cleanup);

  it("mixes native entries and Panel views with independent visibility and pinning", () => {
    const view = render(<QamLayoutEditor catalog={catalog} />);

    fireEvent.click(screen.getByLabelText("Ocultar Ayuda"));
    expect(state.save).toHaveBeenLastCalledWith(expect.objectContaining({
      hiddenNative: ["native:help"],
    }));

    view.rerender(<QamLayoutEditor catalog={catalog} />);
    fireEvent.click(screen.getByLabelText("Anclar HUD"));
    expect(state.save).toHaveBeenLastCalledWith(expect.objectContaining({
      pinnedViews: ["pdc:home", "pdc:section:hud"],
    }));

    view.rerender(<QamLayoutEditor catalog={catalog} />);
    fireEvent.click(screen.getByLabelText("Subir HUD"));
    expect(state.save).toHaveBeenLastCalledWith(expect.objectContaining({
      order: ["native:friends", "native:help", "pdc:section:hud", "pdc:home"],
    }));
  });

  it("keeps Decky protected and exposes reset", () => {
    render(<QamLayoutEditor catalog={catalog} />);

    expect(screen.getByText("Decky")).toBeTruthy();
    expect(screen.queryByLabelText("Ocultar Decky")).toBeNull();
    expect(screen.queryByLabelText("Subir Decky")).toBeNull();
    fireEvent.click(screen.getByText("Restaurar QAM"));
    expect(state.reset).toHaveBeenCalledOnce();
  });

  it("does not describe pending changes as applied", () => {
    state.runtime = {
      ...state.runtime!,
      applied: false,
      restartRequired: true,
      reason: "composition_update_failed",
    };
    render(<QamLayoutEditor catalog={catalog} />);

    expect(screen.queryByText("Aplicado al instante")).toBeNull();
    expect(screen.getByText("Recarga Decky para aplicar los cambios guardados.")).toBeTruthy();
    expect(screen.getByText("Recargar Decky")).toBeTruthy();
  });
});
