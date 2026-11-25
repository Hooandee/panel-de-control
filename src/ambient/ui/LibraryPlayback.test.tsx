// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";
import { LibraryPlayback } from "./LibraryPlayback";

vi.mock("@decky/ui", () => ({
  GamepadButton: { DIR_LEFT: 11, DIR_RIGHT: 12 },
  Focusable: ({ children, onActivate, onGamepadFocus, onGamepadBlur, onGamepadDirection, focusable, onOptionsButton: _options, onOKActionDescription: _ok, onOptionsActionDescription: _description, noFocusRing: _ring, ...props }: any) => <div {...props} data-gamepad-focusable={String(!!(focusable ?? onActivate))}
    onClick={onActivate} onFocus={onGamepadFocus} onBlur={onGamepadBlur}
    onKeyDown={(event) => { if (!onGamepadDirection) return; const handled = onGamepadDirection({ detail: { button: event.key === "ArrowLeft" ? 11 : event.key === "ArrowRight" ? 12 : 10 }, preventDefault: () => event.preventDefault(), stopPropagation: () => event.stopPropagation() }); if (handled !== false) { event.preventDefault(); event.stopPropagation(); } }}>{children}</div>,
}));
vi.mock("../../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("./NowPlaying", () => ({
  RoundButton: ({ label, onActivate }: any) => <button onClick={onActivate}>{label}</button>,
  NowPlaying: ({ player, onToggle, media }: any) => <div>{media}{player.track.title}<button onClick={onToggle}>{player.status === "paused" ? "ambient.player.play" : "ambient.player.pause"}</button></div>,
}));
afterEach(cleanup);

it("keeps pause and resume available for the current track without starting another one", () => {
  const runtime = { pauseMusic: vi.fn(), resumeMusic: vi.fn() } as unknown as AmbientRuntime;
  const player = { track: { title: "Song" }, status: "playing" } as AmbientSnapshot["player"];
  const { rerender } = render(<LibraryPlayback inline runtime={runtime} player={player} />);
  expect(screen.getByText("Song")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "ambient.player.pause" }));
  expect(runtime.pauseMusic).toHaveBeenCalledOnce();
  rerender(<LibraryPlayback inline runtime={runtime} player={{ ...player, status: "retrying" }} />);
  fireEvent.click(screen.getByRole("button", { name: "ambient.player.pause" }));
  expect(runtime.pauseMusic).toHaveBeenCalledTimes(2);
  rerender(<LibraryPlayback inline runtime={runtime} player={{ ...player, status: "paused" }} />);
  fireEvent.click(screen.getByRole("button", { name: "ambient.player.play" }));
  expect(runtime.resumeMusic).toHaveBeenCalledOnce();
  rerender(<LibraryPlayback inline runtime={runtime} player={{ ...player, track: null, status: "idle" }} />);
  expect(screen.queryByRole("button")).toBeNull();
});

it("reserves a dock without creating a second card or media engine", () => {
  const runtime = { pauseMusic: vi.fn(), resumeMusic: vi.fn() } as unknown as AmbientRuntime;
  const player = { track: { title: "Film" }, video: true, status: "playing" } as AmbientSnapshot["player"];
  const { container } = render(<LibraryPlayback runtime={runtime} player={player} />);
  expect(container.querySelector("[data-library-player-dock]")).toBeTruthy();
  expect(container.querySelector("video,audio,iframe,.pdc-np")).toBeNull();
  expect(screen.queryByText("Film")).toBeNull();
});

it("gives video separate pause and seek targets without duplicate activation or horizontal navigation", () => {
  const runtime = { pauseMusic: vi.fn(), resumeMusic: vi.fn(), seekBy: vi.fn() } as unknown as AmbientRuntime;
  const player = { track: { title: "Film", live: false }, video: true, duration: 120, position: 20, status: "playing" } as AmbientSnapshot["player"];
  const navigation = vi.fn();
  const { container, rerender } = render(<div onKeyDown={navigation}><LibraryPlayback runtime={runtime} player={player} /></div>);
  fireEvent.click(container.querySelector('[data-library-control="toggle"]')!);
  expect(runtime.pauseMusic).toHaveBeenCalledOnce();
  const slider = screen.getByRole("slider");
  expect(slider.dataset.gamepadFocusable).toBe("true");
  fireEvent.keyDown(slider, { key: "ArrowRight" });
  fireEvent.keyDown(slider, { key: "ArrowLeft" });
  expect(runtime.seekBy).toHaveBeenNthCalledWith(1, 10);
  expect(runtime.seekBy).toHaveBeenNthCalledWith(2, -10);
  expect(navigation).not.toHaveBeenCalled();
  fireEvent.keyDown(slider, { key: "ArrowDown" });
  expect(navigation).toHaveBeenCalledOnce();
  rerender(<LibraryPlayback runtime={runtime} player={{ ...player, duration: 0 }} />);
  expect(screen.queryByRole("slider")).toBeNull();
  rerender(<LibraryPlayback runtime={runtime} player={{ ...player, track: { ...player.track!, live: true } }} />);
  expect(screen.queryByRole("slider")).toBeNull();
});
