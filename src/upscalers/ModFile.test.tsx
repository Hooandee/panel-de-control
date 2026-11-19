// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  candidates: [] as { path: string; filename: string; size: number }[],
  added: null as unknown,
  opened: null as unknown,
}));
vi.mock("@decky/api", () => ({ openFilePicker: vi.fn() }));
vi.mock("@decky/ui", () => ({
  Navigation: { NavigateToExternalWeb: (url: string) => { api.opened = url; } },
  TextField: ({ value, onChange }: any) => <input aria-label="password" value={value} onChange={onChange} />,
}));
vi.mock("../api", () => ({
  getUpscalerModCandidates: vi.fn(async () => ({ folder: "/home/deck/Downloads", candidates: api.candidates })),
  addUpscalerMod: vi.fn(async (_appid: string, path: string) => { api.added = path; return { appid: "1245620", mod: { applied: false } }; }),
  removeUpscalerMod: vi.fn(),
  addUpscalerUserFile: vi.fn(),
  getUpscalerUserFileCandidates: vi.fn(),
}));
const hold = vi.hoisted(() => vi.fn());
vi.mock("./pageMemory", () => ({ holdPage: hold }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => (params?.name ? `${key} ${params.name}` : key) }) }));
vi.mock("./parts", () => ({
  ListCard: ({ children }: any) => <div>{children}</div>,
  ListRow: ({ label, detail, caption, onPress, busy, disabled }: any) => <button onClick={() => { if (!busy && !disabled) onPress?.(); }}>{[label, detail, caption].filter(Boolean).join(" | ")}</button>,
  Note: ({ children }: any) => <p>{children}</p>,
}));

import { ModFile, modDownload, wikiModName } from "./ModFile";
import { cancelUserFileWatch, MOD_WATCH, watchingFor } from "./userFileWatch";

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
  expect(screen.getByText("up.mod.named ERSS-FG | up.mod.state.pending | ERSS-FG free v4.zip")).toBeTruthy();
  expect(screen.queryByText("up.userFile.download")).toBeNull();
  fireEvent.click(screen.getByText("up.mod.apply"));
  expect(onApply).toHaveBeenCalled();
});

it("keeps to one row on games that need no mod", async () => {
  await act(async () => { render(<ModFile appid="1627720" mod={null} needed={false} name={null} download={null} onDetail={vi.fn()} />); });
  expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["up.mod.add"]);
});

it("lets the download wait be cancelled", async () => {
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} />); });
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.download")); });
  await act(async () => { fireEvent.click(screen.getByText(/up.userFile.waiting/)); });
  expect(screen.getByText("up.userFile.download")).toBeTruthy();
});

it("keeps the error from a picked archive after the picker closed and reopened the panel", async () => {
  const { openFilePicker } = await import("@decky/api");
  const { addUpscalerMod } = await import("../api");
  vi.mocked(openFilePicker).mockResolvedValueOnce({ realpath: "/home/deck/Downloads/broken.7z" } as never);
  vi.mocked(addUpscalerMod).mockRejectedValueOnce(Object.assign(new Error("mod_unreadable"), { pythonTraceback: "RuntimeError: mod_unreadable" }));
  const first = render(<ModFile appid="999" mod={null} needed name="X" download={null} onDetail={vi.fn()} />);
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.choose")); });
  first.unmount();
  await act(async () => { render(<ModFile appid="999" mod={null} needed name="X" download={null} onDetail={vi.fn()} />); });
  expect(screen.getByText("up.error.mod_unreadable")).toBeTruthy();
});

it("shows how much of the mod has downloaded while waiting", async () => {
  vi.useFakeTimers();
  const { getUpscalerModCandidates } = await import("../api");
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} />); });
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.download")); });
  vi.mocked(getUpscalerModCandidates).mockResolvedValue({ folder: "/home/deck/Downloads", candidates: [], downloading: { filename: "x.7z.crdownload", size: 47185920 } });
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(screen.getByText(/up.mod.downloading/)).toBeTruthy();
});

it("asks for the password of a protected archive and uses it", async () => {
  const { openFilePicker } = await import("@decky/api");
  const { addUpscalerMod } = await import("../api");
  vi.mocked(openFilePicker).mockResolvedValueOnce({ realpath: "/home/deck/Downloads/ERSS-FG-v4.14.1-Release.7z" } as never);
  vi.mocked(addUpscalerMod).mockRejectedValueOnce(Object.assign(new Error("mod_password"), { pythonTraceback: "RuntimeError: mod_password" }));
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} />); });
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.choose")); });
  expect(screen.getByText("up.error.mod_password")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("password"), { target: { value: "free" } });
  await act(async () => { fireEvent.click(screen.getByText("up.mod.usePassword")); });
  expect(addUpscalerMod).toHaveBeenLastCalledWith("1245620", "/home/deck/Downloads/ERSS-FG-v4.14.1-Release.7z", "free");
});

it("keeps the game page open across the file picker and Steam's browser", async () => {
  const { openFilePicker } = await import("@decky/api");
  vi.mocked(openFilePicker).mockResolvedValueOnce(null as never);
  hold.mockClear();
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} />); });
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.choose")); });
  expect(hold).toHaveBeenCalledTimes(1);
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.download")); });
  expect(hold).toHaveBeenCalledTimes(2);
});

it("keeps a download's password error for when the card comes back", async () => {
  vi.useFakeTimers();
  const { addUpscalerMod, getUpscalerModCandidates } = await import("../api");
  vi.mocked(getUpscalerModCandidates).mockImplementation(async () => ({ folder: "/home/deck/Downloads", candidates: api.candidates }));
  api.candidates = [];
  const first = render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} />);
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.download")); });
  first.unmount();
  vi.mocked(addUpscalerMod).mockRejectedValueOnce(Object.assign(new Error("mod_password"), { pythonTraceback: "RuntimeError: mod_password" }));
  api.candidates = [{ path: "/home/deck/Downloads/ERSS-FG.7z", filename: "ERSS-FG.7z", size: 1000 }];
  await act(async () => { await vi.advanceTimersByTimeAsync(7000); });
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} />); });
  expect(screen.getByText("up.error.mod_password")).toBeTruthy();
  expect(screen.getByLabelText("password")).toBeTruthy();
});

it("stops waiting for the download once the user picks a file", async () => {
  const { openFilePicker } = await import("@decky/api");
  vi.mocked(openFilePicker).mockResolvedValueOnce({ realpath: "/home/deck/Downloads/mine.zip" } as never);
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" download={PATREON} onDetail={vi.fn()} />); });
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.download")); });
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.choose")); });
  expect(watchingFor("1245620", MOD_WATCH)).toBe(false);
});
