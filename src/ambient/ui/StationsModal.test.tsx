// @vitest-environment happy-dom
import { showModal } from "@decky/ui";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StationsBody, openMediaLibrary } from "./StationsModal";

const state = vi.hoisted(() => ({ runtime: { showLibrary: vi.fn(), radioCatalog: vi.fn(), discoverRadio: vi.fn(), isFavoriteStation: vi.fn() }, modal: {} as any, map: {} as any }));
vi.mock("@decky/ui", () => ({
  NavEntryPositionPreferences: { MAINTAIN_Y: 3 },
  Focusable: ({ children, onActivate, ...props }: any) => <div ref={props.ref} tabIndex={0} onClick={onActivate}>{children}</div>,
  Dropdown: ({ onChange, selectedOption }: any) => <select aria-label="country" value={selectedOption} onChange={(e) => onChange({ data: e.target.value })}><option value="" /><option value="ES">ES</option><option value="US">US</option></select>,
  TextField: (props: any) => <input {...props} />, ModalRoot: (props: any) => { state.modal = props; return props.children; }, showModal: vi.fn(),
}));
vi.mock("../../components/FocusRoot", () => ({ FocusRoot: ({ children }: any) => children }));
vi.mock("../../i18n", () => ({ useI18n: () => ({ t: (key: string) => key, lang: "en" }) }));
vi.mock("./useAmbient", () => ({ useAmbient: () => ({ runtime: state.runtime, snapshot: { player: { track: null, queue: [] } } }) }));
vi.mock("../steam/homeCountry", () => ({ homeCountry: () => Promise.resolve(null) }));
vi.mock("../steam/player", () => ({ trackSource: () => "radio" }));
vi.mock("../steam/runtime", () => ({ stationSubtitle: () => "" }));
vi.mock("./NowPlaying", () => ({ Artwork: () => null, RoundButton: () => null }));
vi.mock("./LibraryPlayback", () => ({ LibraryPlayback: () => null }));
vi.mock("./PlaylistsTab", () => ({ PlaylistsTab: () => null }));
vi.mock("./QueueTab", () => ({ QueueTab: () => null }));
vi.mock("./LibraryTabs", () => ({ LinksTab: () => null }));
vi.mock("./FilesTab", () => ({ FilesTab: () => null }));
vi.mock("./panelModal", () => ({ backToPanel: (callback: any) => callback, leavePanel: vi.fn() }));
vi.mock("./libraryNavigation", () => ({ focusLibraryElement: vi.fn() }));
vi.mock("./WorldMap", () => ({ WorldMap: (props: any) => { state.map = props; return <button onClick={() => props.onViewChange({ zoom: 8, center: { x: 500, y: 250 }, nearestCountry: "ES" })}>zoom</button>; } }));
vi.mock("./VirtualList", () => ({ VirtualList: ({ items, onEndReached }: any) => <div>{items.map((s: any) => <div key={s.id}>{s.name}</div>)}<button onClick={onEndReached}>load more</button></div> }));
vi.mock("./stationsParts", () => ({ Sheet: ({ children }: any) => <div>{children}</div>, Empty: ({ text }: any) => <div>{text}</div>, Chip: ({ label, onActivate }: any) => <button onClick={onActivate}>{label}</button>, DimDialog: () => null, ROW_HEIGHT: 40, oneLine: {}, useMeasuredHeight: () => [null, 300] }));
vi.mock("./primitives", () => ({ Button: ({ label, onActivate }: any) => <button onClick={onActivate}>{label}</button>, Segmented: ({ options, onChange }: any) => <div>{options.map((option: any) => <button key={option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>, menuHandlers: () => ({}) }));

beforeEach(() => { vi.useFakeTimers(); state.runtime.radioCatalog.mockResolvedValue({ countries: [], tags: [] }); state.runtime.discoverRadio.mockResolvedValue([]); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.resetAllMocks(); });
const settle = () => act(async () => { await vi.advanceTimersByTimeAsync(750); });
it("finishes rejected searches and retries catalog, list and area while preserving the filter and view", async () => {
  state.runtime.radioCatalog.mockRejectedValueOnce(new Error("offline"));
  state.runtime.discoverRadio.mockRejectedValue(new Error("offline"));
  render(<StationsBody initialTab="discover" purpose="playback" />);
  fireEvent.change(screen.getByLabelText("country"), { target: { value: "ES" } });
  fireEvent.click(screen.getByText("zoom"));
  await settle();
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(screen.queryByText("ambient.radio.searching")).toBeNull();
  expect(state.map.loadingStations).toBe(false);
  state.runtime.discoverRadio.mockResolvedValue([{ id: "ok", name: "Recovered", geo: [40, -3] }]);
  fireEvent.click(screen.getByText("ambient.retry"));
  await settle();
  expect(state.runtime.radioCatalog).toHaveBeenLastCalledWith(true);
  expect(state.runtime.discoverRadio.mock.calls.slice(-2).every(([filters]) => filters.country === "ES")).toBe(true);
  expect((screen.getByLabelText("country") as HTMLSelectElement).value).toBe("ES");
  expect(state.map.stations).toHaveLength(1);
  expect(screen.getByText("Recovered")).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
});
it("ignores a stale result after filters change and a rejection after unmount", async () => {
  let resolveOld!: (result: any[]) => void;
  let rejectCurrent!: (error: Error) => void;
  state.runtime.discoverRadio.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
  const { unmount } = render(<StationsBody initialTab="discover" purpose="playback" />);
  await settle();
  fireEvent.change(screen.getByLabelText("country"), { target: { value: "US" } });
  state.runtime.discoverRadio.mockResolvedValueOnce([{ id: "new", name: "Current" }]);
  await settle();
  await act(async () => resolveOld([{ id: "old", name: "Old" }]));
  expect(screen.getByText("Current")).toBeTruthy();
  expect(screen.queryByText("Old")).toBeNull();
  state.runtime.discoverRadio.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectCurrent = reject; }));
  fireEvent.change(screen.getByLabelText("country"), { target: { value: "ES" } });
  await settle();
  unmount();
  await act(async () => rejectCurrent(new Error("late")));
});
it("shows catalog recovery error even when cached countries are available", async () => {
  state.runtime.radioCatalog.mockResolvedValue({ countries: [{ code: "ES", count: 1 }], tags: [], error: "catalog_unreachable" });
  render(<StationsBody initialTab="discover" purpose="playback" />);
  await settle();
  expect(state.map.countries).toHaveLength(1);
  expect(screen.getByRole("alert")).toBeTruthy();
});

it("handles the modal B callback by leaving map interaction, then closes on the next B", async () => {
  const close = vi.fn();
  openMediaLibrary("discover");
  const element = vi.mocked(showModal).mock.calls[0][0] as any;
  const Modal = element.type;
  render(<Modal {...element.props} closeModal={close} />);
  await settle();
  act(() => state.map.onActiveChange(true));
  expect(state.map.active).toBe(true);
  act(() => state.modal.onCancel());
  expect(state.map.active).toBe(false);
  expect(close).not.toHaveBeenCalled();
  act(() => state.modal.onCancel());
  expect(close).toHaveBeenCalledOnce();
});

it("does not retain map interaction after switching library tabs", async () => {
  const close = vi.fn();
  openMediaLibrary("discover");
  const element = vi.mocked(showModal).mock.calls[0][0] as any;
  const Modal = element.type;
  render(<Modal {...element.props} closeModal={close} />);
  await settle();
  act(() => state.map.onActiveChange(true));
  fireEvent.click(screen.getByText("ambient.lib.files"));
  act(() => state.modal.onCancel());
  expect(close).toHaveBeenCalledOnce();
});

it("does not replace the current map area with an older area's response", async () => {
  let resolveOld!: (result: any[]) => void;
  state.runtime.discoverRadio.mockImplementation((filters) => {
    if (!filters.hasGeo) return Promise.resolve([]);
    if (filters.country === "ES") return new Promise((resolve) => { resolveOld = resolve; });
    return Promise.resolve([{ id: "us", name: "Current area", geo: [40, -75] }]);
  });
  render(<StationsBody initialTab="discover" purpose="playback" />);
  fireEvent.change(screen.getByLabelText("country"), { target: { value: "ES" } });
  fireEvent.click(screen.getByText("zoom"));
  await settle();
  fireEvent.change(screen.getByLabelText("country"), { target: { value: "US" } });
  await settle();
  await act(async () => resolveOld([{ id: "es", name: "Old area", geo: [40, -3] }]));
  expect(state.map.stations.map((station: any) => station.id)).toEqual(["us"]);
  expect(state.map.loadingStations).toBe(false);
});

it("clears the previous filter's stations before a new search and keeps them cleared if it fails", async () => {
  state.runtime.discoverRadio.mockResolvedValueOnce([{ id: "rtl", name: "RTL" }]);
  render(<StationsBody initialTab="discover" purpose="playback" />);
  await settle();
  expect(screen.getByText("RTL")).toBeTruthy();
  state.runtime.discoverRadio.mockRejectedValueOnce(new Error("provider blocked"));
  fireEvent.click(screen.getByText("ambient.mood.jazz"));
  expect(screen.queryByText("RTL")).toBeNull();
  await settle();
  expect(screen.queryByText("RTL")).toBeNull();
  expect(screen.queryByText("ambient.stations.count")).toBeNull();
  expect(screen.getByRole("alert")).toBeTruthy();
});

it("preserves the current query's stations while loading another page and after a page failure", async () => {
  let rejectPage!: (error: Error) => void;
  state.runtime.discoverRadio.mockResolvedValueOnce([{ id: "rtl", name: "RTL" }]);
  render(<StationsBody initialTab="discover" purpose="playback" />);
  await settle();
  state.runtime.discoverRadio.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectPage = reject; }));
  fireEvent.click(screen.getByText("load more"));
  expect(screen.getByText("RTL")).toBeTruthy();
  expect(state.runtime.discoverRadio).toHaveBeenLastCalledWith({ order: "popular", limit: 40, offset: 40 });
  await act(async () => rejectPage(new Error("provider blocked")));
  expect(screen.getByText("RTL")).toBeTruthy();
  expect(screen.getByRole("alert")).toBeTruthy();
});
