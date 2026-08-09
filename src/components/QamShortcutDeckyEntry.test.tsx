// @vitest-environment happy-dom
import { ReactNode } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const openQuickAccessMenu = vi.hoisted(() => vi.fn());

vi.mock("../api", () => ({
  getUiPrefs: vi.fn(async () => ({})),
  setUiPrefs: vi.fn(async () => true),
}));

vi.mock("@decky/ui", () => ({
  Navigation: { OpenQuickAccessMenu: openQuickAccessMenu },
  PanelSection: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  PanelSectionRow: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ButtonItem: ({ children, description, onClick }: {
    children: ReactNode;
    description: ReactNode;
    onClick(): void;
  }) => <button onClick={onClick}>{children}<span>{description}</span></button>,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string) => ({
      "settings.qamShortcut.deckyEntry": "Abrir Panel de Control",
      "settings.qamShortcut.deckyEntry.desc": "Panel de Control ya tiene un icono propio en el QAM.",
      "settings.qamShortcut.deckyFallback": "Abrir aquí como respaldo",
      "settings.qamShortcut.deckyFallback.desc": "Desactiva temporalmente el acceso directo y abre el panel dentro de Decky.",
    })[key] ?? key,
  }),
}));

import { PDC_QAM_TAB_ID } from "../deckyInternal";
import { setQamShortcutEnabled, setQamShortcutRuntime } from "../system/qamShortcut";
import { QamShortcutDeckyEntry } from "./QamShortcutDeckyEntry";

let intersectionCallback: IntersectionObserverCallback;

class FakeResizeObserver {
  observe() {}
  disconnect() {}
}

class FakeIntersectionObserver {
  constructor(callback: IntersectionObserverCallback) {
    intersectionCallback = callback;
  }
  observe() {}
  disconnect() {}
}

function showFallbackPanel(): void {
  const host = screen.getByTestId("qam-panel-gate");
  const rect = { width: 268, height: 1 } as DOMRect;
  vi.spyOn(host, "getBoundingClientRect").mockReturnValue(rect);
  act(() => intersectionCallback([{
    target: host,
    time: 0,
    rootBounds: null,
    boundingClientRect: rect,
    intersectionRect: rect,
    isIntersecting: true,
    intersectionRatio: 1,
  }], {} as IntersectionObserver));
}

describe("QamShortcutDeckyEntry", () => {
  beforeEach(() => {
    setQamShortcutEnabled(true);
    setQamShortcutRuntime(true, true);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    window.ResizeObserver = FakeResizeObserver as unknown as typeof ResizeObserver;
    window.IntersectionObserver = FakeIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  afterEach(() => {
    cleanup();
    openQuickAccessMenu.mockClear();
    vi.restoreAllMocks();
  });

  it("opens the direct PDC tab without mounting the control center", () => {
    render(
      <QamShortcutDeckyEntry
        lifecycle={new AbortController()}
        fallbackLifecycle={new AbortController().signal}
      >
        <div data-testid="fallback-panel" />
      </QamShortcutDeckyEntry>,
    );

    fireEvent.click(screen.getByText("Abrir Panel de Control"));

    expect(openQuickAccessMenu).toHaveBeenCalledWith(PDC_QAM_TAB_ID);
    expect(screen.queryByTestId("fallback-panel")).toBeNull();
  });

  it("deactivates the direct tree before mounting the standard fallback", () => {
    const lifecycle = new AbortController();
    const abort = vi.spyOn(lifecycle, "abort");
    render(
      <QamShortcutDeckyEntry
        lifecycle={lifecycle}
        fallbackLifecycle={new AbortController().signal}
      >
        <div data-testid="fallback-panel" />
      </QamShortcutDeckyEntry>,
    );

    fireEvent.click(screen.getByText("Abrir aquí como respaldo"));

    expect(abort).toHaveBeenCalledOnce();
    showFallbackPanel();
    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
  });

  it("restores the fallback when the direct lifecycle is already inactive", () => {
    const lifecycle = new AbortController();
    lifecycle.abort();

    render(
      <QamShortcutDeckyEntry
        lifecycle={lifecycle}
        fallbackLifecycle={new AbortController().signal}
      >
        <div data-testid="fallback-panel" />
      </QamShortcutDeckyEntry>,
    );

    showFallbackPanel();
    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
  });

  it("switches to the standard panel when the direct lifecycle is aborted", () => {
    const lifecycle = new AbortController();
    render(
      <QamShortcutDeckyEntry
        lifecycle={lifecycle}
        fallbackLifecycle={new AbortController().signal}
      >
        <div data-testid="fallback-panel" />
      </QamShortcutDeckyEntry>,
    );

    act(() => lifecycle.abort());
    showFallbackPanel();
    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
  });

  it("shows the standard panel when the direct tab is disabled", () => {
    setQamShortcutEnabled(false);
    setQamShortcutRuntime(false, false);

    render(
      <QamShortcutDeckyEntry
        lifecycle={new AbortController()}
        fallbackLifecycle={new AbortController().signal}
      >
        <div data-testid="fallback-panel" />
      </QamShortcutDeckyEntry>,
    );

    showFallbackPanel();
    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
    expect(screen.queryByText("Abrir Panel de Control")).toBeNull();
  });

  it("shows the standard panel when visibility observers are unavailable", () => {
    window.ResizeObserver = undefined as unknown as typeof ResizeObserver;
    window.IntersectionObserver = undefined as unknown as typeof IntersectionObserver;
    setQamShortcutRuntime(true, false);

    render(
      <QamShortcutDeckyEntry
        lifecycle={new AbortController()}
        fallbackLifecycle={new AbortController().signal}
      >
        <div data-testid="fallback-panel" />
      </QamShortcutDeckyEntry>,
    );

    expect(screen.getByTestId("fallback-panel")).toBeTruthy();
  });

  it("unmounts fallback content when the Decky panel becomes hidden", () => {
    const lifecycle = new AbortController();
    const fallbackLifecycle = new AbortController();

    render(
      <QamShortcutDeckyEntry lifecycle={lifecycle} fallbackLifecycle={fallbackLifecycle.signal}>
        <div data-testid="fallback-panel" />
      </QamShortcutDeckyEntry>,
    );
    fireEvent.click(screen.getByText("Abrir aquí como respaldo"));

    showFallbackPanel();
    expect(screen.getByTestId("fallback-panel")).toBeTruthy();

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    fireEvent(document, new Event("visibilitychange"));

    expect(screen.queryByTestId("fallback-panel")).toBeNull();
  });
});
