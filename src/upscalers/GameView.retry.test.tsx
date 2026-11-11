// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { GameDetail, UpscalersOverview, UpscalerJob } from "./types";
import type { GameEntry } from "../launch/steamApi";

const state = vi.hoisted(() => ({ detail: null as unknown, job: null as unknown, nextId: 0, running: null as any, advancedRows: false, frameProps: null as any, t: (key: string, _params?: Record<string, unknown>) => key }));
vi.mock("../system/uiEvents", () => ({ recordUiEvent: vi.fn() }));
vi.mock("../api", () => ({
  getMakoStatus: vi.fn(async () => ({ profiles: {} })),
  getUpscalersGame: vi.fn(async () => state.detail),
  getUpscalersJob: vi.fn(async () => state.job),
  installUpscaler: vi.fn(async () => {
    state.job = { id: `ui-retry-${++state.nextId}`, appid: "777", kind: "install", state: "running", phase: "download", done: 0, total: 100 };
    return state.job;
  }),
  configureUpscaler: vi.fn(async (_appid, choice) => {
    const detail = state.detail as any;
    state.detail = { ...detail, install: { ...detail.install, options: choice } };
    return { live: false };
  }),
  refreshUpscalerWiki: vi.fn(async () => ({ updated: false })),
  recordUpscalerArgs: vi.fn(async () => ({})),
}));
vi.mock("@decky/api", () => ({ openFilePicker: vi.fn() }));
vi.mock("@decky/ui", () => ({ Focusable: ({ children }: any) => <div>{children}</div>, Navigation: {}, ConfirmModal: () => null }));
vi.mock("../i18n", () => ({ useI18n: () => ({ t: state.t }) }));
vi.mock("../components/CompactBackAction", () => ({ CompactBackAction: () => null }));
vi.mock("../components/GameCover", () => ({ GameCover: () => null }));
vi.mock("../components/sectionBack", () => ({ useSectionBack: () => true }));
vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => state.running }));
vi.mock("./gameHotkey", () => ({ pressUpscalerKeyInGame: vi.fn(async () => ({ pressed: "fps_style" })) }));
vi.mock("../themes/useThemes", () => ({ useThemes: () => ({ cards: [], snapshot: { themes: [] } }) }));
vi.mock("../launch/steamApi", () => ({ readAppDetails: vi.fn(async () => ({ compatName: "", launch: "" })), writeLaunchOptions: vi.fn(() => true) }));
vi.mock("../launch/useProtonCapabilities", () => ({ useProtonCapabilities: () => ({ status: "loading" }) }));
vi.mock("./CompareView", () => ({ CompareView: () => null, isComparing: () => false }));
vi.mock("./IdentityModal", () => ({ openIdentityModal: vi.fn() }));
vi.mock("./shortcutHint", () => ({ readShortcutHint: vi.fn() }));
vi.mock("./MakoScaling", () => ({ MakoScaling: () => null }));
vi.mock("./AdvancedIni", () => ({ AdvancedIni: () => null }));
vi.mock("./LivePanel", () => ({ DuringPlay: () => null, useUpscalerLive: () => [{ fps: null, render: null, output: null, generating: null, canPause: false }, vi.fn()] }));
vi.mock("./WikiFacts", () => ({ WikiFacts: () => null }));
vi.mock("./restartGame", () => ({ restartGame: vi.fn() }));
vi.mock("../navigation/showModal", () => ({ showModal: vi.fn() }));
vi.mock("./FrameGenRow", () => ({ FrameGenRow: (props: any) => { state.frameProps = props; return state.advancedRows ? props.renderAdvanced(null) : null; } }));
vi.mock("./parts", () => {
  const Box = ({ children }: any) => <div>{children}</div>;
  return { Row: Box, Note: Box, Label: Box, ListCard: Box, Notice: Box, Skeleton: () => null, Spinner: () => null,
    Fold: () => null,
    ListRow: ({ label, onPress }: any) => state.advancedRows ? <button onClick={onPress}>{label}</button> : null, SegmentRow: ({ options }: any) => <div>{options.map((o: any) => <span key={o.value}>{o.label}{o.caption && <small>{o.caption}</small>}</span>)}</div>, statusColor: () => "",
    ActionButton: ({ label, onPress, disabled }: any) => <button disabled={disabled} onClick={onPress}>{label}</button> };
});
vi.mock("./ModelPicker", () => ({ ModelPicker: ({ choice, onChange, onPendingChoice, onSpatial }: any) => <>
  <button onClick={() => onSpatial(true)}>choose Mako</button>
  <button onClick={() => onPendingChoice(true)}>choose DLL engine</button>
  <output data-testid="selected-build">{choice.build}</output>
  <button onClick={() => onChange({ ...choice, build: "fsr-4.0.2c", quality: "balanced", sharpness: "soft", model: null })}>choose 402</button>
  <button onClick={() => onChange({ ...choice, build: "fsr-4.1.1" })}>choose 411</button>
  <button onClick={() => onChange({ ...choice, build: "fsr-lite", model: null })}>choose Lite</button>
</> }));

import { GameView } from "./GameView";
import { pressUpscalerKeyInGame } from "./gameHotkey";
import { recordUiEvent } from "../system/uiEvents";
import { installUpscaler, configureUpscaler, getMakoStatus } from "../api";
import { readInstallRequest, startInstallJob, trackJob } from "./jobRunner";
import { readAppDetails } from "../launch/steamApi";
import { releasePage, showGame } from "./pageMemory";

const build = { family: "fsr", image: 1, cost: 1, available: true, supported: true, download_bytes: 100 };
const overview = { preferred: "fsr-4.1.1", gpu: "rdna2", display: [1920, 1200], job: null,
  builds: [{ ...build, id: "fsr-4.1.1", version: "4.1.1" }, { ...build, id: "fsr-4.0.2c", version: "4.0.2c" }] } as UpscalersOverview;
const game = { liveAppid: 777, name: "Stellar Blade", isNonSteam: false, coverUrls: [] } as unknown as GameEntry;
const props = { game, overview, onBack: vi.fn(), onChanged: vi.fn() };
afterEach(() => { state.running = null; state.advancedRows = false; state.t = (key) => key; cleanup(); releasePage(); vi.clearAllMocks(); vi.useRealTimers(); });

it.each([true, false])("retries 402 after remount and download failure (installation removed: %s)", async (removed) => {
  vi.useFakeTimers();
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: "fsr-4.1.1", status: "not_run", options: { quality: "native", sharpness: null, fg: "off", fg_route: null } } } as unknown as GameDetail;
  let page: ReturnType<typeof render>;
  await act(async () => { page = render(<GameView {...props} />); });
  expect(screen.getByTestId("selected-build").textContent).toBe("fsr-4.1.1");
  await act(async () => { fireEvent.click(screen.getByText("choose 402")); });
  await act(async () => { fireEvent.click(screen.getByText("up.save")); });
  expect(installUpscaler).toHaveBeenCalledTimes(1);
  const requested = structuredClone(vi.mocked(installUpscaler).mock.calls[0][1]);
  expect(requested.build).toBe("fsr-4.0.2c");
  page!.unmount();
  showGame(null);
  if (removed) state.detail = { ...(state.detail as object), install: null };
  await act(async () => { page = render(<GameView {...props} overview={{ ...overview, job: state.job as UpscalerJob }} />); });
  expect(screen.getByTestId("selected-build").textContent).toBe("fsr-4.0.2c");
  state.job = { ...(state.job as object), state: "error", error: "download_failed" };
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
  expect(screen.getByTestId("selected-build").textContent).toBe("fsr-4.0.2c");
  await act(async () => { fireEvent.click(screen.getByText("up.retry")); });
  expect(installUpscaler).toHaveBeenNthCalledWith(2, "777", requested);
  expect(recordUiEvent).toHaveBeenCalledWith("upscalers", "retry", expect.objectContaining({
    appid: "777", build: "fsr-4.0.2c", quality: "balanced",
  }), true);
  for (const call of vi.mocked(recordUiEvent).mock.calls) {
    expect(call[2]).not.toHaveProperty("env");
    expect(call[2]).not.toHaveProperty("launchOptions");
  }
  state.job = { ...(state.job as object), state: "done" };
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
});


it.each([true, false])("clears failed intent after explicit configuration (job still in overview: %s)", async (visibleJob) => {
  vi.useFakeTimers();
  const started = await startInstallJob({ appid: "777", liveAppid: 777, isNonSteam: false },
    { build: "fsr-4.0.2c", quality: "balanced", sharpness: "soft" });
  state.job = { ...started, state: "error", error: "download_failed" };
  await vi.advanceTimersByTimeAsync(300);
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: "fsr-4.1.1", status: "not_run", options: { quality: "native", sharpness: null } } };
  await act(async () => { render(<GameView {...props} overview={{ ...overview, job: visibleJob ? state.job as UpscalerJob : null }} />); });
  await act(async () => { fireEvent.click(screen.getByText("choose 411")); });
  await act(async () => { fireEvent.click(screen.getByText("up.save")); });
  expect(screen.getByTestId("selected-build").textContent).toBe("fsr-4.1.1");
  expect(readInstallRequest("777", started.id)).toBeNull();
});


it.each([false, true])("only summarizes model changes when both builds have models (origin has models: %s)", async (hasModels) => {
  state.job = null;
  state.t = (key, params) => key === "up.change.model" ? `${key}: ${params?.from} → ${params?.to}` : key;
  const source = { ...build, id: "source", family: hasModels ? "fsr" : "xess", version: "2", ...(hasModels ? { models: ["full", "lite"] } : {}) };
  const target = { ...build, id: "fsr-lite", version: "4.1.2", models: ["lite"] };
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: "source", status: "not_run", options: { quality: null, sharpness: null, model: null } } };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: hasModels ? 779 : 778 }}
    overview={{ ...overview, builds: [source, target] } as UpscalersOverview} />); });
  await act(async () => { fireEvent.click(screen.getByText("choose Lite")); });
  expect(screen.getByText("up.change.version")).toBeTruthy();
  if (hasModels) expect(screen.getByText("up.change.model: up.model.full → up.model.lite")).toBeTruthy();
  else expect(screen.queryByText(/^up.change.model:/)).toBeNull();
});

it.each([
  ["dll", undefined, "4.0.2c", "4.0.2c", "FSR 4.0.2c (up.mode.dll) → FSR 4.0.2c (OptiScaler)"],
  ["optiscaler", "dll", "4.0.2c", "4.0.2c", "FSR 4.0.2c (OptiScaler) → FSR 4.0.2c (up.mode.dll)"],
  ["dll", "optiscaler", "4.0.2c", "4.1.2", "FSR 4.0.2c (up.mode.dll) → FSR 4.1.2 (OptiScaler)"],
  [undefined, "optiscaler", "4.0.2c", "4.1.2", "FSR 4.0.2c → FSR 4.1.2"],
])("distinguishes installation modes in the pending version summary (%s → %s)", async (fromEngine, toEngine, fromVersion, toVersion, expected) => {
  state.job = null;
  state.t = (key, params) => key === "up.change.version" ? `${params?.from} → ${params?.to}` : key;
  const source = { ...build, id: "mode-source", version: fromVersion, engine: fromEngine };
  const target = { ...build, id: "fsr-lite", version: toVersion, engine: toEngine };
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: "mode-source", status: "not_run", options: { quality: null, sharpness: null, model: null } } };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 780 }}
    overview={{ ...overview, builds: [source, target] } as UpscalersOverview} />); });
  await act(async () => { fireEvent.click(screen.getByText("choose Lite")); });
  expect(screen.getByText(expected!)).toBeTruthy();
});


it("uses the same game-focus guard for the FPS style button", async () => {
  state.job = null;
  state.running = { appid: "777", liveAppid: 777, name: "Stellar Blade" };
  state.advancedRows = true;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: "fsr-4.1.1", status: "active", options: { quality: "native", fg: "off" } } };
  await act(async () => { render(<GameView {...props} draft={{ choice: { build: "fsr-4.1.1", quality: "native", fg: "off", sharpness: null }, advanced: true }} />); });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "up.play.fpsStyle" })));
  expect(pressUpscalerKeyInGame).toHaveBeenCalledWith("777", "fps_style");
});

it("keeps the external Helix page free of replacement and inactive installation controls", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: { dlss: true }, candidates: [], foreign: true,
    foreign_identity: { engine: "helixsr", variant: "dlss" } }, history: [], install: null };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 781 }} />); });
  expect(screen.queryByTestId("selected-build")).toBeNull();
  expect(screen.queryByText("up.foreign.adopt")).toBeNull();
  expect(screen.queryByText("up.activate")).toBeNull();
  expect(screen.queryByText("up.section.quality")).toBeNull();
  expect(screen.getByText("HelixSR DLSS")).toBeTruthy();
});

it.each([null, [800, 1280], [3840, 2160]])("does not invent game resolution from display %s", async (display) => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: "fsr-4.1.1", status: "not_run", options: { quality: "native", fg: "off" } } };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 782 }}
    overview={{ ...overview, display } as UpscalersOverview} />); });
  expect(screen.getByText("up.quality.native")).toBeTruthy();
  expect(screen.queryByText(/^\d+p$/)).toBeNull();
});
it("uses the observed game output for quality captions", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] },
    history: [{ facts: { resolution: { render: [853, 480], output: [1280, 720] } } }],
    install: { build: "fsr-4.1.1", status: "active", options: { quality: "native", fg: "off" } } };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 783 }} />); });
  expect(screen.getByText("720p")).toBeTruthy();
  expect(screen.getByText("480p")).toBeTruthy();
});

it("refreshes installed Mako status without claiming runtime activity", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null };
  state.t = (key, params) => params?.name ? `${key}: ${params.name}` : key;
  await act(async () => { render(<GameView {...props} />); });
  vi.mocked(getMakoStatus).mockResolvedValueOnce({ profiles: { "777": { scaling_enabled: true } } } as any);
  await act(async () => window.dispatchEvent(new Event("pdc-mako-changed")));
  expect(screen.getByText("up.state.installed: Mako")).toBeTruthy();
  expect(screen.queryByText("up.state.working: Mako")).toBeNull();
});

it("does not offer the previous OptiScaler action while a DLL model is unchosen", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null };
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.getByRole("button", { name: "up.activate" })).toBeTruthy();
  fireEvent.click(screen.getByText("choose DLL engine"));
  expect(screen.queryByRole("button", { name: "up.activate" })).toBeNull();
  expect(screen.queryByText("up.section.quality")).toBeNull();
  expect(screen.getByTestId("selected-build").textContent).toBe("fsr-4.1.1");
});


it.each([undefined, false, true])("shows the Luma prerequisite only when not detected (%s)", async (detected) => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null,
    recipe_info: { needs: ["luma", "mod"], luma_detected: detected } };
  await act(async () => { render(<GameView {...props} />); });
  expect(!!screen.queryByText("up.recipe.need.luma")).toBe(!detected);
  expect(screen.queryByText("up.recipe.need.mod")).toBeTruthy();
  expect(screen.queryByText("up.detect.noinputs")).toBeNull();
});

it("removes the Luma requirement when choosing Mako", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null,
    recipe_info: { needs: ["luma"] } };
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.queryByText("up.recipe.need.luma")).toBeTruthy();
  fireEvent.click(screen.getByText("choose Mako"));
  expect(screen.queryByText("up.recipe.need.luma")).toBeNull();
});

it.each([undefined, false, true])("announces automatic Luma only when not detected (%s)", async (detected) => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null,
    recipe_info: { needs: ["luma"], luma_detected: detected, automatic: ["Luma"] } };
  await act(async () => { render(<GameView {...props} />); });
  expect(!!screen.queryByText("up.recipe.automatic.luma")).toBe(!detected);
  expect(screen.queryByText("up.recipe.need.luma")).toBeNull();
  expect((screen.getByRole("button", { name: "up.activate" }) as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(screen.getByText("choose Mako"));
  expect(screen.queryByText("up.recipe.automatic.luma")).toBeNull();
});

it("allows attempting unresolved OptiScaler recipes while leaving Mako independent", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null,
    recipe_info: { needs: ["luma"], blocked: true } };
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.queryByText("up.recipe.blocked")).toBeTruthy();
  const activate = screen.getByRole("button", { name: "up.activate" }) as HTMLButtonElement;
  expect(activate.disabled).toBe(false);
  await act(async () => { fireEvent.click(activate); });
  expect(installUpscaler).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText("choose Mako"));
  expect(screen.queryByText("up.recipe.blocked")).toBeNull();
  expect(screen.queryByText("up.recipe.need.luma")).toBeNull();
});

it("allows applying a selected build despite an unresolved recipe warning", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: "fsr-4.1.1", status: "not_run", options: { quality: "native", sharpness: null } },
    recipe_info: { needs: ["luma"], blocked: true } };
  await act(async () => { render(<GameView {...props} />); });
  fireEvent.click(screen.getByText("choose 402"));
  expect((screen.getByRole("button", { name: "up.save" }) as HTMLButtonElement).disabled).toBe(false);
  await act(async () => { fireEvent.click(screen.getByText("up.save")); });
  expect(installUpscaler).toHaveBeenCalledWith("777", expect.objectContaining({ build: "fsr-4.0.2c", quality: "balanced" }));
});


it.each(["optiscaler", "dll", "helixsr", "proton"])("only shows the game input recommendation for OptiScaler (%s)", async (engine) => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: { xess: ["libxess.dll"] }, candidates: [] }, history: [],
    recipe_info: { recommended_input: "xess", needs: [] }, install: null };
  const selected = { ...build, id: "input-guidance", version: "4.1.2", engine };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 998 }}
    overview={{ ...overview, preferred: selected.id, builds: [selected] } as UpscalersOverview} />); });
  if (engine === "optiscaler") expect(screen.getByText("up.input.recommended")).toBeTruthy();
  else expect(screen.queryByText("up.input.recommended")).toBeNull();
});

it.each([
  [false, true, "FSR 4.1.1 → FSR 4.1.1 Lite"],
  [true, false, "FSR 4.1.1 Lite → FSR 4.1.1"],
])("names both DLL variants in the pending change (%s → %s)", async (sourceLite, targetLite, expected) => {
  state.job = null;
  state.t = (key, params) => key === "up.change.version" ? `${params?.from} → ${params?.to}` : key;
  const source = { ...build, id: "dll-source", engine: "dll", version: "4.1.1", ...(sourceLite ? { models: ["lite"] } : {}) };
  const target = { ...build, id: "fsr-lite", engine: "dll", version: "4.1.1", ...(targetLite ? { models: ["lite"] } : {}) };
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: source.id, status: "not_run", options: { quality: null, sharpness: null, model: null } } };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 790 }}
    overview={{ ...overview, builds: [source, target] } as UpscalersOverview} />); });
  await act(async () => { fireEvent.click(screen.getByText("choose Lite")); });
  expect(screen.getByText(expected)).toBeTruthy();
  expect(screen.queryByText("up.change.model")).toBeNull();
});

it("hides quality only where the game decides it, without blocking the other choices", async () => {
  state.job = null;
  const normal = { effective_api: "d3d12", api_source: "detected", quality: { owner: "panel", reason: null }, fg_plan: { routes: { optiscaler: { input: "optiscaler" } }, route: "optiscaler" }, blocked_reason: null, dependencies: [], recipe_revision: 1 };
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null,
    solutions: { "fsr-4.1.1": normal, "fsr-4.0.2c": { ...normal, effective_api: "d3d11", api_source: "recipe", quality: { owner: "game", reason: "recipe" }, fg_plan: null, offered_fg_plan: normal.fg_plan, dependencies: ["luma"], input_reconciled: true } } };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 798 }} />); });
  expect(screen.getByText("up.section.quality")).toBeTruthy();
  expect(state.frameProps.routes).toHaveProperty("optiscaler");
  await act(async () => fireEvent.click(screen.getByText("choose 402")));
  expect(state.frameProps.routes).toHaveProperty("optiscaler");
  expect(state.frameProps.recommendedRoutes).toEqual({});
  expect(screen.queryByText("up.section.quality")).toBeNull();
  expect(screen.getByText("up.quality.inGame")).toBeTruthy();
  expect(screen.queryByText("up.detect.noinputs")).toBeNull();
  await act(async () => fireEvent.click(screen.getByText("up.activate")));
  expect(installUpscaler).toHaveBeenCalledWith("798", expect.objectContaining({ build: "fsr-4.0.2c", quality: "balanced", fg: "off" }));
});

it("disables incompatible installed FG without rewriting the stored quality", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [],
    install: { build: "fsr-4.1.1", status: "not_run", options: { quality: "balanced", sharpness: "soft", fg: "on", fg_route: "optiscaler" } },
    solutions: { "fsr-4.1.1": { effective_api: "d3d11", api_source: "recipe", quality: { owner: "game", reason: "recipe" }, fg_plan: null, blocked_reason: "dependency_unresolved", dependencies: ["luma"], recipe_revision: 3 } } };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 799 }} />); });
  await act(async () => { await state.frameProps.onApplyOptiscaler("off", null); });
  expect(configureUpscaler).toHaveBeenCalledWith("799", { fg: "off" });
});

it.each(["fresh", "draft", "installed"])("applies the recipe recommendation only to a fresh choice: %s", async (mode) => {
  const choice = { build: "fsr-4.1.1", quality: "native" as const, sharpness: null, fg: "off" as const, fg_route: null, model: null };
  state.detail = { preferred: "fsr-4.0.2c", analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: mode === "installed" ? { build: choice.build, status: "not_run", options: choice } : null };
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 778 }} draft={mode === "draft" ? { choice, advanced: false } : null} />); });
  expect(screen.getByTestId("selected-build").textContent).toBe(mode === "fresh" ? "fsr-4.0.2c" : "fsr-4.1.1");
});

it("shows the closing launch notice of a job that finished while the page was closed", async () => {
  vi.useFakeTimers();
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null };
  state.job = { id: "closed-page", appid: "791", kind: "install", state: "done", result: { overrides: ["dxgi=n,b"], args: [] } };
  vi.mocked(readAppDetails).mockResolvedValueOnce(null);
  trackJob({ id: "closed-page", appid: "791", kind: "install", state: "running" } as never, { appid: "791", liveAppid: 791, isNonSteam: false });
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 791 }} overview={{ ...overview, job: state.job as UpscalerJob }} />); });
  expect(screen.getByText("up.launch.failed")).toBeTruthy();
});

it("explains a retryable failure that ended while the page was closed", async () => {
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null };
  const failed = { id: "closed-error", appid: "792", kind: "install", state: "error", error: "download_failed", phase: "download", done: 0, total: 0 } as UpscalerJob;
  state.job = failed;
  state.t = (key) => key === "up.error.download_failed" ? "Download failed" : key;
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 792 }} overview={{ ...overview, job: failed }} />); });
  expect(screen.getByText("Download failed")).toBeTruthy();
  expect(screen.getByText("up.retry")).toBeTruthy();
});

it("ignores another game's job progress and cancel control", async () => {
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null };
  const other = { id: "other-game", appid: "1", kind: "install", state: "running", phase: "download", done: 1, total: 10 } as UpscalerJob;
  await act(async () => { render(<GameView {...props} game={{ ...game, liveAppid: 793 }} overview={{ ...overview, job: other }} />); });
  expect(screen.queryByText("up.cancel")).toBeNull();
});

it("tells which option to change in the game's own menu", async () => {
  state.job = null;
  state.detail = { analysis: { target: "/game", inputs: {}, candidates: [] }, history: [], install: null,
    recipe_info: { needs: [], game_settings: [{ setting: "FidelityFX Super Resolution 2", value: "No" }] } };
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.getByText("up.recipe.gameSetting")).toBeTruthy();
});
