// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ focus: vi.fn(() => true), hold: vi.fn(), menus: [] as any[] }));
vi.mock("../themes/runtime/navigationAccess", () => ({ createThemeNavigationAccess: () => ({ focus: mocks.focus }) }));
vi.mock("./pageMemory", () => ({ holdPage: mocks.hold }));
vi.mock("@decky/ui", () => ({ Dropdown: (props: any) => <button disabled={props.disabled} onClick={() => props.onMenuWillOpen(() => mocks.menus.push(props))}>{props.menuLabel}</button> }));
import { DuoDropdown } from "./DuoDropdown";
let id = 0;
beforeEach(() => { vi.useFakeTimers(); id++; });
afterEach(() => { cleanup(); vi.clearAllTimers(); vi.useRealTimers(); vi.clearAllMocks(); mocks.menus.length = 0; });
const props = () => ({ controlId: `game:1:flow:${id}`, label: "Flujo", value: "quality", options: [{ value: "quality", label: "Calidad" }, { value: "fast", label: "Rápido" }] });
const flush = () => act(() => { vi.runOnlyPendingTimers(); });
it("dispatches an old menu selection only to the live remounted control, once", () => {
  const old = vi.fn(), live = vi.fn();
  const config = props();
  const first = render(<DuoDropdown {...config} onChange={old} />);
  fireEvent.click(screen.getByRole("button"));
  expect(mocks.hold).toHaveBeenCalledOnce();
  const menu = mocks.menus[0];
  first.unmount();
  act(() => menu.onChange({ data: "fast" }));
  render(<DuoDropdown {...config} onChange={live} />);
  flush();
  expect(old).not.toHaveBeenCalled();
  expect(live).toHaveBeenCalledExactlyOnceWith("fast");
  act(() => menu.onChange({ data: "fast" }));
  flush();
  expect(live).toHaveBeenCalledOnce();
});
it("defers selection until the replacement is ready", () => {
  const config = props(), change = vi.fn();
  const first = render(<DuoDropdown {...config} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button"));
  const menu = mocks.menus[0]; first.unmount();
  const second = render(<DuoDropdown {...config} ready={false} onChange={change} />);
  act(() => menu.onChange({ data: "fast" })); flush();
  expect(change).not.toHaveBeenCalled();
  second.rerender(<DuoDropdown {...config} ready onChange={change} />); flush();
  expect(change).toHaveBeenCalledExactlyOnceWith("fast");
});
it("restores the opener after cancellation and remount without a pending selection", () => {
  const config = props(), change = vi.fn();
  const first = render(<DuoDropdown {...config} onChange={change} />);
  fireEvent.click(screen.getByRole("button")); first.unmount();
  render(<DuoDropdown {...config} onChange={change} />); flush();
  expect(change).not.toHaveBeenCalled();
  expect(mocks.focus).toHaveBeenCalledWith(screen.getByRole("button"));
});
it("cleans up deferred delivery when a live control unmounts", () => {
  const config = props(), old = vi.fn(), live = vi.fn();
  const first = render(<DuoDropdown {...config} onChange={old} />);
  fireEvent.click(screen.getByRole("button"));
  act(() => mocks.menus[0].onChange({ data: "fast" })); first.unmount(); flush();
  expect(old).not.toHaveBeenCalled();
  render(<DuoDropdown {...config} onChange={live} />); flush();
  expect(live).toHaveBeenCalledExactlyOnceWith("fast");
});

it("does not restore background focus while the native menu is open", () => {
  render(<DuoDropdown {...props()} onChange={vi.fn()} />);
  fireEvent.click(screen.getByRole("button"));
  flush();
  expect(mocks.focus).not.toHaveBeenCalled();
});

it("keeps icons visible when Steam replaces the selected label after mount", async () => {
  const view = render(<DuoDropdown {...props()} onChange={vi.fn()} />);
  const button = screen.getByRole("button");
  for (const name of ["mako", "optiscaler", "lossless", "dll"]) {
    await act(async () => {
      button.innerHTML = `<span><svg class="pdc-up-${name}-icon"></svg></span><svg class="arrow"></svg>`;
      await vi.runOnlyPendingTimersAsync();
    });
    const icon = button.querySelector<SVGElement>(`.pdc-up-${name}-icon`)!;
    expect(icon.style.display).toBe("inline-block");
    expect(icon.style.getPropertyPriority("display")).toBe("important");
    expect(button.querySelector<SVGElement>(".arrow")!.style.display).toBe("");
  }
  view.unmount();
});
