// @vitest-environment happy-dom
import { act, cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";

const games = vi.hoisted(() => [
  { liveAppid: 1, instanceKey: "1", name: "A", coverUrls: [], lastPlayed: 2, isNonSteam: false },
  { liveAppid: 2, instanceKey: "2", name: "B", coverUrls: [], lastPlayed: 1, isNonSteam: false },
]);
vi.mock("@decky/ui", () => ({ Focusable: ({ children }: any) => <div>{children}</div> }));
vi.mock("../api", () => ({
  getUpscalersOverview: vi.fn(async () => ({ builds: [], installs: {}, job: null, preferred: "fsr" })),
  getUpscalersCompat: vi.fn(async () => ({})),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../components/FocusableCard", () => ({ FocusableCard: ({ children }: any) => <div>{children}</div> }));
vi.mock("../components/GameCover", () => ({ GameCover: () => null }));
vi.mock("../launch/steamApi", () => ({ listInstalledGames: () => games.map((game) => ({ ...game })) }));
vi.mock("../upscalers/BulkPanel", () => ({ BulkPanel: () => null }));
vi.mock("../upscalers/overlays", () => ({
  IN_GAME_MODES: [], publishOverview: vi.fn(), readInGameMode: () => "start", setUpscalersSectionOpen: vi.fn(), writeInGameMode: vi.fn(),
}));
vi.mock("../upscalers/pageMemory", () => ({ showGame: vi.fn(), takeHeldPage: () => null }));
vi.mock("../upscalers/GameView", () => ({
  GameView: ({ game }: { game: { liveAppid: number } }) => {
    const [firstAppid] = useState(game.liveAppid);
    return <output data-testid="page">{`${firstAppid}:${game.liveAppid}`}</output>;
  },
}));

import { openUpscalersFor } from "../upscalers/deepLink";
import { EscaladoresSection } from "./EscaladoresSection";

vi.mock("../deckyInternal", () => ({ setActivePlugin: vi.fn() }));
vi.mock("./activeTab", () => ({ writeActiveTab: vi.fn() }));
vi.mock("./shellMode", () => ({ setShellMode: vi.fn() }));

afterEach(cleanup);

it("gives each requested game a fresh page instead of the previous game's state", async () => {
  await act(async () => { render(<EscaladoresSection />); });
  await act(async () => { openUpscalersFor(1); });
  expect(screen.getByTestId("page").textContent).toBe("1:1");
  await act(async () => { openUpscalersFor(2); });
  expect(screen.getByTestId("page").textContent).toBe("2:2");
});
