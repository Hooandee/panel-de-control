// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  stable: "42", live: 42 as number | null, capabilities: null as Record<string, boolean> | null, active: "42", filter: 1,
  owner: { supported: true, context_appid: "42" as string | null, revision: 1, explicit_owner: null as string | null, owner: "steam", steam_settings: {} },
  reset: vi.fn(), get: vi.fn(), claim: vi.fn(), update: vi.fn(), write: vi.fn(), notify: () => {},
}));
vi.mock("../tdp/runningGame", () => ({readRunningGame: () => state.live === null ? null : ({appid: state.stable, liveAppid: state.live})}));
vi.mock("../api", () => ({ getGamePowerOwner: state.get, setGamePowerOwner: state.claim, updateGameSteamSetting: state.update }));
vi.mock("../steam/performanceReset", () => ({ resetManagedGamePerformance: state.reset }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../system/collapseState", () => ({ isCollapsed: () => false, setCollapsed: vi.fn() }));
vi.mock("../system/uiEvents", () => ({ recordUiEvent: vi.fn() }));
vi.mock("../navigation/showModal", () => ({ showModal: (element: any) => { const dialog = render(element); dialog.rerender({ ...element, props: { ...element.props, closeModal: () => dialog.unmount() } }); } }));
vi.mock("@decky/ui", () => ({
  findModuleByExport: () => undefined, findModuleExport: () => undefined,
  Focusable: ({children}: any) => <div>{children}</div>, PanelSectionRow: ({children}: any) => <div>{children}</div>, ModalRoot: ({children}: any) => <div role="dialog">{children}</div>,
  DialogButton: ({children, onClick, disabled}: any) => <button onClick={onClick} disabled={disabled}>{children}</button>,
  DropdownItem: ({label, rgOptions, selectedOption, disabled, onChange}: any) => <select aria-label={label} value={selectedOption} disabled={disabled} onChange={(event) => onChange({data: Number(event.target.value)})}>{rgOptions.map((option: any) => <option key={option.data} value={option.data}>{option.label}</option>)}</select>,
}));
vi.mock("../steam/performanceSettingsRuntime", () => ({ createPerformanceSettingsDeps: () => ({
  store: () => (window as any).SystemPerfStore,
  runningGameId: () => state.live,
  display: () => null, gamescope: () => null, steamOs: () => state.capabilities,
}) }));
import { SteamPerformanceCard } from "./SteamPerformanceCard";
import { resetSteamPerformanceRuntimeCache } from "../steam/performanceRuntime";

beforeEach(() => {
  vi.useFakeTimers(); state.reset.mockReset(); state.stable = "42"; state.live = 42; state.capabilities = null; state.active = "42"; state.filter = 1;
  state.owner = { supported: true, context_appid: "42" as string | null, revision: 1, explicit_owner: null, owner: "steam", steam_settings: {} };
  state.get.mockReset().mockImplementation(async () => ({...state.owner}));
  state.claim.mockReset().mockImplementation(async (_id, owner, _revision, settings) => ({ok: true, ...state.owner, owner, explicit_owner: owner, revision: 2, steam_settings: settings}));
  state.update.mockReset().mockImplementation(async () => ({ok: true, ...state.owner, owner: "pdc", explicit_owner: "pdc", revision: 3}));
  state.write.mockReset().mockImplementation((value) => { state.filter = value; });
  Object.assign(window, { SystemPerfStore: {
    nCurrentGameID: "42", get nActiveProfileGameID() { return state.active; },
    msgLimits: {split_scaling_filters_available: [1, 2, 3]},
    get msgSettingsPerApp() {return {split_scaling_filter: state.filter};},
    SetSplitScalingFilter: state.write,
  } });
  vi.stubGlobal("SteamClient", { System: { Perf: { RegisterForStateChanges: (notify: () => void) => {state.notify = notify; return {unregister: vi.fn()};} } } });
  resetSteamPerformanceRuntimeCache();
});
afterEach(() => { state.live = null; state.notify(); cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); delete (window as any).SystemPerfStore; delete (window as any).settingsStore; });
const mount = async () => { const view = render(<SteamPerformanceCard profileScope="game" runningGameId={42} />); await act(async () => {}); return view; };
const edit = () => fireEvent.change(screen.getByRole("combobox", {name: "steam.performance.control.splitScalingFilter"}), {target: {value: "3"}});
const confirm = async () => { await act(async () => {fireEvent.click(screen.getByRole("button", {name: "steam.performance.claim"}));}); };

it("canceling first edit never claims, persists or writes Steam", async () => {
  await mount(); edit();
  fireEvent.click(screen.getByRole("button", {name: "steam.performance.cancel"}));
  expect(state.claim).not.toHaveBeenCalled(); expect(state.update).not.toHaveBeenCalled(); expect(state.write).not.toHaveBeenCalled();
});
it("confirms actual Steam snapshot before saving and applying the requested setting", async () => {
  await mount(); edit(); await confirm();
  expect(state.claim).toHaveBeenCalledWith("42", "pdc", 1, {splitScalingFilter: 1});
  expect(state.update).toHaveBeenCalledWith("42", 2, "splitScalingFilter", 3);
  expect(state.write).toHaveBeenCalledWith(3);
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
});
it("rejects confirmation after live game or ownership revision changed", async () => {
  await mount(); edit(); state.owner.revision = 2; await confirm();
  expect(state.claim).not.toHaveBeenCalled(); expect(state.write).not.toHaveBeenCalled();
  edit(); state.live = 43; await confirm(); expect(state.claim).not.toHaveBeenCalled();
});
it("does not apply a queued edit after context changes while ownership is being read", async () => {
  const view = await mount(); edit();
  let resolve!: (value: unknown) => void;
  state.get.mockImplementationOnce(() => new Promise((done) => {resolve = done;}));
  await confirm(); state.live = 43;
  view.rerender(<SteamPerformanceCard profileScope="game" runningGameId={43} />);
  await act(async () => {resolve({...state.owner});});
  expect(state.claim).not.toHaveBeenCalled(); expect(state.update).not.toHaveBeenCalled(); expect(state.write).not.toHaveBeenCalled();
});
it("withdraws own controls when Steam profile changes without selecting a different profile", async () => {
  await mount(); expect(screen.getByRole("combobox")).toBeTruthy();
  state.active = "769"; await act(async () => {state.notify();});
  expect(screen.queryByRole("combobox")).toBeNull(); expect(state.write).not.toHaveBeenCalled();
});
it("does not write Steam after failed persistence", async () => {
  await mount(); state.update.mockResolvedValueOnce({ok: false, detail: "persist_failed"}); edit(); await confirm();
  expect(state.write).not.toHaveBeenCalled(); expect(screen.getByRole("status").textContent).toBe("steam.performance.writeFailed");
});

it.each(["steam", "pdc"])("resets game settings and power while retaining %s ownership", async (owner) => {
  state.owner.owner = owner;
  state.owner.explicit_owner = owner;
  state.reset.mockResolvedValue({ ...state.owner, ok: true });
  const reset = vi.fn();
  (window as any).SystemPerfStore.ResetCurrentPerfProfileSettings = reset;
  await mount();
  const button = screen.getByRole("button", {name: "steam.performance.control.reset"}) as HTMLButtonElement;
  expect(button.disabled).toBe(false);
  await act(async () => { fireEvent.click(button); });
  expect(state.reset).toHaveBeenCalledOnce();
  expect(state.claim).not.toHaveBeenCalled();
  expect(reset).not.toHaveBeenCalled();
});
it("allows explicit global reset through the real Steam adapter", async () => {
  state.active = "769";
  const reset = vi.fn(() => {state.filter = 1;});
  (window as any).SystemPerfStore.ResetCurrentPerfProfileSettings = reset;
  render(<SteamPerformanceCard profileScope="global" runningGameId={42} />);
  await act(async () => {});
  await act(async () => {fireEvent.click(screen.getByRole("button", {name: "steam.performance.control.reset"}));});
  expect(reset).toHaveBeenCalledOnce(); expect(state.claim).not.toHaveBeenCalled(); expect(state.update).not.toHaveBeenCalled();
});
it("does not invoke the Steam setter after a persisted edit loses its context", async () => {
  await mount();
  state.update.mockImplementationOnce(async () => {state.live = 43; return {ok: true, ...state.owner, revision: 3};});
  edit(); await confirm();
  expect(state.update).toHaveBeenCalledOnce(); expect(state.write).not.toHaveBeenCalled();
});

it("confirms once after QAM unmount using stable shortcut identity", async () => {
  state.stable = "shortcut-key";
  state.owner.context_appid = "shortcut-key";
  const view = await mount(); edit();
  const confirmButton = screen.getByRole("button", {name: "steam.performance.claim"});
  view.unmount();
  await act(async () => {fireEvent.click(confirmButton);});
  expect(state.claim).toHaveBeenCalledExactlyOnceWith("shortcut-key", "pdc", 1, {splitScalingFilter: 1});
  expect(state.update).toHaveBeenCalledExactlyOnceWith("shortcut-key", 2, "splitScalingFilter", 3);
  expect(state.write).toHaveBeenCalledExactlyOnceWith(3);
});
it("rejects a shortcut identity change even when the live ID remains equal", async () => {
  const view = await mount(); edit(); view.unmount(); state.stable = "another-shortcut";
  await confirm(); expect(state.claim).not.toHaveBeenCalled(); expect(state.write).not.toHaveBeenCalled();
});

it("returns control using unchanged Steam power settings after releasing ownership", async () => {
  state.owner.explicit_owner = "pdc"; state.owner.owner = "pdc";
  state.capabilities = {is_manual_gpu_clock_available: true};
  const setEnabled = vi.fn(), setValue = vi.fn();
  (window as any).settingsStore = {GetClientSetting: (key: string) => key.endsWith("enabled") ? [false, setEnabled] : [1600, setValue]};
  state.claim.mockImplementationOnce(async (_id, owner) => {
    state.owner = {...state.owner, explicit_owner: owner, owner, revision: 2};
    state.get.mockResolvedValue({...state.owner, supported: true});
    return {...state.owner, ok: true};
  });
  await mount();
  await act(async () => {fireEvent.click(screen.getByRole("button", {name: "steam.performance.release"}));});
  expect(state.claim).toHaveBeenCalledExactlyOnceWith("42", "steam", 1);
  expect(setEnabled).toHaveBeenCalledExactlyOnceWith(false);
  expect(setValue).toHaveBeenCalledExactlyOnceWith(1600);
  expect(state.write).not.toHaveBeenCalled();
});

it("edits and resets global Steam settings without a running game", async () => {
  state.live = null; state.active = "769"; state.owner.context_appid = null;
  state.reset.mockResolvedValue({ ...state.owner, ok: true });
  const reset = vi.fn(); (window as any).SystemPerfStore.ResetCurrentPerfProfileSettings = reset;
  render(<SteamPerformanceCard profileScope="global" runningGameId={null} />);
  await act(async () => {});
  await act(async () => {edit();});
  expect(state.write).toHaveBeenCalledExactlyOnceWith(3);
  await act(async () => {fireEvent.click(screen.getByRole("button", {name: "steam.performance.control.reset"}));});
  expect(reset).not.toHaveBeenCalled(); expect(state.reset).toHaveBeenCalledOnce();
  expect(state.claim).not.toHaveBeenCalled(); expect(state.update).not.toHaveBeenCalled();
});
it("keeps unsupported-device game edits and reset on the direct Steam route", async () => {
  state.owner.supported = false;
  const reset = vi.fn(); (window as any).SystemPerfStore.ResetCurrentPerfProfileSettings = reset;
  await mount(); await act(async () => {edit();});
  expect(state.write).toHaveBeenCalledExactlyOnceWith(3);
  expect(screen.queryByRole("dialog")).toBeNull();
  await act(async () => {fireEvent.click(screen.getByRole("button", {name: "steam.performance.control.reset"}));});
  expect(reset).toHaveBeenCalledOnce(); expect(state.claim).not.toHaveBeenCalled(); expect(state.update).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", {name: "steam.performance.release"})).toBeNull();
});
it("blocks game edits while ownership is unavailable or Steam profile is unknown", async () => {
  state.get.mockRejectedValue(new Error("unavailable"));
  await mount();
  expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(true);
  await act(async () => {edit();}); expect(state.write).not.toHaveBeenCalled();
  state.active = "bad-profile"; await act(async () => {state.notify();});
  expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(true); expect(state.claim).not.toHaveBeenCalled();
});

it("keeps a selection visible while Steam readback is delayed instead of flashing the old option", async () => {
  state.owner.explicit_owner = "pdc";
  state.write.mockImplementation(() => {});
  await mount();
  await act(async () => { edit(); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
  await act(async () => { state.notify(); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
  state.filter = 3;
  await act(async () => { await vi.advanceTimersByTimeAsync(100); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
  expect(screen.getByRole("status").textContent).not.toBe("steam.performance.writeFailed");
});
it("restores the observed option and reports an unconfirmed write after the bounded wait", async () => {
  state.owner.explicit_owner = "pdc";
  state.write.mockImplementation(() => {});
  await mount();
  await act(async () => { edit(); });
  await act(async () => { await vi.advanceTimersByTimeAsync(4100); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("1");
  expect(screen.getByRole("status").textContent).toBe("steam.performance.writeFailed");
});
it("rolls back the displayed selection immediately when Steam rejects the write", async () => {
  state.owner.explicit_owner = "pdc";
  state.write.mockImplementation(() => { throw new Error("rejected"); });
  await mount();
  await act(async () => { edit(); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("1");
  expect(screen.getByRole("status").textContent).toBe("steam.performance.writeFailed");
});

it("does not time out readback while ownership persistence has not sent the write", async () => {
  state.owner.explicit_owner = "pdc";
  let resolve!: (value: unknown) => void;
  state.update.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  await mount();
  await act(async () => { edit(); });
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(state.write).not.toHaveBeenCalled();
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
  expect(screen.getByRole("status").textContent).not.toBe("steam.performance.writeFailed");
  await act(async () => { resolve({ ok: true, ...state.owner }); });
  expect(state.write).toHaveBeenCalledWith(3);
  expect(screen.getByRole("status").textContent).not.toBe("steam.performance.writeFailed");
});
it("discards pending selection when Steam changes profile before component props update", async () => {
  state.owner.explicit_owner = "pdc";
  state.write.mockImplementation(() => {});
  await mount();
  await act(async () => { edit(); });
  state.active = "769";
  await act(async () => { state.notify(); });
  state.active = "42";
  await act(async () => { state.notify(); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("1");
});

it("preserves the selected option across the real QAM remount caused by a context menu", async () => {
  state.owner.explicit_owner = "pdc";
  state.write.mockImplementation(() => {});
  const first = await mount();
  await act(async () => { edit(); });
  first.unmount();
  await mount();
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
  state.filter = 3;
  await act(async () => { await vi.advanceTimersByTimeAsync(100); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
});

it("delivers rejection and rollback to the replacement QAM mount within the pending refresh", async () => {
  state.owner.explicit_owner = "pdc";
  let reject!: (reason: Error) => void;
  state.write.mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
  const first = await mount();
  await act(async () => { edit(); });
  first.unmount();
  await mount();
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
  await act(async () => { reject(new Error("Steam rejected")); await vi.advanceTimersByTimeAsync(100); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("1");
  expect(screen.getByRole("status").textContent).toBe("steam.performance.writeFailed");
});

it("shows readable controls while missing profile identity and recovers without remount", async () => {
  state.active = "missing";
  await mount();
  expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(true);
  expect(screen.getByRole("status").textContent).toBe("steam.performance.profile.unknown");
  state.active = "42";
  await act(async () => { state.notify(); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(false);
  expect(state.write).not.toHaveBeenCalled();
});

it.each(["steam", "pdc"])("blocks degraded Deck ownership and recovers without treating it as unsupported (%s)", async (owner) => {
  Object.assign(state.owner, { supported: false, owner, explicit_owner: owner, reason: "ownership_capability_lost", write_allowed: false });
  const reset = vi.fn(); (window as any).SystemPerfStore.ResetCurrentPerfProfileSettings = reset;
  await mount();
  expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(true);
  const button = screen.getByRole("button", {name: "steam.performance.control.reset"}) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  await act(async () => { edit(); fireEvent.click(button); });
  expect(state.write).not.toHaveBeenCalled(); expect(reset).not.toHaveBeenCalled(); expect(state.reset).not.toHaveBeenCalled();
  Object.assign(state.owner, { supported: true, reason: "explicit_owner", write_allowed: owner === "pdc" });
  await act(async () => { state.notify(); });
  expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(false);
});
it.each(["edit", "reset"])("rechecks capability loss before a queued %s writes to Steam", async (action) => {
  Object.assign(state.owner, { owner: "pdc", explicit_owner: "pdc" });
  const reset = vi.fn(); (window as any).SystemPerfStore.ResetCurrentPerfProfileSettings = reset;
  await mount();
  state.get.mockResolvedValue({ ...state.owner, supported: false, reason: "ownership_capability_lost", write_allowed: false });
  await act(async () => { if (action === "edit") edit(); else fireEvent.click(screen.getByRole("button", {name: "steam.performance.control.reset"})); });
  expect(state.write).not.toHaveBeenCalled(); expect(reset).not.toHaveBeenCalled(); expect(state.reset).not.toHaveBeenCalled(); expect(state.update).not.toHaveBeenCalled();
});
