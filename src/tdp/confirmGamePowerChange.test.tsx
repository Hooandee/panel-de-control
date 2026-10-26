// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { GamePowerOwnerState, TdpScope } from "../api";
const port = vi.hoisted(() => ({
  modal: null as any, get: vi.fn(), claim: vi.fn(), live: {appid: "shortcut", liveAppid: 42},
  profile: "game", store: {msgSettingsPerApp: {split_scaling_filter: 1}, msgLimits: {split_scaling_filters_available: [1, 2]}, SetSplitScalingFilter: () => {}},
}));
vi.mock("@decky/ui", () => ({ Router: {}, findModuleByExport: () => undefined, findModuleExport: () => undefined }));
vi.mock("../api", () => ({getGamePowerOwner: port.get, setGamePowerOwner: port.claim}));
vi.mock("../navigation/showModal", () => ({ showModal: (element: any) => {port.modal = element;} }));
vi.mock("../i18n", () => ({translate: (key: string) => key}));
vi.mock("./runningGame", () => ({readRunningGame: () => port.live}));
vi.mock("../steam/performanceRuntime", () => ({readSteamPerformanceProfile: () => port.profile}));
vi.mock("../steam/performanceSettingsRuntime", () => ({createPerformanceSettingsDeps: () => ({store: () => port.store, display: () => null, gamescope: () => null, steamOs: () => null})}));
import { confirmGamePowerChange, useGamePowerChangeGuard } from "./confirmGamePowerChange";
const owner: GamePowerOwnerState = {context_appid: "shortcut", revision: 7, observed: true, steam_profile: "active", explicit_owner: null, owner: "steam", write_allowed: false, reason: "steam_profile_active", steam_settings: {}};
const flush = async () => {await act(async () => {});};
beforeEach(() => {
  port.modal = null; port.live = {appid: "shortcut", liveAppid: 42}; port.profile = "game";
  port.get.mockReset().mockResolvedValue(owner);
  port.claim.mockReset().mockResolvedValue({...owner, ok: true, explicit_owner: "pdc", owner: "pdc", revision: 8});
});
it("cancel has no effects and confirmed change claims snapshot then executes once", async () => {
  const apply = vi.fn();
  confirmGamePowerChange({scope: "game", appid: "shortcut", owner, isCurrent: () => true, apply});
  expect(apply).not.toHaveBeenCalled(); expect(port.get).not.toHaveBeenCalled(); expect(port.claim).not.toHaveBeenCalled();
  port.modal.props.onConfirm(); port.modal.props.onConfirm(); await flush();
  expect(port.claim).toHaveBeenCalledExactlyOnceWith("shortcut", "pdc", 7, {splitScalingFilter: 1});
  expect(apply).toHaveBeenCalledOnce();
});
it.each(["context", "revision", "failure", "unknown"])("rejects %s changes without executing the setter", async (failure) => {
  const apply = vi.fn();
  confirmGamePowerChange({scope: "game", appid: "shortcut", owner, isCurrent: () => true, apply});
  if (failure === "context") port.live = {appid: "other", liveAppid: 43};
  if (failure === "revision") port.get.mockResolvedValue({...owner, revision: 9});
  if (failure === "failure") port.claim.mockResolvedValue({ok: false});
  if (failure === "unknown") port.profile = "unknown";
  port.modal.props.onConfirm(); await flush(); expect(apply).not.toHaveBeenCalled();
});
it("blocks unknown observation visibly without offering an ownership write", () => {
  const apply = vi.fn();
  confirmGamePowerChange({scope: "game", appid: "shortcut", owner: {...owner, steam_profile: "unknown", owner: "unresolved"}, isCurrent: () => true, apply});
  expect(port.modal.props.desc).toBe("steam.performance.profile.unknown");
  port.modal.props.onConfirm(); expect(apply).not.toHaveBeenCalled(); expect(port.claim).not.toHaveBeenCalled();
});
it("keeps global and legacy routes synchronous", () => {
  const apply = vi.fn();
  confirmGamePowerChange({scope: "global", appid: "shortcut", owner, isCurrent: () => true, apply});
  confirmGamePowerChange({scope: "game", appid: "shortcut", isCurrent: () => true, apply});
  confirmGamePowerChange({scope: "game", appid: "shortcut", owner: {...owner, explicit_owner: "pdc", owner: "pdc"}, isCurrent: () => true, apply});
  expect(apply).toHaveBeenCalledTimes(3); expect(port.modal).toBeNull();
});
it("invalidates pending confirmation on scope changes even when returning to game", async () => {
  const apply = vi.fn();
  const {result, rerender} = renderHook(({scope}: {scope: TdpScope}) => useGamePowerChangeGuard(scope, "shortcut", owner)(apply), {initialProps: {scope: "game" as TdpScope}});
  result.current(); const confirm = port.modal.props.onConfirm;
  rerender({scope: "global"}); rerender({scope: "game"}); confirm(); await flush();
  expect(port.claim).not.toHaveBeenCalled(); expect(apply).not.toHaveBeenCalled();
});

it("rejects stale ownership from another game even if it explicitly belongs to PDC", () => {
  const apply = vi.fn();
  confirmGamePowerChange({scope: "game", appid: "other", owner: {...owner, owner: "pdc", explicit_owner: "pdc"}, isCurrent: () => true, apply});
  expect(apply).not.toHaveBeenCalled(); expect(port.modal.props.desc).toBe("steam.performance.profile.unknown");
});

it("accepts after QAM unmount while game and revision remain unchanged", async () => {
  const apply = vi.fn();
  const {result, unmount} = renderHook(() => useGamePowerChangeGuard("game", "shortcut", owner)(apply));
  result.current(); const confirm = port.modal.props.onConfirm;
  unmount(); confirm(); confirm(); await flush();
  expect(port.claim).toHaveBeenCalledOnce(); expect(apply).toHaveBeenCalledOnce();
});
it("claims inferred PDC ownership silently on supported Deck before applying", async () => {
  const apply = vi.fn();
  const inferred = {...owner, supported: true, owner: "pdc" as const, steam_profile: "inactive" as const};
  port.profile = "global"; port.get.mockResolvedValue(inferred);
  confirmGamePowerChange({scope: "game", appid: "shortcut", owner: inferred, isCurrent: () => true, apply});
  expect(apply).not.toHaveBeenCalled(); expect(port.modal).toBeNull(); await flush();
  expect(port.claim).toHaveBeenCalledExactlyOnceWith("shortcut", "pdc", 7, {splitScalingFilter: 1}); expect(apply).toHaveBeenCalledOnce();
});
it("blocks Steam-owned edits without authoritative hardware readback", () => {
  const apply = vi.fn();
  confirmGamePowerChange({scope: "game", appid: "shortcut", owner, readbackAvailable: false, isCurrent: () => true, apply});
  expect(port.modal.props.desc).toBe("steam.performance.profile.unknown");
  expect(apply).not.toHaveBeenCalled(); expect(port.claim).not.toHaveBeenCalled();
});
