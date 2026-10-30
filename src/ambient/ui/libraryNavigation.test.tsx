// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { GamepadEvent } from "@decky/ui";
import { focusLibraryElement, useLibraryNavigation } from "./libraryNavigation";

const navigation = vi.hoisted(() => ({ controller: {} as any }));
vi.mock("@decky/ui", () => ({
  GamepadButton: { DIR_LEFT: 11, DIR_RIGHT: 12 },
  getFocusNavController: () => navigation.controller,
}));
afterEach(cleanup);

function Harness({ close }: { close: () => void }) {
  const nav = useLibraryNavigation(close);
  return <div ref={nav.ref} onClickCapture={nav.onClickCapture} onFocus={(e) => nav.onGamepadFocus(e as unknown as GamepadEvent)} onKeyDown={(e) => {
    const pad = { target: e.target, detail: { button: e.key === "ArrowRight" ? 12 : 11 }, preventDefault: () => e.preventDefault(), stopPropagation: () => e.stopPropagation() } as GamepadEvent;
    if (e.key === "Escape") { nav.onCancelButton(pad); if (!e.defaultPrevented) close(); }
    else nav.onGamepadDirection(pad);
  }}>
    {[0, 1, 2].map((i) => <div key={i} data-library-column={i} data-testid={`column-${i}`} tabIndex={0}><button>item-{i}</button></div>)}
  </div>;
}

it("returns through columns after pointer selection, closing only from sources", () => {
  const close = vi.fn();
  navigation.controller = { FocusElement: (element: HTMLElement) => element.focus() };
  render(<Harness close={close} />);
  fireEvent.click(screen.getByText("item-2"));
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(document.activeElement).toBe(screen.getByTestId("column-1"));
  expect(close).not.toHaveBeenCalled();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(document.activeElement).toBe(screen.getByTestId("column-0"));
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(close).toHaveBeenCalledOnce();
});

it("moves horizontally and restores the remembered control", () => {
  navigation.controller = { FocusElement: (element: HTMLElement) => element.focus() };
  render(<Harness close={vi.fn()} />);
  screen.getByText("item-0").focus();
  fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" });
  expect(document.activeElement).toBe(screen.getByTestId("column-1"));
  fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
  expect(document.activeElement).toBe(screen.getByText("item-0"));
});

it("uses the owning Steam node when FocusElement is absent", () => {
  const element = document.createElement("div");
  const BTakeFocus = vi.fn().mockReturnValue(true);
  navigation.controller = { GetActiveNavTree: () => ({ m_Root: { m_rgChildren: [{ m_element: element, BTakeFocus }] } }) };
  expect(focusLibraryElement(element)).toBe(true);
  expect(BTakeFocus).toHaveBeenCalledWith(3);
});

it("falls back safely if the native tree disappears", () => {
  navigation.controller = { GetActiveNavTree: () => { throw new Error("closed"); } };
  const element = document.createElement("button");
  document.body.append(element);
  expect(focusLibraryElement(element)).toBe(true);
  element.remove();
});
