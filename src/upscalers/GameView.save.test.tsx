// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { GameDetail, UpscalersOverview } from "./types";
import type { GameEntry } from "../launch/steamApi";

const state = vi.hoisted(() => ({ live: { fps: null, render: null, output: null, generating: null, canPause: false, active: false } as any, imageDirty: null as null | ((dirty: boolean) => void), imageSaves: 0, detail: null as unknown, job: null as unknown, nextId: 0, running: null as any, advancedRows: false, frameProps: null as any, t: (key: string, _params?: Record<string, unknown>) => key }));
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
vi.mock("./LivePanel", () => ({ DuringPlay: () => <span>during-play</span>, useUpscalerLive: () => [state.live, vi.fn()] }));
vi.mock("./ImageControls", async () => {
  const React = await import("react");
  return { ImageControls: React.forwardRef((props: any, ref: any) => {
    React.useImperativeHandle(ref, () => ({ save: async () => { state.imageSaves++; if (props.gameRunning) props.onSavedForNextLaunch?.(); return true; }, discard: () => props.onDirty?.(false) }));
    return <button onClick={() => props.onDirty?.(true)}>change sharpness</button>;
  }) };
});
vi.mock("./WikiFacts", () => ({ WikiFacts: () => null }));
vi.mock("./restartGame", () => ({ restartGame: vi.fn() }));
vi.mock("../navigation/showModal", () => ({ showModal: vi.fn() }));
vi.mock("./FrameGenRow", () => ({ FrameGenRow: (props: any) => { state.frameProps = props; return state.advancedRows ? props.renderAdvanced(null) : null; } }));
vi.mock("./parts", () => {
  const Box = ({ children }: any) => <div>{children}</div>;
  return { Row: Box, Note: Box, Label: Box, ListCard: Box, Notice: Box, Skeleton: () => null, Spinner: () => null,
    Fold: () => null,
    ListRow: ({ label, onPress }: any) => state.advancedRows ? <button onClick={onPress}>{label}</button> : null, SegmentRow: ({ options, onChange }: any) => <div>{options.map((o: any) => <button key={o.value} onClick={() => onChange?.(o.value)}>{o.label}</button>)}</div>, statusColor: () => "",
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
import { configureUpscaler } from "../api";
import { releasePage } from "./pageMemory";

const build = { family: "fsr", image: 1, cost: 1, available: true, supported: true, download_bytes: 100 };
const overview = { preferred: "fsr-4.1.1", gpu: "rdna2", display: [1920, 1200], job: null,
  builds: [{ ...build, id: "fsr-4.1.1", version: "4.1.1" }] } as unknown as UpscalersOverview;
const game = { liveAppid: 777, name: "Remake", isNonSteam: false, coverUrls: [] } as unknown as GameEntry;
const props = { game, overview, onBack: vi.fn(), onChanged: vi.fn() };
const installed = (status = "pending") => ({ analysis: { target: "/game", inputs: { dlss: ["nvngx.dll"] }, candidates: [] }, history: [],
  recipe_info: { recommended_input: "dlss", needs: [] },
  install: { build: "fsr-4.1.1", status, options: { quality: "native", sharpness: null, fg: "off", fg_route: null } } }) as unknown as GameDetail;
afterEach(() => { state.running = null; state.live = { ...state.live, active: false }; state.imageSaves = 0; cleanup(); releasePage(); vi.clearAllMocks(); });

it("saves quality and sharpness with one button", async () => {
  state.detail = installed();
  await act(async () => { render(<GameView {...props} />); });
  await act(async () => { fireEvent.click(screen.getByText("change sharpness")); });
  await act(async () => { fireEvent.click(screen.getByText("up.quality.balanced")); });
  expect(screen.getAllByText("up.save")).toHaveLength(1);
  await act(async () => { fireEvent.click(screen.getByText("up.save")); });
  expect(state.imageSaves).toBe(1);
  expect(configureUpscaler).toHaveBeenCalledWith("777", expect.objectContaining({ quality: "balanced" }));
});

it("says a change waits for a restart right under the scaler, also after leaving the page", async () => {
  state.running = { liveAppid: 777 };
  state.detail = installed();
  let page: ReturnType<typeof render>;
  await act(async () => { page = render(<GameView {...props} />); });
  await act(async () => { fireEvent.click(screen.getByText("change sharpness")); });
  await act(async () => { fireEvent.click(screen.getByText("up.save")); });
  expect(screen.getByText("up.live.appliedNext")).toBeTruthy();
  expect(screen.getByText("up.restart.button")).toBeTruthy();
  const notice = screen.getByText("up.live.appliedNext");
  expect(notice.compareDocumentPosition(screen.getByText("during-play")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  page!.unmount();
  releasePage();
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.getByText("up.live.appliedNext")).toBeTruthy();
  state.running = null;
});

it("drops the in-game input hint once the scaler is seen working", async () => {
  state.running = { liveAppid: 777 };
  state.detail = installed();
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.getByText("up.input.recommended")).toBeTruthy();
  cleanup();
  state.live = { ...state.live, active: true };
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.queryByText("up.input.recommended")).toBeNull();
});

it("hides quality when the game decides it", async () => {
  state.detail = { ...installed(), solution: { quality: { owner: "game" }, recommended_input: null, offered_fg_plan: null, fg_plan: null } } as unknown as GameDetail;
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.queryByText("up.quality.balanced")).toBeNull();
  expect(screen.getByText("up.quality.inGame")).toBeTruthy();
});

it("locks quality with one line when the game sized itself despite offering XeSS", async () => {
  const detail = installed();
  state.detail = { ...detail, analysis: { ...detail.analysis, inputs: { xess: ["libxess.dll"], fsr31: ["x.dll"] } },
    recipe_info: null, install: { ...detail.install!, quality_check: { result: "ignored", input: "FSR3", ratio: 2 } } } as unknown as GameDetail;
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.getByText("up.quality.useInput")).toBeTruthy();
  expect(screen.getByText("up.quality.balanced").closest("div")).toBeTruthy();
  expect(screen.queryByText("up.input.recommended")).toBeNull();
});

it("hides quality for a game that only offers its own FSR", async () => {
  const detail = installed();
  state.detail = { ...detail, analysis: { ...detail.analysis, inputs: { fsr31: ["x.dll"] } }, recipe_info: null } as unknown as GameDetail;
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.queryByText("up.quality.balanced")).toBeNull();
  expect(screen.getByText("up.quality.inGame")).toBeTruthy();
});

it("keeps quality for an FSR-only game once the first launch shows it obeys", async () => {
  const detail = installed();
  state.detail = { ...detail, analysis: { ...detail.analysis, inputs: { fsr31: ["x.dll"] } }, recipe_info: null,
    install: { ...detail.install!, quality_check: { result: "respected", input: "FSR3", ratio: 1 } } } as unknown as GameDetail;
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.getByText("up.quality.balanced")).toBeTruthy();
});

it("saves a new version chosen while playing for when the game closes, and keeps it on return", async () => {
  state.running = { liveAppid: 777 };
  state.detail = installed();
  const page = render(<GameView {...props} overview={{ ...overview, builds: [...overview.builds, { ...build, id: "fsr-4.0.2c", version: "4.0.2c" }] } as unknown as UpscalersOverview} />);
  await act(async () => { await Promise.resolve(); });
  await act(async () => { fireEvent.click(screen.getByText("choose 402")); });
  await act(async () => { fireEvent.click(screen.getByText("up.save")); });
  expect(screen.getByText("up.live.appliedOnExit")).toBeTruthy();
  expect(screen.queryByText("up.save")).toBeNull();
  page.unmount();
  releasePage();
  await act(async () => { render(<GameView {...props} />); });
  expect(screen.getByTestId("selected-build").textContent).toBe("fsr-4.0.2c");
  expect(screen.getByText("up.live.appliedOnExit")).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getAllByText("up.discard")[0]); });
  state.running = null;
});

it("saves a quality chosen while playing a REFramework game for when the game closes", async () => {
  state.running = { liveAppid: 777 };
  const detail = installed();
  state.detail = { ...detail, recipe_info: { ...detail.recipe_info, quality_on_exit: true } } as unknown as GameDetail;
  await act(async () => { render(<GameView {...props} />); });
  await act(async () => { fireEvent.click(screen.getByText("up.quality.balanced")); });
  await act(async () => { fireEvent.click(screen.getByText("up.save")); });
  expect(configureUpscaler).not.toHaveBeenCalled();
  expect(screen.getByText("up.live.appliedOnExit")).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByText("up.quality.performance")); });
  expect(screen.getByText("up.save")).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getAllByText("up.discard")[0]); });
  state.running = null;
});

it("asks REFramework games to run full screen at the display's resolution", async () => {
  const detail = installed();
  state.detail = { ...detail, recipe_info: { ...detail.recipe_info, quality_on_exit: true } } as unknown as GameDetail;
  const plain = state.t;
  state.t = (key: string, params?: Record<string, unknown>) => params?.size ? `${key} ${params.size}` : key;
  await act(async () => { render(<GameView {...props} overview={{ ...overview, display: [800, 1280] } as unknown as UpscalersOverview} />); });
  expect(screen.getByText("up.recipe.fullResolution 1280x800")).toBeTruthy();
  state.t = plain;
});
