// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

const decky = vi.hoisted(() => ({ show: vi.fn(), close: vi.fn() }));
const focus = vi.hoisted(() => vi.fn(() => true));

vi.mock("@decky/ui", () => ({ showModal: decky.show }));
vi.mock("../themes/runtime/navigationAccess", () => ({ createThemeNavigationAccess: () => ({ focus }) }));

import { setQamDocument } from "../qamDocument";
import { showModal } from "./showModal";

function panelControl(label: string, focused = true): HTMLElement {
  const root = document.createElement("div");
  root.className = "pdc-root";
  const control = document.createElement("div");
  control.className = focused ? "Focusable gpfocus" : "Focusable";
  control.setAttribute("aria-label", label);
  root.append(control);
  document.body.append(root);
  return control;
}

function openedProps() {
  const calls = decky.show.mock.calls;
  return calls[calls.length - 1][2] as { fnOnClose: () => void };
}

describe("showModal focus return", () => {
  afterEach(() => {
    document.body.replaceChildren();
    decky.show.mockReset();
    focus.mockClear();
  });

  it("returns gamepad focus to the panel control that opened the modal", () => {
    const opener = panelControl("Glosario");
    setQamDocument(document);
    decky.show.mockReturnValue({ Close: decky.close, Update: vi.fn() });
    const onClose = vi.fn();

    showModal("modal", window, { fnOnClose: onClose });
    openedProps().fnOnClose();

    return new Promise<void>((resolve) => requestAnimationFrame(() => {
      expect(onClose).toHaveBeenCalledOnce();
      expect(focus).toHaveBeenCalledWith(opener);
      resolve();
    }));
  });

  it("leaves focus alone for a modal opened from another modal", () => {
    const opener = panelControl("Glosario");
    setQamDocument(document);
    decky.show.mockReturnValue({ Close: decky.close, Update: vi.fn() });

    showModal("outer", window);
    const outer = openedProps();
    showModal("inner", window);
    openedProps().fnOnClose();

    return new Promise<void>((resolve) => requestAnimationFrame(() => {
      expect(focus).not.toHaveBeenCalled();
      outer.fnOnClose();
      requestAnimationFrame(() => {
        expect(focus).toHaveBeenCalledWith(opener);
        resolve();
      });
    }));
  });

  it("finds the opener again by its label after the panel remounts", () => {
    const opener = panelControl("Glosario");
    setQamDocument(document);
    decky.show.mockReturnValue({ Close: decky.close, Update: vi.fn() });

    showModal("modal", window);
    document.body.replaceChildren();
    const remounted = panelControl("Glosario", false);
    openedProps().fnOnClose();

    return new Promise<void>((resolve) => requestAnimationFrame(() => {
      expect(opener.isConnected).toBe(false);
      expect(focus).toHaveBeenCalledWith(remounted);
      resolve();
    }));
  });

  it("closing twice runs the caller's close handler once", () => {
    setQamDocument(document);
    decky.show.mockReturnValue({ Close: decky.close, Update: vi.fn() });
    const onClose = vi.fn();

    const modal = showModal("modal", window, { fnOnClose: onClose });
    modal.Close();
    openedProps().fnOnClose();

    expect(onClose).toHaveBeenCalledOnce();
  });
});
