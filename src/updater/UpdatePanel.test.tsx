// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, ...props }: any) => <button type="button" {...props}>{children}</button>,
  ModalRoot: ({ children }: any) => <section>{children}</section>,
  showModal: vi.fn(),
}));

vi.mock("./useUpdate", () => ({
  useUpdate: () => ({
    info: null,
    status: "idle",
    hasUpdate: false,
    check: vi.fn(async () => null),
    install: vi.fn(async () => null),
    restart: vi.fn(),
  }),
}));

vi.mock("../components/FocusRoot", () => ({
  FocusRoot: ({ children }: any) => <div>{children}</div>,
}));

import * as updateModalModule from "./UpdateModal";
import * as updatePanelModule from "./UpdatePanel";

const { UpdateModal } = updateModalModule;
const { UpdatePanel } = updatePanelModule;
const getUpdateModalStrings = Reflect.get(updateModalModule, "getUpdateModalStrings") as
  | ((lang: "it") => Record<string, string>)
  | undefined;
const getUpdatePanelStrings = Reflect.get(updatePanelModule, "getUpdatePanelStrings") as
  | ((lang: "it") => Record<string, string>)
  | undefined;

afterEach(cleanup);

describe("Italian updater", () => {
  it("exposes the complete panel and modal copy shared with Colores", () => {
    expect(getUpdatePanelStrings).toBeTypeOf("function");
    expect(getUpdateModalStrings).toBeTypeOf("function");

    expect(getUpdatePanelStrings?.("it")).toEqual({
      version: "Versione",
      latest: "(più recente)",
      newPrefix: "disponibile",
      checking: "verifica in corso…",
      check: "Cerca aggiornamenti",
      update: "Scopri le novità e installa",
      error: "Verifica non riuscita. Controlla la connessione.",
    });
    expect(getUpdateModalStrings?.("it")).toEqual({
      title: "Novità",
      noNotes: "Nessuna nota per questa versione.",
      install: "Installa l'aggiornamento",
      installing: "Installazione in corso…",
      installed: "Aggiornamento installato.",
      restartNote: "Riavvia Decky per applicare l'aggiornamento.",
      restart: "Riavvia Decky",
      failed: "Installazione non riuscita. Riprova.",
    });
  });

  it("does not use em dashes in the Italian panel or modal copy", () => {
    const strings = [
      ...Object.values(getUpdatePanelStrings?.("it") ?? {}),
      ...Object.values(getUpdateModalStrings?.("it") ?? {}),
    ];

    expect(strings.length).toBeGreaterThan(0);
    expect(strings.some((value) => value.includes("—"))).toBe(false);
  });

  it("renders the panel chrome in Italian", () => {
    expect(() => render(<UpdatePanel lang="it" version="0.34.0" />)).not.toThrow();

    expect(screen.getByText(/Versione 0\.34\.0/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cerca aggiornamenti" })).toBeTruthy();
  });

  it("renders the update modal chrome in Italian", () => {
    expect(() => render(
      <UpdateModal lang="it" latest="0.35.0" notes="" />,
    )).not.toThrow();

    expect(screen.getByText("Novità v0.35.0")).toBeTruthy();
    expect(screen.getByText("Nessuna nota per questa versione.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Installa l'aggiornamento" })).toBeTruthy();
  });
});
