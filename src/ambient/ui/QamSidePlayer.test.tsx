// @vitest-environment happy-dom
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QamSidePlayer } from "./QamSidePlayer";

const platform = vi.hoisted(() => ({ keyboard: null as ((showing: boolean) => void) | null }));

vi.mock("@decky/ui", () => ({ findSP: () => window }));
vi.mock("../../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../../platform/qamSurface", () => ({
  subscribeQamSurface: (listener: (surface: { document: Document; visible: boolean }) => void) => {
    listener({ document, visible: true });
    return () => undefined;
  },
  qamPanelWidth: () => 300,
}));
vi.mock("../../platform/virtualKeyboard", () => ({
  subscribeVirtualKeyboard: (listener: (showing: boolean) => void) => {
    platform.keyboard = listener;
    listener(false);
    return () => { platform.keyboard = null; };
  },
}));
vi.mock("./NowPlaying", () => ({ NowPlaying: () => <div data-testid="side-card" /> }));
vi.mock("./useAmbient", () => ({
  useAmbient: () => ({
    runtime: { pauseMusic: vi.fn(), resumeMusic: vi.fn(), nextTrack: vi.fn(), previousTrack: vi.fn(), seekFraction: vi.fn(), setVolume: vi.fn(), isFavoriteTrack: () => false, canFavoriteTrack: () => false, canShowVideo: () => false, startOverlayControl: vi.fn() },
    snapshot: {
      inGame: false,
      pageOpen: false,
      videoCollapsed: false,
      state: { settings: { music: { qamPlayer: true } } },
      player: { status: "playing", video: false, track: { id: "a", title: "Song" } },
    },
  }),
}));

afterEach(() => {
  cleanup();
  document.getElementById("pdc-ambient-qam-player")?.remove();
});

describe("QamSidePlayer", () => {
  it("steps aside while Steam's on-screen keyboard is showing", () => {
    render(<QamSidePlayer />);
    expect(document.querySelector("[data-testid=side-card]")).not.toBeNull();

    act(() => platform.keyboard?.(true));
    expect(document.querySelector("[data-testid=side-card]")).toBeNull();

    act(() => platform.keyboard?.(false));
    expect(document.querySelector("[data-testid=side-card]")).not.toBeNull();
  });
});
