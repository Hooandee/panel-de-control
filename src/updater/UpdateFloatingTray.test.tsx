// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UpdateInfo } from "../api";

vi.mock("@decky/ui", () => ({
  Focusable: ({ onActivate, children, ...props }: any) => (
    <button {...props} onKeyDown={(event) => { if (event.key === "Enter") onActivate?.(); }}>{children}</button>
  ),
  showModal: vi.fn(),
}));
vi.mock("./useUpdate", () => ({ useUpdate: vi.fn() }));
vi.mock("../components/FocusRoot", () => ({ FocusRoot: ({ children }: any) => children }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));

import { showModal } from "@decky/ui";
let UpdateFloatingTray: typeof import("./UpdateFloatingTray").UpdateFloatingTray;
let UpdateModal: typeof import("./UpdateModal").UpdateModal;
let useFloatingTrayClaim: typeof import("../components/useFloatingTrayClaim").useFloatingTrayClaim;
let ColorPreviewConfirm: typeof import("../components/ColorPreviewConfirm").ColorPreviewConfirm;
let CleanerActionTray: typeof import("../cleaner/CleanerActionTray").CleanerActionTray;
const info: UpdateInfo = { current: "0.63.0", latest: "0.64.0", has_update: true, notes: "Release notes", download_url: "", error: "" };

beforeEach(async () => {
  vi.resetModules();
  vi.clearAllMocks();
  ({ UpdateFloatingTray } = await import("./UpdateFloatingTray"));
  ({ UpdateModal } = await import("./UpdateModal"));
  ({ useFloatingTrayClaim } = await import("../components/useFloatingTrayClaim"));
  ({ ColorPreviewConfirm } = await import("../components/ColorPreviewConfirm"));
  ({ CleanerActionTray } = await import("../cleaner/CleanerActionTray"));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });
const Claim = ({ active }: { active: boolean }) => { useFloatingTrayClaim(active); return null; };
const tray = (updateInfo: UpdateInfo | null = info) => <UpdateFloatingTray lang="es" info={updateInfo} status="idle" />;

describe("UpdateFloatingTray", () => {
  it("shows real update versions and a polite status", () => {
    render(tray());
    expect(screen.getByText("Nueva versión disponible")).toBeTruthy();
    expect(screen.getByText("v0.63.0 → v0.64.0")).toBeTruthy();
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite");
  });

  it.each([null, { ...info, has_update: false }])("stays absent without an available update: %j", (value) => {
    const { container } = render(tray(value));
    expect(container.innerHTML).toBe("");
  });

  it.each(["installing", "done"] as const)("stays absent while %s", (status) => {
    const { container } = render(<UpdateFloatingTray lang="es" info={info} status={status} />);
    expect(container.innerHTML).toBe("");
  });

  it.each(["touch", "gamepad"])("opens the existing modal with %s and ignores duplicate activation", (input) => {
    render(tray());
    const button = screen.getByRole("button", { name: "Actualizar" });
    if (input === "gamepad") fireEvent.keyDown(button, { key: "Enter" });
    else fireEvent.click(button);
    fireEvent.click(button);
    expect(showModal).toHaveBeenCalledOnce();
    const modal = vi.mocked(showModal).mock.calls[0][0] as any;
    expect(modal.type).toBe(UpdateModal);
    expect(modal.props).toEqual({ lang: "es", latest: "0.64.0", notes: "Release notes" });
  });

  it("hides during installation and returns on error", () => {
    const view = render(tray());
    view.rerender(<UpdateFloatingTray lang="es" info={info} status="installing" />);
    expect(view.container.innerHTML).toBe("");
    view.rerender(<UpdateFloatingTray lang="es" info={info} status="error" />);
    expect(screen.getByRole("button", { name: "Actualizar" })).toBeTruthy();
    view.rerender(<UpdateFloatingTray lang="es" info={info} status="done" />);
    expect(view.container.innerHTML).toBe("");
  });

  it("shows a newer release again after dismissing the previous one", () => {
    const view = render(tray());
    fireEvent.click(screen.getByRole("button", { name: "Más tarde" }));
    expect(screen.queryByRole("status")).toBeNull();
    view.rerender(tray({ ...info, latest: "0.65.0" }));
    expect(screen.getByText("v0.63.0 → v0.65.0")).toBeTruthy();
  });

  it("keeps dismissal across remounts without changing availability", () => {
    const view = render(tray());
    fireEvent.click(screen.getByRole("button", { name: "Más tarde" }));
    expect(screen.queryByRole("status")).toBeNull();
    view.unmount();
    const reopened = render(tray());
    expect(reopened.container.innerHTML).toBe("");
    expect(info.has_update).toBe(true);
  });

  it("waits until every active claimant releases the space", () => {
    const view = render(<>{tray()}<Claim active /><Claim active /></>);
    expect(screen.queryByRole("status")).toBeNull();
    view.rerender(<>{tray()}<Claim active={false} /><Claim active /></>);
    expect(screen.queryByRole("status")).toBeNull();
    view.rerender(tray());
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("yields to color confirmation and returns when it unmounts", () => {
    const view = render(<>{tray()}<ColorPreviewConfirm seconds={10} saving={false} onSave={vi.fn()} onDiscard={vi.fn()} /></>);
    expect(screen.queryByText("Nueva versión disponible")).toBeNull();
    view.rerender(tray());
    expect(screen.getByText("Nueva versión disponible")).toBeTruthy();
  });

  it("yields while a cleaner action tray is on screen", () => {
    const view = render(<><CleanerActionTray><button>Clean</button></CleanerActionTray>{tray()}</>);
    expect(screen.queryByRole("status")).toBeNull();
    view.rerender(tray());
    expect(screen.getByRole("status")).toBeTruthy();
  });


  it("sticks to the bottom of the QAM scroll instead of floating over a transformed ancestor", () => {
    render(tray());
    const card = screen.getByRole("status");
    expect(card.style.position).toBe("sticky");
    expect(card.style.bottom).toBe("16px");
  });

  it("reserves its height as scroll padding so gamepad focus stays visible, and restores it on dismissal", () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return new DOMRect(0, 0, 268, this.getAttribute("role") === "status" ? 120 : 500);
    });
    const view = render(<div data-testid="scroller" style={{ overflowY: "auto", scrollPaddingBottom: "4px" }}>{tray()}</div>);
    const scroller = screen.getByTestId("scroller");
    expect(scroller.style.scrollPaddingBottom).toBe("152px");
    fireEvent.click(screen.getByRole("button", { name: "Más tarde" }));
    expect(scroller.style.scrollPaddingBottom).toBe("4px");
    view.unmount();
  });
});
