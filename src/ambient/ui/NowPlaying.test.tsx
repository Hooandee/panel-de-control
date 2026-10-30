// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { PlayerSnapshot } from "../steam/player";
import { NowPlaying } from "./NowPlaying";

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, onClick, "aria-label": label }: any) => <div onClick={onClick} aria-label={label}>{children}</div>,
  SliderField: () => null,
}));
vi.mock("../../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
afterEach(cleanup);

it("shows the shared video slot inside the normal card with its existing playback controls", () => {
  const onToggle = vi.fn();
  const player = { track: { id: "film", title: "Film", url: "http://localhost/film.mp4", kind: "video", live: false }, status: "playing", video: true, volume: 0.6, position: 10, duration: 120, error: null } as PlayerSnapshot;
  const { container } = render(<NowPlaying player={player} media={<div data-testid="slot" />} onToggle={onToggle} onNext={vi.fn()} onPrevious={vi.fn()} onVolume={vi.fn()} />);
  expect(container.querySelector(".pdc-np")?.contains(screen.getByTestId("slot"))).toBe(true);
  fireEvent.click(screen.getByLabelText("ambient.player.pause"));
  expect(onToggle).toHaveBeenCalledOnce();
  expect(container.querySelector("video,iframe,audio")).toBeNull();
});
