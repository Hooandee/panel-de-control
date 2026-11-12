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

it("names Mako and Lossless in the list instead of the game's own techniques", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersOverview).mockResolvedValueOnce({ builds: [], installs: {}, job: null, preferred: "fsr",
    engines: { "1": { mako: { spatial: true, fg: true, multiplier: 2 } }, "2": { lossless: { multiplier: 4 } } } } as never);
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({ "1": { inputs: ["DLSS", "XeSS"], native: false } } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.getByText("Mako ×2")).toBeTruthy();
  expect(screen.getByText("Lossless ×4")).toBeTruthy();
  expect(screen.queryByText("DLSS, XeSS")).toBeNull();
});

it("leaves out store shortcuts with no installed game behind them", async () => {
  const api = await import("../api");
  vi.mocked(api.getUpscalersCompat).mockResolvedValueOnce({
    "1": { inputs: [], native: false, unavailable: "unifideck_not_installed" }, "2": { inputs: [], native: true },
  } as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.queryByText("A")).toBeNull();
  expect(screen.getByText("B")).toBeTruthy();
  expect(screen.getByText("up.list.linux")).toBeTruthy();
});

it("holds shortcuts back until it knows whether a game is behind them", async () => {
  const api = await import("../api");
  games.push({ liveAppid: 3, instanceKey: "3", name: "Shortcut", coverUrls: [], lastPlayed: 0, isNonSteam: true });
  let answer: (value: unknown) => void = () => undefined;
  vi.mocked(api.getUpscalersCompat).mockReturnValueOnce(new Promise((resolve) => { answer = resolve; }) as never);
  await act(async () => { render(<EscaladoresSection />); });
  expect(screen.queryByText("Shortcut")).toBeNull();
  expect(screen.getByText("A")).toBeTruthy();
  await act(async () => { answer({ "3": { inputs: ["DLSS"], native: false } }); });
  expect(screen.getByText("Shortcut")).toBeTruthy();
  games.pop();
});

it("asks for compatibility in batches the backend accepts", async () => {
  const api = await import("../api");
  const extra = Array.from({ length: 399 }, (_, i) => ({ liveAppid: 1000 + i, instanceKey: `x${i}`, name: `G${i}`, coverUrls: [], lastPlayed: 0, isNonSteam: false }));
  games.push(...extra);
  vi.mocked(api.getUpscalersCompat).mockClear();
  await act(async () => { render(<EscaladoresSection />); });
  const sizes = vi.mocked(api.getUpscalersCompat).mock.calls.map(([ids]) => ids.length);
  expect(sizes).toEqual([400, 1]);
  games.splice(2, extra.length);
});
