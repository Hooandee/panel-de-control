// @vitest-environment happy-dom
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ gameScan: vi.fn(), protonQueue: vi.fn(), protonScan: vi.fn() }));
vi.mock("../cleaner/useSteamCleaner", () => ({ useSteamCleaner: () => ({ scan: mocks.gameScan, busy: false }) }));
vi.mock("../cleaner/useMediaCleaner", () => ({ useMediaCleaner: () => ({ loading: false }) }));
vi.mock("../cleaner/useProtonCleaner", () => ({ useProtonCleaner: () => ({ queueScan: mocks.protonQueue, scan: mocks.protonScan, busy: false }) }));
vi.mock("../cleaner/CleanupHubView", () => ({ CleanupHubView: () => <div>hub</div> }));
vi.mock("../cleaner/SteamCleanerView", () => ({ SteamCleanerView: () => <div>old</div> }));
import { LimpiezaSection } from "./LimpiezaSection";

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

it("runs Juegos and then Proton only while Limpieza remains mounted", async () => {
  let finishGames!: () => void;
  mocks.gameScan.mockReturnValue(new Promise<void>((resolve) => { finishGames = resolve; }));
  const view = render(<LimpiezaSection />);
  await waitFor(() => expect(mocks.gameScan).toHaveBeenCalledOnce());
  expect(mocks.protonQueue).toHaveBeenCalledOnce();
  expect(mocks.protonScan).not.toHaveBeenCalled();

  view.unmount();
  await act(async () => finishGames());
  expect(mocks.protonScan).not.toHaveBeenCalled();
});

it("starts Proton after the game analysis finishes", async () => {
  mocks.gameScan.mockResolvedValue(undefined);
  mocks.protonScan.mockResolvedValue(undefined);
  render(<LimpiezaSection />);

  await waitFor(() => expect(mocks.protonScan).toHaveBeenCalledOnce());
});
