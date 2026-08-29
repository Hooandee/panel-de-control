// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { startPortalTransition } from "./portalTransition";

describe("Obsidian portal transition", () => {
  afterEach(() => {
    document.documentElement.removeAttribute("data-pdc-portal-phase");
    document.body.innerHTML = "";
  });

  it("bridges library artwork into details without becoming interactive", () => {
    const callbacks = new Map<number, () => void>();
    let nextTimer = 0;
    const portal = startPortalTransition(document, {
      setTimeout(callback) {
        const id = ++nextTimer;
        callbacks.set(id, callback);
        return id;
      },
      clearTimeout(id) {
        callbacks.delete(id);
      },
    });

    portal.remember("https://cdn.example/game.jpg", new DOMRect(24, 48, 160, 240));
    portal.surfaceChanged("library-grid");
    portal.surfaceChanged("game-details");

    const host = document.getElementById("pdc-obsidian-portal");
    expect(host?.getAttribute("aria-hidden")).toBe("true");
    expect(host?.hasAttribute("tabindex")).toBe(false);
    expect(host?.style.getPropertyValue("--pdc-portal-artwork")).toContain("game.jpg");
    expect(host?.style.getPropertyValue("--pdc-portal-x")).toBe("104px");
    expect(document.querySelectorAll("#pdc-obsidian-portal")).toHaveLength(1);

    portal.surfaceChanged("settings");
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();
    portal.dispose();
  });

  it("prearms the entry veil before Steam replaces the library", () => {
    const callbacks = new Map<number, () => void>();
    let nextTimer = 0;
    const portal = startPortalTransition(document, {
      setTimeout(callback) {
        const id = ++nextTimer;
        callbacks.set(id, callback);
        return id;
      },
      clearTimeout(id) {
        callbacks.delete(id);
      },
    });

    portal.remember("https://cdn.example/game.jpg", new DOMRect(425, 238, 172, 299));
    portal.surfaceChanged("library");
    portal.beginEntry();

    const host = document.getElementById("pdc-obsidian-portal");
    expect(host?.dataset.pdcPortalDirection).toBe("entry");
    expect(host?.getAttribute("aria-hidden")).toBe("true");
    expect(getComputedStyle(host!).pointerEvents).toBe("none");

    portal.surfaceChanged("library");
    expect(document.querySelectorAll("#pdc-obsidian-portal")).toHaveLength(1);
    portal.surfaceChanged("game-details");
    expect(document.querySelectorAll("#pdc-obsidian-portal")).toHaveLength(1);
    portal.dispose();
  });

  it("moves the portrait artwork toward a proportional left dock without stretching it", () => {
    const callbacks = new Map<number, { callback: () => void; delay: number }>();
    let nextTimer = 0;
    const portal = startPortalTransition(document, {
      entryDurationMs: 200,
      setTimeout(callback, delay) {
        const id = ++nextTimer;
        callbacks.set(id, { callback, delay });
        return id;
      },
      clearTimeout(id) {
        callbacks.delete(id);
      },
    });

    portal.remember("https://cdn.example/game.jpg", new DOMRect(425, 238, 172, 299));
    portal.surfaceChanged("library");
    portal.beginEntry();

    const host = document.getElementById("pdc-obsidian-portal") as HTMLElement;
    expect(host.dataset.pdcPortalEntryState).toBe("covering");
    expect(host.style.opacity).toBe("1");
    expect(host.style.getPropertyValue("--pdc-portal-dock-x")).not.toBe("");
    expect(host.style.getPropertyValue("--pdc-portal-dock-y")).not.toBe("");
    expect(Number(host.style.getPropertyValue("--pdc-portal-dock-scale"))).toBeGreaterThan(1);
    expect(host.style.getPropertyValue("--pdc-portal-dock-scale-x")).toBe("");
    expect(host.style.getPropertyValue("--pdc-portal-dock-scale-y")).toBe("");

    portal.completeEntry();

    expect(host.dataset.pdcPortalEntryState).toBe("docked");
    const handoff = Array.from(callbacks.entries())[0];
    if (handoff) callbacks.delete(handoff[0]);
    handoff?.[1].callback();
    expect(host.dataset.pdcPortalEntryState).toBe("revealing");
    expect(host.style.opacity).toBe("0");
    expect(host.style.getPropertyValue("--pdc-portal-target-scale-x")).toBe("");
    expect(host.style.getPropertyValue("--pdc-portal-target-scale-y")).toBe("");
    expect(Array.from(callbacks.values()).map(({ delay }) => delay)).toEqual([200]);
    portal.dispose();
  });

  it("falls back to a bounded fade when details never completes the handoff", () => {
    const callbacks = new Map<number, { callback: () => void; delay: number }>();
    let nextTimer = 0;
    const portal = startPortalTransition(document, {
      entryTargetTimeoutMs: 100,
      fallbackDurationMs: 50,
      setTimeout(callback, delay) {
        const id = ++nextTimer;
        callbacks.set(id, { callback, delay });
        return id;
      },
      clearTimeout(id) {
        callbacks.delete(id);
      },
    });

    portal.remember("https://cdn.example/game.jpg", new DOMRect(425, 238, 172, 299));
    portal.surfaceChanged("library");
    portal.beginEntry();
    const wait = Array.from(callbacks.entries())[0];
    expect(wait?.[1].delay).toBe(100);

    if (wait) callbacks.delete(wait[0]);
    wait?.[1].callback();
    const host = document.getElementById("pdc-obsidian-portal") as HTMLElement;
    expect(host.dataset.pdcPortalEntryState).toBe("revealing");
    expect(host.style.opacity).toBe("0");
    const fallback = Array.from(callbacks.entries())[0];
    expect(fallback?.[1].delay).toBe(50);

    fallback?.[1].callback();
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();
    expect(document.documentElement.hasAttribute("data-pdc-portal-phase")).toBe(false);
    portal.dispose();
  });

  it("keeps the exit veil over the first restored library frame", () => {
    let expire: (() => void) | null = null;
    const portal = startPortalTransition(document, {
      setTimeout(callback) {
        expire = callback;
        return 1;
      },
      clearTimeout() {
        expire = null;
      },
    });

    portal.remember("https://cdn.example/game.jpg", new DOMRect(425, 238, 172, 299));
    portal.surfaceChanged("library");
    portal.surfaceChanged("game-details");
    portal.beginExit();
    expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalDirection).toBe("exit");
    expect(document.documentElement.dataset.pdcPortalPhase).toBe("exit");

    portal.surfaceChanged("library");
    expect(document.getElementById("pdc-obsidian-portal")).toBeTruthy();
    portal.remember("https://cdn.example/game.jpg", new DOMRect(425, 238, 172, 299));
    expect(portal.completeExit()).toBe(true);
    expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalExitState).toBe("returning");
    if (expire) (expire as () => void)();
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();
    expect(document.documentElement.hasAttribute("data-pdc-portal-phase")).toBe(false);
    portal.dispose();
  });

  it("targets only a freshly remembered centered library position on exit", () => {
    const portal = startPortalTransition(document, {
      setTimeout() {
        return 1;
      },
      clearTimeout() {},
    });

    portal.remember("https://cdn.example/game.jpg", new DOMRect(780, 80, 120, 210));
    portal.surfaceChanged("library");
    portal.surfaceChanged("game-details");
    portal.beginExit();

    const host = document.getElementById("pdc-obsidian-portal") as HTMLElement;
    expect(host.dataset.pdcPortalExitState).toBe("covering");
    expect(host.style.getPropertyValue("--pdc-portal-target-x")).toBe("");
    expect(host.style.getPropertyValue("--pdc-portal-target-y")).toBe("");
    expect(host.querySelector<HTMLElement>("[data-pdc-portal-artwork]")?.hidden).toBe(false);
    expect(portal.completeExit()).toBe(false);

    portal.surfaceChanged("library");
    portal.remember("https://cdn.example/game.jpg", new DOMRect(425, 238, 172, 299));
    expect(portal.completeExit()).toBe(true);
    expect(host.dataset.pdcPortalExitState).toBe("returning");
    expect(host.style.getPropertyValue("--pdc-portal-target-x")).toBe("511px");
    expect(host.style.getPropertyValue("--pdc-portal-target-y")).toBe("388px");
    expect(host.style.getPropertyValue("--pdc-portal-target-scale-x")).toBe("");
    expect(host.style.getPropertyValue("--pdc-portal-target-scale-y")).toBe("");
    expect(Number(host.style.getPropertyValue("--pdc-portal-target-scale"))).toBeGreaterThan(0);
    portal.dispose();
  });

  it("fails closed for unsafe artwork and always removes its host", () => {
    let expire: (() => void) | null = null;
    const portal = startPortalTransition(document, {
      setTimeout(callback) {
        expire = callback;
        return 1;
      },
      clearTimeout() {
        expire = null;
      },
    });

    portal.remember("javascript:alert(1)", new DOMRect(0, 0, 100, 100));
    portal.surfaceChanged("library");
    portal.surfaceChanged("game-details");
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();

    portal.remember("blob:https://steamloopback.host/art", new DOMRect(0, 0, 100, 100));
    portal.surfaceChanged("library-grid");
    portal.surfaceChanged("game-details");
    expect(document.getElementById("pdc-obsidian-portal")).toBeTruthy();
    if (expire) (expire as () => void)();
    if (expire) (expire as () => void)();
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();

    portal.surfaceChanged("library-grid");
    portal.surfaceChanged("game-details");
    document.dispatchEvent(new Event("visibilitychange"));
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();
    portal.dispose();
  });

  it("fails closed for non-finite or empty geometry even with safe artwork", () => {
    const portal = startPortalTransition(document, {
      setTimeout() {
        return 1;
      },
      clearTimeout() {},
    });

    portal.surfaceChanged("library-grid");
    portal.remember("https://cdn.example/game.jpg", new DOMRect(0, 0, 0, 299));
    portal.beginEntry();
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();

    portal.remember("https://cdn.example/game.jpg", new DOMRect(Number.NaN, 0, 172, 299));
    portal.beginEntry();
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();
    portal.dispose();
  });
});
