// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { openThemeImagePicker } from "./ThemeImagePicker";

const modal = vi.hoisted(() => ({ view: null as null | { unmount(): void }, close: vi.fn(), parent: undefined as unknown }));
const ambient = vi.hoisted(() => ({ value: { runtime: {}, snapshot: { state: {}, error: null } } as { runtime: object | null; snapshot: { state: object | null; error: string | null } | null } }));

vi.mock("@decky/ui", () => ({
  ModalRoot: ({ children, onCancel }: any) => <div><button onClick={onCancel}>back</button>{children}</div>,
  showModal: (element: ReactElement, parent: unknown) => {
    modal.parent = parent;
    const close = () => { modal.close(); modal.view?.unmount(); };
    const props = element.props as object;
    const Component = element.type as any;
    modal.view = render(<Component {...props} closeModal={close} />);
    return { Close: close };
  },
}));
vi.mock("../../components/FocusRoot", () => ({ FocusRoot: ({ children }: any) => <>{children}</> }));
vi.mock("../../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./stationsParts", () => ({ DimDialog: () => null, Empty: ({ text }: any) => <div>{text}</div>, Sheet: ({ children }: any) => <>{children}</> }));
vi.mock("./useAmbient", () => ({ useAmbient: () => ambient.value }));
vi.mock("./FilesTab", () => ({
  FilesTab: ({ header, onClose, onPickPhoto }: any) => <div>
    {header}
    <button onClick={() => void onPickPhoto({ ref: "local:abc", kind: "image", name: "a.jpg", collection: "known.images" })}>pick</button>
    <button onClick={onClose}>close</button>
  </div>,
}));

afterEach(() => {
  cleanup();
  modal.close.mockReset();
  ambient.value = { runtime: {}, snapshot: { state: {}, error: null } };
});

const signal = () => new AbortController().signal;

describe("openThemeImagePicker", () => {
  it("opens over Big Picture with the theme's title and resolves the registered pick", async () => {
    const choose = vi.fn(async (ref: string) => ({ ref, url: "http://127.0.0.1:1/m/t/local%3Aabc" }));
    const result = openThemeImagePicker({ title: "Fondo de la página 2", choose }, signal());
    expect(modal.parent).toBe(window);
    expect(screen.getByText("Fondo de la página 2")).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByText("pick")); });
    await expect(result).resolves.toEqual({ ref: "local:abc", url: "http://127.0.0.1:1/m/t/local%3Aabc" });
    expect(choose).toHaveBeenCalledWith("local:abc");
    expect(modal.close).toHaveBeenCalledOnce();
  });

  it("stays open when the pick cannot be registered", async () => {
    const result = openThemeImagePicker({ choose: async () => null }, signal());
    expect(screen.getByText("ambient.pick.title")).toBeTruthy();
    await act(async () => { fireEvent.click(screen.getByText("pick")); });
    expect(modal.close).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("close"));
    await expect(result).resolves.toBeNull();
  });

  it("resolves null when the user backs out with B", async () => {
    const result = openThemeImagePicker({ choose: vi.fn() }, signal());
    fireEvent.click(screen.getByText("back"));
    await expect(result).resolves.toBeNull();
    expect(modal.close).toHaveBeenCalledOnce();
  });

  it("closes and resolves null when the theme goes away or Steam dismisses the modal", async () => {
    const controller = new AbortController();
    const aborted = openThemeImagePicker({ choose: vi.fn() }, controller.signal);
    controller.abort();
    await expect(aborted).resolves.toBeNull();
    expect(modal.close).toHaveBeenCalledOnce();
    const dismissed = openThemeImagePicker({ choose: vi.fn() }, signal());
    act(() => modal.view?.unmount());
    await expect(dismissed).resolves.toBeNull();
  });

  it("waits for Ambiente instead of failing while its backend loads", async () => {
    ambient.value = { runtime: null, snapshot: null };
    const result = openThemeImagePicker({ choose: vi.fn() }, signal());
    expect(screen.getByText("ambient.lib.loading")).toBeTruthy();
    fireEvent.click(screen.getByText("back"));
    await expect(result).resolves.toBeNull();
  });
});
