// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { WorldMap } from "./WorldMap";

const nav = vi.hoisted(() => ({ props: {} as any }));
vi.mock("@decky/ui", () => ({ GamepadButton: { DIR_UP: 1, DIR_DOWN: 2, DIR_LEFT: 3, DIR_RIGHT: 4, TRIGGER_RIGHT: 5, TRIGGER_LEFT: 6 }, Focusable: (props: any) => { if (props.onActivate) nav.props = props; return <div>{props.children}</div>; } }));
vi.mock("./NowPlaying", () => ({ RoundButton: () => null }));
afterEach(cleanup);
it("lets the d-pad pass before A, consumes directions after A, and exits with B without clearing country", () => {
  const select = vi.fn(); const exit = vi.fn();
  function Harness() {
    const [active, setActive] = useState(false);
    return <WorldMap active={active} onActiveChange={setActive} onExit={exit} navigationHint={active ? "B: leave" : "A: explore"} countries={[{ code: "ES", name: "Spain", count: 10 }, { code: "FR", name: "France", count: 5 }]} stations={[]} loadingStations={false} loadingLabel="loading" selected="ES" playingUrl={null} playingCountry={null} onSelect={select} onPlay={vi.fn()} onViewChange={vi.fn()} zoomInLabel="+" zoomOutLabel="-" />;
  }
  render(<Harness />);
  const event = { detail: { button: 1 }, preventDefault: vi.fn(), stopPropagation: vi.fn() };
  expect(nav.props.onGamepadDirection).toBeUndefined();
  expect(nav.props.onButtonDown).toBeUndefined();
  expect(event.preventDefault).not.toHaveBeenCalled();
  expect(select).not.toHaveBeenCalled();
  act(() => nav.props.onActivate());
  expect(screen.getByText("B: leave")).toBeTruthy();
  act(() => nav.props.onGamepadDirection(event));
  expect(select).toHaveBeenCalledWith("FR");
  const unhandled = { ...event, detail: { button: 99 } };
  expect(nav.props.onGamepadDirection(unhandled)).toBe(false);
  expect(nav.props.onGamepadDirection({ ...event, detail: { button: 2 } })).toBe(false);
  select.mockClear();
  act(() => nav.props.onCancelButton(event));
  expect(exit).toHaveBeenCalledOnce();
  expect(event.stopPropagation).toHaveBeenCalled();
  expect(select).not.toHaveBeenCalled();
  expect(nav.props.onCancelButton).toBeUndefined();
  expect(nav.props.onGamepadDirection).toBeUndefined();
  expect(screen.getByText("A: explore")).toBeTruthy();
});
