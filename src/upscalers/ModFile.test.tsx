// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  candidates: [] as { path: string; filename: string; size: number }[],
  added: null as unknown,
  opened: null as unknown,
}));
vi.mock("@decky/api", () => ({ openFilePicker: vi.fn() }));
vi.mock("@decky/ui", () => ({ Navigation: { NavigateToExternalWeb: (url: string) => { api.opened = url; } } }));
vi.mock("../api", () => ({
  getUpscalerModCandidates: vi.fn(async () => ({ folder: "/home/deck/Downloads", candidates: api.candidates })),
  addUpscalerMod: vi.fn(async (_appid: string, path: string) => { api.added = path; return { appid: "1245620", mod: { applied: false } }; }),
  removeUpscalerMod: vi.fn(),
  addUpscalerUserFile: vi.fn(),
  getUpscalerUserFileCandidates: vi.fn(),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => (params?.name ? `${key} ${params.name}` : key) }) }));
vi.mock("./parts", () => ({
  ListCard: ({ children }: any) => <div>{children}</div>,
  ListRow: ({ label, detail, caption, onPress }: any) => <button onClick={onPress}>{[label, detail, caption].filter(Boolean).join(" | ")}</button>,
  Note: ({ children }: any) => <p>{children}</p>,
}));

import { ModFile, modDownload, wikiModName } from "./ModFile";
import { cancelUserFileWatch } from "./userFileWatch";

afterEach(() => { cancelUserFileWatch(); cleanup(); vi.useRealTimers(); });

const PATREON = "https://www.patreon.com/huutaiii/posts/erss-fg-free-v4-125972766";

it("names the mod from the wiki page title and downloads it from its page, else the wiki", () => {
  expect(wikiModName("Elden-Ring-(ERSS‐FG)")).toBe("ERSS-FG");
  expect(wikiModName("Persona-3-Reload")).toBeNull();
  expect(modDownload({ mod_download: PATREON, recipe_info: null })).toBe(PATREON);
  expect(modDownload({ mod_download: null, recipe_info: { page: "Elden-Ring-(ERSS‐FG)" } as never }))
    .toBe("https://github.com/optiscaler/OptiScaler/wiki/Elden-Ring-(ERSS%E2%80%90FG)");
});

it("offers Download and Choose file for a mod the game needs, and nothing else", async () => {
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} />); });
  expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
    "up.mod.named ERSS-FG | up.userFile.missing | up.mod.required", "up.userFile.download", "up.userFile.choose",
  ]);
});

it("adds the archive once the download finishes landing in Downloads", async () => {
  vi.useFakeTimers();
  const onDetail = vi.fn();
  api.candidates = [];
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={onDetail} />); });
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.download")); });
  expect(api.opened).toBe(PATREON);
  api.candidates = [{ path: "/home/deck/Downloads/ERSS-FG free v4.zip", filename: "ERSS-FG free v4.zip", size: 1000 }];
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.added).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(api.added).toBe("/home/deck/Downloads/ERSS-FG free v4.zip");
  expect(onDetail).toHaveBeenCalled();
});

it("says a mod waits for the upscaler to reinstall and offers to do it", async () => {
  const mod = { filename: "ERSS-FG free v4.zip", count: 12, files: [], native_dlls: ["d3d12"], applied: false };
  const onApply = vi.fn();
  await act(async () => { render(<ModFile appid="1245620" mod={mod} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} onApply={onApply} />); });
  expect(screen.getByText(/ERSS-FG free v4.zip \| up.mod.pending/)).toBeTruthy();
  expect(screen.queryByText("up.userFile.download")).toBeNull();
  fireEvent.click(screen.getByText("up.mod.apply"));
  expect(onApply).toHaveBeenCalled();
});

it("keeps to one row on games that need no mod", async () => {
  await act(async () => { render(<ModFile appid="1627720" mod={null} needed={false} name={null} download={null} onDetail={vi.fn()} />); });
  expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["up.mod.add"]);
});
