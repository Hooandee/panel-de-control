// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";
import { BackgroundView } from "./BackgroundView";
import { SoundView } from "./SoundView";
import { openBackgroundLibrary } from "./BackgroundLibrary";
import { openMediaLibrary } from "./StationsModal";

vi.mock("@decky/ui", () => ({ Focusable: ({ children }: any) => <div>{children}</div> }));
vi.mock("../../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../steam/runtime", () => ({ gameName: (id: string) => id, favoriteToStation: (favorite: unknown) => favorite }));
vi.mock("../steam/player", () => ({ trackSource: () => "music" }));
vi.mock("./BackgroundLibrary", () => ({ openBackgroundLibrary: vi.fn() }));
vi.mock("./StationsModal", () => ({ openMediaLibrary: vi.fn() }));
vi.mock("./NowPlaying", () => ({
  RoundButton: ({ label, onActivate }: any) => <button onClick={onActivate}>{label}</button>,
  NowPlaying: () => <div>Now playing</div>,
}));
vi.mock("./primitives", () => ({
  Button: ({ label, onActivate }: any) => <button onClick={onActivate}>{label}</button>,
  Caption: ({ children }: any) => <div>{children}</div>,
  ChoiceRow: ({ label }: any) => <div>{label}</div>,
  ValueRow: ({ label }: any) => <div>{label}</div>,
  SliderRow: ({ label }: any) => <div>{label}</div>,
  CornerPicker: ({ label }: any) => <div>{label}</div>,
  ToggleRow: ({ label, checked, onChange }: any) => <label>{label}<input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /></label>,
  MoreSettings: ({ children }: any) => <div>{children}</div>,
  TileStrip: ({ children }: any) => <div>{children}</div>,
  Tile: ({ label, onActivate }: any) => <button onClick={onActivate}>{label}</button>,
  cardStyle: {},
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

function fixture(enabled = true, pinned = "") {
  const runtime = {
    loadPreviews: vi.fn(), markPageOpen: vi.fn(), updateSettings: vi.fn(),
    isFavoriteTrack: vi.fn(), canFavoriteTrack: vi.fn(), canShowVideo: vi.fn(),
  } as unknown as AmbientRuntime;
  const snapshot = {
    state: { collections: [], settings: {
      background: { enabled, pinned, perGame: {}, intervalSec: 60, collections: [], gameArt: "mine", order: "shuffle", transition: "fade" },
      collections: { favorites: [] }, radio: { favorites: [] }, music: { enabled: true },
    } },
    current: { kind: "video", ref: "local:clip", name: "Clip", collection: "folder" },
    items: [{ ref: "local:clip" }], previewUrl: "http://localhost/clip", previews: {},
    scan: { music: [], collections: {} }, coveredBy: [], optimizing: false,
    player: { track: null, status: "idle" }, motion: "play",
  } as unknown as AmbientSnapshot;
  return { runtime, snapshot };
}

it("shows only the background switch while disabled, even with pending media status", () => {
  const props = fixture(false);
  props.snapshot.optimizing = true;
  props.snapshot.error = "no_space";
  const { container } = render(<BackgroundView {...props} />);
  expect(container.firstElementChild?.children.length).toBe(1);
  expect(screen.getByRole<HTMLInputElement>("checkbox").checked).toBe(false);
  expect(container.querySelector("video")).toBeNull();
  expect(screen.queryByText("ambient.lib.open")).toBeNull();
  expect(screen.queryByText("ambient.bg.change")).toBeNull();
  fireEvent.click(screen.getByRole("checkbox"));
  const update = vi.mocked(props.runtime.updateSettings).mock.calls[0][0];
  expect(update(props.snapshot.state!.settings).background.enabled).toBe(true);
});

it("places the background switch first and library directly below the enabled preview", () => {
  const props = fixture();
  const { container } = render(<BackgroundView {...props} />);
  const card = container.firstElementChild!;
  expect(card.children[0].textContent).toBe("ambient.bg.enabled");
  expect(card.children[1].querySelector("video")?.src).toBe("http://localhost/clip");
  expect(card.children[2]).toBe(screen.getByRole("button", { name: "ambient.lib.open" }));
  fireEvent.click(card.children[2]);
  expect(openBackgroundLibrary).toHaveBeenCalledOnce();
  expect(screen.getByText("ambient.bg.interval")).toBeTruthy();
  expect(screen.getByText("ambient.bg.order")).toBeTruthy();
  expect(screen.getByText("ambient.bg.transition")).toBeTruthy();
});

it("keeps the fixed/rotation choice but hides rotation options for a fixed background", () => {
  render(<BackgroundView {...fixture(true, "local:clip")} />);
  expect(screen.getByText("ambient.bg.change")).toBeTruthy();
  expect(screen.queryByText("ambient.bg.interval")).toBeNull();
  expect(screen.queryByText("ambient.bg.order")).toBeNull();
  expect(screen.queryByText("ambient.bg.transition")).toBeNull();
});

it("opens the music library directly below the player and before favorites", () => {
  render(<SoundView {...fixture()} />);
  const library = screen.getByRole("button", { name: "ambient.lib.open" });
  expect(screen.getByText("Now playing").nextElementSibling).toBe(library);
  expect(library.nextElementSibling).toBe(screen.getByText("ambient.radio.favorites"));
  fireEvent.click(library);
  expect(openMediaLibrary).toHaveBeenCalledWith("music");
});
