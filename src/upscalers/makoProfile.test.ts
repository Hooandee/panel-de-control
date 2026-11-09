// @vitest-environment happy-dom
import { beforeEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ getMakoStatus: vi.fn(), getUpscalerLaunchReceipt: vi.fn(), setMakoGame: vi.fn(), readAppDetails: vi.fn(), applyManagedLaunch: vi.fn() }));
vi.mock("../api", () => api);
vi.mock("../launch/steamApi", () => api);
vi.mock("./managedLaunch", () => api);
import { saveMakoProfile } from "./makoProfile";
const previous = { enabled: true, scaling_enabled: true, scaling_factor: 1.5, scaling_sharpness: 0.3, mode: "fixed", multiplier: 3, target_fps: 120, max_multiplier: 3, flow: "quality", performance: false };
beforeEach(() => {
  vi.resetAllMocks();
  api.getMakoStatus.mockResolvedValue({ profiles: { "1": previous } });
  api.setMakoGame.mockResolvedValue({ profile: previous, env: { MAKO_CONFIG: "/home/deck/test config" }, wrappers: ["/home/deck/mako-launch"] });
  api.applyManagedLaunch.mockResolvedValue({ ok: true, preserved: { env: [], wrappers: [] } });
});
it("keeps launch ownership when only frame generation is disabled", async () => {
  await saveMakoProfile("1", 1, { enabled: false });
  expect(api.setMakoGame).toHaveBeenCalledWith("1", { enabled: false });
  expect(api.applyManagedLaunch).toHaveBeenCalledWith("1", 1, "mako", { env: { MAKO_CONFIG: "'/home/deck/test config'" }, wrappers: ["/home/deck/mako-launch"] }, { isNonSteam: false, requireComplete: true });
});
it("restores both parts of the profile when the launch change fails", async () => {
  api.applyManagedLaunch.mockResolvedValue({ ok: false, pending: false });
  await expect(saveMakoProfile("1", 1, { scaling_sharpness: 0.9 })).rejects.toThrow("launch_failed");
  expect(api.setMakoGame).toHaveBeenLastCalledWith("1", previous);
});
it("protects an external Mako launch configuration on first activation", async () => {
  api.getMakoStatus.mockResolvedValue({ profiles: {} });
  api.getUpscalerLaunchReceipt.mockResolvedValue(null);
  api.readAppDetails.mockResolvedValue({ launch: "mako-launch %command%" });
  await expect(saveMakoProfile("1", 1, { enabled: false, scaling_enabled: true })).rejects.toThrow("mako_foreign");
  expect(api.setMakoGame).not.toHaveBeenCalled();
});
it("retains pending launch recovery instead of rolling back an activation blindly", async () => {
  api.applyManagedLaunch.mockResolvedValue({ ok: false, pending: true });
  await expect(saveMakoProfile("1", 1, { scaling_enabled: true })).rejects.toThrow("launch_failed");
  expect(api.setMakoGame).toHaveBeenCalledTimes(1);
});
it("creates spatial-only profiles without accidentally enabling frame generation", async () => {
  api.getMakoStatus.mockResolvedValue({ profiles: {} });
  api.getUpscalerLaunchReceipt.mockResolvedValue(null);
  api.readAppDetails.mockResolvedValue({ launch: "MANGOHUD=1 %command% -dx12" });
  await saveMakoProfile("1", 1, { scaling_enabled: true, scaling_sharpness: 0.4 });
  expect(api.setMakoGame).toHaveBeenCalledWith("1", { enabled: false, scaling_enabled: true, scaling_sharpness: 0.4 });
});
