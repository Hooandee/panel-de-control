// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import {
  forwardRef,
  type HTMLAttributes,
  type ReactNode,
  useRef,
  useState,
} from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeviceInfo, LearningStatus } from "../api";
import type { SectionDef } from "../sections/types";

type CancelEvent = { stopPropagation(): void };
type ControllerInputCallback = (
  controllerIndex: number,
  gamepadButton: number,
  isButtonPressed: boolean,
) => void;

type FocusableProps = HTMLAttributes<HTMLDivElement> & {
  children?: ReactNode;
  navEntryPreferPosition?: number;
  onActivate?: () => void;
  onCancel?: (event: CancelEvent) => void;
  preferredFocus?: boolean;
};

const boundaries = vi.hoisted(() => ({ nextId: 0 }));
const focusNavigation = vi.hoisted(() => ({ focus: vi.fn(), available: true }));
const controller = vi.hoisted(() => ({
  callback: null as ControllerInputCallback | null,
  register: vi.fn(),
  unregister: vi.fn(),
}));

vi.mock("@decky/ui", () => ({
  getFocusNavController: () => focusNavigation.available ? { FocusElement: focusNavigation.focus } : undefined,
  NavEntryPositionPreferences: { PREFERRED_CHILD: 4 },
  Focusable: forwardRef<HTMLDivElement, FocusableProps>(function Focusable(
    {
      children,
      navEntryPreferPosition,
      onActivate: _onActivate,
      onCancel,
      onClick,
      preferredFocus,
      ...props
    },
    ref,
  ) {
    return (
      <div
        ref={ref}
        tabIndex={0}
        data-has-on-cancel={onCancel ? "true" : undefined}
        data-nav-entry-prefer-position={navEntryPreferPosition}
        data-preferred-focus={preferredFocus ? "true" : undefined}
        onClick={onClick}
        onContextMenu={onCancel ? (event) => onCancel(event) : undefined}
        {...props}
      >
        {children}
      </div>
    );
  }),
  PanelSection: ({ children }: { children?: ReactNode }) => (
    <section data-testid="panel-section">{children}</section>
  ),
  PanelSectionRow: ({ children }: { children?: ReactNode }) => (
    <div data-testid="panel-section-row">{children}</div>
  ),
  ErrorBoundary: ({ children }: { children?: ReactNode }) => {
    const instance = useRef(0);
    if (instance.current === 0) instance.current = ++boundaries.nextId;
    return <div data-testid="error-boundary" data-instance={instance.current}>{children}</div>;
  },
}));

vi.mock("@decky/api", () => ({ callable: () => async () => ({}) }));

import { getQamDocument } from "../qamDocument";
import { getShellMode, setShellMode } from "../sections/shellMode";
import { ControlCenterShell, type ControlCenterShellProps } from "./ControlCenterShell";

const Power = () => <div data-testid="power-body">power<button>Power control</button></div>;
const Settings = () => <div data-testid="settings-body">settings</div>;
const testIcon = () => <span data-testid="test-section-icon" aria-hidden="true" />;
const testSections: SectionDef[] = [
  {
    id: "power",
    labelKey: "nav.power",
    descriptionKey: "nav.power.desc",
    accent: "#287d8c",
    icon: testIcon,
    learningTags: ["tdp"],
    Component: Power,
  },
  {
    id: "settings",
    labelKey: "nav.settings",
    descriptionKey: "nav.settings.desc",
    accent: "#626b73",
    icon: testIcon,
    Component: Settings,
  },
];

const testDevice: DeviceInfo = {
  key: "test-device",
  display_name: "Test Device",
  chip: "Test APU",
  vendor: "amd",
  tdp_min: 5,
  tdp_default: 15,
  tdp_max: 30,
  tdp_max_charger: 30,
  is_generic: false,
  experimental: false,
  cooler_max: null,
  experimental_tdp_max_ac: null,
  gpu_gen: "rdna3",
  charger_only_extra: false,
};

const pausedLearning: LearningStatus = {
  telemetry_enabled: false,
  tdp_supported: true,
  fan_supported: true,
};

const activeLearning: LearningStatus = {
  telemetry_enabled: true,
  tdp_supported: true,
  fan_supported: true,
};

function renderShell(overrides: Partial<ControlCenterShellProps> = {}) {
  return render(
    <ControlCenterShell
      device={testDevice}
      gameName={null}
      learning={null}
      sections={testSections}
      activeId="power"
      showHome={true}
      showDeviceHeader={true}
      hasUpdate={false}
      onSelectSection={vi.fn()}
      {...overrides}
    />,
  );
}

function alertDotWithin(root: Element): HTMLElement | undefined {
  return Array.from(root.querySelectorAll<HTMLElement>("span")).find(
    (element) => element.style.width === "8px" && element.style.height === "8px",
  );
}

describe("ControlCenterShell", () => {
  const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;

  beforeEach(() => {
    window.localStorage.setItem("panel-de-control-lang", "es");
    setShellMode("home");
    boundaries.nextId = 0;
    focusNavigation.available = true;
    focusNavigation.focus.mockReset();
    focusNavigation.focus.mockImplementation((element: HTMLElement) => element.focus());
    controller.callback = null;
    controller.register.mockReset();
    controller.unregister.mockReset();
    controller.register.mockImplementation((callback: ControllerInputCallback) => {
      controller.callback = callback;
      return { unregister: controller.unregister };
    });
    Object.defineProperty(globalThis, "SteamClient", {
      configurable: true,
      value: { Input: { RegisterForControllerInputMessages: controller.register } },
    });
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.localStorage.clear();
    Reflect.deleteProperty(globalThis, "SteamClient");
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: originalScrollIntoView,
    });
  });

  it("mounts no section and no TabBar on Home", () => {
    const { container } = renderShell();

    expect(screen.queryByTestId("power-body")).toBeNull();
    expect(container.querySelector(".pdc-tabstrip")).toBeNull();
    expect(screen.getByTestId("dashboard")).toBeTruthy();
    expect(screen.queryByTestId("section-body")).toBeNull();
  });

  it("hides device identification when the user disables it", () => {
    renderShell({ showDeviceHeader: false });

    expect(screen.queryByTestId("device-pill")).toBeNull();

    act(() => setShellMode("tabs"));
    expect(screen.queryByTestId("device-pill")).toBeNull();

    act(() => setShellMode("detail"));
    expect(screen.queryByTestId("device-pill")).toBeNull();
  });

  it("keeps a compact device pill before the navigation in every view", () => {
    renderShell();

    const dashboardPill = screen.getByTestId("device-pill");
    expect(within(dashboardPill).getByText("Test APU")).toBeTruthy();
    expect(dashboardPill.style.width).toBe("fit-content");
    expect(dashboardPill.closest('[data-testid="tabs-back-row"]')).toBeNull();
    expect(dashboardPill.closest('[data-testid="detail-back-row"]')).toBeNull();
    expect(dashboardPill.compareDocumentPosition(screen.getByTestId("dashboard-grid")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    act(() => setShellMode("tabs"));

    const tabsPill = screen.getByTestId("device-pill");
    expect(within(tabsPill).queryByText("Test APU")).toBeNull();
    expect(within(screen.getByTestId("tabs-back-row")).getByTestId("device-pill")).toBe(tabsPill);
    expect(tabsPill.compareDocumentPosition(screen.getByTestId("tabs-carousel")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    act(() => setShellMode("detail"));

    const detailPill = screen.getByTestId("device-pill");
    expect(within(detailPill).queryByText("Test APU")).toBeNull();
    expect(within(screen.getByTestId("detail-back-row")).getByTestId("device-pill")).toBe(detailPill);
  });

  it("opens exactly one full-screen section from a card", () => {
    const { container } = renderShell();

    fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));

    expect(screen.getByTestId("power-body")).toBeTruthy();
    expect(container.querySelector(".pdc-tabstrip")).toBeNull();
    expect(screen.getAllByTestId("section-body")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Inicio" })).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Cambiar sección" })).toBeNull();
    expect(screen.queryByText("Potencia")).toBeNull();
  });

  describe("focus after a local navigation action", () => {
    let frames: FrameRequestCallback[];
    const flushFrames = () => act(() => frames.splice(0).forEach((callback) => callback(0)));

    beforeEach(() => {
      frames = [];
      vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
        frames.push(callback);
        return frames.length;
      });
      vi.spyOn(HTMLElement.prototype, "getClientRects").mockImplementation(() => [new DOMRect(0, 0, 100, 30)] as unknown as DOMRectList);
    });

    it("transfers active focus into Detail and back so the next activation opens immediately", () => {
      renderShell();
      fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));
      flushFrames();
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Power control" }));

      fireEvent.contextMenu(screen.getByTestId("shell-surface"));
      flushFrames();
      expect(document.activeElement).toBe(screen.getByRole("button", { name: /Potencia/ }));
      fireEvent.click(document.activeElement!);
      expect(screen.getByTestId("power-body")).toBeTruthy();
    });

    it("uses the return action when a section has no actionable controls", () => {
      renderShell({ activeId: "settings" });
      fireEvent.click(screen.getByRole("button", { name: /Ajustes/ }));
      flushFrames();
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Inicio" }));
    });

    it("does not claim focus for initial rendering or external mode changes", () => {
      renderShell();
      flushFrames();
      act(() => setShellMode("detail"));
      flushFrames();
      expect(focusNavigation.focus).not.toHaveBeenCalled();
    });

    it("does not focus a destination after the shell unmounts", () => {
      const view = renderShell();
      fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));
      view.unmount();
      flushFrames();
      expect(focusNavigation.focus).not.toHaveBeenCalled();
    });

    it("preserves a new focus owner outside the shell", () => {
      renderShell();
      fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));
      const otherSurface = document.createElement("button");
      otherSurface.className = "gpfocus";
      document.body.append(otherSurface);
      otherSurface.focus();
      flushFrames();
      expect(document.activeElement).toBe(otherSurface);
      expect(focusNavigation.focus).not.toHaveBeenCalled();
      otherSurface.remove();
    });

    it("retains keyboard focus when the Steam focus controller is unavailable", () => {
      focusNavigation.available = false;
      renderShell();
      fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));
      flushFrames();
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Power control" }));
    });
  });

  it("uses a full-width device identification in Tabs without Home", () => {
    renderShell({ showHome: false });
    const pill = screen.getByTestId("device-pill");
    expect(within(pill).getByText("Test Device")).toBeTruthy();
    expect(within(pill).getByText("Test APU")).toBeTruthy();
    expect(pill.style.width).toBe("100%");
    expect(screen.queryByTestId("tabs-back-row")).toBeNull();
  });

  it("resets the QAM scroll when opening a Dashboard destination", () => {
    render(
      <div data-testid="scroll-host" style={{ overflowY: "auto" }}>
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId="power"
          showHome
          showDeviceHeader
          hasUpdate={false}
          onSelectSection={vi.fn()}
        />
      </div>,
    );
    const host = screen.getByTestId("scroll-host");
    host.scrollTop = 320;
    host.scrollLeft = 48;

    fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));

    expect(host.scrollTop).toBe(0);
    expect(host.scrollLeft).toBe(48);
  });

  it("prefers the QAM viewport over a nearer non-scrolling overflow wrapper", () => {
    render(
      <div id="quickaccess_content_999" data-testid="qam-scroll-host" style={{ overflowY: "auto" }}>
        <div data-testid="inner-overflow" style={{ overflowY: "auto" }}>
          <ControlCenterShell
            device={testDevice}
            gameName={null}
            learning={null}
            sections={testSections}
            activeId="power"
            showHome
            showDeviceHeader
            hasUpdate={false}
            onSelectSection={vi.fn()}
          />
        </div>
      </div>,
    );
    const qamHost = screen.getByTestId("qam-scroll-host");
    qamHost.scrollTop = 320;

    fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));

    expect(qamHost.scrollTop).toBe(0);
  });

  it("reapplies the reset once after Decky reconciles focus", () => {
    let nextFrame: FrameRequestCallback | undefined;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      nextFrame = callback;
      return 1;
    });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    render(
      <div id="quickaccess_content_999" data-testid="scroll-host" style={{ overflowY: "auto" }}>
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId="power"
          showHome
          showDeviceHeader
          hasUpdate={false}
          onSelectSection={vi.fn()}
        />
      </div>,
    );
    const host = screen.getByTestId("scroll-host");
    host.scrollTop = 320;

    fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));
    host.scrollTop = 180;

    expect(nextFrame).toBeTypeOf("function");
    act(() => nextFrame?.(0));
    expect(host.scrollTop).toBe(0);
  });

  it("keeps the Dashboard position when returning from a detail", () => {
    setShellMode("detail");
    render(
      <div id="quickaccess_content_999" data-testid="scroll-host" style={{ overflowY: "auto" }}>
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId="settings"
          showHome
          showDeviceHeader
          hasUpdate={false}
          onSelectSection={vi.fn()}
        />
      </div>,
    );
    const host = screen.getByTestId("scroll-host");
    host.scrollTop = 240;

    act(() => setShellMode("home"));

    expect(host.scrollTop).toBe(240);
  });

  it("cancels the pending focus reconciliation reset on unmount", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 17);
    const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    setShellMode("detail");
    const view = render(
      <div id="quickaccess_content_999" style={{ overflowY: "auto" }}>
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId="power"
          showHome
          showDeviceHeader
          hasUpdate={false}
          onSelectSection={vi.fn()}
        />
      </div>,
    );

    view.unmount();

    expect(cancelAnimationFrame).toHaveBeenCalledExactlyOnceWith(17);
  });

  it("opens a compact icon carousel below a separate Home row", () => {
    const { container } = renderShell();

    act(() => setShellMode("tabs"));

    const backRow = screen.getByTestId("tabs-back-row");
    const carousel = screen.getByTestId("tabs-carousel");

    expect(container.querySelector(".pdc-tabstrip")).toBeNull();
    expect(within(backRow).getByRole("button", { name: "Inicio" })).toBeTruthy();
    expect(within(backRow).queryByText("B")).toBeNull();
    expect(backRow.style.minHeight).toBe("28px");
    expect(backRow.style.paddingBottom).toBe("");
    expect(backRow.style.borderBottom).toBe("");
    expect(backRow.nextElementSibling).toBe(carousel);
    expect(within(carousel).getByText("L1")).toBeTruthy();
    expect(within(carousel).getByText("Potencia")).toBeTruthy();
    expect(within(carousel).getAllByText("Ajustes")).toHaveLength(2);
    expect(within(carousel).getByText("R1")).toBeTruthy();
    const sectionIcons = within(carousel).getAllByTestId("test-section-icon");
    expect(sectionIcons).toHaveLength(1);
    expect(sectionIcons[0].parentElement?.style.color).toBe("white");
    expect(screen.getAllByTestId("section-body")).toHaveLength(1);
  });

  it("uses the localized label for an empty custom-view label in Dashboard and Tabs", () => {
    const customView: SectionDef = {
      id: "custom-view",
      label: "",
      labelKey: "customize.views.namePlaceholder",
      descriptionKey: "customize.views.cardDesc",
      accent: "#287d8c",
      icon: testIcon,
      Component: Power,
    };
    renderShell({ sections: [customView], activeId: "custom-view" });

    expect(screen.getByRole("button", { name: /^Mi vista\./ })).toBeTruthy();

    act(() => setShellMode("tabs"));

    const carousel = screen.getByTestId("tabs-carousel");
    expect(within(carousel).getByLabelText("Mi vista")).toBeTruthy();
  });

  it("uses Decky cancel only in Detail and visible-Home Tabs, stopping propagation", () => {
    const bubbled = vi.fn();
    const view = render(
      <div onContextMenu={bubbled}>
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId="power"
          showHome
          showDeviceHeader={true}
          hasUpdate={false}
          onSelectSection={vi.fn()}
        />
      </div>,
    );
    const surface = () => screen.getByTestId("shell-surface");

    expect(surface().dataset.hasOnCancel).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: /Potencia/ }));
    expect(surface().dataset.hasOnCancel).toBe("true");
    fireEvent.contextMenu(surface());
    expect(bubbled).not.toHaveBeenCalled();
    expect(screen.getByTestId("dashboard-grid")).toBeTruthy();
    expect(surface().dataset.hasOnCancel).toBeUndefined();

    act(() => setShellMode("tabs"));
    expect(surface().dataset.hasOnCancel).toBe("true");
    fireEvent.contextMenu(surface());
    expect(screen.getByTestId("dashboard-grid")).toBeTruthy();

    act(() => setShellMode("tabs"));
    view.rerender(
      <div onContextMenu={bubbled}>
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId="power"
          showHome={false}
          showDeviceHeader={true}
          hasUpdate={false}
          onSelectSection={vi.fn()}
        />
      </div>,
    );
    expect(surface().dataset.hasOnCancel).toBeUndefined();
    expect(screen.queryByRole("button", { name: "Inicio" })).toBeNull();
  });

  it("switches hidden Home to Tabs immediately and coordinated reactivation to Home without remount", () => {
    const { container, rerender } = renderShell();
    const root = container.querySelector(".pdc-root");

    rerender(
      <ControlCenterShell
        device={testDevice}
        gameName={null}
        learning={null}
        sections={testSections}
        activeId="power"
        showHome={false}
        showDeviceHeader={true}
        hasUpdate={false}
        onSelectSection={vi.fn()}
      />,
    );
    expect(screen.getByTestId("tabs-carousel")).toBeTruthy();
    expect(screen.queryByTestId("tabs-back-row")).toBeNull();
    expect(within(screen.getByTestId("tabs-device-row")).getByTestId("device-pill")).toBeTruthy();
    expect(getShellMode()).toBe("tabs");

    act(() => {
      rerender(
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId="power"
          showHome
          showDeviceHeader={true}
          hasUpdate={false}
          onSelectSection={vi.fn()}
        />,
      );
      setShellMode("home");
    });
    expect(screen.getByTestId("dashboard-grid")).toBeTruthy();
    expect(container.querySelector(".pdc-root")).toBe(root);
  });

  it("enables resolved shoulder navigation in tabs mode", () => {
    const onSelectSection = vi.fn();
    setShellMode("tabs");
    renderShell({ onSelectSection });

    act(() => controller.callback?.(0, 31, true));

    expect(onSelectSection).toHaveBeenCalledWith("settings");
  });

  it("resets the QAM scroll when changing section in Tabs", () => {
    const onSelectSection = vi.fn();
    setShellMode("tabs");

    function TabsCoordinator() {
      const [activeId, setActiveId] = useState("power");
      return (
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId={activeId}
          showHome
          showDeviceHeader
          hasUpdate={false}
          onSelectSection={(id) => {
            onSelectSection(id);
            setActiveId(id);
          }}
        />
      );
    }

    render(
      <div data-testid="scroll-host" style={{ overflowY: "auto" }}>
        <TabsCoordinator />
      </div>,
    );
    const host = screen.getByTestId("scroll-host");
    host.scrollTop = 320;

    act(() => controller.callback?.(0, 31, true));

    expect(host.scrollTop).toBe(0);
    expect(onSelectSection).toHaveBeenCalledWith("settings");
  });

  it("keeps shoulder navigation available inside a Dashboard detail", () => {
    const onSelectSection = vi.fn();
    setShellMode("detail");
    renderShell({ onSelectSection });

    act(() => controller.callback?.(0, 31, true));

    expect(onSelectSection).toHaveBeenCalledWith("settings");
  });

  it("uses a direct QAM destination only as the initial view", () => {
    const onSelectSection = vi.fn();
    setShellMode("home");
    renderShell({ initialMode: "detail", onSelectSection });

    expect(screen.getByTestId("power-body")).toBeTruthy();
    expect(screen.queryByTestId("dashboard")).toBeNull();
    act(() => controller.callback?.(0, 31, true));

    expect(onSelectSection).toHaveBeenCalledWith("settings");
    expect(getShellMode()).toBe("detail");
  });

  it("uses Inicio as the initial view even when another mode was stored", () => {
    setShellMode("tabs");

    renderShell({ initialMode: "home" });

    expect(screen.getByTestId("dashboard")).toBeTruthy();
    expect(getShellMode()).toBe("home");
  });

  it("returns a direct detail to Tabs when Home is hidden", () => {
    setShellMode("home");
    renderShell({ initialMode: "detail", showHome: false });

    fireEvent.click(screen.getByRole("button", { name: "Pestañas" }));

    expect(screen.getByTestId("tabs-carousel")).toBeTruthy();
    expect(getShellMode()).toBe("tabs");
  });

  it("returns a direct detail to Tabs with B when Home is hidden, then releases B to Steam", () => {
    const bubbled = vi.fn();
    setShellMode("home");
    render(
      <div onContextMenu={bubbled}>
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={testSections}
          activeId="power"
          initialMode="detail"
          showHome={false}
          showDeviceHeader
          hasUpdate={false}
          onSelectSection={vi.fn()}
        />
      </div>,
    );

    fireEvent.contextMenu(screen.getByRole("button", { name: "Power control" }));

    expect(screen.getByTestId("tabs-carousel")).toBeTruthy();
    expect(getShellMode()).toBe("tabs");
    expect(bubbled).not.toHaveBeenCalled();

    fireEvent.contextMenu(screen.getByTestId("shell-surface"));

    expect(bubbled).toHaveBeenCalledOnce();
  });

  it("keeps Tabs navigable by direct selection when controller input is unavailable", () => {
    const onSelectSection = vi.fn();
    Reflect.deleteProperty(globalThis, "SteamClient");
    setShellMode("tabs");
    renderShell({ showHome: false, onSelectSection });

    const carousel = screen.getByTestId("tabs-carousel");
    fireEvent.click(within(carousel).getAllByRole("button", { name: "Ajustes" })[0]);

    expect(onSelectSection).toHaveBeenCalledWith("settings");
  });

  it("disables shoulder selection on Home", () => {
    const onSelectSection = vi.fn();
    renderShell({ onSelectSection });

    act(() => controller.callback?.(0, 31, true));

    expect(onSelectSection).not.toHaveBeenCalled();
  });

  it.each(["detail", "tabs"] as const)("keeps %s mode when Learning opens Settings", (mode) => {
    const onSelectSection = vi.fn();
    setShellMode(mode);
    renderShell({ gameName: "Test Game", learning: pausedLearning, onSelectSection });

    fireEvent.click(screen.getByText("Activar en Ajustes"));

    expect(onSelectSection).toHaveBeenCalledExactlyOnceWith("settings");
    expect(getShellMode()).toBe(mode);
  });

  it("places detail navigation before Learning and section content", () => {
    setShellMode("detail");
    renderShell({ gameName: "Test Game", learning: pausedLearning });

    const home = screen.getByRole("button", { name: "Inicio" });
    const learning = screen.getByText("Aprendizaje en pausa");
    const content = screen.getByTestId("section-body");
    expect(home.compareDocumentPosition(learning) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(learning.compareDocumentPosition(content) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps section content clear of the bottom footer", () => {
    setShellMode("detail");
    renderShell();

    expect(screen.getByTestId("section-body").style.paddingBottom).toBe("18px");
  });

  it("hides paused Learning on Home even while a game is active", () => {
    renderShell({ gameName: "Test Game", learning: pausedLearning });

    expect(screen.queryByText("Aprendizaje en pausa")).toBeNull();
    expect(screen.queryByText("Activar en Ajustes")).toBeNull();
  });

  it.each([
    ["power", ["tdp"], "TDP", "Ventiladores"],
    ["fans", ["fans"], "Ventiladores", "TDP"],
    ["view:combined", ["tdp", "fans"], "TDP", null],
  ] as const)(
    "scopes active Learning in %s to its declared consumers",
    (activeId, learningTags, expectedTag, absentTag) => {
      const ScopedBody = () => <div>{activeId}</div>;
      const scopedSection: SectionDef = {
        id: activeId,
        label: activeId,
        labelKey: "nav.power",
        descriptionKey: "nav.power.desc",
        accent: "#287d8c",
        icon: testIcon,
        learningTags: [...learningTags],
        Component: ScopedBody,
      };
      setShellMode("detail");
      renderShell({
        gameName: "Test Game",
        learning: activeLearning,
        sections: [...testSections, scopedSection],
        activeId,
      });

      const title = screen.getByText("Aprendiendo de Test Game");
      const banner = title.parentElement?.parentElement;
      expect(banner).toBeTruthy();
      expect(within(banner!).getByText(expectedTag)).toBeTruthy();
      if (absentTag) expect(within(banner!).queryByText(absentTag)).toBeNull();
      if (activeId === "view:combined") {
        expect(within(banner!).getByText("Ventiladores")).toBeTruthy();
      }
    },
  );

  it("hides Learning in a non-learning section", () => {
    setShellMode("detail");
    renderShell({ gameName: "Test Game", learning: activeLearning, activeId: "settings" });

    expect(screen.queryByText("Aprendiendo de Test Game")).toBeNull();
  });

  it("renders the update dot beside Settings on Dashboard and the Tabs carousel", () => {
    const { container } = renderShell({ hasUpdate: true });
    const settingsCard = container.querySelector('[data-section-id="settings"]')!;
    const dashboardDot = alertDotWithin(settingsCard)!;

    expect(dashboardDot).toBeTruthy();
    expect(dashboardDot.style.marginLeft).toBe("");
    expect(dashboardDot.style.boxShadow).toContain("0 0 0 2px");
    expect(dashboardDot.parentElement?.style.position).toBe("absolute");
    act(() => setShellMode("tabs"));

    const settingsPreviews = screen
      .getByTestId("tabs-carousel")
      .querySelectorAll('[data-section-id="settings"]');
    expect(settingsPreviews).toHaveLength(2);
    settingsPreviews.forEach((preview) => {
      const dot = alertDotWithin(preview)!;
      expect(dot).toBeTruthy();
      expect(dot.style.marginLeft).toBe("");
      expect(dot.style.boxShadow).toContain("0 0 0 2px");
    });
  });

  it("corrects a disappeared active section and returns to Home", () => {
    const onSelectSection = vi.fn();
    setShellMode("detail");

    function CorrectingCoordinator() {
      const [activeId, setActiveId] = useState("power");
      return (
        <ControlCenterShell
          device={testDevice}
          gameName={null}
          learning={null}
          sections={[testSections[1]]}
          activeId={activeId}
          showHome
          showDeviceHeader={true}
          hasUpdate={false}
          onSelectSection={(id) => {
            onSelectSection(id);
            setActiveId(id);
          }}
        />
      );
    }

    render(<CorrectingCoordinator />);

    expect(screen.getByTestId("dashboard-grid")).toBeTruthy();
    expect(onSelectSection).toHaveBeenCalledExactlyOnceWith("settings");
    expect(getShellMode()).toBe("home");
  });

  it("keys the ErrorBoundary by active section while mounting one body", () => {
    setShellMode("detail");
    const { rerender } = renderShell();
    const powerBoundary = screen.getByTestId("error-boundary").dataset.instance;

    rerender(
      <ControlCenterShell
        device={testDevice}
        gameName={null}
        learning={null}
        sections={testSections}
        activeId="settings"
        showHome
        showDeviceHeader={true}
        hasUpdate={false}
        onSelectSection={vi.fn()}
      />,
    );

    expect(screen.getAllByTestId("section-body")).toHaveLength(1);
    expect(screen.getByTestId("settings-body")).toBeTruthy();
    expect(screen.getByTestId("error-boundary").dataset.instance).not.toBe(powerBoundary);
  });

  it("marks the last active card as preferred when returning Home", () => {
    setShellMode("detail");
    renderShell({ activeId: "settings" });

    fireEvent.contextMenu(screen.getByTestId("shell-surface"));

    expect(screen.getByTestId("dashboard-grid")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Ajustes/ }).dataset.preferredFocus).toBe("true");
  });

  it("mounts one QAM structure, DeviceHeader, and publishing FocusRoot on Home", () => {
    const { container } = renderShell({ gameName: "Test Game", learning: pausedLearning });

    expect(screen.getAllByTestId("panel-section")).toHaveLength(1);
    expect(screen.getAllByTestId("panel-section-row")).toHaveLength(1);
    expect(screen.getAllByText("Test Device")).toHaveLength(1);
    expect(screen.queryByText("Aprendizaje en pausa")).toBeNull();
    expect(container.querySelectorAll(".pdc-root")).toHaveLength(1);
    expect(getQamDocument()).toBe(container.ownerDocument);
  });
});
