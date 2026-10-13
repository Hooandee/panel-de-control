// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

const focus = vi.hoisted(() => vi.fn((element: HTMLElement) => {
  element.classList.add("gpfocus");
  return true;
}));
vi.mock("../themes/runtime/navigationAccess", () => ({ createThemeNavigationAccess: () => ({ focus }) }));

import { PREFERRED_FOCUS, refocusWhenRemoved } from "./refocusWhenRemoved";

function element(parent: HTMLElement, label: string, focused = false): HTMLElement {
  const node = document.createElement("div");
  node.className = focused ? "Focusable gpfocus" : "Focusable";
  node.setAttribute("aria-label", label);
  parent.append(node);
  return node;
}

function panel() {
  const root = document.createElement("div");
  root.className = "pdc-root";
  document.body.append(root);
  return root;
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 120));

function remove(block: HTMLElement) {
  block.querySelectorAll(".gpfocus").forEach((node) => node.classList.remove("gpfocus"));
  block.remove();
}

describe("refocusWhenRemoved", () => {
  afterEach(() => {
    document.body.replaceChildren();
    focus.mockClear();
  });

  it("lands on the previous control of the same group once the focused block is gone", async () => {
    const root = panel();
    element(root, "Música");
    const group = element(root, "Mis perfiles");
    const previous = element(group, "Viaje");
    const chip = document.createElement("span");
    group.append(chip);
    element(chip, "Borrar", true);
    element(group, "Guardar");

    refocusWhenRemoved(chip);
    expect(focus).not.toHaveBeenCalled();
    remove(chip);
    await settle();

    expect(focus).toHaveBeenCalledWith(previous);
  });

  it("falls back to the next control of the group when the block was first", async () => {
    const root = panel();
    element(root, "Música");
    const group = element(root, "Mis perfiles");
    const chip = document.createElement("span");
    group.append(chip);
    element(chip, "Borrar", true);
    const next = element(group, "Guardar");

    refocusWhenRemoved(chip);
    remove(chip);
    await settle();

    expect(focus).toHaveBeenCalledWith(next);
  });

  it("leaves focus alone when it already landed somewhere", async () => {
    const root = panel();
    const above = element(root, "Brillo");
    const tray = document.createElement("div");
    root.append(tray);
    element(tray, "Más tarde", true);

    refocusWhenRemoved(tray);
    remove(tray);
    above.classList.add("gpfocus");
    await settle();

    expect(focus).not.toHaveBeenCalled();
  });

  it("does nothing for a block that does not hold focus", async () => {
    const root = panel();
    element(root, "Brillo");
    const tray = document.createElement("div");
    root.append(tray);
    element(tray, "Más tarde");

    refocusWhenRemoved(tray);
    tray.remove();
    await settle();

    expect(focus).not.toHaveBeenCalled();
  });

  it("prefers the control that replaced the block in the same place", async () => {
    const root = panel();
    element(root, "Juego");
    const tray = element(root, "Bandeja");
    const button = element(tray, "Limpiar selección", true);

    refocusWhenRemoved(button);
    remove(button);
    const confirm = element(tray, "Borrar");
    await settle();

    expect(focus).toHaveBeenCalledWith(confirm);
  });

  it("skips fallbacks that went away with the block", async () => {
    const root = panel();
    const game = element(root, "Juego");
    const plan = element(root, "Confirmación");
    element(plan, "Borrar");
    const cancel = element(plan, "Cancelar", true);

    refocusWhenRemoved(cancel);
    remove(plan);
    await settle();

    expect(focus).toHaveBeenCalledWith(game);
  });

  it("moves focus to the replacement even when Steam already picked another neighbour", async () => {
    const root = panel();
    const row = element(root, "Datos del juego");
    const tray = element(root, "Bandeja");
    const button = element(tray, "Limpiar", true);

    refocusWhenRemoved(button);
    remove(button);
    row.classList.add("gpfocus");
    const confirm = element(tray, "Borrar");
    await settle();

    expect(focus).toHaveBeenCalledWith(confirm);
  });

  it("puts focus on the replacement marked as preferred, such as Cancel in a confirmation", async () => {
    const root = panel();
    const tray = element(root, "Bandeja");
    const button = element(tray, "Limpiar", true);

    refocusWhenRemoved(button);
    remove(button);
    const plan = element(tray, "Confirmación");
    const remove_ = element(plan, "Borrar");
    const cancel = element(plan, "Cancelar");
    cancel.setAttribute(PREFERRED_FOCUS, "true");
    remove_.classList.add("gpfocus");
    await settle();

    expect(focus).toHaveBeenCalledWith(cancel);
  });

  it("finds a preferred replacement that appears elsewhere in the panel", async () => {
    const root = panel();
    const header = element(root, "Cabecera");
    const install = element(header, "Instalar", true);
    const confirmation = element(root, "Confirmación");

    refocusWhenRemoved(install);
    remove(install);
    const cancel = element(confirmation, "Cancelar");
    cancel.setAttribute(PREFERRED_FOCUS, "true");
    await settle();

    expect(focus).toHaveBeenCalledWith(cancel);
  });

  it("tries the next fallback when one refuses focus", async () => {
    const root = panel();
    const far = element(root, "Lejos");
    const near = element(root, "Cerca");
    const tray = document.createElement("div");
    root.append(tray);
    element(tray, "Más tarde", true);
    focus.mockImplementationOnce(() => false);

    refocusWhenRemoved(tray);
    remove(tray);
    await settle();

    expect(focus).toHaveBeenNthCalledWith(1, near);
    expect(focus).toHaveBeenNthCalledWith(2, far);
  });
});
