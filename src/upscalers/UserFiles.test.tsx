// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getUpscalerUserFileCandidates: vi.fn(),
  addUpscalerUserFile: vi.fn(),
  removeUpscalerUserFile: vi.fn(),
}));
const picker = vi.hoisted(() => ({ openFilePicker: vi.fn() }));
vi.mock("../api", () => api);
vi.mock("@decky/api", () => picker);
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string, vars?: Record<string, string>) => vars ? `${key} ${Object.values(vars).join(" ")}` : key }) }));
vi.mock("./parts", () => ({
  ListCard: ({ children }: any) => <div>{children}</div>,
  ListRow: ({ label, detail, caption, onPress }: any) => <button onClick={onPress}>{label}|{detail}|{caption}</button>,
  Note: ({ children }: any) => <div>{children}</div>,
}));
import { UserFiles } from "./UserFiles";
import type { UserFile } from "./types";

const missing: UserFile = { id: "puredark-upscaler-base", name: "UpscalerBasePlugin", page_url: "https://www.nexusmods.com/site/mods/502",
  version: "1.1.2", installed_version: null, filename: null, state: "missing" };

beforeEach(() => {
  api.getUpscalerUserFileCandidates.mockResolvedValue({ folder: "/home/deck/Downloads", candidates: [
    { path: "/home/deck/Downloads/UpscalerBasePlugin-502-1-1-2-1.zip", filename: "UpscalerBasePlugin-502-1-1-2-1.zip", version: "1.1.2" },
  ] });
  api.addUpscalerUserFile.mockResolvedValue({ appid: "2050650" });
  api.removeUpscalerUserFile.mockResolvedValue({ appid: "2050650" });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("says where to get a missing file and adopts the one already downloaded with one press", async () => {
  const onDetail = vi.fn();
  await act(async () => { render(<UserFiles appid="2050650" files={[missing]} onDetail={onDetail} />); });
  expect(screen.getByText(/UpscalerBasePlugin\|up.userFile.missing\|up.userFile.where nexusmods.com\/site\/mods\/502 1.1.2/)).toBeTruthy();
  await act(async () => fireEvent.click(screen.getByText(/up.userFile.use UpscalerBasePlugin-502-1-1-2-1.zip/)));
  expect(api.addUpscalerUserFile).toHaveBeenCalledWith("2050650", "puredark-upscaler-base", "/home/deck/Downloads/UpscalerBasePlugin-502-1-1-2-1.zip");
  expect(onDetail).toHaveBeenCalledWith({ appid: "2050650" });
});

it("opens the picker in the downloads folder for archives and DLLs", async () => {
  picker.openFilePicker.mockResolvedValue({ realpath: "/home/deck/Downloads/pd.7z" });
  await act(async () => { render(<UserFiles appid="2050650" files={[missing]} onDetail={() => {}} />); });
  await act(async () => fireEvent.click(screen.getByText(/up.userFile.choose/)));
  expect(picker.openFilePicker).toHaveBeenCalledWith(0, "/home/deck/Downloads", true, true, undefined, ["zip", "7z", "rar", "dll"]);
  expect(api.addUpscalerUserFile).toHaveBeenCalledWith("2050650", "puredark-upscaler-base", "/home/deck/Downloads/pd.7z");
});

it("shows the version in use, warns about a known bad one and can remove it", async () => {
  const bad: UserFile = { ...missing, state: "avoid", installed_version: "1.2.0", filename: "x.zip" };
  await act(async () => { render(<UserFiles appid="2050650" files={[bad]} onDetail={() => {}} />); });
  expect(screen.getByText(/UpscalerBasePlugin\|1.2.0\|up.userFile.avoid 1.2.0 1.1.2/)).toBeTruthy();
  await act(async () => fireEvent.click(screen.getByText(/up.userFile.remove/)));
  expect(api.removeUpscalerUserFile).toHaveBeenCalledWith("2050650", "puredark-upscaler-base");
});

it("names the problem when the chosen file is not the right one", async () => {
  api.addUpscalerUserFile.mockRejectedValue(new Error("user_file_wrong"));
  await act(async () => { render(<UserFiles appid="2050650" files={[missing]} onDetail={() => {}} />); });
  await act(async () => fireEvent.click(screen.getByText(/up.userFile.use/)));
  expect(screen.getByText("up.error.user_file_wrong")).toBeTruthy();
});
