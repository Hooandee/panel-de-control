import { afterEach, beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getUpscalerUserFileCandidates: vi.fn(), addUpscalerUserFile: vi.fn() }));
const ui = vi.hoisted(() => ({ Navigation: { NavigateToExternalWeb: vi.fn() } }));
vi.mock("../api", () => api);
vi.mock("@decky/ui", () => ui);
import { cancelUserFileWatch, downloadUserFile, onUserFileWatch, takePendingReinstall, watchingFor } from "./userFileWatch";

const file = { id: "puredark-upscaler-base", page_url: "https://www.nexusmods.com/site/mods/502",
  download_url: "https://www.nexusmods.com/site/mods/502?tab=files&file_id=2293" };
const old = { path: "/home/deck/Downloads/old.zip", filename: "old.zip", version: "1.1.2" };
const fresh = { path: "/home/deck/Downloads/UpscalerBasePlugin-502-1-1-2-9.zip", filename: "new.zip", version: "1.1.2" };

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cancelUserFileWatch(); vi.useRealTimers(); vi.clearAllMocks(); takePendingReinstall("2050650"); });

it("opens the exact file page and adopts only the archive that arrives afterwards", async () => {
  api.getUpscalerUserFileCandidates.mockResolvedValue({ folder: "/d", candidates: [old] });
  api.addUpscalerUserFile.mockResolvedValue({ appid: "2050650" });
  const events: string[] = [];
  onUserFileWatch((event) => events.push(event.type));
  await downloadUserFile("2050650", file);
  expect(ui.Navigation.NavigateToExternalWeb).toHaveBeenCalledWith(file.download_url);
  expect(watchingFor("2050650", file.id)).toBe(true);
  await vi.advanceTimersByTimeAsync(3000);
  expect(api.addUpscalerUserFile).not.toHaveBeenCalled();
  api.getUpscalerUserFileCandidates.mockResolvedValue({ folder: "/d", candidates: [fresh, old] });
  await vi.advanceTimersByTimeAsync(3000);
  expect(api.addUpscalerUserFile).toHaveBeenCalledWith("2050650", file.id, fresh.path);
  expect(events).toEqual(["watching", "adopted"]);
  expect(watchingFor("2050650", file.id)).toBe(false);
  expect(takePendingReinstall("2050650")).toBe(true);
  expect(takePendingReinstall("2050650")).toBe(false);
});

it("gives up after a while and can be cancelled", async () => {
  api.getUpscalerUserFileCandidates.mockResolvedValue({ folder: "/d", candidates: [] });
  const events: string[] = [];
  onUserFileWatch((event) => events.push(event.type));
  await downloadUserFile("2050650", file);
  await vi.advanceTimersByTimeAsync(16 * 60 * 1000);
  expect(events).toEqual(["watching", "stopped"]);
  expect(watchingFor("2050650", file.id)).toBe(false);
});
