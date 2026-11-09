// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ refreshFrameGenEngine: vi.fn(), getMakoStatus: vi.fn(), installMako: vi.fn(), setMakoGame: vi.fn(), getUpscalerLaunchReceipt: vi.fn(), managedLaunch: vi.fn(), readAppDetails: vi.fn(), getLsfgStatus: vi.fn(), adoptForeignLsfg: vi.fn(), installLsfg: vi.fn(), setLsfgGame: vi.fn(), restoreForeignLsfg: vi.fn(), writeLaunchOptions: vi.fn() }));
vi.mock("../api", () => api);
vi.mock("../components/ContainedSlider", () => ({ ContainedSlider: ({ label, value, min, max, step, disabled, onChange }: any) => <input type="range" aria-label={label} value={value} min={min} max={max} step={step} disabled={disabled} onChange={e => onChange(Number(e.target.value))} /> }));
vi.mock("./managedLaunch", () => ({ applyManagedLaunch: api.managedLaunch }));
vi.mock("./losslessBranch", () => ({ readLosslessBranch: async () => ({ selected: "lsfg-vk", available: true, supported: true }), switchLosslessBranch: vi.fn() }));
vi.mock("../launch/steamApi", () => ({ readAppDetails: api.readAppDetails, writeLaunchOptions: api.writeLaunchOptions }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../components/ExperimentalBadge", () => ({ ExperimentalBadge: ({ children }: any) => <span>{children}</span> }));
vi.mock("./parts", () => ({
  Note: ({ children }: any) => <div>{children}</div>,
  ActionButton: ({ label, onPress, disabled, busy }: any) => <button disabled={disabled || busy} onClick={onPress}>{label}</button>,
  PickerButton: ({ label, value, options, onChange }: any) => <select aria-label={label} value={value} onChange={e => onChange(e.target.value)}>{options.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>,
  Label: ({ children }: any) => <div>{children}</div>, ListCard: ({ children }: any) => <div>{children}</div>,
  ListRow: ({ label }: any) => <div>{label}</div>, Notice: ({ children }: any) => <div>{children}</div>, Row: ({ children }: any) => <div>{children}</div>,
}));
import { FrameGenRow } from "./FrameGenRow";
const foreign = { installed: false, foreign: true, lossless: true, dll: "/lossless/lsfg-vk.dll", profiles: {}, foreign_backup: false };
beforeEach(() => {
  api.refreshFrameGenEngine.mockResolvedValue({ state: "current", version: "4.6.0" });
  api.getMakoStatus.mockResolvedValue(null);
  api.readAppDetails.mockResolvedValue({ launch: "" });
  api.getUpscalerLaunchReceipt.mockResolvedValue(null);
  api.managedLaunch.mockResolvedValue({ ok: true, preserved: { env: [], wrappers: [] } });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });
it("offers detected foreign Lossless without changing it until explicit adoption", async () => {
  api.getLsfgStatus.mockResolvedValue(foreign);
  const onOptiscaler = vi.fn();
  render(<FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} routes={{}} inputs={{ fsrfg: [] }} optiscaler={{ fg: "off", route: "game" }} installedRoute={null} gpu="amd" onOptiscaler={onOptiscaler} />);
  const select = await screen.findByRole("combobox", { name: "up.fg.title" });
  expect(screen.getByText("up.fg.own")).toBeTruthy();
  expect(screen.queryByText("up.lsfg.foreign")).toBeNull();
  expect(screen.queryByRole("button", { name: "up.lsfg.adopt" })).toBeNull();
  fireEvent.change(select, { target: { value: "lsfg" } });
  await waitFor(() => expect((select as HTMLSelectElement).value).toBe("lsfg"));
  expect(screen.queryByText("up.fg.own")).toBeNull();
  expect(api.adoptForeignLsfg).not.toHaveBeenCalled();
  expect(api.installLsfg).not.toHaveBeenCalled();
  expect(api.setLsfgGame).not.toHaveBeenCalled();
  expect(api.writeLaunchOptions).not.toHaveBeenCalled();
  api.adoptForeignLsfg.mockResolvedValue({ ...foreign, foreign: false, foreign_backup: true });
  api.installLsfg.mockResolvedValue({ ...foreign, installed: true, foreign: false });
  api.setLsfgGame.mockResolvedValue({ env: { LSFGVK_PROFILE: "pdc-1", ENABLE_GAMESCOPE_WSI: "0" } });
  api.writeLaunchOptions.mockReturnValue(true);
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false, foreign_backup: true });
  fireEvent.click(screen.getByRole("button", { name: "up.lsfg.adopt" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "up.lsfg.adopt" })).toBeNull());
  expect(api.setLsfgGame).not.toHaveBeenCalled();
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  await waitFor(() => expect(onOptiscaler).toHaveBeenCalledWith("off", null));
  expect(api.adoptForeignLsfg).toHaveBeenCalledOnce();
  expect(api.installLsfg).toHaveBeenCalledOnce();
  expect(api.setLsfgGame).toHaveBeenCalledWith("1", { multiplier: 2, flow: "balanced", performance: true });
});

it("keeps restoration out of the main controls and renders it through advanced options", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false, foreign_backup: true, profiles: { "1": { multiplier: 3, flow: "balanced", performance: false } } });
  const view = (open: boolean) => <FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} routes={{}} inputs={{}} optiscaler={{ fg: "off", route: "game" }} installedRoute={null} gpu="amd" onOptiscaler={vi.fn()} renderAdvanced={restore => open ? <section aria-label="advanced">{restore}</section> : null} />;
  const { rerender } = render(view(false));
  await screen.findByRole("combobox", { name: "up.lsfg.multiplier" });
  expect(screen.queryByText("up.lsfg.restore")).toBeNull();
  rerender(view(true));
  expect(screen.getByRole("region", { name: "advanced" }).textContent).toContain("up.lsfg.restore");
  expect(api.restoreForeignLsfg).not.toHaveBeenCalled();
});

it("retains advanced options when there are no frame generation controls", () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false, lossless: false, dll: null });
  render(<FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} routes={{}} inputs={{}} optiscaler={{ fg: "off", route: "game" }} installedRoute={null} gpu="amd" onOptiscaler={vi.fn()} renderAdvanced={() => <div>advanced options</div>} />);
  expect(screen.getByText("advanced options")).toBeTruthy();
});

const baseProps = { appid: "1", liveAppid: 1, isNonSteam: false, gameRunning: false, routes: {}, inputs: {}, optiscaler: { fg: "off" as const, route: "game" as const }, installedRoute: null, gpu: "amd" };
it("only activates managed Lossless after pressing Activate", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, installed: true, foreign: false });
  api.setLsfgGame.mockResolvedValue({ env: {} });
  api.writeLaunchOptions.mockReturnValue(true);
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  fireEvent.change(await screen.findByRole("combobox", { name: "up.fg.title" }), { target: { value: "lsfg" } });
  expect(api.setLsfgGame).not.toHaveBeenCalled();
  expect(api.installLsfg).not.toHaveBeenCalled();
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  await waitFor(() => expect(api.setLsfgGame).toHaveBeenCalledOnce());
});
it("deactivates an active Lossless profile explicitly", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, installed: true, foreign: false, profiles: { "1": { multiplier: 2, flow: "balanced", performance: true } } });
  api.setLsfgGame.mockResolvedValue({ env: {} });
  api.writeLaunchOptions.mockReturnValue(true);
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "up.deactivate" }));
  await waitFor(() => expect(api.setLsfgGame).toHaveBeenCalledWith("1", null));
});
it("keeps selecting an OptiScaler route separate from committing it", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  const draft = vi.fn(), apply = vi.fn().mockResolvedValue(undefined);
  render(<FrameGenRow {...baseProps} routes={{ optiscaler: {} }} onOptiscaler={draft} onApplyOptiscaler={apply} />);
  fireEvent.change(await screen.findByRole("combobox", { name: "up.fg.title" }), { target: { value: "optiscaler" } });
  expect(draft).toHaveBeenCalledWith("on", "optiscaler");
  expect(apply).not.toHaveBeenCalled();
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  await waitFor(() => expect(apply).toHaveBeenCalledExactlyOnceWith("on", "optiscaler"));
});

it("blocks OptiScaler commits without blocking Lossless activation", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, installed: true, foreign: false });
  api.setLsfgGame.mockResolvedValue({ env: {} });
  api.writeLaunchOptions.mockReturnValue(true);
  const apply = vi.fn();
  render(<FrameGenRow {...baseProps} routes={{ optiscaler: {} }} onOptiscaler={vi.fn()} onApplyOptiscaler={apply} optiscalerDisabled />);
  const select = await screen.findByRole("combobox", { name: "up.fg.title" });
  fireEvent.change(select, { target: { value: "optiscaler" } });
  expect(((await screen.findByRole("button", { name: "up.activate" })) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(select, { target: { value: "lsfg" } });
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  await waitFor(() => expect(api.setLsfgGame).toHaveBeenCalledOnce());
  expect(apply).not.toHaveBeenCalled();
});

it("shows a failed OptiScaler commit in the frame generation section", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  render(<FrameGenRow {...baseProps} routes={{ optiscaler: {} }} onOptiscaler={vi.fn()} onApplyOptiscaler={vi.fn().mockRejectedValue(new Error("failed"))} />);
  fireEvent.change(await screen.findByRole("combobox", { name: "up.fg.title" }), { target: { value: "optiscaler" } });
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  expect(await screen.findByText("up.error.generic")).toBeTruthy();
});

const makoReady = { supported: true, installed: true, dll: true, ready: true, foreign: false, profiles: {} };
it("stages Mako then configures it and its owned launcher on explicit activation", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue(makoReady);
  api.setMakoGame.mockResolvedValue({ env: { MAKO_CONFIG: "/config/mako/1.toml" }, wrappers: ["/private/mako-launch"] });
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  expect(api.setMakoGame).not.toHaveBeenCalled();
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  await waitFor(() => expect(api.managedLaunch).toHaveBeenCalledWith("1", 1, "mako", { env: { MAKO_CONFIG: "/config/mako/1.toml" }, wrappers: ["/private/mako-launch"] }, { isNonSteam: false, requireComplete: true }));
});
it("keeps a manually configured Mako launcher and profile untouched", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue(makoReady);
  api.readAppDetails.mockResolvedValue({ launch: "MAKO_PROFILE=custom ~/.local/bin/mako-run %command% -dx11" });
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  expect(await screen.findByText("up.mako.foreignProfile")).toBeTruthy();
  expect(api.setMakoGame).not.toHaveBeenCalled();
  expect(api.managedLaunch).not.toHaveBeenCalled();
});
it("rolls back Mako configuration when launch composition fails", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue(makoReady);
  api.setMakoGame.mockResolvedValue({ env: {}, wrappers: [] });
  api.managedLaunch.mockResolvedValue({ ok: false, preserved: { env: [], wrappers: [] } });
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  expect(await screen.findByText("up.lsfg.launchFailed")).toBeTruthy();
  expect(api.setMakoGame).toHaveBeenLastCalledWith("1", null);
});

it("retires newly configured Mako when the previous generator cannot be disabled", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false, profiles: { "1": { multiplier: 2, flow: "balanced", performance: true } } });
  api.getMakoStatus.mockResolvedValue(makoReady);
  api.setMakoGame.mockResolvedValue({ env: {}, wrappers: [] });
  api.setLsfgGame.mockRejectedValue(new Error("disk"));
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  fireEvent.click((await screen.findByRole("button", { name: "up.save" })));
  expect(await screen.findByText("up.error.generic")).toBeTruthy();
  expect(api.setMakoGame).toHaveBeenLastCalledWith("1", { enabled: false });
  await waitFor(() => expect(api.getLsfgStatus).toHaveBeenCalledTimes(2));
});

it("explains ambiguous shortcuts and prevents claiming another entry's Mako settings", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue({ ...makoReady, ready: false, reason: "mako_identity_ambiguous" });
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  expect(screen.getByText("up.mako.identity")).toBeTruthy();
  expect(((await screen.findByRole("button", { name: "up.activate" })) as HTMLButtonElement).disabled).toBe(true);
  expect(api.setMakoGame).not.toHaveBeenCalled();
});

it("shows activating while the Mako engine download is pending and clears it on failure", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue({ ...makoReady, installed: false });
  let fail!: (error: Error) => void;
  api.installMako.mockReturnValue(new Promise((_resolve, reject) => { fail = reject; }));
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  fireEvent.click((await screen.findByRole("button", { name: "up.activate" })));
  expect(await screen.findByRole("button", { name: "up.activating" })).toBeTruthy();
  fail(new Error("download_failed"));
  expect(await screen.findByText("up.error.generic")).toBeTruthy();
  await waitFor(() => expect(screen.queryByRole("button", { name: "up.activating" })).toBeNull());
});

const installedMako = { installed: true, supported: true, ready: true, dll: true, reason: null, version: "4.6.0", profiles: {} };
it("checks on selection and updates an installed engine before allowing activation", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue(installedMako);
  let finish!: (value: any) => void;
  api.refreshFrameGenEngine.mockResolvedValueOnce({ state: "available", version: "4.6.0", available: "4.6.1" })
    .mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  render(<FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} routes={{}} inputs={{}} optiscaler={{ fg: "off", route: "game" }} installedRoute={null} gpu="amd" onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  expect(await screen.findByRole("button", { name: "up.engine.updating" })).toHaveProperty("disabled", true);
  expect(api.refreshFrameGenEngine.mock.calls).toEqual([["mako", false], ["mako", true]]);
  finish({ state: "updated", version: "4.6.1" });
  expect(await screen.findByRole("button", { name: "up.activate" })).toHaveProperty("disabled", false);
  expect(api.setMakoGame).not.toHaveBeenCalled();
});
it("keeps the installed engine usable after an offline update check", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue(installedMako);
  api.refreshFrameGenEngine.mockResolvedValue({ state: "failed", version: "4.6.0" });
  render(<FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} routes={{}} inputs={{}} optiscaler={{ fg: "off", route: "game" }} installedRoute={null} gpu="amd" onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  expect(await screen.findByText("up.engine.failed")).toBeTruthy();
  expect(await screen.findByRole("button", { name: "up.activate" })).toHaveProperty("disabled", false);
  expect(api.installMako).not.toHaveBeenCalled();
});
it("defers a shared motor update when another game is running", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false, installed: true });
  api.refreshFrameGenEngine.mockResolvedValueOnce({ state: "available", version: "2.0.0", available: "2.0.1" })
    .mockResolvedValueOnce({ state: "deferred", version: "2.0.0" });
  render(<FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} routes={{}} inputs={{}} optiscaler={{ fg: "off", route: "game" }} installedRoute={null} gpu="amd" onOptiscaler={vi.fn()} />);
  const picker = await screen.findByRole("combobox", { name: "up.fg.title" });
  fireEvent.change(picker, { target: { value: "lsfg" } });
  expect(await screen.findByText("up.engine.deferred")).toBeTruthy();
  expect(api.refreshFrameGenEngine).toHaveBeenCalledWith("lsfg", true);
  expect(api.setLsfgGame).not.toHaveBeenCalled();
});


it("keeps the newly created Mako profile while its launch write is pending", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue(makoReady);
  api.setMakoGame.mockResolvedValue({ env: {}, wrappers: [] });
  api.managedLaunch.mockResolvedValue({ ok: false, pending: true, preserved: { env: [], wrappers: [] } });
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  await screen.findByRole("option", { name: "Mako" });
  fireEvent.change(screen.getByRole("combobox", { name: "up.fg.title" }), { target: { value: "mako" } });
  fireEvent.click(await screen.findByRole("button", { name: "up.activate" }));
  expect(await screen.findByText("up.lsfg.launchFailed")).toBeTruthy();
  expect(api.setMakoGame).toHaveBeenCalledTimes(1);
  expect(api.setMakoGame).not.toHaveBeenCalledWith("1", null);
});

it("restores the previous Mako profile when removing its launcher is pending", async () => {
  const profile = { mode: "fixed", multiplier: 2, target_fps: 120, max_multiplier: 3, flow: "balanced", performance: true };
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false });
  api.getMakoStatus.mockResolvedValue({ ...makoReady, profiles: { "1": profile } });
  api.setMakoGame.mockResolvedValue({ env: {}, wrappers: [] });
  api.managedLaunch.mockResolvedValue({ ok: false, pending: true, preserved: { env: [], wrappers: [] } });
  render(<FrameGenRow {...baseProps} onOptiscaler={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "up.deactivate" }));
  expect(await screen.findByText("up.lsfg.launchFailed")).toBeTruthy();
  expect(api.setMakoGame).toHaveBeenLastCalledWith("1", profile);
});

it("does not show spatial-only Mako as active frame generation", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false, profiles: {} });
  api.getMakoStatus.mockResolvedValue({ supported: true, installed: true, dll: false, profiles: { "1": {
    enabled: false, scaling_enabled: true, scaling_factor: 1.5, scaling_sharpness: 0.8,
    mode: "fixed", multiplier: 2, target_fps: 120, max_multiplier: 3, flow: "balanced", performance: true,
  } } });
  render(<FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} routes={{}} inputs={{}} optiscaler={{ fg: "off", route: "game" }} installedRoute={null} gpu="amd" onOptiscaler={vi.fn()} />);
  await waitFor(() => expect((screen.getByRole("combobox", { name: "up.fg.title" }) as HTMLSelectElement).value).toBe("off"));
  expect(api.setMakoGame).not.toHaveBeenCalled();
});

it("keeps discouraged OptiFG selectable and warns only after selection", async () => {
  api.getLsfgStatus.mockResolvedValue({ ...foreign, foreign: false, lossless: false, dll: null });
  const apply = vi.fn(async () => {});
  render(<FrameGenRow appid="1" liveAppid={1} isNonSteam={false} gameRunning={false} recommendedRoutes={{}} routes={{ optiscaler: {} }} inputs={{}}
    optiscaler={{ fg: "on", route: "optiscaler" }} installedRoute="optiscaler" gpu="rdna3" onOptiscaler={vi.fn()} onApplyOptiscaler={apply} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "up.deactivate" })).toBeTruthy());
  expect(screen.getByRole("option", { name: "up.fg.pick.optiscaler" })).toBeTruthy();
  expect(screen.getByText("up.fg.notRecommended")).toBeTruthy();
  expect(screen.queryByText("up.fg.own")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "up.deactivate" }));
  await waitFor(() => expect(apply).toHaveBeenCalledWith("off", null));
});
