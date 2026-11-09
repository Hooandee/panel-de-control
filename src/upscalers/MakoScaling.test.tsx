// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MakoScaling } from "./MakoScaling";
const mocks = vi.hoisted(() => ({ get: vi.fn(), install: vi.fn(), refresh: vi.fn(), save: vi.fn() }));
vi.mock("../api", () => ({ getMakoStatus: mocks.get, installMako: mocks.install, refreshFrameGenEngine: mocks.refresh }));
vi.mock("./jobRunner", () => ({ saveExclusiveMakoProfile: mocks.save }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../components/ContainedSlider", () => ({ ContainedSlider: ({ label, value, min, max, step, disabled, onChange }: any) => <input type="range" aria-label={label} value={value} min={min} max={max} step={step} disabled={disabled} onChange={e => onChange(Number(e.target.value))} /> }));
vi.mock("./parts", () => ({
  ListCard: ({ children }: any) => <section>{children}</section>, Row: ({ children }: any) => <div>{children}</div>,
  Note: ({ children }: any) => <div>{children}</div>, Notice: ({ children }: any) => <div>{children}</div>, Spinner: () => null,
  ActionButton: ({ label, disabled, onPress }: any) => <button disabled={disabled} onClick={onPress}>{label}</button>,
}));
const props = { appid: "123", liveAppid: 123, isNonSteam: false, disabled: false, gameRunning: false, mixed: false };
let status: any;
beforeEach(() => { vi.clearAllMocks(); status = { installed: true, supported: true, profiles: {}, foreign: false }; mocks.get.mockImplementation(async () => status); mocks.refresh.mockResolvedValue({ state: "current" }); mocks.save.mockResolvedValue(null); });
afterEach(cleanup);
it("downloads the engine and activates spatial scaling without enabling FG", async () => {
  status.installed = false;
  render(<MakoScaling {...props} />);
  await waitFor(() => expect((screen.getByRole("button", { name: "up.activate" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.change(screen.getByRole("slider", { name: "up.image.sharpness" }), { target: { value: "30" } });
  fireEvent.click(screen.getByRole("button", { name: "up.activate" }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({ appid: "123", liveAppid: 123, isNonSteam: false }, { scaling_enabled: true, scaling_factor: 1.5, scaling_sharpness: 0.3 }));
  expect(mocks.install).toHaveBeenCalledOnce();
});
it("disables only spatial scaling and leaves FG to the shared merge", async () => {
  status.profiles[123] = { enabled: true, scaling_enabled: true, scaling_factor: 1.7, scaling_sharpness: 0.2 };
  render(<MakoScaling {...props} />);
  fireEvent.click(await screen.findByRole("button", { name: "up.deactivate" }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({ appid: "123", liveAppid: 123, isNonSteam: false }, { scaling_enabled: false, scaling_factor: 1.7, scaling_sharpness: 0.2 }));
});
it("blocks edits during play and warns about an installed scaler", async () => {
  render(<MakoScaling {...props} gameRunning mixed />);
  await screen.findByText("up.mako.scaling.mixed");
  expect(screen.getAllByRole("slider").every(node => (node as HTMLInputElement).disabled)).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "up.activate" }));
  expect(mocks.save).not.toHaveBeenCalled();
});
it.each([
  ["failed", "up.engine.failed"],
  ["deferred", "up.engine.deferred"],
  ["throws", "up.engine.failed"],
])("activates with the installed engine when its update %s", async (outcome, notice) => {
  if (outcome === "throws") mocks.refresh.mockRejectedValue(new Error("offline"));
  else mocks.refresh.mockResolvedValue({ state: "available", version: "1" }).mockResolvedValueOnce({ state: "available", version: "1" }).mockResolvedValueOnce({ state: outcome, version: "1" });
  render(<MakoScaling {...props} />);
  await waitFor(() => expect((screen.getByRole("button", { name: "up.activate" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "up.activate" }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({ appid: "123", liveAppid: 123, isNonSteam: false }, expect.objectContaining({ scaling_enabled: true })));
  expect(await screen.findByText(notice)).toBeTruthy();
  expect(screen.queryByText("up.error.generic")).toBeNull();
});
it("reports an error only when there is no engine to use", async () => {
  status.installed = false;
  mocks.install.mockRejectedValue(new Error("download_failed"));
  render(<MakoScaling {...props} />);
  await waitFor(() => expect((screen.getByRole("button", { name: "up.activate" }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "up.activate" }));
  await screen.findByText("up.error.generic");
  expect(mocks.save).not.toHaveBeenCalled();
});
