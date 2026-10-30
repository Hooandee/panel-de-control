// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../qamDocument", () => ({ onQamDocument: () => () => undefined }));
vi.mock("../system/uiActivity", () => ({ findQamNavigationDocument: () => null }));

import { onQamLeftEdge, subscribeQamSurface } from "./qamSurface";

describe("qam surface", () => {
  afterEach(() => vi.useRealTimers());

  it("reports the document and follows its visibility", () => {
    const seen: (boolean | null)[] = [];
    let state = "hidden";
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
    const stop = subscribeQamSurface((s) => seen.push(s ? s.visible : null), () => document);
    state = "visible";
    document.dispatchEvent(new Event("visibilitychange"));
    expect(seen).toEqual([false, true]);
    stop();
    document.dispatchEvent(new Event("visibilitychange"));
    expect(seen).toEqual([false, true]);
  });

  it("keeps looking until the QAM exists", () => {
    vi.useFakeTimers();
    let found: Document | null = null;
    const seen: unknown[] = [];
    const stop = subscribeQamSurface((s) => seen.push(s), () => found);
    expect(seen).toEqual([]);
    found = document;
    vi.advanceTimersByTime(2000);
    expect(seen.length).toBe(1);
    stop();
  });
});

describe("onQamLeftEdge", () => {
  function press(target: Element, button: number, left: number, width: number) {
    target.getBoundingClientRect = () => ({ left, width, top: 0, height: 40, right: left + width, bottom: 40, x: left, y: 0, toJSON: () => ({}) });
    target.dispatchEvent(new CustomEvent("vgp_onbuttondown", { bubbles: true, detail: { button } }));
  }

  it("fires only for left on the tab column", () => {
    const tab = document.createElement("div");
    const row = document.createElement("div");
    document.body.append(tab, row);
    const handler = vi.fn();
    const stop = onQamLeftEdge(document, handler);
    press(row, 11, 67, 280);
    press(tab, 10, 5, 50);
    expect(handler).not.toHaveBeenCalled();
    press(tab, 11, 5, 50);
    expect(handler).toHaveBeenCalledOnce();
    stop();
    press(tab, 11, 5, 50);
    expect(handler).toHaveBeenCalledOnce();
  });
});
