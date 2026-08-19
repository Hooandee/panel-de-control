// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  DialogButton: ({ children, ref, ...props }: any) => (
    <button ref={ref} type="button" {...props}>{children}</button>
  ),
  GamepadButton: { DIR_UP: 9, DIR_DOWN: 10 },
  getFocusNavController: () => ({ FocusElement: (element: HTMLElement) => element.focus() }),
  Focusable: ({ children, onActivate: _onActivate, noFocusRing: _noFocusRing, onGamepadDirection, ...props }: any) => (
    <div
      data-testid="notes-focus"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        onGamepadDirection?.({
          detail: { button: event.key === "ArrowUp" ? 9 : 10 },
          preventDefault: () => event.preventDefault(),
          stopPropagation: () => event.stopPropagation(),
        });
      }}
      {...props}
    >
      {children}
    </div>
  ),
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

import { UpdateModal } from "./UpdateModal";
import { UpdatePanel } from "./UpdatePanel";

afterEach(cleanup);

describe("Italian updater", () => {
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

  it("scrolls long release notes with one gamepad target", () => {
    render(
      <UpdateModal
        lang="es"
        latest="0.37.10"
        notes={[
          "## v0.37.10",
          "### Novedades",
          "- Cambio más reciente",
          "### What's new",
          "- Latest change",
          "### Novità",
          "- Ultima modifica",
          "## v0.37.9",
          "### Novedades",
          "- Cambio anterior",
        ].join("\n\n")}
      />,
    );

    expect(screen.getAllByTestId("notes-focus")).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "v0.37.10", level: 2 })).toBeTruthy();
    expect(screen.getByText("Cambio más reciente")).toBeTruthy();
    expect(screen.queryByText("Latest change")).toBeNull();
    expect(screen.queryByText("Ultima modifica")).toBeNull();
    expect(screen.queryByRole("heading", { level: 3 })).toBeNull();

    const target = screen.getByTestId("notes-focus");
    const viewport = screen.getByTestId("notes-scroll");
    Object.defineProperties(viewport, {
      clientHeight: { value: 340 },
      scrollHeight: { value: 1000 },
      scrollBy: {
        value: ({ top }: { top: number }) => {
          viewport.scrollTop += top;
        },
      },
    });

    expect(fireEvent.keyDown(target, { key: "ArrowDown" })).toBe(false);
    expect(viewport.scrollTop).toBe(272);

    viewport.scrollTop = 660;
    expect(fireEvent.keyDown(target, { key: "ArrowDown" })).toBe(true);
    expect(viewport.scrollTop).toBe(660);

    const install = screen.getByRole("button", { name: "Instalar actualización" });
    expect(document.activeElement).toBe(install);
    expect(
      target.compareDocumentPosition(install)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it.each([
    ["en", "Latest change", "Cambio más reciente", "Ultima modifica"],
    ["it", "Ultima modifica", "Cambio más reciente", "Latest change"],
  ] as const)("shows only %s release notes", (lang, visible, hiddenA, hiddenB) => {
    render(
      <UpdateModal
        lang={lang}
        latest="0.37.10"
        notes={[
          "## v0.37.10",
          "### Novedades",
          "- Cambio más reciente",
          "### What's new",
          "- Latest change",
          "### Novità",
          "- Ultima modifica",
        ].join("\n\n")}
      />,
    );

    expect(screen.getByText(visible)).toBeTruthy();
    expect(screen.queryByText(hiddenA)).toBeNull();
    expect(screen.queryByText(hiddenB)).toBeNull();
  });

  it("keeps unsectioned notes from older releases", () => {
    render(
      <UpdateModal
        lang="it"
        latest="0.36.0"
        notes={"## v0.36.0\n\nLegacy release notes"}
      />,
    );

    expect(screen.getByText("Legacy release notes")).toBeTruthy();
  });
});
