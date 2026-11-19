// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  candidates: [{ path: "/home/deck/Downloads/ERSS-FG free v4.zip", filename: "ERSS-FG free v4.zip", version: null }],
  added: null as unknown,
}));
vi.mock("@decky/api", () => ({ openFilePicker: vi.fn() }));
vi.mock("../api", () => ({
  getUpscalerModCandidates: vi.fn(async () => ({ folder: "/home/deck/Downloads", candidates: api.candidates })),
  addUpscalerMod: vi.fn(async (_appid: string, path: string) => { api.added = path; return { appid: "1245620" }; }),
  removeUpscalerMod: vi.fn(),
}));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => (params?.name ? `${key} ${params.name}` : key) }) }));
vi.mock("./parts", () => ({
  ListCard: ({ children }: any) => <div>{children}</div>,
  ListRow: ({ label, detail, caption, onPress }: any) => <button onClick={onPress}>{[label, detail, caption].filter(Boolean).join(" | ")}</button>,
  Note: ({ children }: any) => <p>{children}</p>,
}));

import { ModFile, wikiModName } from "./ModFile";

afterEach(cleanup);

it("names the mod from the wiki page title", () => {
  expect(wikiModName("Elden-Ring-(ERSS‐FG)")).toBe("ERSS-FG");
  expect(wikiModName("Persona-3-Reload")).toBeNull();
  expect(wikiModName(undefined)).toBeNull();
});

it("offers the archive already in Downloads for a game the wiki says needs a mod", async () => {
  const onDetail = vi.fn();
  await act(async () => { render(<ModFile appid="1245620" mod={null} needed name="ERSS-FG" onDetail={onDetail} />); });
  expect(screen.getByText(/up.mod.named ERSS-FG \| up.userFile.missing \| up.mod.where/)).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByText("up.userFile.use ERSS-FG free v4.zip")); });
  expect(api.added).toBe("/home/deck/Downloads/ERSS-FG free v4.zip");
  expect(onDetail).toHaveBeenCalled();
  expect(screen.getByText("up.mod.safety")).toBeTruthy();
});

it("says a mod waits for the upscaler to reinstall until it is in", async () => {
  const mod = { filename: "ERSS-FG free v4.zip", count: 12, files: [], native_dlls: ["d3d12"], applied: false };
  const onApply = vi.fn();
  await act(async () => { render(<ModFile appid="1245620" mod={mod} needed name="ERSS-FG" onDetail={vi.fn()} onApply={onApply} />); });
  expect(screen.getByText(/ERSS-FG free v4.zip \| up.mod.pending/)).toBeTruthy();
  expect(screen.getByText("up.userFile.remove")).toBeTruthy();
  fireEvent.click(screen.getByText("up.mod.apply"));
  expect(onApply).toHaveBeenCalled();
});

it("keeps to one row on games that need no mod", async () => {
  await act(async () => { render(<ModFile appid="1627720" mod={null} needed={false} name={null} onDetail={vi.fn()} />); });
  expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["up.mod.add"]);
  expect(screen.queryByText("up.mod.safety")).toBeNull();
});
