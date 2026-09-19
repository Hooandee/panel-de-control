// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { FC, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const onScope = vi.hoisted(() => vi.fn());

vi.mock("@decky/ui", () => ({
  Focusable: ({ children, ...props }: { children: ReactNode }) => <div {...props}>{children}</div>,
  PanelSectionRow: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../tdp/useTdp", () => ({
  useTdp: () => ({
    tdp: { supported: false, has_game_profile: false },
    game: { appid: "42", name: "Dante" },
    scope: "global",
    onScope,
    refresh: vi.fn(),
  }),
}));
vi.mock("../tdp/useTdpConflict", () => ({
  useTdpConflict: () => ({
    conflict: false,
    monitorOnly: false,
    takeoverAvailable: false,
    rivals: [],
  }),
}));
vi.mock("../customize/modules", () => ({
  useModules: () => new Set<string>(),
  setModuleDisabled: vi.fn(() => Promise.resolve()),
}));
vi.mock("../customize/moduleLogic", () => ({ effectiveEnabled: () => true }));
vi.mock("../api", () => ({ setSeenTdpConflictTakeover: vi.fn(() => Promise.resolve()) }));
vi.mock("../components/TdpConflictModal", () => ({ openTdpConflictModal: vi.fn() }));

import { PotenciaProviderMount } from "./providerMounts";

const PowerMount = PotenciaProviderMount as FC<{
  children: ReactNode;
  showProfileSelector?: boolean;
}>;

describe("PotenciaProviderMount profile scope", () => {
  afterEach(() => {
    onScope.mockReset();
    cleanup();
  });

  it("does not add a profile selector when no visible block consumes it", () => {
    render(
      <PowerMount showProfileSelector={false}>
        <div>desktop-power</div>
      </PowerMount>,
    );

    expect(screen.queryByText("tdp.scope.global")).toBeNull();
    expect(screen.getByText("desktop-power")).toBeTruthy();
  });

  it("keeps the shared global and game selector available when TDP is unsupported", () => {
    render(
      <PowerMount showProfileSelector>
        <div>steam-performance</div>
      </PowerMount>,
    );

    expect(screen.getByText("tdp.scope.global")).toBeTruthy();
    fireEvent.click(screen.getByText("tdp.scope.game"));
    expect(onScope).toHaveBeenCalledWith("game");
    expect(screen.getByText("steam-performance")).toBeTruthy();
  });
});
