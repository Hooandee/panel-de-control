// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const menu = vi.hoisted(() => ({ current: null as any, hide: vi.fn() }));
vi.mock("@decky/ui", () => ({
  DropdownItem: ({label, rgOptions, selectedOption, disabled, onMenuWillOpen}: any) => <button className="Focusable" disabled={disabled} aria-label={label} onClick={() => { const nativeMenu = () => { throw new Error("native menu must not open twice"); }; if (onMenuWillOpen(nativeMenu) !== false) nativeMenu(); }}>{rgOptions.find((option: any) => option.data === selectedOption)?.label}</button>,
  Menu: () => null, MenuItem: () => null,
  showContextMenu: (element: any) => {
    menu.current = element;
    document.querySelectorAll(".gpfocus").forEach((node) => node.classList.remove("gpfocus"));
    return { Hide: menu.hide, Show: vi.fn() };
  },
}));
import { FocusReturningDropdown } from "./FocusReturningDropdown";
import { setQamDocument } from "../qamDocument";
const options = [{data: 1, label: "Lineal"}, {data: 2, label: "Vecino"}];
const focus = vi.fn((target: HTMLElement) => { target.classList.add("gpfocus"); target.focus(); return true; });
let registered = true;
beforeEach(() => {
  vi.useFakeTimers(); menu.current = null; menu.hide.mockClear(); focus.mockClear(); registered = true;
  setQamDocument(document);
  vi.stubGlobal("FocusNavController", { GetActiveNavTree: () => ({ m_Root: {
    m_rgChildren: registered ? Array.from(document.querySelectorAll<HTMLElement>(".Focusable")).map((element) => ({m_element: element, BTakeFocus: () => focus(element)})) : [],
  } }) });
});
afterEach(() => {cleanup(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals();});
const row = (onChange = vi.fn()) => <div className="pdc-root"><FocusReturningDropdown controlId="steam-filter" label="Filtro" selectedOption={1} rgOptions={options} onChange={onChange} /></div>;

it("B cancellation closes without changing selection and restores the opener through gamepad navigation", async () => {
  const change = vi.fn(); render(row(change));
  const opener = screen.getByRole("button", {name: "Filtro"}); opener.classList.add("gpfocus");
  fireEvent.click(opener);
  menu.current.props.onCancel();
  await act(async () => vi.advanceTimersByTimeAsync(0));
  expect(menu.hide).toHaveBeenCalledOnce(); expect(change).not.toHaveBeenCalled();
  expect(opener.textContent).toBe("Lineal"); expect(focus).toHaveBeenCalledWith(opener);
  expect(opener.classList.contains("gpfocus")).toBe(true);
});
it("finds the same control after QAM remount and waits for its navigation node", async () => {
  const first = render(row()); fireEvent.click(screen.getByRole("button", {name: "Filtro"}));
  const cancel = menu.current.props.onCancel; first.unmount();
  cancel(); await act(async () => vi.advanceTimersByTimeAsync(50));
  registered = false; render(row());
  const replacement = screen.getByRole("button", {name: "Filtro"});
  await act(async () => vi.advanceTimersByTimeAsync(50));
  expect(focus).not.toHaveBeenCalled(); registered = true;
  await act(async () => vi.advanceTimersByTimeAsync(50));
  expect(focus).toHaveBeenCalledWith(replacement);
});
it("selects once and also restores focus after confirming an option", async () => {
  const change = vi.fn(); render(row(change)); fireEvent.click(screen.getByRole("button", {name: "Filtro"}));
  const select = menu.current.props.children[1].props.onSelected;
  select(); select(); menu.current.props.onCancel();
  await act(async () => vi.advanceTimersByTimeAsync(0));
  expect(change).toHaveBeenCalledExactlyOnceWith(options[1]); expect(menu.hide).toHaveBeenCalledOnce();
  expect(focus).toHaveBeenCalledOnce();
});
it("does not steal focus if the player already moved to another Panel control", async () => {
  render(<>{row()}<div className="pdc-root"><button className="Focusable" aria-label="Otro" /></div></>);
  fireEvent.click(screen.getByRole("button", {name: "Filtro"}));
  screen.getByRole("button", {name: "Otro"}).classList.add("gpfocus");
  menu.current.props.onCancel(); await act(async () => vi.advanceTimersByTimeAsync(200));
  expect(focus).not.toHaveBeenCalled();
});
