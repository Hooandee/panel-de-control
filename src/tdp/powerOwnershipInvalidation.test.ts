import { afterEach, describe, expect, it, vi } from "vitest";
import type { GamePowerOwnerResult } from "../api";
const rpc = vi.hoisted(() => vi.fn());
vi.mock("@decky/api", () => ({ callable: (name: string) => (...args: unknown[]) => rpc(name, ...args) }));
import { setGamePowerOwner, updateGameSteamSetting } from "../api";
import { subscribePowerOwnershipChanged } from "./powerOwnershipInvalidation";
const state: GamePowerOwnerResult = { ok: true, supported: true, context_appid: "42", revision: 2,
  observed: true, steam_profile: "active", explicit_owner: "pdc", owner: "pdc", write_allowed: true, reason: "explicit" };
afterEach(() => vi.resetAllMocks());
describe("power ownership invalidation", () => {
  it("notifies mounted consumers only after a successful owner or Steam setting update", async () => {
    const listener = vi.fn();
    const stop = subscribePowerOwnershipChanged(listener);
    try {
      rpc.mockResolvedValue(state);
      await setGamePowerOwner("42", "pdc", 1, {});
      expect(rpc).toHaveBeenLastCalledWith("set_game_power_owner", "42", "pdc", 1, {});
      expect(listener).toHaveBeenLastCalledWith(state);
      await updateGameSteamSetting("42", 2, "steam-splitScalingFilter", 3);
      expect(listener).toHaveBeenCalledTimes(2);
      rpc.mockResolvedValue({ ...state, ok: false });
      await setGamePowerOwner("42", "steam", 0);
      expect(listener).toHaveBeenCalledTimes(2);
      rpc.mockRejectedValue(new Error("offline"));
      await expect(updateGameSteamSetting("42", 2, "steam-splitScalingFilter", 1)).rejects.toThrow("offline");
      expect(listener).toHaveBeenCalledTimes(2);
      stop();
      rpc.mockResolvedValue(state);
      await setGamePowerOwner("42", "pdc", 1);
      expect(listener).toHaveBeenCalledTimes(2);
    } finally { stop(); }
  });
});
